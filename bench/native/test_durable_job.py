import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest

SCRIPT = Path(__file__).with_name('durable_job.py').resolve()
PYTHON = str(Path(sys.executable).resolve())


class DurableJobTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=os.environ['TMPDIR'])
        self.root = Path(self.tmp.name)
        self.input = self.root / 'input'
        self.input.write_text('frozen')
        self.receipts = self.root / 'receipts.json'
        self.receipts.write_text(subprocess.check_output(
            [PYTHON, str(SCRIPT), 'receipt', PYTHON, str(self.input)], text=True))
        self.job = self.root / 'job'

    def tearDown(self):
        self.tmp.cleanup()

    def start(self, program, seconds=10):
        return subprocess.run([PYTHON, str(SCRIPT), 'launch', '--job', str(self.job),
                               '--deadline-epoch', str(time.time() + seconds),
                               '--inputs', str(self.receipts), '--', PYTHON, '-c', program],
                              capture_output=True, text=True, timeout=5)

    def read_when_present(self, name):
        end = time.monotonic() + 8
        path = self.job / name
        while time.monotonic() < end:
            if path.exists():
                return json.loads(path.read_text())
            time.sleep(0.02)
        self.fail(f'{name} was not written')

    def test_success_survives_launcher_exit(self):
        launched = self.start("import time; time.sleep(.3); print('finished')")
        self.assertEqual(launched.returncode, 0, launched.stderr)
        status = self.read_when_present('status.json')
        self.assertEqual(status['state'], 'exited')
        self.assertEqual(status['exit_code'], 0)
        self.assertEqual(status['job_id'], launched.stdout.strip())
        self.assertTrue(status['supervisor']['kernel_start_identity'])
        self.assertTrue(status['child']['kernel_start_identity'])
        self.assertEqual((self.job / 'stdout').read_text().strip(), 'finished')

    def test_nonzero_and_signal_exit(self):
        launched = self.start("import sys; print('bad', file=sys.stderr); sys.exit(7)")
        self.assertEqual(launched.returncode, 0, launched.stderr)
        status = self.read_when_present('status.json')
        self.assertEqual((status['state'], status['exit_code'], status['exit_signal']), ('exited', 7, None))
        self.assertIn('bad', (self.job / 'stderr').read_text())

    def test_child_signal_death_is_recorded(self):
        launched = self.start("import os,signal; os.kill(os.getpid(), signal.SIGTERM)")
        self.assertEqual(launched.returncode, 0, launched.stderr)
        status = self.read_when_present('status.json')
        self.assertEqual((status['state'], status['exit_code'], status['exit_signal']),
                         ('exited', None, signal.SIGTERM))

    def test_deadline_kills_child_and_descendant(self):
        program = "import subprocess,sys,time; p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)']); print(p.pid,flush=True); time.sleep(30)"
        launched = self.start(program, seconds=1.5)
        self.assertEqual(launched.returncode, 0, launched.stderr)
        status = self.read_when_present('status.json')
        self.assertEqual(status['state'], 'deadline')
        self.assertIsNotNone(status['exit_signal'])
        pid = int((self.job / 'stdout').read_text().strip())
        with self.assertRaises(ProcessLookupError):
            os.kill(pid, 0)

    def test_interrupt_records_signal(self):
        launched = self.start('import time; time.sleep(30)')
        self.assertEqual(launched.returncode, 0, launched.stderr)
        running = self.read_when_present('running.json')
        os.kill(running['supervisor']['pid'], signal.SIGINT)
        status = self.read_when_present('status.json')
        self.assertEqual((status['state'], status['signal']), ('interrupted', signal.SIGINT))
        self.assertIsNotNone(status['exit_signal'])

    def test_changed_input_rejected_before_launch(self):
        self.input.write_text('modified')
        launched = self.start("print('must not run')")
        self.assertNotEqual(launched.returncode, 0)
        self.assertFalse(self.job.exists())

    def test_duplicate_supervisor_cannot_publish_a_terminal_record(self):
        gate = self.root / 'gate'
        os.mkfifo(gate)
        program = "import pathlib;print('ready',flush=True);pathlib.Path(" + repr(str(gate)) + ").open('r').read(1);print('completed')"
        launched = self.start(program)
        self.assertEqual(launched.returncode, 0, launched.stderr)
        running = self.read_when_present('running.json')
        original = (self.job / 'running.json').read_bytes()
        duplicate = subprocess.run([PYTHON, str(SCRIPT), '_supervise', str(self.job)], capture_output=True, text=True, timeout=5)
        self.assertNotEqual(duplicate.returncode, 0)
        self.assertFalse((self.job / 'status.json').exists())
        self.assertEqual((self.job / 'running.json').read_bytes(), original)
        end = time.monotonic() + 3
        while True:
            try:
                fd = os.open(gate, os.O_WRONLY | os.O_NONBLOCK)
                break
            except OSError:
                if time.monotonic() >= end:
                    self.fail('owned child did not open its gate')
                time.sleep(.02)
        try:
            os.write(fd, b'G')
        finally:
            os.close(fd)
        status = self.read_when_present('status.json')
        self.assertEqual(status['state'], 'exited')
        self.assertEqual(status['exit_code'], 0)
        self.assertTrue(status['cleanup_complete'], status)
        self.assertEqual(status['supervisor'], running['supervisor'])

    def test_normal_leader_exit_also_cleans_remaining_group(self):
        program = "import subprocess,sys; p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)']);print(p.pid,flush=True);sys.exit(7)"
        launched = self.start(program)
        self.assertEqual(launched.returncode, 0, launched.stderr)
        status = self.read_when_present('status.json')
        self.assertEqual((status['state'], status['exit_code']), ('exited', 7))
        self.assertTrue(status['cleanup_complete'], status)
        pid = int((self.job / 'stdout').read_text().strip())
        end = time.monotonic() + 3
        while time.monotonic() < end:
            observed = subprocess.run(['/bin/ps', '-p', str(pid), '-o', 'state='], capture_output=True, text=True)
            if not observed.stdout.strip() or observed.stdout.strip().startswith('Z'):
                break
            time.sleep(.02)
        else:
            self.fail('owned descendant remains live')


if __name__ == '__main__':
    unittest.main()
