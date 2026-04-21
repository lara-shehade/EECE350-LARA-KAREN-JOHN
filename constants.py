# =============================================================================
# constants.py — Πthon Arena
# =============================================================================
# SHARED constants only — needed by both server (game.py) and client.
# Everything else lives at the top of game.py or client.py.
# =============================================================================

# ── Grid ─────────────────────────────────────────────────────────────────────
# NOTE: once you add a HUD strip or side panel, update GRID_COLS/ROWS to use
#       BOARD_WIDTH/HEIGHT instead of WINDOW_WIDTH/HEIGHT.
TILE_SIZE  = 40
GRID_COLS  = 20   # 800px // 40
GRID_ROWS  = 15   # 600px // 40

# ── Timing ────────────────────────────────────────────────────────────────────
SNAKE_MOVE_INTERVAL_MS = 250   # server ticks + client animates at this rate
GAME_STATE_SEND_INTERVAL_MS = 50  # server broadcasts state without speeding movement

# ── Invincibility ─────────────────────────────────────────────────────────────
# Server grants this after any damage hit.
# Client uses it to flash the snake visually.
INVINCIBILITY_MS = 1500

# ── Sudden Death ──────────────────────────────────────────────────────────────
# Triggered when this many seconds remain on the clock.
SUDDEN_DEATH_THRESHOLD_S = 30
# Server ticks this many times faster during sudden death (2 = double speed).
SUDDEN_DEATH_SPEED_MULT  = 1.7
# Damage dealt each time a snake steps on a fire tile.
# Intentionally higher than any regular obstacle (max obstacle = 25).
FIRE_DAMAGE              = 30

# ── Directions ────────────────────────────────────────────────────────────────
UP    = ( 0, -1)
DOWN  = ( 0,  1)
LEFT  = (-1,  0)
RIGHT = ( 1,  0)

DIRECTION_NAMES = {
    UP:    "UP",
    DOWN:  "DOWN",
    LEFT:  "LEFT",
    RIGHT: "RIGHT",
}

OPPOSITE = {
    UP:    DOWN,
    DOWN:  UP,
    LEFT:  RIGHT,
    RIGHT: LEFT,
}
