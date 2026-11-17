import copy
import unittest

from uprobe_trace import analyze

TAG = 'npu0123456789ab'
COMM = 'np0123456789ab'


def capture(events):
    lines = [f' {COMM}-17 [000] ..... 1.{index:06d}: {TAG}_{event}: {payload}'
             for index, (event, payload) in enumerate(events)]
    return {'status': 'ok', 'errors': [],
            'receipt': {'tag': TAG, 'tids': [17], 'cpus': ['cpu0']},
            'raw_trace': '# tracer: nop\n' + '\n'.join(lines)}


class UprobeTraceTests(unittest.TestCase):
    def test_export_spans_outside_calls_and_partial_edges(self):
        value = capture([
            ('futex_ret', 'ret=0'), ('restore_ret', '(address)'),
            ('restore', '(address)'), ('futex', 'op=137'),
            ('futex_ret', 'ret=-11'), ('restore_ret', '(address)'),
            ('futex', 'op=129'), ('futex_ret', 'ret=1'),
            ('save', '(address)'), ('futex', 'op=129'),
            ('futex_ret', 'ret=0'), ('save_ret', '(address)'),
            ('restore', '(address)'), ('futex', 'op=137')])
        result = analyze(value, expected_comm=COMM)
        self.assertEqual(result['status'], 'ok')
        self.assertEqual(result['futex_entry_categories'], {'restore': 2, 'outside_exports': 1, 'save': 1})
        self.assertEqual(result['futex_returns']['restore'], {'-11': 1})
        self.assertEqual(result['phase_edges'], {'leading_futex_return': 1, 'leading_export_return': 1,
                                               'trailing_export_entry': 1, 'trailing_futex_entry': 1})
        self.assertFalse(result['cpu_cost_attribution'])

    def test_missing_interior_entry_is_invalid(self):
        result = analyze(capture([('futex', 'op=128'), ('futex_ret', 'ret=0'),
                                  ('futex_ret', 'ret=-11')]), expected_comm=COMM)
        self.assertEqual(result['status'], 'invalid')
        self.assertIn('unmatched interior futex return', result['errors'])

    def test_foreign_unparsed_unknown_and_missing_tasks_are_invalid(self):
        base = capture([('save', '(address)'), ('save_ret', '(address)')])
        cases = [base['raw_trace'].replace(COMM, 'other'), base['raw_trace'] + '\nnot a trace record',
                 base['raw_trace'].replace('_save:', '_unknown:')]
        for raw in cases:
            with self.subTest(raw=raw):
                value = copy.deepcopy(base)
                value['raw_trace'] = raw
                self.assertEqual(analyze(value, expected_comm=COMM)['status'], 'invalid')
        base['receipt']['tids'].append(18)
        self.assertIn('unobserved required trace tasks', analyze(base, expected_comm=COMM)['errors'])

    def test_empty_filtered_capture_cannot_pass(self):
        result = analyze(capture([]), expected_comm=COMM)
        self.assertEqual(result['status'], 'invalid')
        self.assertIn('unobserved required trace tasks', result['errors'])

    def test_invalid_capture_coverage_is_rejected(self):
        value = capture([])
        value['status'] = 'invalid'
        with self.assertRaisesRegex(ValueError, 'coverage'):
            analyze(value, expected_comm=COMM)
