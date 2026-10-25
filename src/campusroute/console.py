import argparse
import asyncio
import logging
import math
import signal
import sys
import threading
import time
import webbrowser
from pathlib import Path

from prompt_toolkit import PromptSession
from prompt_toolkit.history import DummyHistory
from prompt_toolkit.patch_stdout import patch_stdout

from campusroute import __version__
from campusroute.backends import InstallationError, SessionError, get_backend
from campusroute.library import RouteLibrary
from campusroute.mapserver import MapServer
from campusroute.motion import Motion, pace_label, parse_pace
from campusroute.routes import RoutePath, pending_venues, presets, read_route
from campusroute.runtime import AlreadyRunningError, runtime
from campusroute.settings import Settings, SettingsStore
from campusroute.variation import Variation

PHASE_NAMES = {
    'ready': '起点已准备', 'running': '正在移动', 'paused': '移动已暂停',
    'stopped': '本次移动已中止', 'finished': '目标距离已完成',
}


class ConsoleApp:
    def __init__(self, root: Path, backend='android', adb=None):
        self.root = root
        self.backend = get_backend(backend, adb, root)
        self.builtin_routes = presets()
        self.route_library = RouteLibrary(root)
        self.routes = self.builtin_routes + self.route_library.available()
        self.settings_store = SettingsStore(root)
        settings = self.settings_store.load(self.routes)
        self.route = settings.route
        self.pace_s = settings.pace_s
        self.target_m = settings.target_m
        self.variation = settings.variation
        self.save_custom_routes = settings.save_custom_routes
        if self.route not in self.routes and self.save_custom_routes:
            self.route = self.route_library.save(self.route)
            self.routes = self.builtin_routes + self.route_library.available()
            self.save_settings()
        self.connection = None
        self.motion = None
        self.commands = asyncio.Queue()
        self.map_server = None
        self.closing = False
        self.session = None
        self.menu_message = ''
        self.last_status_refresh = 0

    def save_settings(self):
        self.refresh_routes()
        self.settings_store.save(Settings(self.route, self.pace_s, self.target_m, self.variation,
                                          self.save_custom_routes), self.routes)

    def refresh_routes(self):
        self.routes = self.builtin_routes + self.route_library.available()
        local_id = self.route.properties.get('local_id')
        if local_id:
            matches = [item for item in self.routes if item.properties.get('local_id') == local_id]
            if not matches:
                raise ValueError('当前路线已从收藏中移除，请重新选择路线。')
            self.route = matches[0]

    def available_routes(self):
        routes = self.builtin_routes + self.route_library.available()
        return routes + ([self.route] if self.route not in routes and not self.route.properties.get('local_id') else [])

    def show_menu(self, message=''):
        self.menu_message = message
        if self.session is None:
            print(self.menu_text(), end='', flush=True)
        else:
            self.session.app.invalidate()

    def menu_text(self):
        lines = [f'CampusRoute {__version__}  |  {self.backend.name} 路线调试',
                 '在家里我们就练起来', f'路线：{self.route.name}',
                 f'配速：{pace_label(self.pace_s)}／公里；目标：{self.target_m / 1000:g}公里',
                 *self.status_lines()]
        if self.menu_message:
            lines.extend(('', self.menu_message))
        lines.extend(('', '1  连接手机并准备起点', '2  开始／继续移动', '3  暂停移动',
                      '4  中止本次移动，保持当前位置', '5  恢复真实定位并断开连接',
                      '6  刷新当前状态', '7  选择路线／导入自定义路线',
                      '8  设置配速与目标距离', '9  打开操场地图／绘制自定义路线'))
        if hasattr(self.backend, 'install'):
            lines.append('10 安装／更新 Android 配套 APK')
        lines.extend((f'11 设置配速／轨迹波动（{self.variation.label}）',
                      f'12 自定义路线自动保存（{"开启" if self.save_custom_routes else "关闭"}）',
                      '0  恢复真实定位并退出', '', '请选择数字并按回车：'))
        return '\n'.join(lines)

    def status_lines(self):
        lines = ['状态：' + (PHASE_NAMES[self.motion.phase] if self.motion else '尚未连接')]
        if self.motion:
            lines.append(f'当前累计距离：{self.motion.distance_m / 1000:.3f}公里；移动用时：{self.motion.elapsed_s:.1f}秒')
            if self.motion.variation.enabled:
                seconds = round(1000 / self.motion.speed_at(self.motion.elapsed_s), 1)
                pace = f'{int(seconds // 60)}:{seconds % 60:04.1f}／公里' if self.motion.phase == 'running' else '静止'
                lines.append(f'当前运动配速：{pace}；波动已开启')
        if self.connection and getattr(self.connection, 'last_position', None):
            latitude, longitude = self.connection.last_position
            lines.append(f'手机已确认坐标：{latitude:.7f}, {longitude:.7f}')
        if self.connection and getattr(self.connection, 'last_motion', None) is not None:
            speed, bearing = self.connection.last_motion
            lines.append(f'已发送速度：{speed:.2f}米／秒；朝向：{bearing:.1f}°（正北为0°）')
        return lines

    def refresh_status(self):
        now = time.monotonic()
        if self.session is not None and now - self.last_status_refresh >= 1:
            self.session.app.invalidate()
            self.last_status_refresh = now

    def enable_terminal_input(self):
        self.session = PromptSession(
            history=DummyHistory(), erase_when_done=True,
            interrupt_exception=EOFError,
        )

    async def read_command(self, prompt=None):
        if self.session is None:
            return await self.commands.get()
        try:
            with patch_stdout():
                return (await self.session.prompt_async(
                    self.menu_text if prompt is None else prompt, handle_sigint=False,
                )).strip()
        except EOFError:
            self.closing = True
            return None

    async def answer(self, prompt):
        if self.session is None:
            print(prompt, end='', flush=True)
        reply = await self.read_command(prompt)
        if reply is None:
            self.closing = True
            raise asyncio.CancelledError
        return reply

    async def select_device(self):
        devices = await self.backend.devices()
        if not devices:
            raise SessionError(f'未检测到 {self.backend.name} USB 设备。请连接数据线、解锁手机并完成设备授权。')
        selected = 0
        if len(devices) > 1:
            print('\n检测到多台设备，请选择：')
            for index, device in enumerate(devices, 1):
                print(f'{index}  {device.label}')
            reply = await self.answer('设备编号（输入0取消）：')
            if reply == '0':
                return None
            if not reply.isdecimal() or not 1 <= int(reply) <= len(devices):
                raise ValueError('设备编号无效。')
            selected = int(reply) - 1
        return devices[selected]

    async def connect(self):
        device = await self.select_device()
        if device is None:
            return False
        print('\n正在准备开发者服务，请保持手机连接并解锁……', flush=True)
        self.connection = self.backend.connection()
        await self.connection.connect(device.serial)
        self.motion = Motion(RoutePath(self.route), self.pace_s, self.target_m, variation=self.variation)
        await self.tick()
        return True

    async def restore(self):
        connection, self.connection = self.connection, None
        self.motion = None
        if connection:
            await connection.close()

    async def end_failed_session(self, error):
        state = '\n' + '\n'.join(self.status_lines()) if self.motion else ''
        message = f'本次连接已中断：{type(error).__name__}：{error}' + state
        try:
            await self.restore()
        except Exception as cleanup_error:
            message += f'\n清理未确认：{type(cleanup_error).__name__}：{cleanup_error}'
            message += '\n请在手机点击“停止并恢复”，确认手机状态后再连接。'
        message += '\n电脑端仍在运行，路线和设置已保留。输入1重新连接；不会自动继续移动。'
        return message

    async def select_route(self):
        self.refresh_routes()
        print('\n可选路线（内置操场与本地收藏）：')
        for index, route in enumerate(self.routes, 1):
            print(f'{index}  {route.name}')
        print('I  导入 GPX／GeoJSON；输入0返回菜单。')
        for venue in pending_venues():
            print(f'待补充：{venue["name"]}（跑道坐标待核验，暂不可播放）。')
        print('自定义方法：菜单9打开地图 → 完成绘制并保存 → 回到这里按编号选择。')
        print('导入路线默认加入收藏；菜单12可关闭自动保存，仅在本次窗口使用。')
        print('坐标要求：WGS84；GeoJSON 使用 [经度, 纬度]；GPX 需要一条连续路线。')
        print('闭合路线循环前进；开放路线沿原路往返。')
        reply = await self.answer('请选择路线编号或输入 I：')
        if reply == '0':
            return '路线设置已关闭。'
        if reply.lower() == 'i':
            raw = await self.answer('请粘贴路线文件的完整路径（输入0取消）：')
            if raw == '0':
                return '路线导入已取消。'
            path = Path(raw.strip().strip("\"'")).expanduser()
            route = read_route(path)
            self.route = self.route_library.save(route, persist=self.save_custom_routes)
            self.routes = self.builtin_routes + self.route_library.available()
        elif reply.isdecimal() and 1 <= int(reply) <= len(self.routes):
            self.route = self.routes[int(reply) - 1]
        else:
            raise ValueError('路线编号无效。')
        number = f'，路线编号{self.routes.index(self.route) + 1}'
        if self.route.properties.get('session_only'):
            number += '，仅本次窗口使用'
        self.save_settings()
        return f'已选择：{self.route.name}{number}。路线全长约{RoutePath(self.route).length_m:.1f}米。'

    async def configure(self):
        print('\n配速格式为 分钟:秒，最快2:00／公里，慢速没有人为上限。')
        reply = await self.answer(f'配速（直接回车保留{pace_label(self.pace_s)}，输入0取消）：')
        if reply == '0':
            return '设置已取消。'
        pace_s = parse_pace(reply) if reply else self.pace_s
        reply = await self.answer(f'目标公里数（直接回车保留{self.target_m / 1000:g}，输入0取消）：')
        if reply == '0':
            return '设置已取消。'
        target_m = float(reply) * 1000 if reply else self.target_m
        if not math.isfinite(target_m) or target_m <= 0:
            raise ValueError('目标公里数必须为有限的正数。')
        self.pace_s, self.target_m = pace_s, target_m
        self.save_settings()
        return '配速与目标距离已设置。'

    async def configure_variation(self):
        print(f'\n当前波动：{self.variation.label}。配速和偏移缓慢变化，暂停、中止时保持静止。')
        print('配速仍不快于2:00／公里；横向范围相对原路线，不代表一定处于跑道边界内。')
        reply = await self.answer('1 开启／修改；2 关闭；0 取消：')
        if reply == '0':
            return '波动设置已取消。'
        if reply == '2':
            self.variation = Variation(False, self.variation.pace_percent, self.variation.lateral_m)
        elif reply == '1':
            reply = await self.answer(f'配速波动百分比，0—20（回车保留{self.variation.pace_percent:g}，Q取消）：')
            if reply.lower() == 'q':
                return '波动设置已取消。'
            percent = float(reply) if reply else self.variation.pace_percent
            reply = await self.answer(f'最大横向偏移米数，0—3（回车保留{self.variation.lateral_m:g}，Q取消）：')
            if reply.lower() == 'q':
                return '波动设置已取消。'
            lateral = float(reply) if reply else self.variation.lateral_m
            self.variation = Variation(True, percent, lateral)
        else:
            raise ValueError('请选择1、2或0。')
        self.save_settings()
        return f'波动已设置：{self.variation.label}。下次连接生效。'

    async def choose(self, choice):
        if choice == '0':
            return False, ''
        if choice == '1':
            if self.connection:
                return True, '当前已有连接。准备新的一次移动时，请先选择5。'
            if await self.connect():
                return True, '路线起点已准备。输入2开始移动。'
            return True, '设备选择已取消。'
        if choice == '5':
            had_connection = self.connection is not None
            await self.restore()
            return True, '已发送恢复真实定位指令，连接已关闭。' if had_connection else '当前没有设备连接。'
        if choice == '6':
            return True, '状态已刷新。'
        if choice == '10' and hasattr(self.backend, 'install'):
            if self.connection:
                return True, '安装前请先选择5恢复定位并断开连接。'
            default = self.root / 'build' / 'android' / 'CampusRoute-debug.apk'
            raw = await self.answer(f'APK 完整路径（回车使用 {default}，输入0取消）：')
            if raw == '0':
                return True, '安装已取消。'
            apk = Path(raw.strip().strip("\"'")) if raw else default
            device = await self.select_device()
            if device is None:
                return True, '安装已取消。'
            print('\n正在安装 APK，请保持手机解锁，并在手机弹窗中确认安装……', flush=True)
            await self.backend.install(device.serial, apk)
            return True, 'APK 已安装。请选择1连接，并在手机完成授权、启动接收。'
        if choice in ('7', '8', '9', '11', '12'):
            if self.connection:
                return True, '修改路线或参数前，请选择5恢复定位并断开连接。'
            if choice == '7':
                return True, await self.select_route()
            if choice == '8':
                return True, await self.configure()
            if choice == '11':
                return True, await self.configure_variation()
            if choice == '12':
                reply = await self.answer('自定义路线自动保存：1 开启；2 关闭；0 取消：')
                if reply == '0':
                    return True, '保存设置已取消。'
                if reply not in ('1', '2'):
                    raise ValueError('请选择1、2或0。')
                self.save_custom_routes = reply == '1'
                if self.map_server:
                    self.map_server.save_custom_routes = self.save_custom_routes
                self.save_settings()
                return True, '自定义路线自动保存已' + ('开启。' if self.save_custom_routes else '关闭，现有收藏继续保留。')
            self.refresh_routes()
            displayed = self.available_routes()
            if not self.map_server:
                self.map_server = MapServer(self.available_routes, self.route_library, self.save_custom_routes)
            url = f'{self.map_server.url}?route={displayed.index(self.route)}'
            opened = await asyncio.to_thread(webbrowser.open, url)
            return True, (('地图已打开。' if opened else '请在浏览器打开地图。')
                          + f'本地地址：{url}\n完成绘制后默认加入收藏，返回菜单7按编号选择。')
        if choice not in ('2', '3', '4'):
            return True, '请输入菜单中的数字。'
        if not self.motion:
            return True, '请先输入1连接手机并准备起点。'
        if choice == '2':
            if self.motion.phase not in ('ready', 'paused'):
                return True, '当前状态无法继续移动。准备新的一次移动时，请先选择5。'
            self.motion.start(time.monotonic())
            return True, '正在移动，输入3暂停，输入4中止。'
        if choice == '3':
            if self.motion.phase != 'running':
                return True, '当前没有正在进行的移动。'
            self.motion.pause(time.monotonic())
            await self.tick()
            return True, '移动已暂停，当前位置持续保持。输入2继续移动。'
        self.motion.stop(time.monotonic())
        await self.tick()
        return True, '本次移动已中止，当前位置持续保持。输入5恢复定位，输入0退出。'

    async def tick(self):
        if not self.motion:
            return
        previous = self.motion.phase
        self.motion.advance(time.monotonic())
        set_motion = getattr(self.connection, 'set_motion', None)
        if set_motion:
            speed, bearing = self.motion.velocity
            await set_motion(*self.motion.position, speed=speed, bearing=bearing)
        else:
            await self.connection.set(*self.motion.position)
        if previous != 'finished' and self.motion.phase == 'finished':
            self.show_menu('目标距离已完成，当前位置持续保持。输入5恢复定位，输入0退出。')
        else:
            self.refresh_status()

    async def run(self):
        loop = asyncio.get_running_loop()
        task = asyncio.current_task()
        input_closed = threading.Event()
        if sys.stdin.isatty() and sys.stdout.isatty():
            self.enable_terminal_input()

        def receive():
            # 输入线程允许阻塞读取，退出时由主任务完成资源清理。
            while not input_closed.is_set():
                try:
                    line = sys.stdin.readline()
                except (OSError, ValueError):
                    line = ''
                if input_closed.is_set():
                    return
                try:
                    loop.call_soon_threadsafe(self.commands.put_nowait, line.strip() if line else None)
                except RuntimeError:
                    return
                if not line:
                    return

        def request_exit(*_):
            self.closing = True
            loop.call_soon_threadsafe(task.cancel)

        previous_signals = {}
        for name in ('SIGINT', 'SIGTERM', 'SIGHUP', 'SIGBREAK'):
            event = getattr(signal, name, None)
            if event is not None:
                previous_signals[event] = signal.signal(event, request_exit)
        pending = asyncio.create_task(self.read_command())
        try:
            if self.session is None:
                threading.Thread(target=receive, name='campusroute-input', daemon=True).start()
            self.show_menu()
            while True:
                # 优先处理排队的停止指令，再发送下一个位置。
                if pending.done():
                    choice = pending.result()
                    if choice is None:
                        break
                    try:
                        if choice in ('7', '8', '10', '11', '12') and not self.connection:
                            try:
                                keep_running, message = await self.choose(choice)
                            except (ValueError, FileNotFoundError) as error:
                                keep_running, message = True, f'输入无效：{error}'
                            except InstallationError as error:
                                keep_running, message = True, str(error)
                        else:
                            keep_running, message = await self.choose(choice)
                    except (SessionError, ConnectionError, OSError) as error:
                        keep_running, message = True, await self.end_failed_session(error)
                    if not keep_running or self.closing:
                        break
                    self.show_menu(message)
                    pending = asyncio.create_task(self.read_command())
                    continue
                started = time.monotonic()
                try:
                    await self.tick()
                except (SessionError, ConnectionError, OSError) as error:
                    self.show_menu(await self.end_failed_session(error))
                await asyncio.wait({pending}, timeout=max(0, 0.2 - (time.monotonic() - started)))
        except asyncio.CancelledError:
            if not self.closing:
                raise
        finally:
            original_error = sys.exception()
            input_closed.set()
            pending.cancel()
            await asyncio.gather(pending, return_exceptions=True)
            for event, handler in previous_signals.items():
                signal.signal(event, handler)
            try:
                had_connection = bool(self.connection and self.connection.simulated)
                await self.restore()
                print('\n已发送恢复真实定位指令，程序已退出。' if had_connection else '\n程序已退出。', flush=True)
            except Exception as error:
                if original_error is None:
                    raise
                print(f'\n清理时另有错误：{error}\n请在手机点击“停止并恢复”。', flush=True)
            finally:
                if self.map_server:
                    self.map_server.close()


def main():
    parser = argparse.ArgumentParser(description='CampusRoute：Android / iPhone 路线与定位调试工具')
    parser.add_argument('--version', action='version', version=__version__)
    parser.add_argument('--root', type=Path, default=Path.cwd(), help='本地工作文件夹')
    parser.add_argument('--backend', choices=('android', 'ios'),
                        default='ios' if sys.platform == 'darwin' else 'android', help='设备后端')
    parser.add_argument('--adb', help='adb 可执行文件路径')
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING, force=True)
    try:
        with runtime(args.root):
            asyncio.run(ConsoleApp(args.root, args.backend, args.adb).run())
    except AlreadyRunningError as error:
        print(str(error), flush=True)
        return 2
    except Exception as error:
        print(f'\n操作已终止：{type(error).__name__}：{error}', flush=True)
        print('Android 请查看手机端状态，必要时点击“停止并恢复”；iPhone 请重新连接后执行菜单1、5。', flush=True)
        return 1
    return 0
