"""Tiny HTTP/1.0 client for the loopback daemon.

urllib.request + http.client import ~150 ms of modules (email, ssl, ...) that every `dr` command would pay for;
the daemon only needs one request/response over a plain socket.
"""

from __future__ import annotations

import socket


def request(port: int, method: str, path: str, body: bytes = b"", headers: dict[str, str] | None = None,
            timeout: float = 30) -> tuple[int, bytes]:
    """Return (status, body). Raises OSError when the port cannot be reached."""
    lines = [f"{method} {path} HTTP/1.0", f"Host: 127.0.0.1:{port}", f"Content-Length: {len(body)}"]
    lines += [f"{k}: {v}" for k, v in (headers or {}).items()]
    payload = ("\r\n".join(lines) + "\r\n\r\n").encode("latin-1") + body
    with socket.create_connection(("127.0.0.1", port), timeout=timeout) as sock:
        sock.sendall(payload)
        chunks = []
        while chunk := sock.recv(65536):
            chunks.append(chunk)
    raw = b"".join(chunks)
    head, sep, content = raw.partition(b"\r\n\r\n")
    if not sep:
        raise OSError("bad response from daemon")
    try:
        status = int(head.split(b" ", 2)[1])
    except (IndexError, ValueError):
        raise OSError("bad response from daemon") from None
    return status, content
