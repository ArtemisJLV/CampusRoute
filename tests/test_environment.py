import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
import venv

from campusroute import __version__

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / 'work' / '.cache'


@unittest.skipUnless(sys.platform == 'darwin', '需要 macOS 文件属性与启动器。')
class EnvironmentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        CACHE.mkdir(parents=True, exist_ok=True)

    def prepare_project(self, root):
        (root / 'tools').mkdir()
        shutil.copyfile(ROOT / 'tools' / 'check_environment.py', root / 'tools' / 'check_environment.py')
        for name in ('CampusRoute.command', 'pyproject.toml'):
            shutil.copyfile(ROOT / name, root / name)
        (root / 'src').symlink_to(ROOT / 'src', target_is_directory=True)

    def run_launcher(self, root):
        return subprocess.run(
            ['zsh', str(root / 'CampusRoute.command')], input='0\n',
            capture_output=True, text=True, encoding='utf-8', timeout=30,
            env={**os.environ, 'PYTHONPATH': '', 'TMPDIR': str(root)},
        )

    def test_launcher_reuses_environment_with_hidden_editable_path(self):
        with tempfile.TemporaryDirectory(prefix='launcher-hidden-', dir=CACHE) as directory:
            root = Path(directory)
            self.prepare_project(root)
            prefix = root / '.conda' / 'campusroute'
            venv.EnvBuilder(with_pip=False, symlinks=True, system_site_packages=True).create(prefix)
            site = next((prefix / 'lib').glob('python*/site-packages'))
            path = site / f'__editable__.campusroute-{__version__}.pth'
            path.write_text(str(root / 'src') + '\n', encoding='utf-8')
            os.chflags(path, stat.UF_HIDDEN)
            for _ in range(2):
                result = self.run_launcher(root)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn(f'CampusRoute {__version__}', result.stdout)
                self.assertIn('程序已退出', result.stdout)
                self.assertNotIn('安装／升级／修复环境', result.stdout)
                self.assertTrue(path.stat().st_flags & stat.UF_HIDDEN)
                self.assertEqual(list((root / 'work' / '.cache').iterdir()), [])

    def test_launcher_displays_environment_check_error(self):
        with tempfile.TemporaryDirectory(prefix='launcher-incomplete-', dir=CACHE) as directory:
            root = Path(directory)
            self.prepare_project(root)
            venv.EnvBuilder(with_pip=False, symlinks=True).create(root / '.conda' / 'campusroute')
            result = self.run_launcher(root)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('环境检查未通过', result.stdout)
            self.assertRegex(result.stdout, r'(?:PackageNotFoundError|ModuleNotFoundError):')
            self.assertIn('check_environment.py', result.stdout)
            self.assertIn('安装／升级／修复环境', result.stdout)
            self.assertNotIn('在家里我们就练起来', result.stdout)

    def test_launcher_reports_missing_python(self):
        with tempfile.TemporaryDirectory(prefix='launcher-missing-', dir=CACHE) as directory:
            root = Path(directory)
            self.prepare_project(root)
            result = self.run_launcher(root)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('项目环境中没有可执行的 Python', result.stdout)
            self.assertIn('安装／升级／修复环境', result.stdout)
