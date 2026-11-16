"""W10 diagnostic entrypoint; identical on both engines, outside acceptance runs."""
import json
import os
import sys
import threading
import time
from contextlib import asynccontextmanager


def emit(event):
    value = {'event': event, 'pid': os.getpid(), 'wall_ns': time.time_ns(),
             'monotonic_ns': time.monotonic_ns()}
    with open('/tmp/np-recovery-events.jsonl', 'a') as output:
        output.write(json.dumps(value) + '\n')


emit('python_entry')
sys.path.insert(0, '/app')
import uvicorn
import app as application

original_lifespan = application.app.router.lifespan_context


@asynccontextmanager
async def traced_lifespan(app):
    async with original_lifespan(app):
        emit('application_dependencies_ready')
        yield


application.app.router.lifespan_context = traced_lifespan
server = uvicorn.Server(uvicorn.Config(application.app, host='0.0.0.0', port=8000,
                                       workers=1, access_log=False))


def watch_listener():
    deadline = time.monotonic() + 60
    while not server.started:
        if time.monotonic() >= deadline:
            emit('listener_deadline')
            return
        time.sleep(.001)
    emit('uvicorn_listener_started')


threading.Thread(target=watch_listener, daemon=True).start()
server.run()
