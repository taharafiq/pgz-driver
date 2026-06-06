"""
pgzd.driver — Headless Pygame Zero game driver.

Loads and runs any pgzero game without a display window.  All draw calls write
real pixels to an in-memory surface that can be sampled and saved as PNG.
Input is injected via pygame's event queue — the same path a physical keyboard
or mouse uses.

Time model: agent-stepped with fixed dt.  The game never advances on its own;
`step(n)` is the only thing that ticks `update(dt)` / `draw()`.

Event vs. time separation: input methods (`key_down`, `mouse_down`, …) *post*
pygame events into a pending queue but do not advance time.  `step()` drains the
queue once — dispatching handlers and updating pgzero `keyboard` / mouse state —
then ticks update+draw `n` times.  This lets a key stay held across many frames:

    d.key_down("LEFT"); d.step(30); d.key_up("LEFT")   # held for 30 frames

Implementation notes
--------------------
* SDL_VIDEODRIVER=dummy: flip() is a no-op but draw calls write real pixels to
  the display Surface.  SDL_VIDEODRIVER=offscreen requires OpenGL/GLES which is
  unavailable on this macOS build.

* pgzero.__file__ bug: prepare_mod() injects its builtins via
  mod.__dict__.update(builtins.__dict__), which overwrites mod.__file__ with the
  pgzero builtins path.  We restore mod.__file__ to the game path after
  prepare_mod so __file__-relative paths inside the game work correctly.

* The driver replicates pgzero's mainloop() using the same PGZeroGame internals
  (dispatch_event, keyboard._press/_release, pgzclock.tick) so event handling is
  identical to a real run.
"""

import os
import sys
import types

# ── env vars must be set before pygame is imported ────────────────────────────
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame  # noqa: E402  (import after env vars)

# Build a key-name → pygame-constant map once at import time
_KEY_MAP: dict[str, int] = {
    name[2:]: getattr(pygame, name)          # "K_SPACE" → ("SPACE", K_SPACE)
    for name in dir(pygame)
    if name.startswith("K_")
}

_MOUSE_BUTTONS = {"left": 1, "middle": 2, "right": 3}

_DEFAULT_DT = 1 / 60.0


class PgzDriver:
    """Drive a Pygame Zero game headlessly.

    Boots on construction.  Not a context manager — the owning daemon keeps it
    alive for the whole session.
    """

    def __init__(self, game_path: str):
        self._game_path = os.path.abspath(game_path)
        self._mod = None
        self._game_obj = None
        self._update_fn = None
        self._draw_fn = None
        self._pgzclock = None
        self._surf: pygame.Surface | None = None
        self._pending: list[pygame.event.Event] = []
        self._frame = 0
        self._boot()

    # ── lifecycle ─────────────────────────────────────────────────────────────

    def restart(self) -> None:
        """Re-execute the game module from scratch, resetting all state."""
        self._pending.clear()
        self._frame = 0
        self._boot()

    @property
    def frame(self) -> int:
        return self._frame

    @property
    def size(self) -> tuple[int, int]:
        return self._surf.get_size()

    @property
    def game_path(self) -> str:
        return self._game_path

    # ── time ──────────────────────────────────────────────────────────────────

    def step(self, n: int = 1, dt: float = _DEFAULT_DT) -> pygame.Surface:
        """Drain pending input events, then advance `n` frames at fixed `dt`.

        Returns a copy of the final rendered surface.
        """
        self._drain_events()
        for _ in range(max(0, n)):
            self._pgzclock.clock.tick(dt)
            if self._update_fn:
                self._update_fn(dt)
            self._frame += 1
        self._render()
        return self._surf

    def apply(self) -> pygame.Surface:
        """Apply queued input immediately and refresh the frame, *without*
        advancing game time.

        Lets a standalone `mousemove` / `keydown` / `mousedown` take effect — its
        handler fires and game state updates — so the next screenshot or state
        read is current.  A held key stays held (its release isn't queued yet).
        """
        self._drain_events()
        self._render()
        return self._surf

    def _render(self) -> None:
        """Draw the current game state to the surface (no update tick)."""
        self._draw_fn()
        pygame.display.flip()
        self._capture()

    def _drain_events(self) -> None:
        """Move queued events into pgzero: update keyboard/mouse state and fire
        handlers."""
        # Push our pending events through the real pygame queue so any code that
        # calls pygame.event.get() sees them too, then process identically to
        # pgzero's mainloop.
        for evt in self._pending:
            pygame.event.post(evt)
        self._pending.clear()

        for event in pygame.event.get():
            if event.type == pygame.KEYDOWN:
                self._game_obj.keyboard._press(event.key)
            elif event.type == pygame.KEYUP:
                self._game_obj.keyboard._release(event.key)
            self._game_obj.dispatch_event(event)

    # ── keyboard input ────────────────────────────────────────────────────────

    def key_down(self, key: "int | str") -> None:
        """Queue a KEYDOWN.  The key stays held until `key_up`."""
        self._pending.append(pygame.event.Event(
            pygame.KEYDOWN, key=self._resolve_key(key),
            unicode="", mod=0, scancode=0,
        ))

    def key_up(self, key: "int | str") -> None:
        """Queue a KEYUP, releasing a held key."""
        self._pending.append(pygame.event.Event(
            pygame.KEYUP, key=self._resolve_key(key),
            unicode="", mod=0, scancode=0,
        ))

    def tap(self, key: "int | str", dt: float = _DEFAULT_DT) -> pygame.Surface:
        """Press and release a key within a single frame.

        Enough to fire `on_key_down` handlers (menu start, snake turns).  Both
        events are drained in the same frame, so no key stays held afterward.
        """
        self.key_down(key)
        self.key_up(key)
        return self.step(1, dt)

    def hold(self, key: "int | str", frames: int,
             dt: float = _DEFAULT_DT) -> pygame.Surface:
        """Hold a key down for `frames` frames, then release it.

        Required for games that poll `keyboard.left` etc. for continuous motion.
        The release is flushed (without advancing time) so state is clean after.
        """
        self.key_down(key)
        self.step(frames, dt)
        self.key_up(key)
        return self.step(0, dt)   # flush the release without advancing time

    # ── mouse input ───────────────────────────────────────────────────────────

    def mouse_move(self, x: int, y: int) -> None:
        self._pending.append(pygame.event.Event(
            pygame.MOUSEMOTION, pos=(x, y), rel=(0, 0), buttons=(0, 0, 0),
        ))

    def mouse_down(self, x: int, y: int, button: str = "left") -> None:
        self._pending.append(pygame.event.Event(
            pygame.MOUSEBUTTONDOWN, pos=(x, y), button=self._resolve_button(button),
        ))

    def mouse_up(self, x: int, y: int, button: str = "left") -> None:
        self._pending.append(pygame.event.Event(
            pygame.MOUSEBUTTONUP, pos=(x, y), button=self._resolve_button(button),
        ))

    def click(self, x: int, y: int, button: str = "left",
              dt: float = _DEFAULT_DT) -> pygame.Surface:
        self.mouse_move(x, y)
        self.mouse_down(x, y, button)
        self.step(1, dt)
        self.mouse_up(x, y, button)
        return self.step(0, dt)   # flush the release without advancing time

    def drag(self, x1: int, y1: int, x2: int, y2: int, steps: int = 10,
             button: str = "left", dt: float = _DEFAULT_DT) -> pygame.Surface:
        steps = max(1, steps)
        self.mouse_move(x1, y1)
        self.mouse_down(x1, y1, button)
        for i in range(1, steps + 1):
            t = i / steps
            self.mouse_move(round(x1 + (x2 - x1) * t), round(y1 + (y2 - y1) * t))
            self.step(1, dt)
        self.mouse_up(x2, y2, button)
        return self.step(1, dt)

    def scroll(self, x: int, y: int, dy: int = 1,
               dt: float = _DEFAULT_DT) -> pygame.Surface:
        """Inject a mouse-wheel scroll (positive dy = up/away from user)."""
        self.mouse_move(x, y)
        self._pending.append(pygame.event.Event(
            pygame.MOUSEWHEEL, x=0, y=dy, flipped=False,
        ))
        # Also emit legacy button-4/5 events for games that read them.
        button = 4 if dy > 0 else 5
        for _ in range(abs(dy)):
            self._pending.append(pygame.event.Event(
                pygame.MOUSEBUTTONDOWN, pos=(x, y), button=button))
            self._pending.append(pygame.event.Event(
                pygame.MOUSEBUTTONUP, pos=(x, y), button=button))
        return self.step(1, dt)

    # ── visual inspection ─────────────────────────────────────────────────────

    def screenshot(self, path: str) -> str:
        """Save the current frame as PNG at `path`.  Returns the absolute path."""
        path = os.path.abspath(path)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        pygame.image.save(self._surf, path)
        return path

    def pixel(self, x: int, y: int) -> tuple[int, int, int]:
        """Return ``(r, g, b)`` of the pixel at ``(x, y)``."""
        return tuple(self._surf.get_at((x, y))[:3])

    def find_color(
        self,
        color: tuple[int, int, int],
        region: tuple[int, int, int, int] | None = None,
        tolerance: int = 30,
        step: int = 4,
    ) -> list[tuple[int, int]]:
        """Return (x, y) positions matching *color* within *region* (x0,y0,x1,y1).

        Samples every *step* pixels.  Useful for locating objects by colour.
        """
        w, h = self._surf.get_size()
        x0, y0, x1, y1 = region if region else (0, 0, w, h)
        tr, tg, tb = color
        hits = []
        for x in range(x0, x1, step):
            for y in range(y0, y1, step):
                r, g, b = self._surf.get_at((x, y))[:3]
                if abs(r - tr) + abs(g - tg) + abs(b - tb) < tolerance * 3:
                    hits.append((x, y))
        return hits

    def surface(self) -> pygame.Surface:
        """Return a copy of the last rendered surface."""
        return self._surf.copy()

    # ── state introspection ───────────────────────────────────────────────────

    def eval_expr(self, expr: str):
        """Evaluate *expr* against the live game module namespace (read-only use).

        Examples: ``score``, ``screen_state``, ``len(snake)``.
        """
        return eval(expr, self._mod.__dict__)  # noqa: S307 (intended introspection)

    @property
    def mod(self):
        """The live game module — read any game global directly."""
        return self._mod

    # ── private helpers ───────────────────────────────────────────────────────

    def _boot(self) -> None:
        """Initialise pygame headlessly and exec the game as __main__."""
        pygame.init()

        # Create a fresh __main__ module to hold the game's globals
        mod = types.ModuleType("__main__")
        mod.__file__ = self._game_path
        mod.__name__ = "__main__"
        sys.modules["__main__"] = mod

        # Intercept pgzrun.go — we drive the loop ourselves
        _pgzrun = types.ModuleType("pgzrun")
        _pgzrun.go = lambda: None
        sys.modules["pgzrun"] = _pgzrun

        # Inject pgzero builtins (screen, Rect, keys, …) into the game module.
        # prepare_mod() also calls pygame.display.set_mode((100,100)) — fine with
        # the dummy driver; reinit_screen() resizes it below.
        # prepare_mod() overwrites mod.__file__ via mod.__dict__.update(...); we
        # restore it so __file__-relative paths in the game resolve correctly.
        from pgzero.runner import prepare_mod
        from pgzero.game import PGZeroGame
        import pgzero.clock as _pgzclock

        prepare_mod(mod)
        mod.__file__ = self._game_path   # restore after prepare_mod clobbers it

        # Execute the game file — all module-level code runs now
        with open(self._game_path) as f:
            exec(compile(f.read(), self._game_path, "exec"), mod.__dict__)

        # Build the PGZeroGame wrapper so we get identical event dispatch
        game_obj = PGZeroGame(mod)
        game_obj.reinit_screen()   # sets display size from mod.WIDTH / mod.HEIGHT
        game_obj.load_handlers()

        self._mod = mod
        self._game_obj = game_obj
        self._update_fn = game_obj.get_update_func()
        self._draw_fn = game_obj.get_draw_func()
        self._pgzclock = _pgzclock

        # Render the first frame so self._surf is always valid
        self._draw_fn()
        pygame.display.flip()
        self._capture()

    def _capture(self) -> None:
        self._surf = pygame.display.get_surface().copy()

    def _resolve_key(self, key: "int | str") -> int:
        if isinstance(key, str):
            # pygame letter keys are K_a…K_z (lowercase); special keys K_SPACE etc.
            # Try original → upper → lower so both "SPACE" and "m"/"M" work.
            k = (_KEY_MAP.get(key) or _KEY_MAP.get(key.upper())
                 or _KEY_MAP.get(key.lower()))
            if k is None:
                raise ValueError(
                    f"Unknown key {key!r}. Try 'SPACE', 'UP', 'DOWN', 'LEFT', "
                    f"'RIGHT', 'W', 'A', 'S', 'D', 'M', …"
                )
            return k
        return key

    @staticmethod
    def _resolve_button(button: "int | str") -> int:
        if isinstance(button, int):
            return button
        b = _MOUSE_BUTTONS.get(button.lower())
        if b is None:
            raise ValueError(f"Unknown mouse button {button!r}. Use left/middle/right.")
        return b
