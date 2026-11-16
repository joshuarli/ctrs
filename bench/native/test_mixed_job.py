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

import mixed_job


class MixedJob(unittest.TestCase):
    def test_qualification_refused_before_engine_or_inputs(self):
        command = [sys.executable, str(mixed_job.__file__), '--job', '/missing/job', '--duration', '43200',
                   '--engine', 'ctrs', '--portfolio-layout', '/missing', '--worker-layout', '/missing',
                   '--ctrs-binary', '/missing', '--compose-plugin', '/missing', '--qualification']
        result = subprocess.run(command, capture_output=True, text=True, timeout=5)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('readiness evidence schema/proof are missing', result.stderr)
        pilot = Path(mixed_job.__file__).parent / 'diagnostics/mixed_pilot.py'
        result = subprocess.run([sys.executable, str(pilot), '--portfolio-layout', '/missing',
                                 '--worker-layout', '/missing', '--ctrs-binary', '/missing',
                                 '--qualification'], capture_output=True, text=True, timeout=5)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('readiness evidence schema/proof are missing', result.stderr)

    def test_separate_deadlines_and_frozen_inputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ('portfolio', 'worker'):
                (root / name).mkdir()
                (root / name / 'blob').write_text(name)
            binary = root / 'ctrs'; binary.write_text('binary')
            argv = ['mixed_job', '--job', str(root / 'job'), '--duration', '10', '--engine', 'orbstack',
                    '--portfolio-layout', str(root / 'portfolio'), '--worker-layout', str(root / 'worker'), '--ctrs-binary', str(binary), '--compose-plugin', str(binary)]
            captured = {}
            def launch(job, hard, receipt, child, **kwargs):
                captured.update(hard=hard, receipts=json.loads(Path(receipt).read_text()), child=child, **kwargs)
            with patch.object(sys, 'argv', argv), patch.object(mixed_job.sys, 'platform', 'darwin'), \
                 patch.object(mixed_job.os, 'uname', return_value=type('U', (), {'machine':'arm64'})()), \
                 patch.object(mixed_job.shutil, 'which', return_value=sys.executable), \
                 patch.object(mixed_job.durable_job, 'launch', side_effect=launch):
                self.assertEqual(mixed_job.main(), 0)
            child = captured['child']
            work = float(child[child.index('--work-deadline-epoch') + 1])
            drain = float(child[child.index('--drain-deadline-epoch') + 1])
            self.assertEqual(drain - work, mixed_job.DRAIN_SECONDS)
            self.assertEqual(captured['hard'] - drain, mixed_job.CLEANUP_SECONDS)
            self.assertEqual(captured['interrupt_grace_seconds'], mixed_job.CLEANUP_SECONDS)
            self.assertIn(str(binary), [r['path'] for r in captured['receipts']])
            self.assertIn(str((root / 'portfolio/blob')), [r['path'] for r in captured['receipts']])

    def test_signal_cleanup_reraises_original_signal(self):
        with tempfile.TemporaryDirectory() as tmp:
            marker = Path(tmp) / 'marker'
            code = ('import sys,time; from pathlib import Path; import diagnostic_signals; '
                    'diagnostic_signals.install_cleanup_signals(); print("ready", flush=True);\n'
                    'try:\n while True: time.sleep(1)\n'
                    'finally:\n Path(sys.argv[1]).write_text("cleaned")\n')
            process = subprocess.Popen([sys.executable, '-c', code, str(marker)], cwd=Path(mixed_job.__file__).parent,
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            self.assertEqual(process.stdout.readline().strip(), 'ready')
            process.send_signal(signal.SIGTERM)
            out, err = process.communicate(timeout=5)
            self.assertEqual(process.returncode, -signal.SIGTERM, err)
            self.assertEqual(marker.read_text(), 'cleaned')


class SupervisorOutcome(unittest.TestCase):
    def test_nonzero_child_status_is_preserved(self):
        import contextlib
        import io
        import durable_job
        with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']) as tmp:
            root = Path(tmp)
            receipt = root / 'receipts.json'
            receipt.write_text(json.dumps([durable_job.receipt(sys.executable)]))
            job = root / 'job'
            with contextlib.redirect_stdout(io.StringIO()):
                durable_job.launch(job, time.time() + 15, receipt,
                                   [str(Path(sys.executable).resolve()), '-c', 'import sys;sys.exit(7)'])
            deadline = time.monotonic() + 10
            while not (job / 'status.json').exists() and time.monotonic() < deadline:
                time.sleep(.02)
            status = json.loads((job / 'status.json').read_text())
            self.assertEqual((status['state'], status['exit_code'], status['exit_signal']), ('exited', 7, None))
            self.assertTrue(status['cleanup_complete'])
