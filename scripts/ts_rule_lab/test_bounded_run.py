import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest


RUNNER = Path(__file__).with_name('bounded_run.py')


class BoundedRunTests(unittest.TestCase):
    def command(self, receipt, script):
        return [sys.executable, str(RUNNER), '--receipt', str(receipt),
                '--as-limit-mib', '128', '--rss-limit-mib', '96', '--',
                sys.executable, '-c', script]

    def test_nonzero_exit_is_recorded(self):
        with tempfile.TemporaryDirectory() as tmp:
            receipt = Path(tmp) / 'run.json'
            result = subprocess.run(self.command(receipt, 'raise SystemExit(7)'),
                                    capture_output=True, timeout=15)
            self.assertEqual(result.returncode, 7)
            record = json.loads(receipt.read_text())
            self.assertEqual(record['returncode'], 7)
            self.assertIsNone(record['stop_reason'])

    def test_address_space_limit_fails_without_kernel_oom(self):
        with tempfile.TemporaryDirectory() as tmp:
            receipt = Path(tmp) / 'run.json'
            result = subprocess.run(self.command(receipt, 'bytearray(200*1024*1024)'),
                                    capture_output=True, timeout=15)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(b'MemoryError', result.stderr)
            self.assertEqual(json.loads(receipt.read_text())['returncode'], 1)

    def test_concurrent_launcher_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            receipt = Path(tmp) / 'run.json'
            ready = Path(tmp) / 'ready'
            script = ('from pathlib import Path; import time; '
                      f'Path({str(ready)!r}).touch(); time.sleep(3)')
            command = self.command(receipt, script)
            command[2:2] = ['--cache-root', tmp]
            first = subprocess.Popen(command,
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            try:
                deadline = time.monotonic() + 10
                while not ready.exists() and first.poll() is None and time.monotonic() < deadline:
                    time.sleep(.02)
                self.assertTrue(ready.exists())
                # Different receipt names still cannot overlap on one task root.
                duplicate_command = self.command(Path(tmp) / 'second.json', 'raise SystemExit(9)')
                duplicate_command[2:2] = ['--cache-root', tmp]
                duplicate = subprocess.run(duplicate_command,
                                           capture_output=True, timeout=10)
                self.assertNotEqual(duplicate.returncode, 0)
                self.assertIn(b'already has an active runner', duplicate.stderr)
                first.communicate(timeout=10)
                self.assertEqual(first.returncode, 0)
                self.assertEqual(json.loads(receipt.read_text())['returncode'], 0)
            finally:
                if first.poll() is None:
                    first.terminate()
                    first.communicate(timeout=10)


if __name__ == '__main__':
    unittest.main()
