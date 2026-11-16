import unittest
import sched_trace

TAG = 'np012345abcdef'


def snapshot(start=123):
    tail = ['S'] + ['0'] * 18 + [str(start)]
    return {'1': {'comm': TAG+'\n', 'stat': '1 ('+TAG+') '+' '.join(tail)}}


def event(ns, kind, payload, comm='swapper', tid=0):
    return f'{comm} {1 if tid else 0}/{tid} [000] 1.{ns:09d}: sched:{kind}: {payload}'


def wake(ns, kind):
    return event(ns, kind, f'comm={TAG} pid=268 prio=120 target_cpu=000')


def switch(ns, out=False, state='S'):
    body = (f'prev_comm={TAG} prev_pid=268 prev_prio=120 prev_state={state} ==> next_comm=swapper/0 next_pid=0 next_prio=120'
            if out else f'prev_comm=swapper/0 prev_pid=0 prev_prio=120 prev_state=R ==> next_comm={TAG} next_pid=268 next_prio=120')
    return event(ns, 'sched_switch', body, TAG if out else 'swapper', 1 if out else 0)


def fixture():
    return '\n'.join([wake(0, 'sched_waking'), wake(2000, 'sched_wakeup'), switch(10000),
                      switch(20000, True), wake(30000, 'sched_waking'), wake(32000, 'sched_wakeup'),
                      switch(35000), switch(45000, True, 'R+'), switch(55000), switch(65000, True)])


def analyze(text, **kwargs):
    return sched_trace.analyze(text, tag=TAG, tasks_before=snapshot(), tasks_after=kwargs.get('after', snapshot()),
                               global_main_tid=kwargs.get('main_tid', 268))


class SchedulerTraceTests(unittest.TestCase):
    def test_namespace_mapping_and_blocked_vs_runnable_intervals(self):
        result = analyze(fixture())
        self.assertEqual(result['status'], 'ok', result['errors'])
        self.assertEqual(result['namespace_to_global_tid'], {'1': 268})
        self.assertEqual(result['totals_ns'], dict(scheduled_running_observed=30000,
                         off_cpu_ns=25000, blocked_ns=10000, wake_transition_ns=2000,
                         wake_transition_off_cpu_ns=2000, runnable_wait_ns=13000))
        self.assertEqual(result['coverage']['complete_closed_cycle_fraction'], 1)
        self.assertEqual(result['coverage']['unobserved_boundary_time'], 'unknown')
        self.assertFalse(result['coverage']['scheduled_running_is_task_cpu_time'])
        self.assertFalse(result['coverage']['wake_transition_is_task_cpu_time'])

    def test_loss_or_malformed_data_cannot_become_small_cost(self):
        for line in ('LOST 50 events', 'unrecognized row'):
            result = analyze(fixture()+'\n'+line)
            self.assertEqual(result['status'], 'invalid')
            self.assertIsNone(result['totals_ns'])

    def test_boundary_only_trace_keeps_unmeasured_time_unknown(self):
        result = analyze(switch(10000, True))
        self.assertEqual(result['status'], 'partial')
        self.assertIsNone(result['totals_ns']['off_cpu_ns'])
        self.assertIsNone(result['totals_ns']['scheduled_running_observed'])
        self.assertIsNone(result['coverage']['complete_closed_cycle_fraction'])

    def test_namespace_tid_is_not_the_global_main_identity(self):
        result = analyze(fixture(), main_tid=1)
        self.assertEqual(result['status'], 'invalid')
        self.assertIn('global main task differs from independently verified kernel PID', result['errors'])
        joined = sched_trace.analyze(fixture(), tag=TAG, tasks_before=snapshot(), tasks_after=snapshot())
        self.assertEqual(joined['status'], 'ok')
        self.assertEqual(joined['global_main_tid_from_trace'], 268)

    def test_task_reuse_or_filter_leak_invalidates(self):
        self.assertEqual(analyze(fixture(), after=snapshot(start=124))['status'], 'invalid')
        self.assertEqual(analyze(fixture(), after={'1': {'comm': TAG}})['status'], 'invalid')
        wrong = snapshot()
        wrong['1']['stat'] = '2' + wrong['1']['stat'][1:]
        self.assertEqual(analyze(fixture(), after=wrong)['status'], 'invalid')
        other = event(70000, 'sched_waking', 'comm=unrelated pid=999 prio=120 target_cpu=000')
        self.assertEqual(analyze(fixture()+'\n'+other)['status'], 'invalid')

    def test_missing_wakeup_and_duplicate_wake_are_partial_not_zero_wait(self):
        lines = fixture().splitlines()
        for text in ('\n'.join(line for line in lines if not ('1.000032000:' in line)),
                     '\n'.join(lines[:6]+[wake(33000, 'sched_wakeup')]+lines[6:])):
            result = analyze(text)
            self.assertEqual(result['status'], 'partial')
            self.assertEqual(result['coverage']['complete_closed_cycle_fraction'], .5)
            self.assertEqual(len(result['cycles']), 1)

    def test_waking_before_switch_out_preserves_overlap_without_negative_sleep(self):
        lines = fixture().splitlines()
        lines.remove(wake(30000, 'sched_waking'))
        lines.insert(3, wake(15000, 'sched_waking'))
        result = analyze('\n'.join(lines))
        self.assertEqual(result['status'], 'ok', result['incomplete'])
        cycle = result['cycles'][0]
        self.assertEqual(cycle['blocked_ns'], 0)
        self.assertEqual(cycle['wake_transition_ns'], 17000)
        self.assertEqual(cycle['wake_transition_off_cpu_ns'], 12000)
        self.assertEqual(cycle['off_cpu_ns'], cycle['blocked_ns']+cycle['wake_transition_off_cpu_ns']+cycle['runnable_wait_ns'])
        self.assertEqual(result['running_wake_observations']['waking_preceded_switch_out'], 1)

    def test_migrations_and_nanosecond_timestamps_survive_parsing(self):
        migration = event(70001, 'sched_migrate_task', f'comm={TAG} pid=268 prio=120 orig_cpu=0 dest_cpu=16')
        result = analyze(fixture()+'\n'+migration)
        self.assertEqual(result['migrations_by_global_tid'], {268: 1})
        events, errors = sched_trace.parse(migration, TAG)
        self.assertEqual(errors, [])
        self.assertEqual(events[0]['time_ns'], 1_000_070_001)

    def test_application_cpu_excludes_helpers_but_requires_all_api_threads(self):
        def task(tid, user, system):
            record = snapshot()['1']
            tail = record['stat'][record['stat'].rfind(')')+2:].split()
            tail[11], tail[12] = str(user), str(system)
            return {**record, 'stat': tid+' ('+TAG+') '+' '.join(tail)}
        before = {'1': task('1', 10, 5), '2': task('2', 100, 50)}
        after = {'1': task('1', 15, 8), '2': task('2', 200, 90)}
        result = sched_trace.application_cpu_delta(before, after, 100, required_tids={'1', '2'})
        self.assertEqual(result['status'], 'ok')
        self.assertEqual(result['user_cpu_seconds'], 1.05)
        self.assertEqual(result['system_cpu_seconds'], .43)
        self.assertEqual(result['cpu_seconds'], 1.48)
        missing_both = sched_trace.application_cpu_delta({'1': before['1']}, {'1': after['1']}, 100, required_tids={'1', '2'})
        self.assertIsNone(missing_both['cpu_seconds'])
        for incomplete, hz in [({'1': after['1']}, 100), (after, None), ({**after, '2': task('2', 99, 90)}, 100)]:
            invalid = sched_trace.application_cpu_delta(before, incomplete, hz, required_tids={'1', '2'})
            self.assertEqual(invalid['status'], 'unknown')
            self.assertIsNone(invalid['cpu_seconds'])


if __name__ == '__main__':
    unittest.main()
