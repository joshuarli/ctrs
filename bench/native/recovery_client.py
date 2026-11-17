"""Per-worker W10 persistent probe; every call records exactly one HTTP attempt."""
import http.client
import json
import time

import recovery_trace


VERSION = 'w10-client-v2-persistent'


class _Connection(http.client.HTTPConnection):
    def __init__(self, host, port, timeout):
        super().__init__(host, port, timeout=timeout)
        self.attempts = 0
        self.opened = 0

    def connect(self):
        self.attempts += 1
        super().connect()
        self.opened += 1


class ProbeClient:
    """One owner thread, bounded socket timeout, no implicit application retry."""
    def __init__(self, host, port, *, timeout=.2):
        self.connection = _Connection(host, port, timeout)

    def query(self, kind):
        if kind not in ('health', 'read'):
            raise ValueError('unknown probe kind')
        path = '/health' if kind == 'health' else '/items?limit=25'
        expected = {'ok': True} if kind == 'health' else {'items': [{'id': i, 'name': f'item-{i}'} for i in range(1, 26)]}
        result, _ = self._exchange(kind, 'GET', path, 200, lambda body: body == expected)
        return result

    def write(self, name, payload):
        request = json.dumps({'name': name, 'payload': payload}).encode()

        def exact_ack(body):
            return (isinstance(body, dict) and set(body) == {'id', 'name'} and body['name'] == name
                    and type(body['id']) is int and body['id'] > 500)

        result, body = self._exchange('write', 'POST', '/items', 201, exact_ack, request)
        result['write'] = {'name': name, 'payload': payload, 'id': body['id'] if result['ok'] else None}
        return result

    def _exchange(self, kind, method, path, expected_status, valid_body, request=None):
        conn = self.connection
        attempts, opened, reused = conn.attempts, conn.opened, conn.sock is not None
        begin = time.monotonic_ns()
        status = body = error = error_errno = None
        malformed_body = False
        try:
            headers = {'Content-Type': 'application/json'} if request is not None else {}
            conn.request(method, path, body=request, headers=headers)
            response = conn.getresponse()
            status = response.status
            body = json.loads(response.read())
        except Exception as exc:
            malformed_body = isinstance(exc, (json.JSONDecodeError, UnicodeDecodeError))
            error, error_errno = recovery_trace.transport_error(exc)
            conn.close()
        ok = error is None and status == expected_status and valid_body(body)
        return dict(kind=kind, started_ns=begin, ended_ns=time.monotonic_ns(),
            wall_ns=time.time_ns(), status=status, ok=ok, error=error,
            invalid_response=not ok and status is not None and status < 500 and (error is None or malformed_body),
            error_errno=error_errno, body=body if not ok else None,
            connect_attempts=conn.attempts - attempts, connections_opened=conn.opened - opened,
            reused_socket=reused, client_version=VERSION), body

    def close(self):
        self.connection.close()
