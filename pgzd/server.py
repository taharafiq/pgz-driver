"""pgzd.server — the daemon: boot a PgzDriver, serve commands over a socket.

Single-threaded and serial: one connection, one command, one reply.  The game
only advances when a `step` (or an input convenience that steps) arrives, so the
session is fully deterministic.
"""

import os
import socket
import sys
import traceback

from pgzd import protocol


class Server:
    def __init__(self, game_path: str, session: str):
        from pgzd.driver import PgzDriver  # heavy import (pygame) — defer

        self.session = session
        self.game_path = os.path.abspath(game_path)
        self.driver = PgzDriver(self.game_path)
        self._sock_path = protocol.socket_path(session)
        self._running = True

    # ── command handlers ──────────────────────────────────────────────────────

    def _frame_info(self) -> dict:
        w, h = self.driver.size
        return {"frame": self.driver.frame, "width": w, "height": h}

    def dispatch(self, cmd: str, args: dict) -> dict:
        d = self.driver
        if cmd == "status":
            return {"running": True, "session": self.session,
                    "game_path": self.game_path, **self._frame_info()}
        if cmd == "ping":
            return {"running": True}
        if cmd == "stop":
            self._running = False
            return {"stopped": True}
        if cmd == "restart":
            d.restart()
            return self._frame_info()
        if cmd == "step":
            d.step(int(args.get("n", 1)), float(args.get("dt", 1 / 60.0)))
            return self._frame_info()

        # keyboard
        if cmd == "keydown":
            d.key_down(args["key"]);  return self._frame_info()
        if cmd == "keyup":
            d.key_up(args["key"]);    return self._frame_info()
        if cmd == "tap":
            d.tap(args["key"]);       return self._frame_info()
        if cmd == "hold":
            d.hold(args["key"], int(args["frames"]));  return self._frame_info()

        # mouse
        if cmd == "mousemove":
            d.mouse_move(int(args["x"]), int(args["y"]));  return self._frame_info()
        if cmd == "mousedown":
            d.mouse_down(int(args["x"]), int(args["y"]), args.get("button", "left"))
            return self._frame_info()
        if cmd == "mouseup":
            d.mouse_up(int(args["x"]), int(args["y"]), args.get("button", "left"))
            return self._frame_info()
        if cmd == "click":
            d.click(int(args["x"]), int(args["y"]), args.get("button", "left"))
            return self._frame_info()
        if cmd == "drag":
            d.drag(int(args["x1"]), int(args["y1"]), int(args["x2"]), int(args["y2"]),
                   int(args.get("steps", 10)), args.get("button", "left"))
            return self._frame_info()
        if cmd == "scroll":
            d.scroll(int(args["x"]), int(args["y"]), int(args.get("dy", 1)))
            return self._frame_info()

        # visual
        if cmd == "screenshot":
            name = args.get("name") or f"shot_{d.frame:05d}"
            directory = args.get("dir") or protocol.session_dir(self.session)
            path = d.screenshot(os.path.join(directory, f"{name}.png"))
            return {"path": path, **self._frame_info()}
        if cmd == "pixel":
            return {"rgb": list(d.pixel(int(args["x"]), int(args["y"])))}
        if cmd == "find-color":
            region = args.get("region")
            pts = d.find_color(
                tuple(args["color"]),
                tuple(region) if region else None,
                int(args.get("tol", 30)),
                int(args.get("step", 4)),
            )
            return {"count": len(pts), "points": pts[:200]}

        # state
        if cmd == "state":
            return {"repr": repr(d.eval_expr(args["expr"]))}

        raise ValueError(f"unknown command: {cmd!r}")

    # ── serve loop ────────────────────────────────────────────────────────────

    def serve(self) -> None:
        os.makedirs(protocol.session_dir(self.session), exist_ok=True)
        if os.path.exists(self._sock_path):
            os.unlink(self._sock_path)

        srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        srv.bind(self._sock_path)
        srv.listen(8)
        try:
            while self._running:
                conn, _ = srv.accept()
                with conn:
                    try:
                        msg = protocol.recv_message(conn)
                        if msg is None:
                            continue
                        result = self.dispatch(msg.get("cmd", ""), msg.get("args") or {})
                        protocol.send_message(conn, {"ok": True, "result": result})
                    except Exception as exc:  # noqa: BLE001 — report to client
                        protocol.send_message(conn, {
                            "ok": False,
                            "error": f"{type(exc).__name__}: {exc}",
                            "traceback": traceback.format_exc(),
                        })
        finally:
            srv.close()
            if os.path.exists(self._sock_path):
                os.unlink(self._sock_path)


def serve(game_path: str, session: str) -> None:
    """Boot the driver and run the serve loop (blocking)."""
    Server(game_path, session).serve()


def spawn_daemon(game_path: str, session: str) -> None:
    """Fork a detached server process (double-fork + setsid), redirecting its
    stdio to the session log.  Returns in the parent immediately; the caller
    waits for the socket to appear."""
    os.makedirs(protocol.RUNTIME_DIR, exist_ok=True)

    # First fork
    if os.fork() > 0:
        return  # parent returns to caller

    # Child: detach from controlling terminal
    os.setsid()

    # Second fork so the daemon can never reacquire a terminal
    if os.fork() > 0:
        os._exit(0)

    # Grandchild: redirect stdio to the log file
    log = protocol.log_path(session)
    with open(os.devnull) as devnull:
        os.dup2(devnull.fileno(), sys.stdin.fileno())
    logfd = open(log, "ab", buffering=0)
    os.dup2(logfd.fileno(), sys.stdout.fileno())
    os.dup2(logfd.fileno(), sys.stderr.fileno())

    try:
        serve(game_path, session)
    except Exception:
        traceback.print_exc()
        os._exit(1)
    os._exit(0)
