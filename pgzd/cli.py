"""pgzd.cli — `pgz` command-line interface.

Thin client over the daemon (see pgzd.server / pgzd.client), plus the `start`
command which spawns the daemon and waits until its socket is ready.
"""

import argparse
import os
import sys
import time

from pgzd import client, protocol


def _wait_for_socket(session: str, timeout: float = 20.0) -> bool:
    deadline = time.time() + timeout
    path = protocol.socket_path(session)
    while time.time() < deadline:
        if os.path.exists(path) and client.is_running(session):
            return True
        time.sleep(0.05)
    return False


# ── command implementations ───────────────────────────────────────────────────

def cmd_start(a) -> int:
    game_path = os.path.abspath(a.game)
    if not os.path.exists(game_path):
        print(f"error: game not found: {game_path}", file=sys.stderr)
        return 1

    if client.is_running(a.session):
        print(f"error: session {a.session!r} already running "
              f"(use `pgz stop` first)", file=sys.stderr)
        return 1

    from pgzd import server

    if a.foreground:
        server.serve(game_path, a.session)
        return 0

    server.spawn_daemon(game_path, a.session)
    if not _wait_for_socket(a.session):
        print(f"error: daemon failed to start; see {protocol.log_path(a.session)}",
              file=sys.stderr)
        return 1
    info = client.request(a.session, "status")
    print(f"started session {a.session!r}: {os.path.basename(game_path)} "
          f"{info['width']}x{info['height']}")
    return 0


def cmd_stop(a) -> int:
    if not client.is_running(a.session):
        print(f"session {a.session!r} not running")
        return 0
    try:
        client.request(a.session, "stop")
    except client.DaemonNotRunning:
        pass
    print(f"stopped session {a.session!r}")
    return 0


def cmd_status(a) -> int:
    if not client.is_running(a.session):
        print(f"session {a.session!r}: not running")
        return 1
    info = client.request(a.session, "status")
    print(f"session {a.session!r}: running")
    print(f"  game:  {info['game_path']}")
    print(f"  frame: {info['frame']}")
    print(f"  size:  {info['width']}x{info['height']}")
    return 0


def _print_frame(info) -> None:
    print(f"frame={info['frame']} {info['width']}x{info['height']}")


def cmd_restart(a) -> int:
    _print_frame(client.request(a.session, "restart"))
    return 0


def cmd_step(a) -> int:
    _print_frame(client.request(a.session, "step", {"n": a.n, "dt": a.dt}))
    return 0


def cmd_key(a, which) -> int:
    _print_frame(client.request(a.session, which, {"key": a.key}))
    return 0


def cmd_tap(a) -> int:
    _print_frame(client.request(a.session, "tap", {"key": a.key}))
    return 0


def cmd_hold(a) -> int:
    _print_frame(client.request(a.session, "hold", {"key": a.key, "frames": a.frames}))
    return 0


def cmd_mousemove(a) -> int:
    _print_frame(client.request(a.session, "mousemove", {"x": a.x, "y": a.y}))
    return 0


def cmd_mousebtn(a, which) -> int:
    _print_frame(client.request(a.session, which,
                                {"x": a.x, "y": a.y, "button": a.button}))
    return 0


def cmd_drag(a) -> int:
    _print_frame(client.request(a.session, "drag", {
        "x1": a.x1, "y1": a.y1, "x2": a.x2, "y2": a.y2,
        "steps": a.steps, "button": a.button}))
    return 0


def cmd_scroll(a) -> int:
    _print_frame(client.request(a.session, "scroll", {"x": a.x, "y": a.y, "dy": a.dy}))
    return 0


def cmd_screenshot(a) -> int:
    res = client.request(a.session, "screenshot", {"name": a.name, "dir": a.dir})
    print(res["path"])
    return 0


def cmd_pixel(a) -> int:
    r, g, b = client.request(a.session, "pixel", {"x": a.x, "y": a.y})["rgb"]
    print(f"({r}, {g}, {b})")
    return 0


def cmd_find_color(a) -> int:
    region = None
    if a.region:
        region = [int(v) for v in a.region.split(",")]
    res = client.request(a.session, "find-color", {
        "color": [a.r, a.g, a.b], "region": region,
        "tol": a.tol, "step": a.step})
    print(f"{res['count']} match(es)")
    for x, y in res["points"]:
        print(f"  ({x}, {y})")
    return 0


def cmd_state(a) -> int:
    print(client.request(a.session, "state", {"expr": a.expr})["repr"])
    return 0


# ── argument parser ───────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="pgz", description="Headless Pygame Zero driver for agents.")
    p.add_argument("--session", default="default",
                   help="session name (default: 'default')")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("start", help="boot a game daemon")
    sp.add_argument("game", help="path to the pgzero game .py")
    sp.add_argument("--foreground", action="store_true",
                    help="run the server inline (for debugging)")
    sp.set_defaults(func=cmd_start)

    sub.add_parser("stop", help="shut the daemon down").set_defaults(func=cmd_stop)
    sub.add_parser("status", help="show daemon status").set_defaults(func=cmd_status)
    sub.add_parser("restart", help="reboot the game fresh").set_defaults(func=cmd_restart)

    sp = sub.add_parser("step", help="advance N frames")
    sp.add_argument("n", type=int, nargs="?", default=1)
    sp.add_argument("--dt", type=float, default=1 / 60.0)
    sp.set_defaults(func=cmd_step)

    # keyboard
    for name in ("keydown", "keyup"):
        sp = sub.add_parser(name, help=f"{name} a key (held until released)")
        sp.add_argument("key")
        sp.set_defaults(func=lambda a, w=name: cmd_key(a, w))

    sp = sub.add_parser("tap", help="press+release a key over one frame")
    sp.add_argument("key")
    sp.set_defaults(func=cmd_tap)

    sp = sub.add_parser("hold", help="hold a key down for N frames")
    sp.add_argument("key")
    sp.add_argument("frames", type=int)
    sp.set_defaults(func=cmd_hold)

    # mouse
    sp = sub.add_parser("mousemove", help="move the mouse to (x, y)")
    sp.add_argument("x", type=int)
    sp.add_argument("y", type=int)
    sp.set_defaults(func=cmd_mousemove)

    for name in ("mousedown", "mouseup", "click"):
        sp = sub.add_parser(name, help=f"{name} at (x, y)")
        sp.add_argument("x", type=int)
        sp.add_argument("y", type=int)
        sp.add_argument("--button", default="left", choices=["left", "middle", "right"])
        sp.set_defaults(func=lambda a, w=name: cmd_mousebtn(a, w))

    sp = sub.add_parser("drag", help="drag from (x1,y1) to (x2,y2)")
    for arg in ("x1", "y1", "x2", "y2"):
        sp.add_argument(arg, type=int)
    sp.add_argument("--steps", type=int, default=10)
    sp.add_argument("--button", default="left", choices=["left", "middle", "right"])
    sp.set_defaults(func=cmd_drag)

    sp = sub.add_parser("scroll", help="scroll the wheel at (x, y)")
    sp.add_argument("x", type=int)
    sp.add_argument("y", type=int)
    sp.add_argument("--dy", type=int, default=1, help="positive = up/away")
    sp.set_defaults(func=cmd_scroll)

    # visual
    sp = sub.add_parser("screenshot", help="save a PNG and print its path")
    sp.add_argument("name", nargs="?", default=None,
                    help="file stem (default: shot_<frame>)")
    sp.add_argument("--dir", default=None, help="output directory")
    sp.set_defaults(func=cmd_screenshot)

    sp = sub.add_parser("pixel", help="print the (r,g,b) at (x, y)")
    sp.add_argument("x", type=int)
    sp.add_argument("y", type=int)
    sp.set_defaults(func=cmd_pixel)

    sp = sub.add_parser("find-color", help="find pixels matching a colour")
    for arg in ("r", "g", "b"):
        sp.add_argument(arg, type=int)
    sp.add_argument("--region", help="x0,y0,x1,y1")
    sp.add_argument("--tol", type=int, default=30)
    sp.add_argument("--step", type=int, default=4)
    sp.set_defaults(func=cmd_find_color)

    # state
    sp = sub.add_parser("state", help="eval an expression against game globals")
    sp.add_argument("expr", help="e.g. score, screen_state, 'len(snake)'")
    sp.set_defaults(func=cmd_state)

    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except client.DaemonNotRunning as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except client.CommandError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
