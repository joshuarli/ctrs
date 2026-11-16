"""Name only this diagnostic API's threads for kernel scheduler event filters."""
import ctypes
import os
import re
import sys
import threading

if sys.implementation.name != 'cpython' or sys.version_info[:3] != (3, 13, 18):
    raise RuntimeError('scheduler bootstrap requires the pinned CPython 3.13.18')
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
