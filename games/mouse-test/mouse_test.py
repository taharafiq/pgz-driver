"""
Mouse Test — a tiny Pygame Zero game that visualises every mouse interaction,
so the pgz driver's mouse support can be verified end-to-end.

What it shows:
  * a white crosshair tracking the live cursor position    (on_mouse_move)
  * a coloured dot at every click — green/red/blue for L/R/M (on_mouse_down)
  * a yellow trail drawn while dragging                      (move + down/up)
  * a scroll bar + counter driven by the mouse wheel         (WHEEL_UP/DOWN)
  * a HUD with per-button click counts and live state

All of this is also exposed as plain module globals (cursor, left_clicks,
scroll_value, dots, drag_path, …) so it can be checked with `pgz state`.
"""

import pgzrun

TITLE = "Mouse Test"
WIDTH = 640
HEIGHT = 480

# ── colours ───────────────────────────────────────────────────────────────────
BG = (20, 22, 30)
PANEL = (32, 36, 48)
WHITE = (235, 238, 245)
GREEN = (80, 210, 110)
RED = (230, 80, 80)
BLUE = (90, 150, 240)
YELLOW = (240, 210, 90)
GRAY = (120, 128, 140)

HUD_H = 96
BUTTON_COLOR = {"left": GREEN, "right": RED, "middle": BLUE}

# ── state (also read via `pgz state ...`) ─────────────────────────────────────
cursor = (WIDTH // 2, HEIGHT // 2)
last_button = "none"
left_clicks = 0
right_clicks = 0
middle_clicks = 0
scroll_value = 0
dragging = False
drag_path = []
drag_count = 0
dots = []          # list of (x, y, (r, g, b))


# ── input handlers ────────────────────────────────────────────────────────────

def on_mouse_down(pos, button):
    global last_button, left_clicks, right_clicks, middle_clicks
    global scroll_value, dragging, drag_path

    if button == mouse.WHEEL_UP:
        scroll_value += 1
        last_button = "wheel_up"
        return
    if button == mouse.WHEEL_DOWN:
        scroll_value -= 1
        last_button = "wheel_down"
        return

    if button == mouse.LEFT:
        left_clicks += 1
        last_button = "left"
    elif button == mouse.RIGHT:
        right_clicks += 1
        last_button = "right"
    elif button == mouse.MIDDLE:
        middle_clicks += 1
        last_button = "middle"

    dots.append((pos[0], pos[1], BUTTON_COLOR.get(last_button, WHITE)))
    dragging = True
    drag_path = [pos]


def on_mouse_up(pos, button):
    global dragging, drag_count
    if button in (mouse.WHEEL_UP, mouse.WHEEL_DOWN):
        return
    if dragging and len(drag_path) > 1:
        drag_count += 1
    dragging = False


def on_mouse_move(pos, rel, buttons):
    global cursor
    cursor = pos
    if dragging:
        drag_path.append(pos)


# ── rendering ─────────────────────────────────────────────────────────────────

def draw():
    screen.fill(BG)
    screen.draw.filled_rect(Rect(0, 0, WIDTH, HUD_H), PANEL)

    # dots from clicks
    for x, y, col in dots:
        screen.draw.filled_circle((x, y), 8, col)
        screen.draw.circle((x, y), 8, WHITE)

    # drag trail
    if len(drag_path) > 1:
        for a, b in zip(drag_path, drag_path[1:]):
            screen.draw.line(a, b, YELLOW)

    # scroll bar (grows up = positive, down = negative)
    bar_x = WIDTH - 34
    base = HEIGHT - 30
    h = max(-120, min(120, scroll_value * 12))
    if h > 0:
        screen.draw.filled_rect(Rect(bar_x - 10, base - h, 20, h), GREEN)
    elif h < 0:
        screen.draw.filled_rect(Rect(bar_x - 10, base, 20, -h), RED)
    screen.draw.line((bar_x - 16, base), (bar_x + 16, base), GRAY)
    screen.draw.text("scroll", midtop=(bar_x, base + 6), fontsize=18, color=GRAY)

    # crosshair at the cursor
    cx, cy = cursor
    screen.draw.line((cx - 12, cy), (cx + 12, cy), WHITE)
    screen.draw.line((cx, cy - 12), (cx, cy + 12), WHITE)
    screen.draw.circle((cx, cy), 6, WHITE)

    # HUD
    screen.draw.text(f"cursor: {cursor}    last: {last_button}",
                     topleft=(12, 10), fontsize=26, color=WHITE)
    screen.draw.text(
        f"L:{left_clicks}  R:{right_clicks}  M:{middle_clicks}   "
        f"scroll:{scroll_value}   drags:{drag_count}",
        topleft=(12, 42), fontsize=26, color=YELLOW)
    screen.draw.text(
        f"dots:{len(dots)}   drag_path:{len(drag_path)}   dragging:{dragging}",
        topleft=(12, 72), fontsize=20, color=GRAY)


pgzrun.go()
