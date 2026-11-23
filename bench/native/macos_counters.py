"""macOS ARM64 process counters through the SDK's rusage_info_v0 ABI."""
import ctypes
import os
import sys
import time


class RusageInfo(ctypes.Structure):
    _fields_ = [('uuid', ctypes.c_uint8 * 16)] + [
        (name, ctypes.c_uint64) for name in (
            'user_time', 'system_time', 'pkg_idle_wkups', 'interrupt_wkups',
            'pageins', 'wired_size', 'resident_size', 'phys_footprint',
            'proc_start_abstime', 'proc_exit_abstime')]


class Timebase(ctypes.Structure):
    _fields_ = [('numer', ctypes.c_uint32), ('denom', ctypes.c_uint32)]


class Counters:
    def __init__(self):
        if sys.platform != 'darwin' or os.uname().machine != 'arm64':
            raise RuntimeError('native resource counters require ARM64 macOS')
        self.lib = ctypes.CDLL('/usr/lib/libSystem.B.dylib', use_errno=True)
        self.lib.proc_pid_rusage.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_void_p]
        self.lib.proc_pid_rusage.restype = ctypes.c_int
        self.lib.mach_timebase_info.argtypes = [ctypes.POINTER(Timebase)]
        self.lib.mach_timebase_info.restype = ctypes.c_int
        base = Timebase()
        if self.lib.mach_timebase_info(ctypes.byref(base)) or not base.denom:
            raise RuntimeError('mach_timebase_info failed')
        self.seconds_per_tick = base.numer / base.denom / 1e9

    def read(self, pid):
        info = RusageInfo()
        started = time.monotonic()
        if self.lib.proc_pid_rusage(pid, 0, ctypes.byref(info)):
            code = ctypes.get_errno()
            raise OSError(code, os.strerror(code), str(pid))
        return {'pid': pid, 'cputime_s': (info.user_time + info.system_time) * self.seconds_per_tick,
                'user_cpu_s': info.user_time * self.seconds_per_tick,
                'system_cpu_s': info.system_time * self.seconds_per_tick,
                'footprint_bytes': info.phys_footprint,
                'rss_kb': info.resident_size / 1024,
                'kernel_start_identity': info.proc_start_abstime,
                'pkg_idle_wakeups': info.pkg_idle_wkups,
                'interrupt_wakeups': info.interrupt_wkups,
                'started_monotonic': started, 'ended_monotonic': time.monotonic(),
                'counter_method': 'proc_pid_rusage RUSAGE_INFO_V0; Mach timebase conversion',
                'footprint_method': 'rusage_info_v0.ri_phys_footprint'}


PROCESSOR_CPU_LOAD_INFO = 2
CPU_STATES = 4
CPU_STATE_IDLE = 2


def host_cpu_ticks(lib=None):
    """Cumulative 32-bit CPU ticks per state. Read the per-processor API
    because XNU rate-limits HOST_CPU_LOAD_INFO and may return cached ticks."""
    lib = lib or ctypes.CDLL('/usr/lib/libSystem.B.dylib')
    task = ctypes.c_uint32.in_dll(lib, 'mach_task_self_').value
    count_type = ctypes.c_uint32
    ticks_type = ctypes.POINTER(ctypes.c_int32)
    lib.mach_host_self.restype = ctypes.c_uint32
    lib.host_processor_info.argtypes = [ctypes.c_uint32, ctypes.c_int32,
                                       ctypes.POINTER(count_type), ctypes.POINTER(ticks_type),
                                       ctypes.POINTER(count_type)]
    lib.host_processor_info.restype = ctypes.c_int32
    lib.vm_deallocate.argtypes = [ctypes.c_uint32, ctypes.c_size_t, ctypes.c_size_t]
    lib.vm_deallocate.restype = ctypes.c_int32
    lib.mach_port_deallocate.argtypes = [ctypes.c_uint32, ctypes.c_uint32]
    lib.mach_port_deallocate.restype = ctypes.c_int32
    host = lib.mach_host_self()
    if not host:
        raise OSError('mach_host_self failed')
    cpus = count_type()
    words = count_type()
    ticks = ticks_type()
    try:
        error = lib.host_processor_info(host, PROCESSOR_CPU_LOAD_INFO, ctypes.byref(cpus),
                                        ctypes.byref(ticks), ctypes.byref(words))
        if error:
            raise OSError(f'host_processor_info(PROCESSOR_CPU_LOAD_INFO) failed ({error})')
        try:
            if not cpus.value or not ticks or words.value != cpus.value * CPU_STATES:
                raise OSError('host_processor_info returned an invalid CPU tick array')
            return [ctypes.c_uint32(sum(ticks[i] for i in range(state, words.value, CPU_STATES))).value
                    for state in range(CPU_STATES)]
        finally:
            if ticks:
                address = ctypes.cast(ticks, ctypes.c_void_p).value
                size = words.value * ctypes.sizeof(ctypes.c_int32)
                error = lib.vm_deallocate(task, address, size)
                if error:
                    raise OSError(f'vm_deallocate CPU ticks failed ({error})')
    finally:
        error = lib.mach_port_deallocate(task, host)
        if error:
            raise OSError(f'mach_port_deallocate host port failed ({error})')


def busy_cores(before, after, cpus):
    delta = [(b - a) % (1 << 32) for a, b in zip(before, after)]
    total = sum(delta)
    return (total - delta[CPU_STATE_IDLE]) / total * cpus if total else None
