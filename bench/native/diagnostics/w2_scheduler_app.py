"""Name only this diagnostic API's threads for kernel scheduler event filters."""
import ctypes
import os
import re
import sys
import threading

def parse_api_cpus(spec):
    if not re.fullmatch(r'[0-9]+(?:,[0-9]+)*', spec):
        raise ValueError('API CPUs must be comma-separated nonnegative integers')
    cpus = [int(cpu) for cpu in spec.split(',')]
    if len(set(cpus)) != len(cpus):
        raise ValueError('API CPUs must be unique')
    return tuple(sorted(cpus))


def validate_available(cpus, available):
    if not cpus or len(set(cpus)) != len(cpus) or any(cpu < 0 for cpu in cpus):
        raise ValueError('API CPUs must be nonempty, unique and nonnegative')
    if not set(cpus) <= set(available):
        raise ValueError('API CPUs are not available in the current affinity')


def main():
    if sys.implementation.name != 'cpython' or sys.version_info[:3] != (3, 13, 18):
        raise RuntimeError('scheduler bootstrap requires the pinned CPython 3.13.18')
    spec = os.environ.get('NP_API_CPUS')
    if spec is not None:
        cpus = parse_api_cpus(spec)
        validate_available(cpus, os.sched_getaffinity(0))
        os.sched_setaffinity(0, cpus)
    name = os.environ['NP_SCHED_TAG']
    if not re.fullmatch(r'np[0-9a-f]{12}', name):
        raise ValueError('scheduler tag must be np plus twelve hex digits')
    libc = ctypes.CDLL(None, use_errno=True)
    libc.prctl.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong]
    libc.prctl.restype = ctypes.c_int

    def name_thread():
        if libc.prctl(15, name.encode(), 0, 0, 0):
            raise OSError(ctypes.get_errno(), 'PR_SET_NAME failed')

    name_thread()
    bootstrap_inner = threading.Thread._bootstrap_inner

    def traced_bootstrap(self):
        name_thread()
        bootstrap_inner(self)

    threading.Thread._bootstrap_inner = traced_bootstrap
    import uvicorn
    uvicorn.run('app:app', host='0.0.0.0', port=8000, workers=1, access_log=False, app_dir='/app')


if __name__ == '__main__':
    main()
