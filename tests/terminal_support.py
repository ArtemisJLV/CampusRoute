import os
from pathlib import Path
import sys
import time

import pyte

if os.name == 'posix':
    import pexpect
    import termios

ROOT = Path(__file__).resolve().parents[1]


class ReplyScreen(pyte.Screen):
    def __init__(self, columns, rows, send):
        super().__init__(columns, rows)
        self.send = send
        self.cursor_reports = 0

    def write_process_input(self, data):
        self.send(data)

    def report_device_status(self, mode):
        super().report_device_status(mode)
        if mode == 6:
            self.cursor_reports += 1


class Terminal:
    def __init__(self, root, probe=False, rows=36, columns=90):
        arguments = ([str(ROOT / 'tests' / 'test_terminal.py'), '--status-probe', str(root)]
                     if probe else ['-m', 'campusroute', '--backend', 'android', '--root', str(root)])
        self.child = pexpect.spawn(
            sys.executable, ['-B', *arguments], encoding='utf-8', timeout=10,
            dimensions=(rows, columns), env={**os.environ, 'TERM': 'xterm-256color',
                                          'TMPDIR': str(root), 'TEMP': str(root), 'TMP': str(root),
                                          'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONUTF8': '1'},
        )
        self.screen = ReplyScreen(columns, rows, self.child.send)
        self.stream = pyte.Stream(self.screen)
        self.output = ''

    def read(self, timeout=0.1):
        try:
            text = self.child.read_nonblocking(65536, timeout=timeout)
        except pexpect.TIMEOUT:
            return
        self.output += text
        self.stream.feed(text)

    def wait(self, predicate, timeout=10):
        deadline = time.monotonic() + timeout
        while not predicate():
            if time.monotonic() >= deadline:
                raise AssertionError('\n'.join(self.screen.display) + '\n' + repr(self.output[-2000:]))
            self.read()

    def send(self, text):
        self.child.send(text)

    def resize(self, rows, columns):
        cursor_reports = self.screen.cursor_reports
        self.screen.resize(lines=rows, columns=columns)
        self.child.setwinsize(rows, columns)
        self.wait(lambda: self.screen.cursor_reports > cursor_reports)

    def finish(self, timeout=10):
        deadline = time.monotonic() + timeout
        while True:
            if time.monotonic() >= deadline:
                raise AssertionError('终端进程没有正常退出。\n' + self.output[-2000:])
            try:
                self.read()
            except pexpect.EOF:
                break
        self.input_flags = termios.tcgetattr(self.child.child_fd)[3]
        self.child.close()
        if self.child.exitstatus != 0:
            raise AssertionError(self.output)

    def close(self):
        self.child.close(force=True)
