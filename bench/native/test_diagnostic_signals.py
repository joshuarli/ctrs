from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import unittest


class DiagnosticSignalTests(unittest.TestCase):
    def test_cleanup_completes_before_original_signal_death(self):
        script = """import pathlib,signal,sys
from diagnostic_signals import install_cleanup_signals
install_cleanup_signals()
try:
 print('ready',flush=True)
 signal.pause()
finally:
 pathlib.Path(sys.argv[1]).write_text('cleaned')
"""
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory)/'cleanup'
            proc = subprocess.Popen([sys.executable,'-c',script,str(marker)],
                    cwd=Path(__file__).parent,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
            try:
                self.assertEqual(proc.stdout.readline().strip(),'ready')
                proc.send_signal(signal.SIGTERM)
                stdout,stderr=proc.communicate(timeout=5)
                self.assertEqual(proc.returncode,-signal.SIGTERM,stderr)
                self.assertEqual(marker.read_text(),'cleaned')
            finally:
                if proc.poll() is None:
                    proc.kill()
                    proc.wait(timeout=5)
                proc.stdout.close()
                proc.stderr.close()


if __name__ == '__main__':
    unittest.main()
