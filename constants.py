#shared constants only

#grid
TILE_SIZE  = 40
GRID_COLS  = 20   # 800px // 40
GRID_ROWS  = 15   # 600px // 40

# timing
SNAKE_MOVE_INTERVAL_MS = 250   # server ticks + client animates at this rate
GAME_STATE_SEND_INTERVAL_MS = 50  # server broadcasts state without speeding movement

# invincibility: snake flashes visually
INVINCIBILITY_MS = 1500

# sudden death
SUDDEN_DEATH_THRESHOLD_S = 30
SUDDEN_DEATH_SPEED_MULT  = 1.7
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
