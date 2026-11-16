import unittest
from pathlib import Path

import cpu_profile

TAG = 'np123456789abc'


def task(tid, ticks):
    fields = ['S'] + ['0'] * 40
    fields[11] = str(ticks)
    fields[19] = '123'
    return {'comm': TAG + '\n', 'stat': f'{tid} ({TAG}) ' + ' '.join(fields)}


class CPUProfile(unittest.TestCase):
    def analyze(self, text, **overrides):
        args = dict(tag=TAG, tasks_before={'1': task('1', 0)}, tasks_after={'1': task('1', 10)},
                    application_cpu={'status': 'ok', 'clock_ticks_per_second': 100, 'cpu_seconds': .1}, successful_operations=100)
        args.update(overrides)
        return cpu_profile.analyze(text, **args)

    def test_leaf_and_inclusive_cost_use_own_thread_cpu(self):
        text = f'{TAG} 1/1 [000] 1.123456789: cpu-clock:\n\t1234 take_gil+0x8 (/lib/libpython.so)\n\t2345 caller (/lib/libpython.so)\n\n'
        result = self.analyze(text)
        self.assertEqual(result['status'], 'ok', result)
        thread = result['per_thread']['1']
        self.assertEqual(thread['samples'], 1)
        self.assertEqual(thread['inclusive_counts']['caller (/lib/libpython.so)'], 1)
        self.assertAlmostEqual(thread['cost_per_success_estimates']['take_gil+0x8 (/lib/libpython.so)'], .001)

    def test_native_multi_thread_dwarf_trace(self):
        text = (Path(__file__).parent / 'fixtures/diagnostics/w2-cpu-native-v1.txt').read_text()
        tag = text.split()[0]
        before = {tid: task(tid, 0) for tid in ('1', '2', '6', '7', '8')}
        after = {tid: task(tid, 10) for tid in before}
        for records in (before, after):
            for record in records.values():
                record['comm'] = tag + '\n'
        result = self.analyze(text, tag=tag, tasks_before=before, tasks_after=after)
        self.assertEqual(result['status'], 'ok', result)
        self.assertEqual(result['sample_count'], 5)
        self.assertTrue(all(record['samples'] == 1 for record in result['per_thread'].values()))

    def test_loss_unrecognized_frames_empty_and_foreign_tasks_invalidate(self):
        good = f'{TAG} 1/1 [000] 1.1: cpu-clock: 1234 leaf (/lib/libc.so)\n'
        for text in ('', good + 'LOST 10 events\n', good + 'bad frame\n', good.replace('1/1', '1/2'), good.replace(TAG, 'other')):
            with self.subTest(text=text):
                result = self.analyze(text)
                self.assertEqual(result['status'], 'unknown')
                self.assertIsNone(result['per_thread'])
        self.assertEqual(self.analyze(good, diagnostics='PERF_RECORD_THROTTLE')['status'], 'unknown')

    def test_identity_change_and_unknown_frames_not_silently_filled(self):
        text = f'{TAG} 1/1 [000] 1.1: cpu-clock: 1234 [unknown] ([unknown])\n'
        result = self.analyze(text)
        self.assertEqual(result['per_thread']['1']['unknown_leaf_samples'], 1)
        changed = task('1', 10)
        changed['stat'] = changed['stat'].replace(' 123 ', ' 124 ')
        self.assertEqual(self.analyze(text, tasks_after={'1': changed})['status'], 'unknown')

    def test_raw_loss_throttle_or_omitted_sample_invalidates(self):
        text = f'{TAG} 1/1 [000] 1.1: cpu-clock: 1234 leaf (/lib/libc.so)\n'
        self.assertEqual(self.analyze(text, raw_events='PERF_RECORD_SAMPLE')['status'], 'ok')
        for raw in ('PERF_RECORD_SAMPLE\nPERF_RECORD_LOST_SAMPLES',
                    'PERF_RECORD_SAMPLE\nPERF_RECORD_THROTTLE', 'PERF_RECORD_SAMPLE\nPERF_RECORD_SAMPLE'):
            self.assertEqual(self.analyze(text, raw_events=raw)['status'], 'unknown')

    def test_unsampled_thread_remains_unknown_cost_not_zero(self):
        text = f'{TAG} 1/1 [000] 1.1: cpu-clock: 1234 leaf (/lib/libc.so)\n'
        result = self.analyze(text, tasks_before={'1': task('1', 0), '2': task('2', 0)},
                             tasks_after={'1': task('1', 10), '2': task('2', 1)})
        self.assertEqual(result['per_thread']['2']['samples'], 0)
        self.assertIsNone(result['per_thread']['2']['cost_per_success_estimates'])
        self.assertEqual(self.analyze(text, application_cpu={'status': 'unknown', 'cpu_seconds': None})['status'], 'unknown')


if __name__ == '__main__':
    unittest.main()
