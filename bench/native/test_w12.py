import unittest

import workspace


class WorkspaceTests(unittest.TestCase):
    def test_edit_plan_covers_event_kinds_and_files(self):
        paths = [f'server/d{i}/file.ts' for i in range(12)]
        plan = workspace.edit_plan(paths)
        self.assertEqual(len(plan), 60)
        self.assertEqual({event['kind'] for event in plan},
                         {'save', 'atomic', 'create_import', 'rename', 'delete', 'burst'})
        self.assertGreaterEqual(len({path for event in plan for path in event['paths']}), 10)
        self.assertTrue(all(len(event['paths']) == 5 and len(set(event['paths'])) == 5
                            for event in plan if event['kind'] == 'burst'))
        self.assertEqual(len({event['token'] for event in plan}), 60)
        with self.assertRaises(ValueError):
            workspace.edit_plan(paths, edits=59)
        workspace.verify_burst(.05)
        with self.assertRaises(ValueError):
            workspace.verify_burst(.051)

    def test_output_mismatch_fails(self):
        expected = {'server': {'sha256': 'a'}, 'tests': ['a', 'b']}
        self.assertTrue(workspace.verify_output(expected, expected))
        with self.assertRaises(ValueError):
            workspace.verify_output({'server': {'sha256': 'b'}, 'tests': ['a', 'b']}, expected)
        with self.assertRaises(ValueError):
            workspace.verify_output({'server': {'sha256': 'a'}, 'tests': ['b', 'a']}, expected)

    def test_result_classification(self):
        self.assertEqual(workspace.classify_result('new', 'new', False), 'correct')
        self.assertEqual(workspace.classify_result('new', 'old', False), 'stale')
        self.assertEqual(workspace.classify_result('new', None, True), 'missed')
        self.assertEqual(workspace.classify_result(None, 'old-output', True), 'stale')
        self.assertEqual(workspace.classify_result(None, None, False), 'correct')
        self.assertFalse(workspace.observed_stale('old', 'expected', 'old', True))
        self.assertTrue(workspace.observed_stale('wrong', 'expected', 'old', True))
        self.assertTrue(workspace.observed_stale('expected', 'expected', 'old', False))
        self.assertFalse(workspace.observed_stale('expected', 'expected', 'old', True))

    def test_watch_admission_needs_every_result_correct(self):
        good = {'results': 120, 'correct': 120, 'missed': 0, 'stale': 0, 'edits': [0] * 120}
        checks, error = workspace.watch_admission(good, 60)
        self.assertEqual(checks, {'watch_run_completed': True, 'every_result_correct': True})
        self.assertIsNone(error)
        for bad in ({'correct': 97, 'missed': 23}, {'correct': 119, 'stale': 1}, {'results': 0, 'correct': 0, 'edits': []}):
            checks, error = workspace.watch_admission({**good, **bad}, 60)
            self.assertFalse(checks['every_result_correct'])
            self.assertIn('W12-watch', error)

    def test_phase_metrics_cover_scored_workflow(self):
        phases = {name: {'operation_wall_seconds': float(i + 1)}
                  for i, name in enumerate(('setup',) + workspace.BUILD_PHASES + ('cleanup',))}
        metrics = workspace.phase_metrics(phases)
        self.assertEqual(metrics['install_seconds'], 2.0)
        self.assertEqual(metrics['branch_switch_seconds'], 8.0)
        self.assertEqual(metrics['workflow_seconds'], sum(range(2, 9)))
        with self.assertRaises(KeyError):
            workspace.phase_metrics({'install': {'operation_wall_seconds': 1.0}})


class BaselineCliTests(unittest.TestCase):
    def test_baseline_accepts_new_cases_and_condition_flags(self):
        import subprocess
        import sys
        for extra in (['--case', 'W12', '--workspace-layout', 'all-volume'],
                      ['--case', 'W12-watch', '--watch-mount', 'volume'],
                      ['--case', 'W13', '--transfer-path', 'container-to-mac']):
            cp = subprocess.run([sys.executable, 'runner.py', 'baseline', '--a', 'ctrs', '--b', 'orbstack',
                                 *extra, '--help'], capture_output=True, text=True)
            self.assertEqual(cp.returncode, 0, cp.stderr)

    def test_script_run_shares_runner_module_with_trial_modules(self):
        import subprocess
        import sys
        script = ("import runpy, sys\nsys.argv = ['runner.py', '--help']\ntry:\n"
                  "    runpy.run_path('runner.py', run_name='__main__')\nexcept SystemExit:\n    pass\n"
                  "print(sys.modules['runner'].__name__)")
        cp = subprocess.run([sys.executable, '-c', script], capture_output=True, text=True)
        self.assertEqual(cp.stdout.strip().splitlines()[-1], '__main__', cp.stderr)
