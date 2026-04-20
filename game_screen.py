# =============================================================================
# game_screen.py — Πthon Arena
# =============================================================================
# Full game screen for both players and spectators.
#
# Entry point called from client.py:
#
#   from game_screen import run_game_screen, load_assets
#   assets = load_assets()
#   result = run_game_screen(
#       sock        = sock,
#       player_info = player_info,
#       mode        = "player" | "spectator",
#       assets      = assets,
#   )
#   # result → "lobby" | "quit"
#
# Server integration
# ──────────────────
# Background receiver thread → queue → drained every frame:
#   GAME_STATE   → prev_state / state updated, timestamp recorded
#   PLAYERS_LIST → spectator_count derived accurately   (bug 4 fix)
#   GAME_OVER    → game-over overlay, returns "lobby"
#   CHAT         → sidebar message + floating bubble (player mode)
#   FAN_JOINED   → system message in sidebar
#   DISCONNECT   → returns "quit"
#
# move_progress = (now − last_state_time) / SNAKE_MOVE_INTERVAL_MS  [0..1]
# Used by draw_snake() to lerp every segment between consecutive states.
# =============================================================================

import math
import os
import queue
import random
import threading

import pygame
import pygame.gfxdraw

import protocol
from constants import TILE_SIZE, GRID_COLS, GRID_ROWS, SNAKE_MOVE_INTERVAL_MS, SUDDEN_DEATH_SPEED_MULT

# =============================================================================
# THEME  — identical to lobby.py / login.py
# =============================================================================

SKY_BLUE    = (135, 206, 235)
WHITE       = (255, 255, 255)
BLACK       = (0,   0,   0)
TEAL        = (0,  180, 160)
TEAL_HOV    = (0,  210, 185)
TEAL_DARK   = (0,  115, 100)
CARD_BG     = (236, 249, 244)
CARD_BORDER = (188, 226, 216)
TEXT_DARK   = (22,  42,  35)
TEXT_MID    = (82, 108,  94)
TEXT_LIGHT  = (152, 176, 165)

# Game-specific colors
BAR_EMPTY   = (180, 210, 200)
CHEER_BG    = (210, 238, 230)
INPUT_BG    = (224, 244, 238)
INPUT_ACT   = (200, 235, 225)

# =============================================================================
# LAYOUT  — change one constant and everything reflows
# =============================================================================

BRICK_THICKNESS = 24
BOARD_LEFT_MARGIN = 20                             # background strip visible left of bricks
HUD_H      = 90
BOARD_W    = GRID_COLS * TILE_SIZE
BOARD_H    = GRID_ROWS * TILE_SIZE
BOARD_X    = BRICK_THICKNESS + BOARD_LEFT_MARGIN  # = 44
BOARD_Y    = HUD_H + BRICK_THICKNESS
BOTTOM_H   = 36
SIDEBAR_W  = 300
SIDEBAR_X  = BOARD_X + BOARD_W + BRICK_THICKNESS  # = 868
WINDOW_W   = SIDEBAR_X + SIDEBAR_W                # = 1168
WINDOW_H   = BOARD_Y + BOARD_H + BRICK_THICKNESS + BOTTOM_H

FPS        = 60
AVA_R      = 20

# ── Asset sizes ───────────────────────────────────────────────────────────────
PIE_MAX_PX = 52
OBSTACLE_SIZES = {
    "cactus":    50,
    "rock":      34,
    "3rocks":    46,
    "spikes":    40,
    "dirtyPond": 54,
}

# ── Snake geometry ────────────────────────────────────────────────────────────
PUFFS = [
    ( 0,  0, 18),
    (-7, -5, 14),
    ( 7, -5, 14),
    (-7,  5, 14),
    ( 7,  5, 14),
]
NECK_W = 20

# ── Cheer bubbles ─────────────────────────────────────────────────────────────
BUBBLE_LIFETIME_MS = 4000

# ── Spectator emoji buttons ───────────────────────────────────────────────────
QUICK_EMOJIS = ["👏", "❤️", "💀", "🔥", "😢"]
BACKGROUND_MUSIC_PATH = os.path.join("assets", "game.mp3")
GAME_WON_SOUND_PATH = os.path.join("assets", "gamewonsoundeffect.mp3")
GAME_LOST_SOUND_PATH = os.path.join("assets", "gamelostsoundeffect.mp3")
KEY_PRESS_SOUND_PATH = os.path.join("assets", "sound-8.mp3")
BUTTON_SOUND_PATH = os.path.join("assets", "button_lara.mp3")
FRICTION_SOUND_PATH = os.path.join("assets", "friction.mp3")
PIE_SOUND_PATH = os.path.join("assets", "pie_sound.mp3")
HIT_SOUND_PATH = os.path.join("assets", "hit_sound.mp3")
_friction_sound = None


# =============================================================================
# LAYOUT HELPER  — bug 3 & 6 fix
# Single source of truth for the spectator input rect.
# Used identically in draw_sidebar() AND the event handler.
# =============================================================================

def _spectator_input_rect():
    INPUT_H    = 36
    EMOJI_H    = 36
    BTN_AREA_H = EMOJI_H + INPUT_H + 12
    EMOJI_Y    = WINDOW_H - BOTTOM_H - BTN_AREA_H
    INP_Y      = EMOJI_Y + EMOJI_H + 4
    return pygame.Rect(SIDEBAR_X + 8, INP_Y, SIDEBAR_W - 16, INPUT_H)


# =============================================================================
# ASSET LOADING
# =============================================================================

def _load_img(path, max_px=None, keep_alpha=True):
    if not os.path.exists(path):
        return None
    try:
        img = pygame.image.load(path)
        img = img.convert_alpha() if keep_alpha else img.convert()
        if max_px is not None:
            w, h  = img.get_size()
            scale = max_px / max(w, h)
            img   = pygame.transform.smoothscale(
                img, (max(1, int(w * scale)), max(1, int(h * scale))))
        return img
    except Exception as e:
        print(f"[ASSETS] Could not load {path}: {e}")
        return None


def _fallback_surf(color, size):
    s = pygame.Surface((size, size), pygame.SRCALPHA)
    pygame.draw.rect(s, color, s.get_rect(), border_radius=6)
    return s


def _start_background_music():
    """
    Start looping match music if the asset and mixer are available.
    Returns True when this function actually started playback.
    """
    if not os.path.exists(BACKGROUND_MUSIC_PATH):
        return False
    try:
        if pygame.mixer.get_init() is None:
            pygame.mixer.init()
        pygame.mixer.music.load(BACKGROUND_MUSIC_PATH)
        pygame.mixer.music.set_volume(0.2)
        pygame.mixer.music.play(-1)
        return True
    except Exception as e:
        print(f"[AUDIO] Could not start background music: {e}")
        return False


def _stop_background_music():
    try:
        if pygame.mixer.get_init() is not None:
            pygame.mixer.music.stop()
    except Exception:
        pass


def _play_game_over_sound(mode, winner, local_name):
    """
    Play a one-shot end-of-match sound for the local player.
    Spectators and ties get no result sound.
    """
    if mode != "player" or winner == "TIE":
        return

    sound_path = GAME_WON_SOUND_PATH if winner == local_name else GAME_LOST_SOUND_PATH
    if not os.path.exists(sound_path):
        return

    try:
        if pygame.mixer.get_init() is None:
            pygame.mixer.init()
        sound = pygame.mixer.Sound(sound_path)
        sound.set_volume(0.6)
        sound.play()
    except Exception as e:
        print(f"[AUDIO] Could not play game-over sound: {e}")


def _play_key_press_sound():
    """
    Play a one-shot sound for key/button presses.
    """
    if not os.path.exists(KEY_PRESS_SOUND_PATH):
        return

    try:
        if pygame.mixer.get_init() is None:
            pygame.mixer.init()
        sound = pygame.mixer.Sound(KEY_PRESS_SOUND_PATH)
        sound.set_volume(0.8)
        sound.play()
    except Exception as e:
        print(f"[AUDIO] Could not play key press sound: {e}")


def _play_button_sound():
    """
    Play the main action-button sound.
    """
    if not os.path.exists(BUTTON_SOUND_PATH):
        return

    try:
        if pygame.mixer.get_init() is None:
            pygame.mixer.init()
        sound = pygame.mixer.Sound(BUTTON_SOUND_PATH)
        sound.set_volume(0.45)
        sound.play()
    except Exception as e:
        print(f"[AUDIO] Could not play button sound: {e}")


def _play_friction_sound():
    """
    Play a short field-movement friction sound.
    """
    global _friction_sound
    if not os.path.exists(FRICTION_SOUND_PATH):
        return

    try:
        if pygame.mixer.get_init() is None:
            pygame.mixer.init()
        if _friction_sound is None:
            _friction_sound = pygame.mixer.Sound(FRICTION_SOUND_PATH)
            _friction_sound.set_volume(0.35)
        _friction_sound.play()
    except Exception as e:
        print(f"[AUDIO] Could not play friction sound: {e}")


def _play_pie_sound():
    """
    Play when the local player's snake eats a pie.
    """
    if not os.path.exists(PIE_SOUND_PATH):
        return

    try:
        if pygame.mixer.get_init() is None:
            pygame.mixer.init()
        sound = pygame.mixer.Sound(PIE_SOUND_PATH)
        sound.set_volume(0.2)
        sound.play()
    except Exception as e:
        print(f"[AUDIO] Could not play pie sound: {e}")


def _play_hit_sound():
    """
    Play when the local player's snake takes obstacle damage.
    """
    if not os.path.exists(HIT_SOUND_PATH):
        return

    try:
        if pygame.mixer.get_init() is None:
            pygame.mixer.init()
        sound = pygame.mixer.Sound(HIT_SOUND_PATH)
        sound.set_volume(0.2)
        sound.play()
    except Exception as e:
        print(f"[AUDIO] Could not play hit sound: {e}")


def _xy(cell):
    return tuple(cell[:2])


def _player_from_state(state, username):
    if not state:
        return None
    for key in ("player1", "player2"):
        player = state.get(key)
        if player and player.get("username") == username:
            return player
    return None


def _local_ate_pie(prev, current, local_name):
    player = _player_from_state(current, local_name)
    if not prev or not player or not player.get("snake"):
        return False

    head = _xy(player["snake"][0])
    previous_pies = {_xy(pie) for pie in prev.get("pies", [])}
    current_pies = {_xy(pie) for pie in current.get("pies", [])}
    return head in previous_pies and head not in current_pies


def _local_hit_obstacle(prev, current, local_name):
    old_player = _player_from_state(prev, local_name)
    new_player = _player_from_state(current, local_name)
    if not old_player or not new_player or not new_player.get("snake"):
        return False

    if new_player.get("health", 0) >= old_player.get("health", 0):
        return False

    head = _xy(new_player["snake"][0])
    obstacle_cells = {_xy(obs) for obs in current.get("obstacles", [])}
    return head in obstacle_cells


def load_assets():
    """
    Load all game assets once at startup (called from client.py).
    All image files are flat inside assets/.
    Missing files get solid-color fallbacks.
    """
    a = {}

    for name, fallback in [("grass1", (106, 168, 79)),
                            ("grass2", ( 93, 150, 68))]:
        img = _load_img(os.path.join("assets", f"{name}.png"), keep_alpha=False)
        if img:
            a[name] = pygame.transform.scale(img, (TILE_SIZE, TILE_SIZE))
        else:
            s = pygame.Surface((TILE_SIZE, TILE_SIZE))
            s.fill(fallback)
            a[name] = s

    pie_fallbacks = {
        "blueberry":  (100, 120, 220),
        "cherry":     (210,  40,  60),
        "strawberry": (240,  80, 100),
        "lemon":      (240, 220,  50),
        "orange":     (240, 140,  30),
    }
    a["pies"] = {}
    for name, color in pie_fallbacks.items():
        img = _load_img(os.path.join("assets", f"{name}.png"), max_px=PIE_MAX_PX)
        a["pies"][name] = img if img else _fallback_surf(color, PIE_MAX_PX)

    obs_fallbacks = {
        "cactus":    ( 60, 140,  60),
        "rock":      (120, 120, 130),
        "3rocks":    ( 90,  90, 100),
        "spikes":    (180,  60,  60),
        "dirtyPond": ( 80, 110,  60),
    }
    a["obstacles"] = {}
    for name, color in obs_fallbacks.items():
        size = OBSTACLE_SIZES[name]
        img  = _load_img(os.path.join("assets", f"{name}.png"), max_px=size)
        a["obstacles"][name] = img if img else _fallback_surf(color, size)

    # ── Border bricks ─────────────────────────────────────────────────────────
    # Pre-tile four border strips to exact pixel dimensions at load time.
    # draw_border() then does four blits — no per-frame math, no gaps.

    def _tile_surf(img, target_w, target_h):
        """Fill a Surface of exactly target_w × target_h by tiling img."""
        out = pygame.Surface((target_w, target_h))
        iw, ih = img.get_size()
        for ty in range(0, target_h, max(1, ih)):
            for tx in range(0, target_w, max(1, iw)):
                out.blit(img, (tx, ty))
        return out

    frame_w = BOARD_W + BRICK_THICKNESS * 2   # top/bottom strip width

    h_raw = _load_img(os.path.join("assets", "horizontal_brick.png"))
    if h_raw is None:
        h_raw = pygame.Surface((64, 24))
        h_raw.fill((160, 100, 60))
    else:
        w, h  = h_raw.get_size()
        unit_w = max(1, int(w * BRICK_THICKNESS / h))
        h_raw  = pygame.transform.smoothscale(h_raw, (unit_w, BRICK_THICKNESS))

    v_raw = _load_img(os.path.join("assets", "vertical.png"))
    if v_raw is None:
        v_raw = pygame.Surface((24, 64))
        v_raw.fill((140, 85, 50))
    else:
        w, h   = v_raw.get_size()
        unit_h = max(1, int(h * BRICK_THICKNESS / w))
        v_raw  = pygame.transform.smoothscale(v_raw, (BRICK_THICKNESS, unit_h))

    a["border_top"]    = _tile_surf(h_raw, frame_w,         BRICK_THICKNESS)
    a["border_bottom"] = _tile_surf(h_raw, frame_w,         BRICK_THICKNESS)
    a["border_left"]   = _tile_surf(v_raw, BRICK_THICKNESS, BOARD_H)
    a["border_right"]  = _tile_surf(v_raw, BRICK_THICKNESS, BOARD_H)

    # ── Background ────────────────────────────────────────────────────────────
    bg = _load_img(os.path.join("assets", "blurred.png"), keep_alpha=False)
    if bg:
        a["bg"] = pygame.transform.smoothscale(bg, (WINDOW_W, WINDOW_H))
    else:
        s = pygame.Surface((WINDOW_W, WINDOW_H))
        s.fill(SKY_BLUE)
        a["bg"] = s

    # ── Shield icon (replaces VS text in HUD) ────────────────────────────────
    shield = _load_img(os.path.join("assets", "shield.png"))
    if shield:
        a["shield"] = pygame.transform.smoothscale(shield, (36, 36))
    else:
        a["shield"] = None

    a["cheerful"] = _load_img(os.path.join("assets", "cheerful.png"))

    # ── Fire tile (sudden death) ──────────────────────────────────────────────
    # Ground texture — rendered flush, replaces grass entirely.
    fire_img = _load_img(os.path.join("assets", "fireground.png"), keep_alpha=False)
    if fire_img:
        a["fire"] = pygame.transform.scale(fire_img, (TILE_SIZE, TILE_SIZE))
    else:
        s = pygame.Surface((TILE_SIZE, TILE_SIZE))
        s.fill((220, 60, 0))
        a["fire"] = s

    # Fireball decoration — centered on top of the ground, like an obstacle sprite.
    # 34 px fits nicely on the 40 px tile leaving a visible fire border around it.
    # Loaded at the MAX size the pulse will ever reach.
    # draw_fire_tiles() smoothscales it down each frame so we never upscale.
    fireball_img = _load_img(os.path.join("assets", "fireball.png"), max_px=52)
    a["fireball"] = fireball_img   # may be None — draw_fire_tiles handles gracefully

    return a


# =============================================================================
# DRAWING HELPERS
# =============================================================================

def _tile_center(col, row):
    return (
        BOARD_X + col * TILE_SIZE + TILE_SIZE // 2,
        BOARD_Y + row * TILE_SIZE + TILE_SIZE // 2,
    )


def _darker(color, factor=0.55):
    return (
        max(0, int(color[0] * factor)),
        max(0, int(color[1] * factor)),
        max(0, int(color[2] * factor)),
    )


def _lerp_pos(prev_grid, curr_grid, t):
    px, py = _tile_center(prev_grid[0], prev_grid[1])
    cx, cy = _tile_center(curr_grid[0], curr_grid[1])
    return (px + (cx - px) * t, py + (cy - py) * t)


def _gradient_color(index, total, base_color):
    if total <= 1:
        return base_color
    head = _darker(base_color, 0.55)
    t    = index / (total - 1)
    return (
        int(head[0] + (base_color[0] - head[0]) * t),
        int(head[1] + (base_color[1] - head[1]) * t),
        int(head[2] + (base_color[2] - head[2]) * t),
    )


def _infer_direction(snake):
    if len(snake) < 2:
        return (1, 0)
    dx = snake[0][0] - snake[1][0]
    dy = snake[0][1] - snake[1][1]
    if dx == 0 and dy == 0:
        return (1, 0)
    return (max(-1, min(1, dx)), max(-1, min(1, dy)))


def _truncate(name, max_chars=14):
    return name if len(name) <= max_chars else name[:13] + "…"


def _wrap(font, text, max_w):
    words, lines, line = text.split(), [], ""
    for w in words:
        t = (line + " " + w).strip()
        if font.size(t)[0] <= max_w:
            line = t
        else:
            if line:
                lines.append(line)
            line = w
    if line:
        lines.append(line)
    return lines or [""]


# =============================================================================
# SNAKE RENDERING
# =============================================================================

def _draw_fluffy_segment(surface, cx, cy, color):
    outline = _darker(color, 0.60)
    for dx, dy, r in PUFFS:
        pygame.draw.circle(surface, outline, (int(cx+dx), int(cy+dy)), r+2)
    for dx, dy, r in PUFFS:
        pygame.draw.circle(surface, color,   (int(cx+dx), int(cy+dy)), r)


def _draw_neck(surface, p1, p2, color):
    x1, y1 = p1
    x2, y2 = p2
    if abs(x2-x1) > TILE_SIZE*2 or abs(y2-y1) > TILE_SIZE*2:
        return
    dx, dy = x2-x1, y2-y1
    length = max(1, (dx**2 + dy**2)**0.5)
    px, py = -dy/length, dx/length
    hw     = NECK_W / 2
    pts    = [
        (x1+px*hw, y1+py*hw), (x2+px*hw, y2+py*hw),
        (x2-px*hw, y2-py*hw), (x1-px*hw, y1-py*hw),
    ]
    pygame.draw.polygon(surface, _darker(color, 0.75),
                        [(int(x), int(y)) for x, y in pts])


def _draw_classic_eyes(surface, center, direction):
    cx, cy   = center
    dx, dy   = direction
    off, fwd = 8, 6
    eyes = ([(cx+dx*fwd, cy-off), (cx+dx*fwd, cy+off)] if dx != 0
            else [(cx-off, cy+dy*fwd), (cx+off, cy+dy*fwd)])
    for ex, ey in eyes:
        ex, ey = int(ex), int(ey)
        pygame.draw.circle(surface, WHITE, (ex, ey), 5)
        pygame.draw.circle(surface, BLACK, (int(ex+dx*2), int(ey+dy*2)), 3)


def _draw_robot_eyes(surface, center, direction):
    """
    Robot eyes — identical geometry to classic eyes, just recoloured:
      outer circle : light blue  (180, 220, 255)  instead of white
      inner pupil  : white       (255, 255, 255)  instead of black
    """
    cx, cy   = center
    dx, dy   = direction
    off, fwd = 8, 6
    eyes = ([(cx+dx*fwd, cy-off), (cx+dx*fwd, cy+off)] if dx != 0
            else [(cx-off, cy+dy*fwd), (cx+off, cy+dy*fwd)])
    LIGHT_BLUE = (180, 220, 255)
    for ex, ey in eyes:
        ex, ey = int(ex), int(ey)
        pygame.draw.circle(surface, LIGHT_BLUE, (ex, ey), 5)
        pygame.draw.circle(surface, WHITE, (int(ex+dx*2), int(ey+dy*2)), 3)


def _draw_emoji_head(surface, center, emoji, fonts):
    # bug 8 fix — uses pre-loaded font, no SysFont call per frame
    lbl = fonts["emoji"].render(emoji, True, WHITE)
    cx, cy = int(center[0]), int(center[1])
    surface.blit(lbl, (cx - lbl.get_width()//2, cy - lbl.get_height()//2))


def _draw_avatar(surface, cx, cy, r, color, head_style, head_emoji, fonts):
    """
    Colored circle avatar — identical to lobby.py _draw_avatar().
    bug 8 fix — accepts fonts dict, no SysFont calls inside.
    """
    try:
        pygame.gfxdraw.filled_circle(surface, cx, cy, r, color)
        dark = _darker(color, 0.60)
        pygame.gfxdraw.aacircle(surface, cx, cy, r,     dark)
        pygame.gfxdraw.aacircle(surface, cx, cy, r - 1, dark)
    except Exception:
        pygame.draw.circle(surface, color, (cx, cy), r)

    if head_style == "emoji" and head_emoji:
        lbl = fonts["emoji_sm"].render(head_emoji, True, WHITE)
        lbl = pygame.transform.smoothscale(
            lbl, (min(lbl.get_width(),  r*2-6),
                  min(lbl.get_height(), r*2-6)))
        surface.blit(lbl, (cx - lbl.get_width()//2, cy - lbl.get_height()//2))
    else:
        er  = max(2, r//5)
        off = max(3, r//3)
        for ex in [cx-off, cx+off]:
            pygame.draw.circle(surface, WHITE, (ex, cy-2), er)
            pygame.draw.circle(surface, BLACK, (ex-1, cy-2), max(1, er-1))


# =============================================================================
# BOARD / OBSTACLES / PIES
# =============================================================================

def draw_board(surface, assets):
    for row in range(GRID_ROWS):
        for col in range(GRID_COLS):
            tile = assets["grass1"] if (row+col) % 2 == 0 else assets["grass2"]
            surface.blit(tile, (BOARD_X + col*TILE_SIZE, BOARD_Y + row*TILE_SIZE))


def draw_border(surface, assets):
    """Four blits of pre-tiled brick strips flush against the board edges."""
    bx = BOARD_X - BRICK_THICKNESS
    surface.blit(assets["border_top"],    (bx,                BOARD_Y - BRICK_THICKNESS))
    surface.blit(assets["border_bottom"], (bx,                BOARD_Y + BOARD_H))
    surface.blit(assets["border_left"],   (bx,                BOARD_Y))
    surface.blit(assets["border_right"],  (BOARD_X + BOARD_W, BOARD_Y))


def draw_obstacles(surface, assets, obstacles):
    """obstacles: list of (col, row, kind) — cached after first GAME_STATE."""
    for col, row, kind in obstacles:
        img = assets["obstacles"].get(kind)
        if img is None:
            continue
        cx, cy = _tile_center(col, row)
        surface.blit(img, img.get_rect(center=(cx, cy)))


# =============================================================================
# SUDDEN DEATH RENDERING
# =============================================================================

def draw_fire_tiles(surface, assets, fire_tiles):
    """
    Render fire ground + animated fireball decoration on every fire tile.
    Layer order:
      1. fireground.png — flush tile replacing the grass underneath
      2. fireball.png   — centered on top, smoothly pulsing size via sine wave

    Animation:
      A sine wave driven by pygame.time.get_ticks() moves the size between
      FIREBALL_MIN_PX and FIREBALL_MAX_PX. math.sin gives a perfectly smooth
      [-1, 1] oscillation; we remap it to [0, 1] and lerp between the two sizes.
      Each tile gets its own phase offset based on its position so they don't
      all pulse in lockstep — gives a natural, lively look.
    """
    FIREBALL_MIN_PX = 38   # smallest the fireball shrinks to
    FIREBALL_MAX_PX = 52   # largest it grows to
    PULSE_SPEED     = 2.2  # oscillations per second — tweak for faster/slower pulse

    fire_img = assets.get("fire")
    fireball  = assets.get("fireball")
    if not fire_img or not fire_tiles:
        return

    now_s = pygame.time.get_ticks() / 1000.0   # current time in seconds

    # Pre-fetch original fireball size once (used for aspect-ratio scaling)
    if fireball:
        fb_w, fb_h = fireball.get_size()

    for col, row in fire_tiles:
        # ── Ground layer ──────────────────────────────────────────────────────
        surface.blit(fire_img, (BOARD_X + col * TILE_SIZE, BOARD_Y + row * TILE_SIZE))

        # ── Animated fireball ─────────────────────────────────────────────────
        if fireball:
            # Each tile gets a unique phase so they pulse independently.
            # (col * 3 + row * 7) is a cheap hash — prime multipliers spread phases well.
            phase = (col * 3 + row * 7) * 0.4
            # sin oscillates -1..1 → remap to 0..1
            t     = (math.sin(now_s * PULSE_SPEED * math.tau + phase) + 1.0) / 2.0
            size  = int(FIREBALL_MIN_PX + (FIREBALL_MAX_PX - FIREBALL_MIN_PX) * t)

            # Scale preserving aspect ratio (smoothscale for anti-aliased result)
            scale  = size / max(fb_w, fb_h)
            scaled = pygame.transform.smoothscale(
                fireball,
                (max(1, int(fb_w * scale)), max(1, int(fb_h * scale)))
            )

            cx, cy = _tile_center(col, row)
            surface.blit(scaled, scaled.get_rect(center=(cx, cy)))


def draw_sudden_death_banner(surface, fonts):
    """
    Semi-transparent red banner across the top of the board announcing
    SUDDEN DEATH.  Pulses between two reds to draw attention.
    """
    pulse      = (pygame.time.get_ticks() // 400) % 2 == 0
    banner_col = (200, 30, 30, 180) if pulse else (160, 10, 10, 180)

    banner = pygame.Surface((BOARD_W, 32), pygame.SRCALPHA)
    banner.fill(banner_col)
    surface.blit(banner, (BOARD_X, BOARD_Y))

    label = fonts["small_bold"].render("⚡ SUDDEN DEATH — FIRE TILES ACTIVE ⚡",
                                       True, (255, 230, 100))
    lx = BOARD_X + BOARD_W // 2 - label.get_width() // 2
    ly = BOARD_Y + 16 - label.get_height() // 2
    surface.blit(label, (lx, ly))


def draw_pies(surface, assets, pies):
    """pies: list of (col, row, kind) — updated every GAME_STATE."""
    for col, row, kind in pies:
        img = assets["pies"].get(kind)
        if img is None:
            continue
        cx, cy = _tile_center(col, row)
        surface.blit(img, img.get_rect(center=(cx, cy)))


def draw_snake(surface, snake, prev_snake, move_progress,
               color, head_style, head_emoji, invincible, fonts):
    """
    Draw one snake with smooth interpolation between server ticks.
    move_progress: (now − last_state_time) / SNAKE_MOVE_INTERVAL_MS, clamped 0..1
    invincible: player["invincible"] from GAME_STATE — flashes the snake
    """
    if not snake:
        return
    if invincible and pygame.time.get_ticks() % 300 < 150:
        return

    total = len(snake)
    if len(prev_snake) < total:
        prev_snake = prev_snake + [prev_snake[-1]] * (total - len(prev_snake))
    elif len(prev_snake) > total:
        prev_snake = prev_snake[:total]

    centers   = [_lerp_pos(prev_snake[i], snake[i], move_progress)
                 for i in range(total)]
    direction = _infer_direction(snake)

    # Pass 1 — necks behind segments
    for i in range(total - 1):
        frac      = (i + 0.5) / max(total - 1, 1)
        mid_color = _gradient_color(int(frac * (total-1)), total, color)
        _draw_neck(surface, centers[i], centers[i+1], mid_color)

    # Pass 2 — segments tail → head
    for i in range(total - 1, -1, -1):
        seg_color = _gradient_color(i, total, color)
        cx, cy    = int(centers[i][0]), int(centers[i][1])
        _draw_fluffy_segment(surface, cx, cy, seg_color)
        if i == 0:
            if head_style == "robot":
                _draw_robot_eyes(surface, centers[0], direction)
            elif head_style == "emoji" and head_emoji:
                _draw_emoji_head(surface, centers[0], head_emoji, fonts)
            else:
                _draw_classic_eyes(surface, centers[0], direction)


# =============================================================================
# HUD  (top strip)
# =============================================================================

def _draw_empty_cheers_state(surface, panel_rect, fonts, assets):
    """Shows cheerful.png centered in the empty sidebar area with text below."""
    cx = panel_rect.centerx
    img = assets.get("cheerful")

    if img:
        # Scale to fit nicely — max 100px tall
        iw, ih = img.get_size()
        scale  = min(100 / ih, (panel_rect.width - 20) / iw)
        nw, nh = int(iw * scale), int(ih * scale)
        scaled = pygame.transform.smoothscale(img, (nw, nh))
        img_y  = panel_rect.y + panel_rect.height // 2 - nh // 2 - 20
        surface.blit(scaled, (cx - nw // 2, img_y))
        text_y = img_y + nh + 14
    else:
        # Fallback: simple smiley circle if image missing
        cy = panel_rect.y + panel_rect.height // 2 - 20
        pygame.draw.circle(surface, (255, 220, 75), (cx, cy), 34)
        pygame.draw.circle(surface, (200, 160, 35), (cx, cy), 34, 3)
        for ex in [cx - 11, cx + 11]:
            pygame.draw.circle(surface, (55, 35, 25), (ex, cy - 9), 4)
        smile = [(cx-14,cy+7),(cx-8,cy+15),(cx,cy+18),(cx+8,cy+15),(cx+14,cy+7)]
        pygame.draw.lines(surface, (55, 35, 25), False, smile, 3)
        text_y = cy + 46

    t1 = fonts["empty_title"].render("No cheers yet",       True, (50,  90, 110))
    t2 = fonts["empty_body"].render("Spectator reactions",  True, (100, 140, 160))
    t3 = fonts["empty_body"].render("will appear here.",    True, (100, 140, 160))
    surface.blit(t1, (cx - t1.get_width()//2, text_y))
    surface.blit(t2, (cx - t2.get_width()//2, text_y + 24))
    surface.blit(t3, (cx - t3.get_width()//2, text_y + 40))


def draw_hud(surface, left_data, right_data, time_left, fonts, my_name, mode, assets,
             sudden_death=False):
    """
    Floating rounded HUD card with yellow timer badge.
    Card: y=8 to y=86 — bricks start at y=90, so background is visible in the gap.
    During sudden death the timer badge pulses red.
    """
    cx_mid = BOARD_X + BOARD_W // 2   # 424

    # ── Card ──────────────────────────────────────────────────────────────────
    CARD_X, CARD_Y = 10, 8
    CARD_W = SIDEBAR_X - 20           # 828
    CARD_H = 78                        # ends y=86, before bricks at y=90

    sh = pygame.Surface((CARD_W + 8, CARD_H + 8), pygame.SRCALPHA)
    pygame.draw.rect(sh, (0, 0, 0, 35),
                     (4, 4, CARD_W, CARD_H), border_radius=18)
    surface.blit(sh, (CARD_X - 2, CARD_Y - 2))

    card = pygame.Surface((CARD_W, CARD_H), pygame.SRCALPHA)
    pygame.draw.rect(card, (255, 255, 255, 215),
                     (0, 0, CARD_W, CARD_H), border_radius=18)
    surface.blit(card, (CARD_X, CARD_Y))
    pygame.draw.rect(surface, CARD_BORDER,
                     (CARD_X, CARD_Y, CARD_W, CARD_H), 1, border_radius=18)

    # ── Timer badge ────────────────────────────────────────────────────────────
    BADGE_W, BADGE_H = 108, 60
    badge_x = cx_mid - BADGE_W // 2   # 370
    badge_y = CARD_Y + (CARD_H - BADGE_H) // 2   # 17

    if sudden_death:
        pulse        = (pygame.time.get_ticks() // 300) % 2 == 0
        badge_fill   = (220, 35, 35)  if pulse else (170, 15, 15)
        badge_border = (140, 10, 10)
        time_color   = (255, 230, 200)
        label_color  = (255, 180, 180)
    else:
        badge_fill   = (251, 224, 100)
        badge_border = (215, 181,  60)
        time_color   = (120,  80,   0)
        label_color  = TEXT_MID

    pygame.draw.rect(surface, badge_fill,
                     (badge_x, badge_y, BADGE_W, BADGE_H), border_radius=28)
    pygame.draw.rect(surface, badge_border,
                     (badge_x, badge_y, BADGE_W, BADGE_H), 3, border_radius=28)
    mins = time_left // 60
    secs = time_left % 60
    ts = fonts["timer"].render(f"{mins:02d}:{secs:02d}", True, time_color)
    surface.blit(ts, (cx_mid - ts.get_width()//2, badge_y + 6))
    badge_label = "SUDDEN DEATH" if sudden_death else "TIME"
    tl = fonts["small"].render(badge_label, True, label_color)
    surface.blit(tl, (cx_mid - tl.get_width()//2,
                       badge_y + BADGE_H - tl.get_height() - 6))

    # ── Avatars + names ────────────────────────────────────────────────────────
    lc    = tuple(left_data["color"])
    lname = left_data["username"]
    if mode == "player" and lname == my_name:
        lname += " (you)"
    rc    = tuple(right_data["color"])
    rname = right_data["username"]
    if mode == "player" and rname == my_name:
        rname += " (you)"

    AVA_CY  = CARD_Y + 26
    L_AVA_X = CARD_X + 14 + AVA_R
    R_AVA_X = CARD_X + CARD_W - 14 - AVA_R

    _draw_avatar(surface, L_AVA_X, AVA_CY, AVA_R,
                 lc, left_data["head_style"], left_data["head_emoji"], fonts)
    _draw_avatar(surface, R_AVA_X, AVA_CY, AVA_R,
                 rc, right_data["head_style"], right_data["head_emoji"], fonts)

    ln = fonts["name"].render(_truncate(lname), True, TEXT_DARK)
    rn = fonts["name"].render(_truncate(rname), True, TEXT_DARK)
    surface.blit(ln, (L_AVA_X + AVA_R + 10, AVA_CY - ln.get_height()//2))
    surface.blit(rn, (R_AVA_X - AVA_R - 10 - rn.get_width(),
                       AVA_CY - rn.get_height()//2))

    # ── Health bars ────────────────────────────────────────────────────────────
    # Left bar fills from card-left to badge-left (minus gap).
    # Right bar fills from badge-right (plus gap) to card-right.
    BAR_Y = CARD_Y + CARD_H - 25    # 61
    BAR_H = 16

    L_BAR_X = CARD_X + 14                           # 24
    L_BAR_W = badge_x - 14 - L_BAR_X               # 370-14-24 = 332
    R_BAR_X = badge_x + BADGE_W + 14               # 492
    R_BAR_W = (CARD_X + CARD_W - 14) - R_BAR_X    # 824-492 = 332

    _draw_health_bar(surface, L_BAR_X, BAR_Y, L_BAR_W, BAR_H,
                     left_data["health"],  lc, right_aligned=False)
    _draw_health_bar(surface, R_BAR_X, BAR_Y, R_BAR_W, BAR_H,
                     right_data["health"], rc, right_aligned=True)

    shield = assets.get("shield")
    if shield:
        srect = shield.get_rect(center=(cx_mid, BAR_Y + BAR_H // 2))
        surface.blit(shield, srect)
    else:
        vs = fonts["small"].render("VS", True, TEXT_MID)
        surface.blit(vs, (cx_mid - vs.get_width()//2,
                           BAR_Y + BAR_H//2 - vs.get_height()//2))


def _draw_health_bar(surface, x, y, w, h, health, color, right_aligned=False):
    filled_w = max(0, int(w * health / 100))
    pygame.draw.rect(surface, BAR_EMPTY, (x, y, w, h), border_radius=5)
    if filled_w > 0:
        fx = (x + w - filled_w) if right_aligned else x
        pygame.draw.rect(surface, color, (fx, y, filled_w, h), border_radius=5)
    pygame.draw.rect(surface, _darker(color, 0.7), (x, y, w, h), 2, border_radius=5)


# =============================================================================
# SIDEBAR  (right panel)
# =============================================================================

def draw_sidebar(surface, cheer_msgs, spectator_count,
                 mode, input_text, input_active, fonts, assets, sidebar_bubbles):
    """
    Cheer messages visible for everyone.
    Spectator mode adds emoji buttons + text input at the bottom.

    bug 6 fix — returns {"emoji_rects": dict, "input_rect": Rect|None}
    so the event handler uses the exact same rect that was drawn.
    """
    # Floating rounded semi-transparent card — 8px margin so background peeks through
    panel_surf = pygame.Surface((SIDEBAR_W - 16, WINDOW_H - 16), pygame.SRCALPHA)
    pygame.draw.rect(panel_surf, (236, 249, 244, 220),
                     (0, 0, SIDEBAR_W - 16, WINDOW_H - 16), border_radius=20)
    surface.blit(panel_surf, (SIDEBAR_X + 8, 8))
    pygame.draw.rect(surface, CARD_BORDER,
                     (SIDEBAR_X + 8, 8, SIDEBAR_W - 16, WINDOW_H - 16), 1, border_radius=20)

    # Header: big shield icon + "Spectators & Cheers" — approx HUD card height
    HEADER_H = 64                              # roughly matches HUD card (78px), slightly less
    hdr_x = SIDEBAR_X + 16
    shield_sm = assets.get("shield")
    if shield_sm:
        icon = pygame.transform.smoothscale(shield_sm, (42, 42))
        icon_y = 8 + (HEADER_H - 42) // 2    # vertically centered in header area
        surface.blit(icon, (hdr_x, icon_y))
        hdr_x += 50
    hdr = fonts["sidebar_hdr"].render("Spectators & Cheers", True, TEXT_DARK)
    hdr_y = 8 + HEADER_H // 2 - hdr.get_height() // 2
    surface.blit(hdr, (hdr_x, hdr_y))
    DIV_Y = 8 + HEADER_H + 4
    pygame.draw.line(surface, CARD_BORDER,
                     (SIDEBAR_X + 16, DIV_Y), (SIDEBAR_X + SIDEBAR_W - 16, DIV_Y), 1)

    INPUT_H    = 36
    EMOJI_H    = 36
    BTN_AREA_H = EMOJI_H + INPUT_H + 12 if mode == "spectator" else 0
    MSG_TOP    = DIV_Y + 6
    MSG_BOT    = WINDOW_H - BOTTOM_H - BTN_AREA_H - 6
    MSG_W      = SIDEBAR_W - 16

    # Empty state
    if not cheer_msgs:
        msg_area = pygame.Rect(SIDEBAR_X + 8, MSG_TOP, MSG_W, MSG_BOT - MSG_TOP)
        _draw_empty_cheers_state(surface, msg_area, fonts, assets)
    else:
        # Draw oldest messages at TOP, newest at BOTTOM — chronological order
        clip_h = MSG_BOT - MSG_TOP
        clip   = pygame.Surface((MSG_W, clip_h), pygame.SRCALPHA)
        clip.fill((0, 0, 0, 0))

        def _msg_height(msg):
            if msg.get("system"):
                return fonts["emoji_chat"].get_height() + 8 + 6
            lines    = _wrap(fonts["emoji_chat"], msg.get("text", ""), MSG_W - 28)
            sender_h = fonts["small_bold"].get_height() + 2
            return sender_h + len(lines) * (fonts["emoji_chat"].get_height() + 2) + 16 + 6

        # Find which messages fit — always oldest→newest top→bottom
        # When overflow: drop oldest until newest fit from top
        recent = cheer_msgs[-60:]
        fitting = []
        total = 0
        for msg in reversed(recent):
            h = _msg_height(msg)
            if total + h > clip_h - 8:
                break
            fitting.insert(0, msg)
            total += h

        y = 4
        for msg in fitting:
            if y >= clip_h:
                break
            sender = msg.get("sender", "")
            text   = msg.get("text",   "")
            system = msg.get("system", False)

            if system:
                # Styled pill — use emoji font so icons render
                lbl  = fonts["emoji_chat"].render(text, True, TEXT_MID)
                pill_w = min(lbl.get_width() + 20, MSG_W - 4)
                pill_h = lbl.get_height() + 8
                pill_x = (MSG_W - pill_w) // 2
                pygame.draw.rect(clip, (220, 238, 235),
                                 (pill_x, y, pill_w, pill_h), border_radius=10)
                pygame.draw.rect(clip, CARD_BORDER,
                                 (pill_x, y, pill_w, pill_h), 1, border_radius=10)
                clip.blit(lbl, (pill_x + 10, y + 4))
                y += pill_h + 6
            else:
                lines     = _wrap(fonts["emoji_chat"], text, MSG_W - 28)
                sender_h  = fonts["small_bold"].get_height() + 2
                block_h   = sender_h + len(lines) * (fonts["emoji_chat"].get_height() + 2) + 16

                # Card with teal left accent bar
                pygame.draw.rect(clip, (245, 252, 249),
                                 (0, y, MSG_W, block_h), border_radius=9)
                pygame.draw.rect(clip, CARD_BORDER,
                                 (0, y, MSG_W, block_h), 1, border_radius=9)
                pygame.draw.rect(clip, TEAL,
                                 (0, y, 4, block_h), border_radius=2)

                # Sender name in teal
                sn = fonts["small_bold"].render(sender, True, TEAL_DARK)
                clip.blit(sn, (10, y + 4))

                # Message text — emoji_chat font renders emojis correctly
                ty = y + 4 + sn.get_height() + 2
                for line in lines:
                    ls = fonts["emoji_chat"].render(line, True, TEXT_DARK)
                    clip.blit(ls, (10, ty))
                    ty += fonts["emoji_chat"].get_height() + 2

                y += block_h + 6

        surface.blit(clip, (SIDEBAR_X + 8, MSG_TOP))

    if mode != "spectator":
        # Players: read-only sidebar, no input
        draw_sidebar_bubbles(surface, sidebar_bubbles, fonts)
        return {"emoji_rects": {}, "input_rect": None}

    # ── Spectator only: emoji buttons + text input ────────────────────────────
    BTN_AREA_H = EMOJI_H + INPUT_H + 12
    EMOJI_Y    = WINDOW_H - BOTTOM_H - BTN_AREA_H
    BTN_W      = (SIDEBAR_W - 16) // len(QUICK_EMOJIS)

    emoji_rects = {}
    for i, em in enumerate(QUICK_EMOJIS):
        bx = SIDEBAR_X + 8 + i * BTN_W
        br = pygame.Rect(bx, EMOJI_Y, BTN_W - 4, EMOJI_H - 4)
        pygame.draw.rect(surface, CARD_BG,     br, border_radius=8)
        pygame.draw.rect(surface, CARD_BORDER, br, 1, border_radius=8)
        lbl = fonts["emoji"].render(em, True, TEXT_DARK)
        surface.blit(lbl, (br.centerx - lbl.get_width()//2,
                           br.centery - lbl.get_height()//2))
        emoji_rects[em] = br

    # Text input
    inp_r = _spectator_input_rect()
    pygame.draw.rect(surface, INPUT_ACT if input_active else INPUT_BG,
                     inp_r, border_radius=8)
    pygame.draw.rect(surface, TEAL if input_active else CARD_BORDER,
                     inp_r, 2, border_radius=8)
    display = input_text if input_text else "Cheer (30 chars)…"
    lbl     = fonts["chat"].render(display, True,
                                   TEXT_DARK if input_text else TEXT_LIGHT)
    surface.blit(lbl, (inp_r.x + 8, inp_r.centery - lbl.get_height()//2))
    if input_active and pygame.time.get_ticks() % 1000 < 500:
        cur_x = inp_r.x + 8 + fonts["chat"].size(input_text)[0] + 1
        pygame.draw.line(surface, TEXT_DARK,
                         (cur_x, inp_r.y + 6), (cur_x, inp_r.bottom - 6), 1)

    # Floating emoji reactions drawn last (on top of everything in sidebar)
    draw_sidebar_bubbles(surface, sidebar_bubbles, fonts)

    return {"emoji_rects": emoji_rects, "input_rect": inp_r}


# =============================================================================
# BOTTOM BAR
# =============================================================================

def draw_bottom_bar(surface, spectator_count, fonts, mode="player"):
    """
    Bottom status strip.  For spectators, also draws a Leave button on the right.
    Returns the Leave button Rect (spectator mode) or None (player mode).
    """
    y = WINDOW_H - BOTTOM_H
    rect = pygame.Rect(0, y, SIDEBAR_X, BOTTOM_H)
    strip = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
    strip.fill((255, 255, 255, 190))
    surface.blit(strip, rect.topleft)
    pygame.draw.line(surface, CARD_BORDER, (0, y), (SIDEBAR_X, y), 1)

    if spectator_count == 0:
        txt = "No spectators watching"
    elif spectator_count == 1:
        txt = "1 spectator watching"
    else:
        txt = f"{spectator_count} spectators watching"

    lbl = fonts["small"].render(txt, True, TEXT_MID)
    dot_x = 16
    dot_y = y + BOTTOM_H // 2
    pygame.draw.circle(surface, TEAL, (dot_x, dot_y), 5)
    surface.blit(lbl, (dot_x + 12, dot_y - lbl.get_height() // 2))

    # ── Spectator Leave button ────────────────────────────────────────────────
    if mode != "spectator":
        return None

    BTN_W, BTN_H = 118, 24
    BTN_X = SIDEBAR_X - BTN_W - 12
    BTN_Y = y + (BOTTOM_H - BTN_H) // 2
    leave_r = pygame.Rect(BTN_X, BTN_Y, BTN_W, BTN_H)

    hov = leave_r.collidepoint(pygame.mouse.get_pos())
    bg  = (210, 60, 60) if hov else (180, 50, 50)
    pygame.draw.rect(surface, bg, leave_r, border_radius=7)
    lt = fonts["small_bold"].render("Back to Lobby", True, (255, 255, 255))
    surface.blit(lt, (leave_r.centerx - lt.get_width()//2,
                      leave_r.centery - lt.get_height()//2))
    return leave_r


# =============================================================================
# FLOATING CHEER BUBBLES  (player mode only)
# =============================================================================

def spawn_bubble(bubbles, text):
    bubbles.append({
        "text":    text,
        "born_at": pygame.time.get_ticks(),
        "x":       float(random.randint(BOARD_X + 60, BOARD_X + BOARD_W - 60)),
        "y":       float(BOARD_Y + BOARD_H - 60),
    })


def draw_bubbles(surface, bubbles, fonts):
    now    = pygame.time.get_ticks()
    active = []
    for b in bubbles:
        age = now - b["born_at"]
        if age >= BUBBLE_LIFETIME_MS:
            continue
        alpha  = int(255 * (1.0 - age / BUBBLE_LIFETIME_MS))
        b["y"] -= 0.4   # slower rise → more height covered over longer lifetime

        lbl = fonts["name"].render(b["text"], True, TEXT_DARK)
        bg  = pygame.Surface((lbl.get_width() + 18, lbl.get_height() + 10),
                              pygame.SRCALPHA)
        bg.fill((*CARD_BG, int(alpha * 0.9)))
        pygame.draw.rect(bg, (*TEAL, alpha), bg.get_rect(), 2, border_radius=10)
        bg.set_alpha(alpha)
        lbl.set_alpha(alpha)
        bx = int(b["x"]) - bg.get_width()//2
        by = int(b["y"])
        surface.blit(bg,  (bx, by))
        surface.blit(lbl, (bx + 9, by + 5))
        active.append(b)
    bubbles[:] = active


SIDEBAR_BUBBLE_LIFETIME_MS = 3000

def spawn_sidebar_bubble(sidebar_bubbles, emoji):
    """Spawn a large emoji that floats up inside the sidebar panel."""
    panel_cx = SIDEBAR_X + SIDEBAR_W // 2
    sidebar_bubbles.append({
        "emoji":   emoji,
        "born_at": pygame.time.get_ticks(),
        "x":       float(panel_cx + random.randint(-30, 30)),
        "y":       float(WINDOW_H - BOTTOM_H - 80),
    })


def draw_sidebar_bubbles(surface, sidebar_bubbles, fonts):
    """Draw large emoji reactions floating upward inside the sidebar."""
    now    = pygame.time.get_ticks()
    active = []
    for b in sidebar_bubbles:
        age = now - b["born_at"]
        if age >= SIDEBAR_BUBBLE_LIFETIME_MS:
            continue
        t      = age / SIDEBAR_BUBBLE_LIFETIME_MS
        alpha  = int(255 * (1.0 - t))
        b["y"] -= 1.2   # float upward

        lbl = fonts["emoji_lg"].render(b["emoji"], True, (255, 255, 255))
        lbl.set_alpha(alpha)
        surface.blit(lbl, (int(b["x"]) - lbl.get_width()//2, int(b["y"])))
        active.append(b)
    sidebar_bubbles[:] = active


# =============================================================================
# GAME OVER OVERLAY
# =============================================================================

def _run_game_over(surface, clock, fonts, screenshot,
                   winner, h1, h2, name1, name2, reason, mode,
                   msg_q, sock):
    """
    Blocking game-over screen.

    Each frame:
      1. Blit the frozen screenshot (board paused exactly as it was)
      2. Blit a dark semi-transparent tint
      3. Draw the overlay panel on top

    Queue handling:
      Only REMATCH_* and DISCONNECT messages are consumed here.
      Everything else (PLAYERS_LIST, FAN_JOINED, etc.) is collected and
      put back so the lobby receives it untouched.

    Returns: "lobby" | "quit" | "rematch"
    """
    disconnect = (reason == "disconnect")

    if mode == "player":
        if winner == "TIE":
            result_text, result_color = "DRAW!",    (140, 100, 0)
        elif winner == name1:
            result_text, result_color = "YOU WIN!", (0, 130, 70)
        else:
            result_text, result_color = "YOU LOSE", (160, 35, 35)
    else:
        if winner == "TIE":
            result_text, result_color = "DRAW!",                        (140, 100, 0)
        else:
            result_text, result_color = f"{_truncate(winner, 12)} WINS!", (0, 130, 70)

    # Panel geometry — computed once
    # ov_w = 480 gives comfortable padding; buttons derived from ov_x so they
    # always stay inside the panel with 20px margin on each side.
    ov_w, ov_h = 480, 260
    ov_x = WINDOW_W // 2 - ov_w // 2
    ov_y = WINDOW_H // 2 - ov_h // 2

    BTN_W = (ov_w - 60) // 2
    BTN_H = 36
    BTN_Y = ov_y + ov_h - 52

    if mode == "spectator":
        # Single centered button — spectators cannot rematch
        btn_lobby   = pygame.Rect(ov_x + ov_w//2 - BTN_W//2, BTN_Y, BTN_W, BTN_H)
        btn_rematch = None
    else:
        btn_lobby   = pygame.Rect(ov_x + 20,              BTN_Y, BTN_W, BTN_H)
        btn_rematch = pygame.Rect(ov_x + 20 + BTN_W + 10, BTN_Y, BTN_W, BTN_H)

    # Pre-build tint — drawn on top of screenshot every frame
    tint = pygame.Surface((WINDOW_W, WINDOW_H), pygame.SRCALPHA)
    tint.fill((10, 30, 15, 150))

    rematch_state = None   # None | "queued" | "incoming" | "declined"

    while True:
        # ── Drain queue — only process rematch/disconnect, defer the rest ──────
        deferred = []
        while not msg_q.empty():
            try:
                h, b = msg_q.get_nowait()
            except queue.Empty:
                break

            if h == "REMATCH_QUEUED":
                # Server confirmed it recorded our request — now show "waiting"
                rematch_state = "queued"
            elif h == "REMATCH_FROM":
                # Opponent requested rematch — show accept button
                rematch_state = "incoming"
            elif h == "REMATCH_START":
                for item in deferred:
                    msg_q.put(item)
                return "rematch"
            elif h == "REMATCH_DECLINED":
                rematch_state = "declined"
            elif h == "DISCONNECT":
                for item in deferred:
                    msg_q.put(item)
                return "quit"
            else:
                deferred.append((h, b))

        for item in deferred:
            msg_q.put(item)

        # ── Events ────────────────────────────────────────────────────────────
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return "quit"

            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                mx, my = event.pos
                if btn_lobby.collidepoint(mx, my):
                    _play_button_sound()
                    protocol.send(sock, protocol.send_decline_rematch())
                    return "lobby"
                # Rematch button — players only
                can_click = (btn_rematch is not None
                             and not disconnect
                             and rematch_state in (None, "incoming"))
                if can_click and btn_rematch.collidepoint(mx, my):
                    _play_key_press_sound()
                    protocol.send(sock, protocol.send_rematch())
                    rematch_state = "queued"

            elif event.type == pygame.KEYDOWN and event.key == pygame.K_RETURN:
                protocol.send(sock, protocol.send_decline_rematch())
                return "lobby"

        # ── Draw: screenshot → tint → panel ───────────────────────────────────
        surface.blit(screenshot, (0, 0))
        surface.blit(tint, (0, 0))

        # Panel
        pygame.draw.rect(surface, WHITE,
                         (ov_x, ov_y, ov_w, ov_h), border_radius=18)
        pygame.draw.rect(surface, CARD_BORDER,
                         (ov_x, ov_y, ov_w, ov_h), 2, border_radius=18)

        # Result
        rt = fonts["result"].render(result_text, True, result_color)
        surface.blit(rt, (WINDOW_W//2 - rt.get_width()//2, ov_y + 18))

        # Score / sub-text
        if disconnect:
            sub = fonts["name"].render("Opponent disconnected", True, TEXT_MID)
            surface.blit(sub, (WINDOW_W//2 - sub.get_width()//2, ov_y + 82))
        else:
            score = f"{_truncate(name1, 10)}: {h1} HP     {_truncate(name2, 10)}: {h2} HP"
            sc = fonts["name"].render(score, True, TEXT_DARK)
            surface.blit(sc, (WINDOW_W//2 - sc.get_width()//2, ov_y + 82))
            if winner != "TIE":
                wt = fonts["small"].render(f"Winner: {winner}", True, TEXT_MID)
                surface.blit(wt, (WINDOW_W//2 - wt.get_width()//2, ov_y + 112))

        # Rematch status line
        if rematch_state == "queued":
            rs = fonts["small"].render("Waiting for opponent…", True, TEXT_MID)
            surface.blit(rs, (WINDOW_W//2 - rs.get_width()//2, ov_y + 138))
        elif rematch_state == "declined":
            rs = fonts["small"].render("Opponent declined", True, (160, 50, 50))
            surface.blit(rs, (WINDOW_W//2 - rs.get_width()//2, ov_y + 138))
        elif rematch_state == "incoming":
            rs = fonts["small"].render("Opponent wants a rematch!", True, (0, 130, 70))
            surface.blit(rs, (WINDOW_W//2 - rs.get_width()//2, ov_y + 138))

        # Return to Lobby button
        hover_l = btn_lobby.collidepoint(pygame.mouse.get_pos())
        pygame.draw.rect(surface, TEAL_HOV if hover_l else TEAL,
                         btn_lobby, border_radius=10)
        bl = fonts["name"].render("Return to Lobby", True, WHITE)
        surface.blit(bl, (btn_lobby.centerx - bl.get_width()//2,
                           btn_lobby.centery - bl.get_height()//2))

        # Rematch button — players only
        if btn_rematch is not None:
            can_rematch = (not disconnect and rematch_state in (None, "incoming"))
            hover_r  = can_rematch and btn_rematch.collidepoint(pygame.mouse.get_pos())
            rm_col   = TEAL_HOV if hover_r else TEAL if can_rematch else (190, 205, 202)
            pygame.draw.rect(surface, rm_col,        btn_rematch, border_radius=10)
            pygame.draw.rect(surface, CARD_BORDER,   btn_rematch, 1, border_radius=10)
            rm_txt = "Requested…" if rematch_state == "queued" else "Rematch"
            rm_lbl = fonts["name"].render(
                rm_txt, True, WHITE if can_rematch else TEXT_MID)
            surface.blit(rm_lbl, (btn_rematch.centerx - rm_lbl.get_width()//2,
                                   btn_rematch.centery - rm_lbl.get_height()//2))

        pygame.display.flip()
        clock.tick(FPS)


# =============================================================================
# RECEIVER THREAD  (same pattern as lobby.py)
# =============================================================================

def _start_receiver(sock, q):
    def _run():
        while True:
            try:
                raw = protocol.receive(sock)
                if not raw:
                    q.put(("DISCONNECT", None)); break
                h, b = protocol.parse(raw)
                q.put((h, b))
            except Exception:
                q.put(("DISCONNECT", None)); break
    threading.Thread(target=_run, daemon=True, name="game-rx").start()


# =============================================================================
# MAIN ENTRY POINT
# =============================================================================

def run_game_screen(sock, player_info, mode, assets, msg_q):
    """
    Parameters
    ──────────
    sock        : server socket (open and authenticated)
    player_info : dict from run_login_screen()
    mode        : "player" | "spectator"
    assets      : dict from load_assets()
    msg_q       : shared queue from client.py — single receiver thread

    Returns "lobby" or "quit".
    """
    screen = pygame.display.set_mode((WINDOW_W, WINDOW_H))
    pygame.display.set_caption("Πthon Arena — Match")
    clock  = pygame.time.Clock()
    music_started = _start_background_music()

    # bug 8 fix — all fonts created once here, passed down into helpers
    fonts = {
        "result":     pygame.font.SysFont("comicsansms", 36, bold=True),  # game over headline
        "timer":      pygame.font.SysFont("impact",      28, bold=True),
        "name":       pygame.font.SysFont("tahoma",      14, bold=True),
        "small":      pygame.font.SysFont("Arial",       12),
        "small_bold": pygame.font.SysFont("Arial",       12, bold=True),
        "chat":       pygame.font.SysFont("tahoma",      12),
        "emoji":      pygame.font.SysFont("segoeuiemoji,segoe ui emoji,tahoma", 18),
        "emoji_sm":   pygame.font.SysFont("segoeuiemoji,segoe ui emoji,tahoma", 12),
        "emoji_lg":   pygame.font.SysFont("segoeuiemoji,segoe ui emoji,tahoma", 52),
        "emoji_chat": pygame.font.SysFont("segoeuiemoji,segoe ui emoji,tahoma", 13),
        "sidebar_title": pygame.font.SysFont("Arial",       16, bold=True),
        "sidebar_hdr":   pygame.font.SysFont("comicsansms", 17, bold=True),
        "empty_title":   pygame.font.SysFont("tahoma",      15, bold=True),
        "empty_body":    pygame.font.SysFont("tahoma",      12),
    }

    my_name = player_info["username"]

    # Custom key bindings — inverted for O(1) lookup in event handler
    key_map    = player_info.get("keys", {
        "UP":    pygame.K_UP,
        "DOWN":  pygame.K_DOWN,
        "LEFT":  pygame.K_LEFT,
        "RIGHT": pygame.K_RIGHT,
    })
    key_to_dir = {v: k for k, v in key_map.items()}

    # ── State ─────────────────────────────────────────────────────────────────
    state           = None
    prev_state      = None
    last_state_time = 0
    obstacles       = None
    fire_tiles      = []    # cached once when SD triggers — never changes after
    sudden_death    = False  # mirrors game.sudden_death for rendering

    cheer_msgs      = []
    bubbles         = []
    sidebar_bubbles = []
    spectator_count = 0

    input_text  = ""
    input_active = False
    sidebar_out = {"emoji_rects": {}, "input_rect": None}

    result   = "lobby"
    leave_btn = None   # spectator Leave button rect — set each frame
    running = True
    while running:
        clock.tick(FPS)

        # ── Drain server messages ─────────────────────────────────────────────
        while not msg_q.empty():
            try:
                hdr, body = msg_q.get_nowait()
            except queue.Empty:
                break

            if hdr == "GAME_STATE":
                prev_state      = state
                state           = protocol.parse_game_state(body)
                last_state_time = pygame.time.get_ticks()
                if mode == "player":
                    if _local_ate_pie(prev_state, state, my_name):
                        _play_pie_sound()
                    if _local_hit_obstacle(prev_state, state, my_name):
                        _play_hit_sound()
                if obstacles is None and state:
                    obstacles = state["obstacles"]
                # Fire tiles are fixed once SD triggers — cache on first non-empty value
                if not fire_tiles and state and state.get("fire_tiles"):
                    fire_tiles = state["fire_tiles"]
                # Always mirror the SD flag so HUD / banner update live
                if state:
                    sudden_death = state.get("sudden_death", False)

            elif hdr == "PLAYERS_LIST":
                players = protocol.parse_players_list(body)
                spectator_count = sum(
                    1 for p in players if p.get("status") == "spectating")

            elif hdr == "GAME_OVER":
                winner, h1, h2, reason = protocol.parse_game_over(body)
                _stop_background_music()
                _play_game_over_sound(mode, winner, my_name)

                if state:
                    p1, p2 = state["player1"], state["player2"]
                else:
                    p1 = {"username": "Player 1"}
                    p2 = {"username": "Player 2"}
                    h1 = h2 = 0

                if mode == "player":
                    if p1["username"] == my_name:
                        name1, go_h1, go_h2 = my_name, h1, h2
                        name2 = p2["username"]
                    else:
                        name1, go_h1, go_h2 = my_name, h2, h1
                        name2 = p1["username"]
                else:
                    name1, name2 = p1["username"], p2["username"]
                    go_h1, go_h2 = h1, h2

                # Take screenshot of the current frame — board frozen at this moment
                screenshot = screen.copy()

                go_result = _run_game_over(
                    screen, clock, fonts, screenshot,
                    winner, go_h1, go_h2, name1, name2, reason, mode,
                    msg_q, sock)

                if go_result == "rematch":
                    if music_started:
                        music_started = _start_background_music()
                    # Reset game state — new GAME_STATE messages will arrive
                    state           = None
                    prev_state      = None
                    last_state_time = 0
                    obstacles       = None
                    fire_tiles      = []
                    sudden_death    = False
                    cheer_msgs.append({"sender": "", "text": "⚔ Rematch!",
                                       "system": True})
                else:
                    result  = go_result   # "lobby" or "quit"
                    running = False
                break   # stop draining — PLAYERS_LIST stays in queue for lobby

            elif hdr == "CHAT":
                parts  = body.split(":", 1)
                sender = parts[0] if len(parts) == 2 else "?"
                text   = parts[1] if len(parts) == 2 else body
                # Emoji reactions: sidebar bubble only, don't flood panel
                if text.strip() in QUICK_EMOJIS:
                    spawn_sidebar_bubble(sidebar_bubbles, text.strip())
                else:
                    cheer_msgs.append({"sender": sender, "text": text, "system": False})

            elif hdr == "FAN_JOINED":
                cheer_msgs.append({
                    "sender": "", "text": f"{body} joined as spectator", "system": True})

            elif hdr == "DISCONNECT":
                result  = "quit"
                running = False

            else:
                # REMATCH_FROM, REMATCH_QUEUED, REMATCH_START, REMATCH_DECLINED
                # can arrive while the main loop is still draining pre-GAME_OVER
                # messages. Put them back so _run_game_over can process them.
                msg_q.put((hdr, body))

        # ── Events ────────────────────────────────────────────────────────────
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                result = "quit"; running = False

            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                mx, my = event.pos
                if mode == "spectator":
                    # Leave button — return to lobby
                    if leave_btn and leave_btn.collidepoint(mx, my):
                        _play_button_sound()
                        protocol.send(sock, protocol.send_leave_watch())
                        result = "lobby"; running = False
                    else:
                        for em, r in sidebar_out["emoji_rects"].items():
                            if r.collidepoint(mx, my):
                                _play_key_press_sound()
                                protocol.send(sock, protocol.send_chat(em))
                                spawn_sidebar_bubble(sidebar_bubbles, em)
                        ir = sidebar_out["input_rect"]
                        input_active = bool(ir and ir.collidepoint(mx, my))
                else:
                    input_active = False

            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE and mode == "spectator" and not input_active:
                    protocol.send(sock, protocol.send_leave_watch())
                    result = "lobby"; running = False
                elif input_active and mode == "spectator":
                    if event.key == pygame.K_RETURN:
                        msg = input_text.strip()
                        if msg:
                            protocol.send(sock, protocol.send_chat(msg))
                            # Add locally — server doesn't echo back to sender
                            cheer_msgs.append({"sender": my_name, "text": msg, "system": False})
                            input_text = ""
                    elif event.key == pygame.K_BACKSPACE:
                        input_text = input_text[:-1]
                    elif len(input_text) < 30 and event.unicode.isprintable():
                        input_text += event.unicode
                elif mode == "player" and not input_active:
                    direction = key_to_dir.get(event.key)
                    if direction:
                        protocol.send(sock, protocol.send_move(direction))
                        _play_friction_sound()

        # ── Interpolation ─────────────────────────────────────────────────────
        # During sudden death the server ticks twice as often, so the effective
        # interval is halved — the lerp must match or the snake looks laggy.
        _tick_interval = (SNAKE_MOVE_INTERVAL_MS / SUDDEN_DEATH_SPEED_MULT
                          if sudden_death else SNAKE_MOVE_INTERVAL_MS)
        if last_state_time > 0:
            move_progress = min(
                1.0,
                (pygame.time.get_ticks() - last_state_time) / _tick_interval)
        else:
            move_progress = 1.0

        # ── Draw ──────────────────────────────────────────────────────────────
        screen.blit(assets["bg"], (0, 0))
        draw_board(screen, assets)

        # Fire tiles sit on top of grass, underneath obstacles and snakes
        if fire_tiles:
            draw_fire_tiles(screen, assets, fire_tiles)

        draw_border(screen, assets)

        if obstacles:
            draw_obstacles(screen, assets, obstacles)

        if state:
            draw_pies(screen, assets, state["pies"])

            p1 = state["player1"]
            p2 = state["player2"]

            if mode == "player":
                left_data  = p1 if p1["username"] == my_name else p2
                right_data = p2 if p1["username"] == my_name else p1
            else:
                left_data, right_data = p1, p2

            prev_p1 = prev_state["player1"]["snake"] if prev_state else p1["snake"]
            prev_p2 = prev_state["player2"]["snake"] if prev_state else p2["snake"]

            draw_snake(screen, p1["snake"], prev_p1, move_progress,
                       tuple(p1["color"]), p1["head_style"], p1["head_emoji"],
                       p1["invincible"], fonts)
            draw_snake(screen, p2["snake"], prev_p2, move_progress,
                       tuple(p2["color"]), p2["head_style"], p2["head_emoji"],
                       p2["invincible"], fonts)

            draw_hud(screen, left_data, right_data,
                     state["time_left"], fonts, my_name, mode, assets,
                     sudden_death)

        sidebar_out = draw_sidebar(screen, cheer_msgs, spectator_count,
                                   mode, input_text, input_active, fonts, assets,
                                   sidebar_bubbles)
        leave_btn = draw_bottom_bar(screen, spectator_count, fonts, mode)

        pygame.display.flip()

    if music_started:
        _stop_background_music()

    return result
