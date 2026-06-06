import os as _os
_GAME_DIR = _os.path.dirname(_os.path.abspath(__file__))  # must be before pgzrun overwrites __file__

import pgzrun
import pygame
import random
import math
import json
import os

# ── config ────────────────────────────────────────────────────────────────────

TITLE = "Treasure Town"

TILE = 48                       # source art is 16px, drawn at 3x
COLS = 16
ROWS = 11
WIDTH = COLS * TILE             # 768
HEIGHT = ROWS * TILE            # 528
HUD_H = 44                      # translucent heads-up strip at the top

GAME_TIME = 45.0                # seconds per round
PLAYER_SPEED = 205.0            # pixels / second
TARGET_TREASURES = 6            # how many treasures live on the map at once

NUM_HOUSES = 4
NUM_TREES = 11
NUM_BUSHES = 7
NUM_MUSHROOMS = 6

# asset locations (assets/ sits next to the game folder)
ASSETS = os.path.join(_GAME_DIR, "..", "assets")
TILES_DIR = os.path.join(ASSETS, "tiny-town", "Tiles")
CHAR_SHEET = os.path.join(
    ASSETS, "roguelike-characters", "Spritesheet", "roguelikeChar_transparent.png"
)
HIGH_SCORE_FILE = os.path.join(_GAME_DIR, "highscore.json")

# tile ids picked out of the tiny-town sheet
GROUND_TILES = [0, 0, 0, 0, 0, 0, 0, 1, 1, 2]   # mostly plain grass, some detail
TREE_TILES = [28, 28, 3]                         # green pines, occasional autumn tree
BUSH_TILE = 5
MUSHROOM_TILES = [29, 30]

# house templates: (roof_top, roof_bottom, door, window)
HOUSE_TEMPLATES = [
    (53, 65, 85, 84),   # red roof, brown walls
    (49, 61, 89, 88),   # grey roof, grey walls
]

# treasure kinds: name -> (tile id, points, spawn weight)
TREASURE_KINDS = {
    "coin": (93, 10, 0.60),
    "key": (117, 25, 0.30),
    "gem": (131, 50, 0.10),
}

# colours
WHITE = (245, 245, 245)
GOLD = (255, 210, 70)
DARK = (24, 22, 30)
PANEL = (18, 16, 24)
GREEN = (120, 200, 90)
SHADOW = "black"

# ── asset loading (lazy: needs the display, which exists once we draw) ─────────

_tile_cache = {}


def tile(idx, size=TILE):
    key = (idx, size)
    surf = _tile_cache.get(key)
    if surf is None:
        img = pygame.image.load(os.path.join(TILES_DIR, "tile_%04d.png" % idx)).convert_alpha()
        surf = pygame.transform.scale(img, (size, size))
        _tile_cache[key] = surf
    return surf


_player_frames = {}


def player_image(facing):
    """The hero sprite (orange adventurer at grid col 0, row 5), flipped per facing."""
    img = _player_frames.get(facing)
    if img is None:
        sheet = pygame.image.load(CHAR_SHEET).convert_alpha()
        step = 16 + 1                              # 16px tiles, 1px margin
        frame = sheet.subsurface((0 * step, 5 * step, 16, 16))
        frame = pygame.transform.scale(frame, (44, 44))
        if facing < 0:
            frame = pygame.transform.flip(frame, True, False)
        _player_frames[facing] = frame
    return _player_frames[facing]


_shadow_cache = {}


def shadow(w, h):
    surf = _shadow_cache.get((w, h))
    if surf is None:
        surf = pygame.Surface((w, h), pygame.SRCALPHA)
        pygame.draw.ellipse(surf, (0, 0, 0, 70), surf.get_rect())
        _shadow_cache[(w, h)] = surf
    return surf


# ── persistent high score ─────────────────────────────────────────────────────

def load_high_score():
    if os.path.exists(HIGH_SCORE_FILE):
        try:
            with open(HIGH_SCORE_FILE) as f:
                return int(json.load(f).get("high_score", 0))
        except (ValueError, OSError, json.JSONDecodeError):
            return 0
    return 0


def save_high_score(value):
    with open(HIGH_SCORE_FILE, "w") as f:
        json.dump({"high_score": value}, f)


# ── game state ────────────────────────────────────────────────────────────────

state = "menu"            # "menu" | "play" | "over"
high_score = load_high_score()
new_record = False

score = 0
time_left = GAME_TIME
anim_t = 0.0

# the town
ground = []               # ground[gy][gx] -> tile id
blocked = set()           # (gx, gy) tiles a treasure / player may not occupy
obstacles = []            # pygame.Rect list for movement collisions
houses = []               # dicts describing houses to draw
trees = []                # (tile_id, gx, gy)
mushrooms = []            # (tile_id, gx, gy)
treasures = []            # dicts: x, y, gx, gy, kind, value, phase
popups = []               # floating "+10" score text

# player (centre position in pixels)
px = WIDTH / 2
py = HEIGHT / 2
facing = 1

CENTER = (COLS // 2, ROWS // 2)


# ── town generation ───────────────────────────────────────────────────────────

def area_free(gx, gy, w, h, margin=0):
    """True if the w×h block (plus margin) is on-map, unblocked and clear of spawn."""
    for x in range(gx - margin, gx + w + margin):
        for y in range(gy - margin, gy + h + margin):
            if x < 0 or y < 1 or x >= COLS or y >= ROWS:
                return False
            if (x, y) in blocked:
                return False
            # keep the player's start patch open
            if abs(x - CENTER[0]) <= 1 and abs(y - CENTER[1]) <= 1:
                return False
    return True


def build_town():
    global ground, blocked, obstacles, houses, trees, mushrooms
    ground = [[random.choice(GROUND_TILES) for _ in range(COLS)] for _ in range(ROWS)]
    blocked = set()
    obstacles = []
    houses = []
    trees = []
    mushrooms = []

    # houses (2 wide, 3 tall: two roof rows + a wall row)
    placed = 0
    attempts = 0
    while placed < NUM_HOUSES and attempts < 400:
        attempts += 1
        gx = random.randint(1, COLS - 3)
        gy = random.randint(1, ROWS - 4)
        if not area_free(gx, gy, 2, 3, margin=1):
            continue
        top, bot, door, window = random.choice(HOUSE_TEMPLATES)
        houses.append({"gx": gx, "gy": gy, "top": top, "bot": bot,
                       "door": door, "window": window})
        for x in range(gx, gx + 2):
            for y in range(gy, gy + 3):
                blocked.add((x, y))
        obstacles.append(pygame.Rect(gx * TILE + 4, gy * TILE + 6,
                                     2 * TILE - 8, 3 * TILE - 8))
        placed += 1

    # trees & bushes — single tiles with a small solid base
    def scatter(count, tile_pool, base_w, base_h):
        n = 0
        tries = 0
        while n < count and tries < 400:
            tries += 1
            gx = random.randint(0, COLS - 1)
            gy = random.randint(1, ROWS - 1)
            if not area_free(gx, gy, 1, 1):
                continue
            blocked.add((gx, gy))
            trees.append((random.choice(tile_pool), gx, gy))
            bx = gx * TILE + (TILE - base_w) // 2
            by = gy * TILE + TILE - base_h - 4
            obstacles.append(pygame.Rect(bx, by, base_w, base_h))
            n += 1

    scatter(NUM_TREES, TREE_TILES, 20, 14)
    scatter(NUM_BUSHES, [BUSH_TILE], 22, 16)

    # mushrooms are pure decoration — walkable
    n = 0
    tries = 0
    while n < NUM_MUSHROOMS and tries < 200:
        tries += 1
        gx = random.randint(0, COLS - 1)
        gy = random.randint(1, ROWS - 1)
        if (gx, gy) in blocked:
            continue
        mushrooms.append((random.choice(MUSHROOM_TILES), gx, gy))
        n += 1


def free_tiles():
    occupied = {(t["gx"], t["gy"]) for t in treasures}
    occupied.add((int(px // TILE), int(py // TILE)))
    out = []
    for gy in range(1, ROWS):
        for gx in range(COLS):
            if (gx, gy) in blocked or (gx, gy) in occupied:
                continue
            out.append((gx, gy))
    return out


def spawn_treasure():
    spots = free_tiles()
    if not spots:
        return
    gx, gy = random.choice(spots)
    names = list(TREASURE_KINDS.keys())
    weights = [TREASURE_KINDS[n][2] for n in names]
    kind = random.choices(names, weights=weights)[0]
    tid, value, _ = TREASURE_KINDS[kind]
    treasures.append({
        "gx": gx, "gy": gy,
        "x": gx * TILE + TILE / 2,
        "y": gy * TILE + TILE / 2,
        "kind": kind, "tile": tid, "value": value,
        "phase": random.uniform(0, math.tau),
    })


def start_game():
    global state, score, time_left, treasures, popups, px, py, facing, new_record
    build_town()
    score = 0
    time_left = GAME_TIME
    treasures = []
    popups = []
    px = CENTER[0] * TILE + TILE / 2
    py = CENTER[1] * TILE + TILE / 2
    facing = 1
    new_record = False
    for _ in range(TARGET_TREASURES):
        spawn_treasure()
    state = "play"


# ── collision helpers ─────────────────────────────────────────────────────────

def feet_rect(cx, cy):
    w, h = 26, 20
    return pygame.Rect(int(cx - w / 2), int(cy + 9 - h / 2), w, h)


def blocked_at(cx, cy):
    r = feet_rect(cx, cy)
    if r.left < 2 or r.right > WIDTH - 2 or r.top < HUD_H or r.bottom > HEIGHT - 2:
        return True
    return any(r.colliderect(o) for o in obstacles)


def body_rect():
    return pygame.Rect(int(px - 17), int(py - 17), 34, 34)


# ── update ────────────────────────────────────────────────────────────────────

def update(dt):
    global px, py, facing, score, time_left, high_score, new_record, state

    global anim_t
    anim_t += dt

    # treasure bob + score popups animate regardless of state
    for p in popups:
        p["y"] -= 26 * dt
        p["t"] -= dt
    popups[:] = [p for p in popups if p["t"] > 0]

    if state != "play":
        return

    # movement
    dx = dy = 0.0
    if keyboard.left or keyboard.a:
        dx -= 1
    if keyboard.right or keyboard.d:
        dx += 1
    if keyboard.up or keyboard.w:
        dy -= 1
    if keyboard.down or keyboard.s:
        dy += 1
    if dx or dy:
        mag = math.hypot(dx, dy)
        dx, dy = dx / mag, dy / mag
        if dx < 0:
            facing = -1
        elif dx > 0:
            facing = 1
        nx = px + dx * PLAYER_SPEED * dt
        if not blocked_at(nx, py):
            px = nx
        ny = py + dy * PLAYER_SPEED * dt
        if not blocked_at(px, ny):
            py = ny

    # collect treasures
    pr = body_rect()
    remaining = []
    for t in treasures:
        tr = pygame.Rect(int(t["x"] - 16), int(t["y"] - 16), 32, 32)
        if pr.colliderect(tr):
            score += t["value"]
            popups.append({"x": t["x"], "y": t["y"] - 10,
                           "text": "+%d" % t["value"], "t": 0.8})
        else:
            remaining.append(t)
    treasures[:] = remaining
    while len(treasures) < TARGET_TREASURES:
        spawn_treasure()

    # countdown
    time_left -= dt
    if time_left <= 0:
        time_left = 0
        if score > high_score:
            high_score = score
            new_record = True
            save_high_score(high_score)
        state = "over"


# ── drawing ───────────────────────────────────────────────────────────────────

def draw_town():
    for gy in range(ROWS):
        for gx in range(COLS):
            screen.blit(tile(ground[gy][gx]), (gx * TILE, gy * TILE))
    for tid, gx, gy in mushrooms:
        screen.blit(tile(tid), (gx * TILE, gy * TILE))
    for h in houses:
        gx, gy = h["gx"], h["gy"]
        for col in range(2):
            screen.blit(tile(h["top"]), ((gx + col) * TILE, gy * TILE))
            screen.blit(tile(h["bot"]), ((gx + col) * TILE, (gy + 1) * TILE))
        screen.blit(tile(h["door"]), (gx * TILE, (gy + 2) * TILE))
        screen.blit(tile(h["window"]), ((gx + 1) * TILE, (gy + 2) * TILE))
    for tid, gx, gy in trees:
        screen.blit(shadow(30, 12), (gx * TILE + 9, gy * TILE + TILE - 12))
        screen.blit(tile(tid), (gx * TILE, gy * TILE))


def draw_treasures():
    for t in treasures:
        bob = math.sin(anim_t * 3 + t["phase"]) * 3
        screen.blit(shadow(26, 10), (int(t["x"] - 13), int(t["y"] + 14)))
        img = tile(t["tile"], 34)
        screen.blit(img, (int(t["x"] - 17), int(t["y"] - 17 + bob)))


def draw_player():
    bob = -abs(math.sin(anim_t * 9)) * 3 if (keyboard.left or keyboard.right or
                                             keyboard.up or keyboard.down or
                                             keyboard.a or keyboard.d or
                                             keyboard.w or keyboard.s) else 0
    screen.blit(shadow(30, 12), (int(px - 15), int(py + 12)))
    img = player_image(facing)
    screen.blit(img, (int(px - 22), int(py - 24 + bob)))


def draw_popups():
    for p in popups:
        screen.draw.text(p["text"], center=(p["x"], p["y"]), fontsize=24,
                         color=GOLD, owidth=1, ocolor=SHADOW)


def draw_hud():
    bar = pygame.Surface((WIDTH, HUD_H), pygame.SRCALPHA)
    bar.fill((0, 0, 0, 150))
    screen.blit(bar, (0, 0))
    screen.blit(tile(93, 28), (12, 8))
    screen.draw.text("%d" % score, midleft=(46, HUD_H // 2), fontsize=30,
                     color=GOLD, owidth=1, ocolor=SHADOW)
    # timer (turns red when low)
    col = (235, 80, 70) if time_left <= 10 else WHITE
    screen.draw.text("Time  %2d" % math.ceil(time_left), midright=(WIDTH - 14, HUD_H // 2),
                     fontsize=30, color=col, owidth=1, ocolor=SHADOW)


def dim(alpha=170):
    overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
    overlay.fill((PANEL[0], PANEL[1], PANEL[2], alpha))
    screen.blit(overlay, (0, 0))


def draw_menu():
    draw_town()
    draw_treasures()
    dim(160)
    cx = WIDTH // 2
    screen.draw.text("TREASURE TOWN", center=(cx, 120), fontsize=72,
                     color=GOLD, owidth=1.4, ocolor=SHADOW)
    screen.draw.text("Grab every coin, key and gem before the clock runs out!",
                     center=(cx, 178), fontsize=28, color=WHITE, owidth=1, ocolor=SHADOW)
    # little treasure showcase
    for i, kind in enumerate(["coin", "key", "gem"]):
        tid, value, _ = TREASURE_KINDS[kind]
        x = cx - 150 + i * 150
        screen.blit(tile(tid, 40), (x - 20, 232))
        screen.draw.text("+%d" % value, center=(x, 296), fontsize=24,
                         color=GOLD, owidth=1, ocolor=SHADOW)
    screen.draw.text("High Score: %d" % high_score, center=(cx, 350), fontsize=34,
                     color=GREEN, owidth=1, ocolor=SHADOW)
    pulse = 200 + int(55 * math.sin(anim_t * 4))
    screen.draw.text("Press SPACE to start", center=(cx, 420), fontsize=40,
                     color=(pulse, pulse, pulse), owidth=1.2, ocolor=SHADOW)
    screen.draw.text("Move with Arrow Keys or WASD     Q to quit",
                     center=(cx, 470), fontsize=22, color=WHITE, owidth=1, ocolor=SHADOW)


def draw_over():
    draw_town()
    draw_treasures()
    dim(180)
    cx = WIDTH // 2
    screen.draw.text("TIME'S UP!", center=(cx, 130), fontsize=72,
                     color=(235, 90, 80), owidth=1.4, ocolor=SHADOW)
    screen.blit(tile(131, 56), (cx - 28, 188))
    screen.draw.text("You collected", center=(cx, 280), fontsize=30,
                     color=WHITE, owidth=1, ocolor=SHADOW)
    screen.draw.text("%d" % score, center=(cx, 330), fontsize=80,
                     color=GOLD, owidth=1.4, ocolor=SHADOW)
    if new_record:
        glow = 180 + int(75 * math.sin(anim_t * 6))
        screen.draw.text("NEW HIGH SCORE!", center=(cx, 392), fontsize=36,
                         color=(glow, glow, 120), owidth=1.2, ocolor=SHADOW)
    else:
        screen.draw.text("High Score: %d" % high_score, center=(cx, 392),
                         fontsize=30, color=GREEN, owidth=1, ocolor=SHADOW)
    screen.draw.text("SPACE to play again      M for menu", center=(cx, 458),
                     fontsize=26, color=WHITE, owidth=1, ocolor=SHADOW)


def draw():
    screen.clear()
    if state == "menu":
        draw_menu()
    elif state == "play":
        draw_town()
        draw_treasures()
        draw_player()
        draw_popups()
        draw_hud()
    else:
        draw_over()


# ── input ─────────────────────────────────────────────────────────────────────

def on_key_down(key):
    global state
    if state == "menu":
        if key == keys.SPACE:
            start_game()
        elif key == keys.Q:
            exit()
    elif state == "over":
        if key == keys.SPACE:
            start_game()
        elif key == keys.M:
            state = "menu"


# build an initial town so the menu has a backdrop
build_town()
for _ in range(TARGET_TREASURES):
    spawn_treasure()

pgzrun.go()
