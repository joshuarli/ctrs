import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

import durable_job

SCRIPT = Path(__file__).with_name('durable_job.py').resolve()
PYTHON = str(Path(sys.executable).resolve())


NATIVE = sys.platform == 'darwin' and os.uname().machine == 'arm64'


@unittest.skipUnless(NATIVE, 'durable_job launches only on native ARM64 macOS')
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

    def start(self, program, seconds=10, grace=.5):
        return subprocess.run([PYTHON, str(SCRIPT), 'launch', '--job', str(self.job),
                               '--deadline-epoch', str(time.time() + seconds),
                               '--inputs', str(self.receipts), '--interrupt-grace-seconds', str(grace), '--', PYTHON, '-c', program],
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

    def test_interrupt_grace_allows_child_cleanup_beyond_default(self):
        marker = self.root / 'cleaned'
        program = ("import signal,time,pathlib,subprocess,sys;"
                   "helper=subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)']);"
                   "signal.signal(signal.SIGTERM,lambda *a: (_ for _ in ()).throw(SystemExit(143)));"
                   "print('ready',flush=True);\n"
                   "try: time.sleep(30)\n"
                   "finally:\n time.sleep(.8)\n assert helper.poll() is None, 'owned service died before cleanup'\n helper.terminate()\n helper.wait(timeout=2)\n pathlib.Path(" + repr(str(marker)) + ").write_text('cleaned')\n")
        launched = self.start(program, seconds=15, grace=2)
        self.assertEqual(launched.returncode, 0, launched.stderr)
        running = self.read_when_present('running.json')
        until = time.monotonic() + 3
        while not (self.job / 'stdout').read_text().strip() and time.monotonic() < until:
            time.sleep(.02)
        self.assertEqual((self.job / 'stdout').read_text().strip(), 'ready')
        os.kill(running['supervisor']['pid'], signal.SIGTERM)
        status = self.read_when_present('status.json')
        self.assertEqual(status['state'], 'interrupted')
        self.assertEqual(marker.read_text(), 'cleaned')
        self.assertTrue(status['cleanup_complete'])

    def test_sparse_input_is_verified_by_detached_supervisor(self):
        with self.input.open('r+b') as file:
            file.truncate(1 << 40)
        receipts = [durable_job.receipt(PYTHON), durable_job.receipt(self.input, sparse=True)]
        self.receipts.write_text(json.dumps(receipts))
        launched = self.start("print('sparse frozen')")
        self.assertEqual(launched.returncode, 0, launched.stderr)
        status = self.read_when_present('status.json')
        self.assertEqual((status['state'], status['exit_code']), ('exited', 0))
        self.assertTrue(status['cleanup_complete'])

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


class SparseReceipts(unittest.TestCase):
    def test_holes_mutation_and_ordinary_receipt_contract(self):
        with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']) as tmp:
            path = Path(tmp) / 'sparse'
            with path.open('wb') as file:
                file.truncate(1 << 40)
                file.seek((1 << 40) - 4096)
                file.write(b'x' * 4096)
            read_bytes = [0]
            original = os.read
            def count_read(fd, size):
                result = original(fd, size)
                read_bytes[0] += len(result)
                return result
            with patch.object(durable_job.os, 'read', side_effect=count_read):
                frozen = durable_job.receipt(path, sparse=True)
            self.assertEqual(frozen['hash_method'], 'sparse-extent-v1')
            self.assertLess(read_bytes[0], 1024 * 1024)
            durable_job.check_receipt(frozen)
            with path.open('r+b') as file:
                file.seek(1024 * 1024)
                file.write(b'changed hole')
            changed = durable_job.receipt(path, sparse=True)
            self.assertNotEqual(changed['sha256'], frozen['sha256'])
            with self.assertRaisesRegex(ValueError, 'input changed'):
                durable_job.check_receipt(frozen)
            path.write_text('regular')
            ordinary = durable_job.receipt(path)
            self.assertEqual(set(ordinary), {'path', 'identity', 'sha256'})
            durable_job.check_receipt(ordinary)
            with self.assertRaisesRegex(ValueError, 'unsupported input hash method'):
                durable_job.check_receipt({**ordinary, 'hash_method': 'unknown'})

    def test_sparse_query_errors_are_not_treated_as_holes(self):
        import errno
        with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']) as tmp:
            path = Path(tmp) / 'input'
            path.write_text('data')
            with patch.object(durable_job.os, 'lseek', side_effect=OSError(errno.EIO, 'input error')):
                with self.assertRaises(OSError):
                    durable_job.receipt(path, sparse=True)
