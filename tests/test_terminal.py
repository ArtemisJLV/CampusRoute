import asyncio
import json
import os
from pathlib import Path
import signal
import sys
import tempfile
import time
import unittest

from wcwidth import wcswidth

from campusroute.console import ConsoleApp
from campusroute.motion import Motion
from campusroute.routes import RoutePath
from terminal_support import Terminal

if os.name == 'posix':
    import termios

CACHE = Path(__file__).resolve().parents[1] / 'work' / '.cache'
PROMPT = '请选择数字并按回车：'


@unittest.skipUnless(os.name == 'posix', '需要 POSIX 伪终端。')
class TerminalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        CACHE.mkdir(parents=True, exist_ok=True)

    def launch(self, root, **options):
        terminal = Terminal(root, **options)
        self.addCleanup(terminal.close)
        terminal.wait(lambda: PROMPT in terminal.screen.display[terminal.screen.cursor.y])
        return terminal

    def wait_input(self, terminal, text, offset=None):
        expected_x = wcswidth(PROMPT) + (len(text) if offset is None else offset)
        terminal.wait(lambda: PROMPT + text in terminal.screen.display[terminal.screen.cursor.y]
                      and terminal.screen.cursor.x == expected_x
                      and not terminal.screen.cursor.hidden)

    def wait_status_change(self, terminal):
        before = next(line for line in terminal.screen.display if '当前累计距离：' in line)
        terminal.wait(lambda: any('当前累计距离：' in line and line != before
                                 for line in terminal.screen.display))

    def test_live_status_keeps_partial_input_and_editing_cursor(self):
        with tempfile.TemporaryDirectory(prefix='terminal-status-', dir=CACHE) as directory:
            terminal = self.launch(Path(directory), probe=True)
            terminal.send('12')
            self.wait_input(terminal, '12')
            self.wait_status_change(terminal)
            self.wait_input(terminal, '12')
            terminal.send('\033[D')
            self.wait_input(terminal, '12', 1)
            self.wait_status_change(terminal)
            self.wait_input(terminal, '12', 1)
            terminal.send('\1776')
            self.wait_input(terminal, '62', 1)
            terminal.send('\r')
            terminal.finish()
            self.assertIn('输入结果：62', terminal.output)

    def test_resize_preserves_input_in_small_and_large_windows(self):
        with tempfile.TemporaryDirectory(prefix='terminal-resize-', dir=CACHE) as directory:
            terminal = self.launch(Path(directory), probe=True)
            terminal.send('6')
            self.wait_input(terminal, '6')
            for rows, columns in ((14, 36), (40, 100), (24, 60)):
                terminal.resize(rows, columns)
                self.wait_input(terminal, '6')
                self.assertGreater(terminal.screen.cursor.y, 5)
            terminal.send('\r')
            terminal.finish()
            self.assertIn('输入结果：6', terminal.output)

    def test_arrow_keys_and_submenu_parameters(self):
        with tempfile.TemporaryDirectory(prefix='terminal-menu-', dir=CACHE) as directory:
            root = Path(directory)
            terminal = self.launch(root)
            terminal.send('\033[A\033[B8\r')
            terminal.wait(lambda: '配速（' in terminal.screen.display[terminal.screen.cursor.y])
            terminal.send('6:30\033[D\1774\r')
            terminal.wait(lambda: '目标公里数（' in terminal.screen.display[terminal.screen.cursor.y])
            terminal.send('0.02\r')
            terminal.wait(lambda: PROMPT in terminal.screen.display[terminal.screen.cursor.y])
            self.assertIn('配速：6:40／公里；目标：0.02公里', '\n'.join(terminal.screen.display))
            terminal.send('60\033[D\177\r')
            terminal.finish()
            self.assertIn('程序已退出', terminal.output)
            settings = json.loads((root / 'work' / 'settings.json').read_text(encoding='utf-8'))
            self.assertEqual(settings['pace_s'], 400)
            self.assertEqual(settings['target_m'], 20)

    def test_interrupt_and_eof_clean_up_main_and_nested_prompts(self):
        for nested, key in ((False, '\003'), (False, '\004'), (True, '\003'), (True, '\004'),
                            (False, None), (True, None)):
            with self.subTest(nested=nested, key=repr(key)):
                with tempfile.TemporaryDirectory(prefix='terminal-exit-', dir=CACHE) as directory:
                    root = Path(directory)
                    terminal = self.launch(root)
                    if nested:
                        terminal.send('7\r')
                        terminal.wait(lambda: '请选择路线编号或输入 I：' in
                                      terminal.screen.display[terminal.screen.cursor.y])
                    if key is None:
                        terminal.child.kill(signal.SIGTERM)
                    else:
                        terminal.send(key)
                    terminal.finish()
                    self.assertIn('程序已退出', terminal.output)
                    self.assertEqual(list((root / 'work' / '.cache').iterdir()), [])
                    self.assertTrue(terminal.input_flags & termios.ECHO)
                    self.assertTrue(terminal.input_flags & termios.ICANON)


async def probe_status(root):
    app = ConsoleApp(root)
    app.enable_terminal_input()
    app.motion = Motion(RoutePath(app.route), target_m=10000)
    app.motion.start(time.monotonic())

    async def advance():
        while True:
            app.motion.advance(time.monotonic())
            app.refresh_status()
            await asyncio.sleep(0.2)

    updates = asyncio.create_task(advance())
    try:
        result = await app.read_command()
    finally:
        updates.cancel()
        await asyncio.gather(updates, return_exceptions=True)
    print('输入结果：' + result, flush=True)


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--status-probe':
        asyncio.run(probe_status(Path(sys.argv[2])))
    else:
        unittest.main()
