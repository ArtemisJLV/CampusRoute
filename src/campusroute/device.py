import asyncio
from pathlib import Path
import sys
import tempfile
from contextlib import AsyncExitStack

from packaging.version import Version
from pymobiledevice3.exceptions import DeveloperDiskImageNotFoundError
from pymobiledevice3.lockdown import create_using_usbmux
from pymobiledevice3.remote.userspace_tunnel import UserspaceRsdTunnel
from pymobiledevice3.services.mobile_image_mounter import (
    AlreadyMountedError,
    auto_mount,
)
from pymobiledevice3.services.dvt.instruments.dvt_provider import DvtProvider
from pymobiledevice3.services.dvt.instruments.location_simulation import LocationSimulation
from pymobiledevice3.usbmux import list_devices

from campusroute.runtime import validate_ios_temporary_directory


async def usb_devices():
    return [device for device in await list_devices() if device.is_usb]


async def device_label(serial: str):
    async with await create_using_usbmux(serial=serial, connection_type="USB") as lockdown:
        values = lockdown.all_values
        return f"{values['DeviceName']}（{values['ProductType']}，iOS {values['ProductVersion']}）"


class DeviceConnection:
    def __init__(self):
        self.resources = AsyncExitStack()
        self.location = None
        self.simulated = False

    async def connect(self, serial: str):
        validate_ios_temporary_directory(Path(tempfile.gettempdir()))
        async with await create_using_usbmux(serial=serial, connection_type="USB") as lockdown:
            version = lockdown.all_values["ProductVersion"]
            if Version(version) < Version("17.4"):
                raise RuntimeError("本版本要求 iOS 17.4 或更新版本。")
            enabled = await lockdown.get_value(
                domain="com.apple.security.mac.amfi", key="DeveloperModeStatus"
            )
            if not enabled:
                raise RuntimeError("请在 iPhone 的“隐私与安全性”中打开开发者模式，并完成重启确认。")
        rsd = await self.resources.enter_async_context(UserspaceRsdTunnel(serial=serial, autopair=True))
        try:
            await asyncio.wait_for(auto_mount(rsd), timeout=90)
        except AlreadyMountedError:
            pass
        except asyncio.TimeoutError as error:
            raise RuntimeError(
                "开发者镜像下载超时。请检查网络后重试；镜像会缓存到用户目录的 .pymobiledevice3 文件夹。"
            ) from error
        except DeveloperDiskImageNotFoundError as error:
            raise RuntimeError("没有找到与这台手机匹配的开发者镜像。请更新 pymobiledevice3 后重试。") from error
        except Exception as error:
            hint = ""
            if sys.platform == "win32":
                hint = "\n请确认手机保持解锁，并允许电脑访问这台 iPhone。"
            raise RuntimeError(f"开发者服务准备失败。\n{error}{hint}") from error
        dvt = await self.resources.enter_async_context(DvtProvider(rsd))
        self.location = await self.resources.enter_async_context(LocationSimulation(dvt))

    async def set(self, latitude: float, longitude: float):
        if self.location is None:
            raise RuntimeError("设备连接尚未建立。")
        # 在发送前标记，确保发送途中出错时也会尝试清理定位。
        self.simulated = True
        await asyncio.wait_for(self.location.set(latitude, longitude), timeout=5)

    async def close(self):
        if self.simulated and self.location is None:
            raise RuntimeError("恢复真实定位未能确认，请重新连接设备或重启手机。")
        try:
            if self.location is not None and self.simulated:
                await asyncio.wait_for(self.location.clear(), timeout=10)
                self.simulated = False
        finally:
            await self.resources.aclose()
            self.location = None
