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


if __name__ == '__main__':
    unittest.main()
