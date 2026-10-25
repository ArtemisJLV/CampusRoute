import hashlib
import os
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path


class AlreadyRunningError(RuntimeError):
    pass


def validate_ios_temporary_directory(directory: Path):
    if sys.platform != 'darwin':
        return
    relay = directory / 'pmd3-xxxxxxxx' / 'relay.sock'
    if len(os.fsencode(relay)) >= 104:
        raise RuntimeError('项目路径过长，无法创建 iPhone 本地连接。请将项目放到路径较短的文件夹。')


@contextmanager
def console_output():
    if sys.platform != 'win32' or not sys.stdout.isatty():
        yield
        return
    import ctypes
    import msvcrt
    from ctypes import wintypes

    try:
        handle = msvcrt.get_osfhandle(sys.stdout.fileno())
    except (OSError, ValueError):
        yield
        return
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.GetConsoleMode.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
    kernel.GetConsoleMode.restype = wintypes.BOOL
    kernel.SetConsoleMode.argtypes = (wintypes.HANDLE, wintypes.DWORD)
    kernel.SetConsoleMode.restype = wintypes.BOOL
    previous = wintypes.DWORD()
    changed = kernel.GetConsoleMode(handle, ctypes.byref(previous)) and kernel.SetConsoleMode(handle, previous.value | 0x0004)
    try:
        yield
    finally:
        if changed:
            kernel.SetConsoleMode(handle, previous.value)


@contextmanager
def instance_lock(root: Path):
    if sys.platform == 'win32':
        import ctypes
        from ctypes import wintypes

        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.CreateMutexW.argtypes = (ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR)
        kernel.CreateMutexW.restype = wintypes.HANDLE
        kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
        kernel.CloseHandle.restype = wintypes.BOOL
        identity = os.path.normcase(str(root.resolve())).encode('utf-8')
        name = 'Local\\CampusRoute-' + hashlib.sha256(identity).hexdigest()
        ctypes.set_last_error(0)
        handle = kernel.CreateMutexW(None, False, name)
        error = ctypes.get_last_error()
        if not handle:
            raise ctypes.WinError(error)
        try:
            if error == 183:
                raise AlreadyRunningError('操作窗口已经打开，请使用现有窗口。')
            yield
        finally:
            kernel.CloseHandle(handle)
    else:
        import fcntl

        descriptor = os.open(root, os.O_RDONLY)
        try:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise AlreadyRunningError('操作窗口已经打开，请使用现有窗口。') from None
            yield
        finally:
            os.close(descriptor)


@contextmanager
def runtime(root: Path):
    root = root.resolve()
    with instance_lock(root):
        cache = root / 'work' / '.cache'
        cache.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='', dir=cache) as directory:
            previous_directory = tempfile.tempdir
            previous_environment = {key: os.environ.get(key) for key in ('TMPDIR', 'TEMP', 'TMP')}
            tempfile.tempdir = directory
            os.environ.update({key: directory for key in previous_environment})
            if sys.platform == 'win32':
                import ctypes
                ctypes.windll.kernel32.SetThreadExecutionState(0x80000001)
            try:
                with console_output():
                    yield
            finally:
                if sys.platform == 'win32':
                    ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
                tempfile.tempdir = previous_directory
                for key, value in previous_environment.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value
