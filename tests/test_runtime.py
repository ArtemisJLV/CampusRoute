import os
from pathlib import Path
import socket
import sys
import tempfile
import unittest

from campusroute.runtime import runtime, validate_ios_temporary_directory

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / 'work' / '.cache'


@unittest.skipUnless(sys.platform == 'darwin', '需要 macOS 的 AF_UNIX 路径限制。')
class RuntimeSocketTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        CACHE.mkdir(parents=True, exist_ok=True)

    def test_runtime_supports_native_ios_relay_socket_and_cleanup(self):
        previous_directory = tempfile.tempdir
        previous_environment = {key: os.environ.get(key) for key in ('TMPDIR', 'TEMP', 'TMP')}
        with runtime(ROOT):
            temporary = Path(tempfile.gettempdir())
            self.assertEqual(temporary.parent, CACHE)
            validate_ios_temporary_directory(temporary)
            with tempfile.TemporaryDirectory(prefix='pmd3-') as directory:
                path = str(Path(directory) / 'relay.sock')
                self.assertLess(len(os.fsencode(path)), 104)
                with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as listener:
                    listener.settimeout(2)
                    listener.bind(path)
                    listener.listen(1)
                    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                        client.settimeout(2)
                        client.connect(path)
                        accepted, _ = listener.accept()
                        with accepted:
                            accepted.settimeout(2)
                            client.sendall(b'campusroute')
                            self.assertEqual(accepted.recv(64), b'campusroute')
            self.assertEqual(list(temporary.iterdir()), [])
        self.assertFalse(temporary.exists())
        self.assertEqual(tempfile.tempdir, previous_directory)
        self.assertEqual(previous_environment, {key: os.environ.get(key) for key in previous_environment})

    def test_path_validation_counts_utf8_bytes_at_native_limit(self):
        suffix = '/pmd3-xxxxxxxx/relay.sock'
        directory = Path('/' + '中' * 10 + 'a' * (103 - len(suffix.encode()) - 31))
        path = directory / 'pmd3-xxxxxxxx' / 'relay.sock'
        self.assertEqual(len(os.fsencode(path)), 103)
        validate_ios_temporary_directory(directory)
        with self.assertRaisesRegex(RuntimeError, '项目路径过长'):
            validate_ios_temporary_directory(Path(str(directory) + 'a'))
        with self.assertRaisesRegex(RuntimeError, '项目路径过长'):
            validate_ios_temporary_directory(Path(str(directory) + '中'))

    def test_runtime_cleans_up_when_socket_path_validation_fails(self):
        previous_directory = tempfile.tempdir
        previous_environment = {key: os.environ.get(key) for key in ('TMPDIR', 'TEMP', 'TMP')}
        with tempfile.TemporaryDirectory(prefix='runtime-', dir=CACHE) as directory:
            root = Path(directory) / ('中文路径' * 5)
            root.mkdir()
            with self.assertRaisesRegex(RuntimeError, '项目路径过长'):
                with runtime(root):
                    temporary = Path(tempfile.gettempdir())
                    validate_ios_temporary_directory(temporary)
            self.assertFalse(temporary.exists())
            self.assertEqual(list((root / 'work' / '.cache').iterdir()), [])
        self.assertEqual(tempfile.tempdir, previous_directory)
        self.assertEqual(previous_environment, {key: os.environ.get(key) for key in previous_environment})
