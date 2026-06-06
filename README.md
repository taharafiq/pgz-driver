# pgz-driver

Drive any [Pygame Zero](https://pygame-zero.readthedocs.io/) game **headlessly** from the command line — built for AI agents (e.g. Claude Code) that interact one shell command at a time.

A background **daemon** keeps the game alive in a single process; the `pgz` CLI is a thin client that injects keyboard/mouse input, advances time, and captures screenshots so the agent can *see* and *play* the game.

```bash
pgz start games/snake/snake.py     # boot the game (no window)
pgz tap SPACE                      # press a key
pgz hold RIGHT 10                  # hold a key for 10 frames
pgz screenshot menu                # → /tmp/pgzd/default/menu.png
pgz state score                    # read a game global → 0
pgz stop
```

## How it works

A Pygame Zero game needs to stay running in one process to keep its state, but an agent issues **separate** shell commands. So `pgz` is split in two:

```
 agent (one bash command at a time)        daemon (one per session)
 ┌──────────────────────────────┐   JSON   ┌────────────────────────────┐
 │ pgz <subcommand>  (client)   │ ───────▶ │ serial command loop        │
 │                              │ ◀─────── │   PgzDriver → live game     │
 └──────────────────────────────┘  socket  └────────────────────────────┘
              Unix socket: /tmp/pgzd/<session>.sock
```

Two design choices make it predictable for an agent:

- **Agent-stepped time (fixed `dt`).** The game never advances on its own. It only moves forward when you run `pgz step` (or a convenience like `tap`/`hold`/`click` that steps for you). Each frame advances `1/60s` of game time by default, so runs are fully deterministic and reproducible.
- **Input is queued, time is separate.** Input commands *queue* a pygame event; `step` *drains* the queue once (firing handlers, updating key/mouse state) and then ticks the game. This is what lets a key stay **held** across many frames:

  ```bash
  pgz keydown LEFT      # queue the press
  pgz step 30           # held for all 30 frames (continuous movement)
  pgz keyup LEFT        # release
  ```

## Install

Requires Python ≥ 3.12. Using [uv](https://docs.astral.sh/uv/):

```bash
uv sync                       # installs deps + the `pgz` entry point
uv run pgz start <game.py>    # run via uv …
# or activate the venv and call `pgz` directly
```

## Command reference

Every command takes an optional `--session NAME` (default `default`) so you can run multiple games at once.

### Lifecycle

| Command | Description |
| --- | --- |
| `pgz start <game.py>` | Boot a detached daemon for the game; returns once it's ready. `--foreground` runs it inline for debugging. |
| `pgz stop` | Shut the daemon down. |
| `pgz status` | Report whether the session is running, plus game path, frame count, and size. |
| `pgz restart` | Re-boot the game from scratch (same daemon), resetting all state. |

### Time

| Command | Description |
| --- | --- |
| `pgz step [N=1] [--dt 0.0166]` | Advance `N` frames at `dt` seconds each. The only thing that moves game time forward. |

### Keyboard

Keys are named: `SPACE`, `LEFT`, `RIGHT`, `UP`, `DOWN`, `W`, `A`, `S`, `D`, `M`, … (any pygame `K_*` name, case-insensitive).

| Command | Description |
| --- | --- |
| `pgz keydown <KEY>` | Press and **hold** a key (until released). |
| `pgz keyup <KEY>` | Release a held key. |
| `pgz tap <KEY>` | Press + release around one frame — fires `on_key_down` (menu start, snake turns). |
| `pgz hold <KEY> <N>` | Hold a key down for `N` frames, then release — for continuous movement. |

### Mouse

| Command | Description |
| --- | --- |
| `pgz mousemove <X> <Y>` | Move the cursor. |
| `pgz click <X> <Y> [--button left\|middle\|right]` | Click at a point. |
| `pgz mousedown / mouseup <X> <Y> [--button …]` | Separate press / release (for click-and-hold). |
| `pgz drag <X1> <Y1> <X2> <Y2> [--steps 10] [--button …]` | Press, move across `--steps` frames, release. |
| `pgz scroll <X> <Y> [--dy 1]` | Mouse-wheel scroll (positive `--dy` = up/away). |

### Visual inspection

| Command | Description |
| --- | --- |
| `pgz screenshot [name] [--dir DIR]` | Render the current frame to PNG and **print its absolute path** (pass it to your Read tool). Defaults to `/tmp/pgzd/<session>/<name>.png`. |
| `pgz pixel <X> <Y>` | Print the `(r, g, b)` at a pixel. |
| `pgz find-color <R> <G> <B> [--region x0,y0,x1,y1] [--tol 30] [--step 4]` | Print pixel positions matching a colour — useful for locating objects. |

### State introspection

| Command | Description |
| --- | --- |
| `pgz state <expr>` | Evaluate an expression against the game's globals and print its `repr`. E.g. `pgz state score`, `pgz state screen_state`, `pgz state 'len(snake)'`. |

Screenshots are the primary, game-agnostic interface; `state` is an optional shortcut when you want to read internals directly.

## Example: play a few moves of Snake

```bash
pgz start games/snake/snake.py
pgz screenshot menu            # inspect the title screen
pgz tap SPACE                  # start the game
pgz step 5
pgz hold RIGHT 10              # steer right
pgz screenshot game
pgz state direction            # (1, 0)
pgz stop
```

## Notes & limitations

- **Headless rendering** uses `SDL_VIDEODRIVER=dummy`: draw calls write real pixels to an in-memory surface (so screenshots are accurate), but there is no window.
- Under the dummy driver, `pygame.mouse.get_pos()` may not reflect injected motion. Mouse input is delivered via the dispatched event's `pos`, which covers the standard `on_mouse_down` / `on_mouse_up` / `on_mouse_move` handlers.
- Runtime state (sockets, logs, screenshots) lives under `/tmp/pgzd/`.

## Project layout

```
pgzd/
  driver.py     # PgzDriver: headless boot, step, input injection, capture
  server.py     # the daemon (serial command loop) + process spawning
  client.py     # connect + send one command
  protocol.py   # Unix socket path + newline-JSON framing
  cli.py        # `pgz` argparse entry point
games/          # sample games (snake, collect-treasure) + shared assets
```
