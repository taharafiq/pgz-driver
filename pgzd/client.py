"""pgzd.client — connect to a running daemon and run one command."""

import socket

from pgzd import protocol


class DaemonNotRunning(Exception):
    pass


class CommandError(Exception):
    def __init__(self, message: str, server_traceback: str | None = None):
        super().__init__(message)
        self.server_traceback = server_traceback


def request(session: str, cmd: str, args: dict | None = None,
            timeout: float = 30.0) -> dict:
    """Send one command to the daemon for *session*; return its `result`.

    Raises DaemonNotRunning if no daemon is listening, CommandError if the
    daemon reports failure.
    """
    path = protocol.socket_path(session)
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        sock.connect(path)
    except (FileNotFoundError, ConnectionRefusedError):
        raise DaemonNotRunning(
            f"no pgz daemon for session {session!r} (start one with `pgz start`)"
        )
    try:
        protocol.send_message(sock, {"cmd": cmd, "args": args or {}})
        reply = protocol.recv_message(sock)
    finally:
        sock.close()

    if reply is None:
        raise CommandError("daemon closed the connection without replying")
    if not reply.get("ok"):
        raise CommandError(reply.get("error", "unknown error"),
                           reply.get("traceback"))
    return reply.get("result", {})


def is_running(session: str) -> bool:
    try:
        request(session, "ping", timeout=2.0)
        return True
    except DaemonNotRunning:
        return False
    except (OSError, CommandError):
        return False
