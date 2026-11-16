import json
from pathlib import Path
import unittest

import perf_counts

RAW = (Path(__file__).parent / 'fixtures/diagnostics/w2-perf-stat-v1.jsonl').read_text()
TAG = 'npba9f20237329'
TIDS = ['1', '2', '6', '7', '8']


class PerfCounts(unittest.TestCase):
    def analyze(self, rows):
        return perf_counts.summarize(rows, tag=TAG, required_tids=TIDS, successful_operations=5000)

    def test_real_per_thread_output_normalizes_raw_totals(self):
        result = self.analyze(RAW)
        self.assertEqual(result['status'], 'ok', result)
        self.assertEqual(result['observed_cells'], 50)
        self.assertEqual(result['counts'][TAG + ':enter_futex'], 180183)
        self.assertAlmostEqual(result['application_cpu_seconds'], 1.992622173)
        self.assertAlmostEqual(result['application_cpu_seconds_per_success'], 1.992622173 / 5000)
        self.assertEqual(result['per_successful_operation'][TAG + ':enter_futex'], 180183 / 5000)

    def test_missing_thread_counter_invalidates_all_totals(self):
        rows = RAW.splitlines()
        result = self.analyze('\n'.join(row for row in rows if json.loads(row)['thread'] != TAG + '-1'))
        self.assertEqual(result['status'], 'unknown')
        self.assertIsNone(result['counts'])
        self.assertIsNone(result['application_cpu_seconds'])

    def test_missing_event_not_counted_duplicate_and_partial_schedule_fail(self):
        rows = RAW.splitlines()
        cases = ['\n'.join(rows[:-1]), RAW + rows[0] + '\n']
        for field, value in [('counter-value', '<not counted>'), ('counter-value', 'NaN'), ('pcnt-running', 95), ('event-runtime', 0)]:
            first = json.loads(rows[0]); first[field] = value
            cases.append('\n'.join([json.dumps(first), *rows[1:]]))
        for text in cases:
            with self.subTest(text=text[:80]):
                result = self.analyze(text)
                self.assertEqual(result['status'], 'unknown')
                self.assertIsNone(result['per_successful_operation'])


class DetailedPerfCounts(unittest.TestCase):
    def setUp(self):
        self.raw = (Path(__file__).parent / 'fixtures/diagnostics/w2-perf-stat-v2.jsonl').read_text()
        self.tag = 'np7fc7492938a0'

    def analyze(self, text):
        return perf_counts.summarize_detail(text, tag=self.tag, required_tids=TIDS, successful_operations=5000)

    def test_real_command_return_blocks_and_direct_raw_normalization(self):
        result = self.analyze(self.raw)
        self.assertEqual(result['status'], 'ok', result)
        self.assertEqual(result['required_cells'], 90)
        self.assertEqual(result['counts']['futex_all'], 241717)
        self.assertEqual(result['counts']['futex_eagain'], 9395)
        self.assertEqual(result['counts']['futex_positive'], 78962)
        self.assertEqual(result['counts']['futex_other_commands'], 0)
        self.assertEqual(result['counts']['futex_other_negative_returns'], 0)
        self.assertEqual(result['per_successful_operation']['futex_all'], 241717 / 5000)

    def test_missing_or_duplicate_thread_never_becomes_a_smaller_total(self):
        rows = self.raw.splitlines()
        for text in ('\n'.join(rows[:-1]), '\n'.join([rows[0], rows[0], *rows[2:]])):
            result = self.analyze(text)
            self.assertEqual(result['status'], 'unknown')
            self.assertIsNone(result['counts'])
            self.assertIsNone(result['application_cpu_seconds_per_success'])

    def test_wrong_selector_order_invalid_value_and_partial_schedule_are_unknown(self):
        rows = self.raw.splitlines()
        cases = ['\n'.join(rows[5:10] + rows[:5] + rows[10:])]
        for field, value in [('counter-value', '<not supported>'), ('counter-value', 'NaN'), ('pcnt-running', 97)]:
            first = json.loads(rows[0]); first[field] = value
            cases.append('\n'.join([json.dumps(first), *rows[1:]]))
        for text in cases:
            result = self.analyze(text)
            self.assertEqual(result['status'], 'unknown')
            self.assertIsNone(result['per_successful_operation'])


if __name__ == '__main__':
    unittest.main()
