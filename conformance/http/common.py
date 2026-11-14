"""Tiny raw HTTP/1.1 client over the engine's unix socket.

Deliberately minimal: the fixtures test the server's framing, so the
client must not paper over anything on its own. Responses are read
according to the declared framing (Content-Length or chunked).
"""
import socket


class Conn:
    def __init__(self, path, timeout=10.0):
        self.s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.s.settimeout(timeout)
        self.s.connect(path)
        self.f = self.s.makefile("rb", buffering=0)

    def close(self):
        try:
            self.f.close()
        finally:
            self.s.close()

    def send_all(self, data):
        self.s.sendall(data)

    def send_byte_at_a_time(self, data, delay=0.02):
        import time
        for b in data:
            self.s.sendall(bytes([b]))
            time.sleep(delay)

    def readline(self, limit=65536):
        line = self.f.readline(limit)
        if not line:
            raise EOFError("connection closed by server")
        return line

    def _read_exactly(self, n):
        out = b""
        while len(out) < n:
            chunk = self.f.read(n - len(out))
            if not chunk:
                raise EOFError("body cut short")
            out += chunk
        return out

    def read_response(self):
        """(status:int, headers:dict, body:bytes)"""
        status_line = self.readline().decode("latin-1").rstrip("\r\n")
        parts = status_line.split(" ", 2)
        if len(parts) < 2 or not parts[1].isdigit():
            raise ValueError(f"bad status line: {status_line!r}")
        status = int(parts[1])
        headers = {}
        while True:
            line = self.readline()
            if line in (b"\r\n", b"\n"):
                break
            k, _, v = line.partition(b":")
            if k:
                headers[k.decode().strip().lower()] = v.decode().strip()
        te = headers.get("transfer-encoding", "").lower()
        if "chunked" in te:
            body = b""
            while True:
                size = int(self.readline().split(b";")[0].strip(), 16)
                if size == 0:
                    while self.readline().strip():
                        pass
                    break
                body += self._read_exactly(size)
                self._read_exactly(2)
            return status, headers, body
        if "content-length" in headers:
            return status, headers, self._read_exactly(int(headers["content-length"]))
        return status, headers, b""

    def roundtrip(self, method, path, headers=None, body=b""):
        hs = "".join(f"{k}: {v}\r\n" for k, v in (headers or {}).items())
        self.send_all(f"{method} {path} HTTP/1.1\r\nhost: localhost\r\n{hs}content-length: {len(body)}\r\n\r\n".encode() + body)
        return self.read_response()


def report(name, ok, detail=""):
    if ok:
        print(f"PASS {name}")
        return 0
    print(f"FAIL {name}: {detail}")
    return 1
