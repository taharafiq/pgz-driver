import os as _os
_GAME_DIR = _os.path.dirname(_os.path.abspath(__file__))  # must be before pgzrun overwrites __file__

import pgzrun
import random
import json
import os

TITLE = "Snake"
WIDTH = 600
HEIGHT = 650

GRID_SIZE = 20
GRID_WIDTH = WIDTH // GRID_SIZE        # 30 columns
GRID_HEIGHT = (HEIGHT - 50) // GRID_SIZE  # 30 rows, 50px reserved for score bar

# Colors
BLACK   = (0,   0,   0)
DARK    = (18,  18,  18)
WHITE   = (255, 255, 255)
GRAY    = (120, 120, 120)
GREEN   = (50,  200, 80)
DK_GRN  = (30,  120, 50)
RED     = (220, 60,  60)
YELLOW  = (255, 215, 0)
PANEL   = (28,  28,  28)
CELL_BG = (22,  22,  22)

HIGH_SCORE_FILE = os.path.join(_GAME_DIR, "highscore.json")

# ── persistent state ──────────────────────────────────────────────────────────

def load_high_score():
    if os.path.exists(HIGH_SCORE_FILE):
        with open(HIGH_SCORE_FILE) as f:
            return json.load(f).get("high_score", 0)
    return 0

def save_high_score(value):
    with open(HIGH_SCORE_FILE, "w") as f:
        json.dump({"high_score": value}, f)

# ── game state ────────────────────────────────────────────────────────────────

screen_state = "menu"   # "menu" | "game" | "game_over"

snake       = []
direction   = (1, 0)
next_dir    = (1, 0)
food        = (0, 0)
score       = 0
high_score  = load_high_score()
move_timer  = 0.0
MOVE_SPEED  = 0.13      # seconds per step; lower = faster

# ── helpers ───────────────────────────────────────────────────────────────────

def spawn_food():
    global food
    occupied = set(snake)
    while True:
        pos = (random.randint(0, GRID_WIDTH - 1), random.randint(0, GRID_HEIGHT - 1))
        if pos not in occupied:
            food = pos
            return

def init_game():
    global snake, direction, next_dir, score, move_timer
    cx, cy = GRID_WIDTH // 2, GRID_HEIGHT // 2
    snake     = [(cx, cy), (cx - 1, cy), (cx - 2, cy)]
    direction = (1, 0)
    next_dir  = (1, 0)
    score     = 0
    move_timer = 0.0
    spawn_food()

def grid_rect(gx, gy, inset=1):
    return Rect(
        gx * GRID_SIZE + inset,
        gy * GRID_SIZE + 50 + inset,
        GRID_SIZE - inset * 2,
        GRID_SIZE - inset * 2,
    )

# ── draw ──────────────────────────────────────────────────────────────────────

def draw():
    if screen_state == "menu":
        _draw_menu()
    elif screen_state == "game":
        _draw_game()
    elif screen_state == "game_over":
        _draw_game_over()

def _draw_menu():
    screen.fill(DARK)

    # decorative snake in background
    for i, (gx, gy) in enumerate(_demo_snake()):
        alpha_color = DK_GRN if i > 0 else GREEN
        screen.draw.filled_rect(grid_rect(gx, gy, inset=2), alpha_color)

    # title
    screen.draw.text(
        "SNAKE",
        center=(WIDTH // 2, HEIGHT // 4),
        fontsize=90,
        color=GREEN,
        shadow=(2, 2),
        scolor=DK_GRN,
    )

    # high score badge
    screen.draw.filled_rect(Rect(WIDTH // 2 - 110, HEIGHT // 2 - 18, 220, 36), PANEL)
    screen.draw.text(
        f"High Score: {high_score}",
        center=(WIDTH // 2, HEIGHT // 2),
        fontsize=26,
        color=YELLOW,
    )

    # instructions
    screen.draw.text(
        "SPACE  –  Play",
        center=(WIDTH // 2, HEIGHT * 2 // 3),
        fontsize=30,
        color=WHITE,
    )
    screen.draw.text(
        "Q  –  Quit",
        center=(WIDTH // 2, HEIGHT * 2 // 3 + 44),
        fontsize=22,
        color=GRAY,
    )

def _draw_game():
    screen.fill(BLACK)

    # score bar
    screen.draw.filled_rect(Rect(0, 0, WIDTH, 50), PANEL)
    screen.draw.text(f"Score  {score}", (14, 14), fontsize=24, color=WHITE)
    screen.draw.text(f"Best  {high_score}", (WIDTH - 160, 14), fontsize=24, color=YELLOW)

    # grid cells
    for gx in range(GRID_WIDTH):
        for gy in range(GRID_HEIGHT):
            screen.draw.filled_rect(grid_rect(gx, gy, inset=0), CELL_BG)

    # food
    fx, fy = food
    screen.draw.filled_rect(grid_rect(fx, fy, inset=3), RED)

    # snake
    for i, (gx, gy) in enumerate(snake):
        color = GREEN if i == 0 else DK_GRN
        screen.draw.filled_rect(grid_rect(gx, gy, inset=1), color)

def _draw_game_over():
    screen.fill(DARK)

    screen.draw.text(
        "GAME OVER",
        center=(WIDTH // 2, HEIGHT // 4),
        fontsize=72,
        color=RED,
        shadow=(2, 2),
        scolor=(100, 0, 0),
    )

    new_best = score >= high_score and score > 0
    score_color = YELLOW if new_best else WHITE
    label = "New Best!" if new_best else f"Best  {high_score}"

    screen.draw.text(
        f"Score  {score}",
        center=(WIDTH // 2, HEIGHT // 2 - 30),
        fontsize=42,
        color=score_color,
    )
    screen.draw.text(
        label,
        center=(WIDTH // 2, HEIGHT // 2 + 24),
        fontsize=26,
        color=YELLOW,
    )

    screen.draw.text(
        "SPACE  –  Play Again",
        center=(WIDTH // 2, HEIGHT * 3 // 4),
        fontsize=28,
        color=GREEN,
    )
    screen.draw.text(
        "M  –  Menu",
        center=(WIDTH // 2, HEIGHT * 3 // 4 + 42),
        fontsize=22,
        color=GRAY,
    )

# ── update ────────────────────────────────────────────────────────────────────

def update(dt):
    global screen_state, move_timer, direction, score, high_score

    if screen_state != "game":
        return

    move_timer += dt
    if move_timer < MOVE_SPEED:
        return
    move_timer = 0.0

    direction = next_dir
    hx, hy   = snake[0]
    new_head  = (hx + direction[0], hy + direction[1])

    # wall collision
    if not (0 <= new_head[0] < GRID_WIDTH and 0 <= new_head[1] < GRID_HEIGHT):
        _end_game()
        return

    # self collision
    if new_head in snake:
        _end_game()
        return

    snake.insert(0, new_head)

    if new_head == food:
        score += 10
        if score > high_score:
            high_score = score
            save_high_score(high_score)
        spawn_food()
    else:
        snake.pop()

def _end_game():
    global screen_state
    screen_state = "game_over"

# ── input ─────────────────────────────────────────────────────────────────────

def on_key_down(key):
    global screen_state, next_dir

    if screen_state == "menu":
        if key == keys.SPACE:
            init_game()
            screen_state = "game"
        elif key == keys.Q:
            exit()

    elif screen_state == "game":
        if   key == keys.UP    and direction != (0,  1): next_dir = (0, -1)
        elif key == keys.DOWN  and direction != (0, -1): next_dir = (0,  1)
        elif key == keys.LEFT  and direction != (1,  0): next_dir = (-1, 0)
        elif key == keys.RIGHT and direction != (-1, 0): next_dir = (1,  0)
        # WASD aliases
        elif key == keys.W and direction != (0,  1): next_dir = (0, -1)
        elif key == keys.S and direction != (0, -1): next_dir = (0,  1)
        elif key == keys.A and direction != (1,  0): next_dir = (-1, 0)
        elif key == keys.D and direction != (-1, 0): next_dir = (1,  0)

    elif screen_state == "game_over":
        if key == keys.SPACE:
            init_game()
            screen_state = "game"
        elif key == keys.M:
            screen_state = "menu"

# ── decorative demo snake on menu ─────────────────────────────────────────────

def _demo_snake():
    # a static snake shape drawn in the background for visual interest
    cx, cy = GRID_WIDTH // 2, GRID_HEIGHT // 2
    return [(cx + i, cy + 5) for i in range(-8, 8)]

# ── go ────────────────────────────────────────────────────────────────────────

pgzrun.go()
