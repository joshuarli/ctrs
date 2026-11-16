"""Termination policy for standalone diagnostics that own child processes."""
import atexit
import os
import signal


def install_cleanup_signals():
    """Call once in a diagnostic's main thread; finally cleanup precedes original signal death."""
    requested = None
    signals = (signal.SIGTERM, signal.SIGINT, signal.SIGHUP, signal.SIGQUIT)

    def stop(number, frame):
        nonlocal requested
        requested = number
        for item in signals:
            signal.signal(item, signal.SIG_IGN)
        raise SystemExit(128 + number)

    def restore():
        if requested is not None:
            signal.signal(requested, signal.SIG_DFL)
            os.kill(os.getpid(), requested)

    atexit.register(restore)
    for number in signals:
        signal.signal(number, stop)
