import unittest
import sys
from unittest import mock
from pathlib import Path

import cpu_profile
sys.path.insert(0, str(Path(__file__).parent / 'diagnostics'))
import syscall_pilot
import w2_scheduler_app

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

    def test_kernel_symbol_is_not_a_perf_throttle_diagnostic(self):
        text = f'{TAG} 1/1 [000] 1.1: cpu-clock:\n\t1234 blkcg_maybe_throttle_current ([kernel.kallsyms])\n\n'
        result = self.analyze(text, raw_events='PERF_RECORD_SAMPLE')
        self.assertEqual(result['status'], 'ok', result)
        self.assertEqual(result['sample_count'], 1)
        self.assertEqual(self.analyze(text, diagnostics='THROTTLED')['status'], 'unknown')
        self.assertEqual(self.analyze(text, raw_events='PERF_RECORD_SAMPLE\nPERF_RECORD_THROTTLE')['status'], 'unknown')

    def test_attachment_task_reuse_before_phase_is_rejected(self):
        warm = {'1': task('1', 0)}
        measured = {'1': task('1', 10)}
        cpu_profile.check_attachment(warm, measured, 100)
        measured['1']['stat'] = measured['1']['stat'].replace(' 123 ', ' 124 ')
        with self.assertRaisesRegex(ValueError, 'attachment task identity changed'):
            cpu_profile.check_attachment(warm, measured, 100)

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


class APIAffinity(unittest.TestCase):
    def test_parse_and_validate_available_cpus(self):
        self.assertEqual(w2_scheduler_app.parse_api_cpus('2,0,1'), (0, 1, 2))
        for spec in ('', '-1', '0,', ',0', '0,,1', '0,00', '1 2', '1-2', '+1'):
            with self.subTest(spec=spec), self.assertRaises(ValueError):
                w2_scheduler_app.parse_api_cpus(spec)
        w2_scheduler_app.validate_available((0, 2), {0, 1, 2})
        for cpus in ((), (0, 0), (-1,), (3,)):
            with self.subTest(cpus=cpus), self.assertRaises(ValueError):
                w2_scheduler_app.validate_available(cpus, {0, 1, 2})

    def test_every_task_must_inherit_requested_affinity(self):
        tasks = {'1': {'status': 'Cpus_allowed_list:\t0-1,3\n'},
                 '2': {'status': 'Cpus_allowed_list:\t0,1,3\n'}}
        expected = {'1': [0, 1, 3], '2': [0, 1, 3]}
        self.assertEqual(syscall_pilot.task_affinities(tasks, (0, 1, 3)), expected)
        self.assertEqual(syscall_pilot.task_affinities(tasks, None), expected)
        tasks['2']['status'] = 'Cpus_allowed_list:\t0-1\n'
        with self.assertRaisesRegex(ValueError, 'differs from request'):
            syscall_pilot.task_affinities(tasks, (0, 1, 3))
        for status in ('', 'Cpus_allowed_list:\t1-0', 'Cpus_allowed_list:\t0,0',
                       'Cpus_allowed_list:\t0\nCpus_allowed_list:\t0'):
            with self.subTest(status=status), self.assertRaises(ValueError):
                syscall_pilot.task_affinities({'1': {'status': status}}, None)
        with self.assertRaises(ValueError):
            syscall_pilot.task_affinities({}, (0,))

    def test_unavailable_guest_cpu_fails_before_setting_affinity(self):
        with mock.patch.dict(w2_scheduler_app.os.environ, {'NP_API_CPUS': '2'}, clear=True), \
             mock.patch.object(w2_scheduler_app.sys, 'version_info', (3, 13, 18)), \
             mock.patch.object(w2_scheduler_app.os, 'sched_getaffinity', create=True, return_value={0, 1}), \
             mock.patch.object(w2_scheduler_app.os, 'sched_setaffinity', create=True) as setter:
            with self.assertRaisesRegex(ValueError, 'not available'):
                w2_scheduler_app.main()
            setter.assert_not_called()

    def test_bootstrap_sets_affinity_before_uvicorn_and_default_does_not(self):
        for spec in (None, '1,0'):
            with self.subTest(spec=spec):
                events = []
                env = {'NP_SCHED_TAG': TAG}
                if spec is not None:
                    env['NP_API_CPUS'] = spec
                libc = mock.MagicMock()
                libc.prctl.return_value = 0
                uvicorn = mock.Mock()
                uvicorn.run.side_effect = lambda *a, **kw: events.append('run')
                original = w2_scheduler_app.threading.Thread._bootstrap_inner
                try:
                    with mock.patch.dict(w2_scheduler_app.os.environ, env, clear=True), \
                         mock.patch.object(w2_scheduler_app.sys, 'version_info', (3, 13, 18)), \
                         mock.patch.object(w2_scheduler_app.ctypes, 'CDLL', return_value=libc), \
                         mock.patch.object(w2_scheduler_app.os, 'sched_getaffinity', create=True, return_value={0, 1}), \
                         mock.patch.object(w2_scheduler_app.os, 'sched_setaffinity', create=True, side_effect=lambda *a: events.append(('set', a))), \
                         mock.patch.dict(sys.modules, {'uvicorn': uvicorn}):
                        w2_scheduler_app.main()
                finally:
                    w2_scheduler_app.threading.Thread._bootstrap_inner = original
                self.assertEqual(events, [('set', (0, (0, 1))), 'run'] if spec else ['run'])


if __name__ == '__main__':
    unittest.main()
