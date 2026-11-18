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

    def test_phase_metrics_cover_scored_workflow(self):
        phases = {name: {'operation_wall_seconds': float(i + 1)}
                  for i, name in enumerate(('setup',) + workspace.BUILD_PHASES + ('cleanup',))}
        metrics = workspace.phase_metrics(phases)
        self.assertEqual(metrics['install_seconds'], 2.0)
        self.assertEqual(metrics['branch_switch_seconds'], 8.0)
        self.assertEqual(metrics['workflow_seconds'], sum(range(2, 9)))
        with self.assertRaises(KeyError):
            workspace.phase_metrics({'install': {'operation_wall_seconds': 1.0}})
