"""pgzd.protocol — socket paths and newline-delimited JSON framing.

Request:  {"cmd": "<name>", "args": {...}}\n
Response: {"ok": true, "result": ...}\n   or   {"ok": false, "error": "..."}\n
"""

import json
import os
import socket

RUNTIME_DIR = "/tmp/pgzd"


def session_dir(session: str) -> str:
    return os.path.join(RUNTIME_DIR, session)


def socket_path(session: str) -> str:
    return os.path.join(RUNTIME_DIR, f"{session}.sock")


def log_path(session: str) -> str:
    return os.path.join(RUNTIME_DIR, f"{session}.log")


def send_message(sock: socket.socket, obj: dict) -> None:
    sock.sendall((json.dumps(obj) + "\n").encode("utf-8"))


def recv_message(sock: socket.socket, _buf: dict | None = None) -> dict | None:
    """Read one newline-delimited JSON message.  Returns None on clean EOF.

    Stateless single-message helper: reads until the first newline.
    """
    chunks = []
    while True:
        data = sock.recv(4096)
        if not data:
            if not chunks:
                return None
            break
        chunks.append(data)
        if b"\n" in data:
            break
    raw = b"".join(chunks)
    line, _, _ = raw.partition(b"\n")
    return json.loads(line.decode("utf-8"))
