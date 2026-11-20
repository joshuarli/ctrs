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


HOST_CPU_LOAD_INFO = 3
CPU_STATES = 4
CPU_STATE_IDLE = 2


def host_cpu_ticks(lib=None):
    """Cumulative per-state CPU ticks over all cores from
    host_statistics(HOST_CPU_LOAD_INFO). The counters are 32-bit and wrap;
    the tick unit cancels in `busy_cores`."""
    lib = lib or ctypes.CDLL('/usr/lib/libSystem.B.dylib')
    lib.mach_host_self.restype = ctypes.c_uint32
    ticks = (ctypes.c_uint32 * CPU_STATES)()
    count = ctypes.c_uint32(CPU_STATES)
    if lib.host_statistics(lib.mach_host_self(), HOST_CPU_LOAD_INFO, ticks, ctypes.byref(count)):
        raise OSError('host_statistics(HOST_CPU_LOAD_INFO) failed')
    return list(ticks)


def busy_cores(before, after, cpus):
    delta = [(b - a) % (1 << 32) for a, b in zip(before, after)]
    total = sum(delta)
    return (total - delta[CPU_STATE_IDLE]) / total * cpus if total else None
