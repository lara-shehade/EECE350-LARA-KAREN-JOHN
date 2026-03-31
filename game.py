# =============================================================================
# game.py — Πthon Arena
# =============================================================================
# Pure game logic — no sockets, no pygame, no rendering.
#
# The server creates one GameState instance per match and calls:
#   game = GameState(p1_info, p2_info)
#   game.set_direction(username, "UP")   ← called when MOVE received
#   game.tick()                          ← called every SNAKE_MOVE_INTERVAL_MS
#   state = game.get_state()             ← called after tick to broadcast
#   over, winner = game.check_game_over()
# =============================================================================

import random
import time

from constants import (
    GRID_COLS, GRID_ROWS,
    SNAKE_MOVE_INTERVAL_MS,
    INVINCIBILITY_MS,
    OPPOSITE,
)

# =============================================================================
# SERVER-SIDE CONSTANTS
# =============================================================================

# ── Snake ─────────────────────────────────────────────────────────────────────
# Head first, then body segments
SNAKE1_START     = [(3, 7), (2, 7), (1, 7), (0, 7)]     # moves RIGHT
SNAKE2_START     = [(16, 7), (17, 7), (18, 7), (19, 7)]  # moves LEFT
SNAKE1_START_DIR = (1,  0)   # RIGHT
SNAKE2_START_DIR = (-1, 0)   # LEFT

# ── Health ────────────────────────────────────────────────────────────────────
HEALTH_START = 100
HEALTH_MAX   = 100

# Pie rewards (health gained on collection)
PIE_HEALTH = {
    "blueberry":  14,
    "cherry":     15,
    "strawberry": 18,
    "lemon":       5,
    "orange":      8,
}

# Obstacle damage (health lost on collision)
OBSTACLE_DAMAGE = {
    "cactus":    15,
    "rock":      10,
    "3rocks":    20,
    "spikes":    25,
    "dirtyPond":  8,
}

# Collision damage
WALL_DAMAGE      = 20   # snake tries to move into the border wall
SELF_HIT_DAMAGE  = 30   # snake head enters its own body
SNAKE_HIT_DAMAGE = 25   # snake head enters the other snake's body

# ── Pies ──────────────────────────────────────────────────────────────────────
PIE_TYPES      = list(PIE_HEALTH.keys())
PIE_COUNT      = 3       # pies on the board at all times
PIE_RESPAWN_MS = 3000    # delay after eaten before new pie spawns

# ── Obstacles ─────────────────────────────────────────────────────────────────
# Format: (col, row, type)
OBSTACLES = [
    # top-right 3R cluster
    (17, 1, "3rocks"),
    (18, 1, "3rocks"),
    (19, 1, "3rocks"),
    (17, 2, "3rocks"),
    # top area
    (5,  2, "cactus"),
    (13, 2, "rock"),
    # left side
    (1,  4, "dirtyPond"),
    # center spikes
    (9,  6, "spikes"),
    (11, 8, "spikes"),
    # right side
    (18, 11, "dirtyPond"),
    # bottom area
    (6,  11, "rock"),
    (14, 12, "cactus"),
    # bottom-left 3R cluster
    (2,  12, "3rocks"),
    (0,  13, "3rocks"),
    (1,  13, "3rocks"),
    (2,  13, "3rocks"),
]

# ── Game timing ───────────────────────────────────────────────────────────────
GAME_DURATION_S = 120


# =============================================================================
# HELPERS
# =============================================================================

def _now_ms():
    """Current time in milliseconds."""
    return int(time.time() * 1000)


def _obstacle_set():
    """Return a set of (col, row) for fast collision lookup."""
    return {(c, r) for c, r, _ in OBSTACLES}


def _clamp(val, lo, hi):
    return max(lo, min(hi, val))


# =============================================================================
# PLAYER STATE
# =============================================================================

class Player:
    """Holds everything about one snake player."""

    def __init__(self, username, color, head_style, head_emoji, start_pos, start_dir):
        self.username   = username
        self.color      = color
        self.head_style = head_style
        self.head_emoji = head_emoji

        self.snake     = list(start_pos)   # list of (col, row), head first
        self.direction = start_dir         # current movement direction
        self._next_dir = start_dir         # buffered input (applied on next tick)

        self.health = HEALTH_START
        self.alive  = True

        # Timestamp (ms) until which this player cannot take damage.
        self._invincible_until = 0

    # ── Direction ─────────────────────────────────────────────────────────────

    def set_direction(self, direction):
        """
        Buffer a new direction. Ignores reversal (can't do a 180).
        Applied on the next tick so rapid keypresses don't skip a frame.
        """
        if direction != OPPOSITE.get(self.direction):
            self._next_dir = direction

    def _apply_direction(self):
        self.direction = self._next_dir

    # ── Invincibility ─────────────────────────────────────────────────────────

    def is_invincible(self):
        return _now_ms() < self._invincible_until

    def grant_invincibility(self):
        self._invincible_until = _now_ms() + INVINCIBILITY_MS

    # ── Damage / Heal ─────────────────────────────────────────────────────────

    def apply_damage(self, amount):
        """
        Apply damage if not invincible.
        Grants invincibility after the hit.
        Returns True if damage was actually applied.
        """
        if self.is_invincible():
            return False
        self.health = _clamp(self.health - amount, 0, HEALTH_MAX)
        self.grant_invincibility()
        if self.health <= 0:
            self.alive = False
        return True

    def apply_heal(self, amount):
        self.health = _clamp(self.health + amount, 0, HEALTH_MAX)

    # ── Movement ──────────────────────────────────────────────────────────────

    def move(self):
        """
        Attempt to move the snake one step in the current direction.

        Wall behavior (Option B — stops at wall):
          If the new head position is outside the grid, the snake stays
          in place, takes WALL_DAMAGE, and iframes kick in.
          The tail is still popped so the body slides forward.

        Returns: "ok" | "wall"
        """
        self._apply_direction()

        head    = self.snake[0]
        new_col = head[0] + self.direction[0]
        new_row = head[1] + self.direction[1]

        # ── Wall hit ──────────────────────────────────────────────────────────
        if new_col < 0 or new_col >= GRID_COLS or new_row < 0 or new_row >= GRID_ROWS:
            # Snake stays exactly where it is — no position change at all.
            # This avoids the duplicate-head bug that would trigger self-collision.
            self.apply_damage(WALL_DAMAGE)
            return "wall"

        # ── Normal move ───────────────────────────────────────────────────────
        self.snake.insert(0, (new_col, new_row))
        self.snake.pop()   # no growth — health only
        return "ok"

    # ── Serialisation ─────────────────────────────────────────────────────────

    def to_dict(self):
        return {
            "username":   self.username,
            "snake":      self.snake,
            "color":      self.color,
            "health":     self.health,
            "head_style": self.head_style,
            "head_emoji": self.head_emoji,
            "invincible": self.is_invincible(),  # client uses this to flash
        }


# =============================================================================
# GAME STATE
# =============================================================================

class GameState:
    """
    Manages one complete match between two players.

    Lifecycle (in server game loop thread):
        game = GameState(p1_info, p2_info)
        while True:
            time.sleep(SNAKE_MOVE_INTERVAL_MS / 1000)
            game.tick()
            state = game.get_state()
            # broadcast state to both players + spectators
            over, winner = game.check_game_over()
            if over: break
    """

    def __init__(self, p1_username, p1_info, p2_username, p2_info):
        """
        Takes username separately because in connected_players the username
        is the dict KEY, not a field inside the dict.

        Usage in server.py:
            game = GameState(
                challenger, connected_players[challenger],
                accepter,   connected_players[accepter],
            )

        p1_info / p2_info are the values from connected_players:
            {
                "socket":     ...,
                "color":      [r, g, b],
                "head_style": str,
                "head_emoji": str | None,
                "address":    ...,
                "status":     str,
            }
        """
        self.player1 = Player(
            username   = p1_username,
            color      = p1_info["color"],
            head_style = p1_info.get("head_style", "classic"),
            head_emoji = p1_info.get("head_emoji", None),
            start_pos  = SNAKE1_START,
            start_dir  = SNAKE1_START_DIR,
        )
        self.player2 = Player(
            username   = p2_username,
            color      = p2_info["color"],
            head_style = p2_info.get("head_style", "classic"),
            head_emoji = p2_info.get("head_emoji", None),
            start_pos  = SNAKE2_START,
            start_dir  = SNAKE2_START_DIR,
        )

        self.obstacles = list(OBSTACLES)
        self._obs_set  = _obstacle_set()

        self.pies: list = []
        self._pending_respawns: list = []

        # Spawn initial pies
        for _ in range(PIE_COUNT):
            pie = self._spawn_pie()
            if pie:
                self.pies.append(pie)

        self._start_time_ms = _now_ms()
        self.game_over      = False
        self.winner         = None   # username string or "TIE"

    # ── Direction input ───────────────────────────────────────────────────────

    def set_direction(self, username, direction_str):
        """Called by server when MOVE message received."""
        direction_map = {
            "UP":    (0, -1),
            "DOWN":  (0,  1),
            "LEFT":  (-1, 0),
            "RIGHT": (1,  0),
        }
        direction = direction_map.get(direction_str)
        if direction is None:
            return
        if self.player1.username == username:
            self.player1.set_direction(direction)
        elif self.player2.username == username:
            self.player2.set_direction(direction)

    # ── Pie spawning ──────────────────────────────────────────────────────────

    def _occupied_cells(self):
        cells = set()
        cells.update(self.player1.snake)
        cells.update(self.player2.snake)
        cells.update((c, r) for c, r, _ in self.pies)
        cells.update(self._obs_set)
        return cells

    def _spawn_pie(self):
        """Try to find a free cell. Returns (col, row, type) or None."""
        occupied = self._occupied_cells()
        for _ in range(100):
            col  = random.randint(0, GRID_COLS - 1)
            row  = random.randint(0, GRID_ROWS - 1)
            kind = random.choice(PIE_TYPES)
            if (col, row) not in occupied:
                return (col, row, kind)
        return None

    def _process_respawns(self):
        """Spawn pies whose respawn timer has expired."""
        now          = _now_ms()
        still_pending = []
        for spawn_at in self._pending_respawns:
            if now >= spawn_at:
                pie = self._spawn_pie()
                if pie:
                    self.pies.append(pie)
            else:
                still_pending.append(spawn_at)
        self._pending_respawns = still_pending

    # ── Collision detection ───────────────────────────────────────────────────

    def _check_obstacle_collision(self, player: Player):
        head = player.snake[0]
        for col, row, kind in self.obstacles:
            if head == (col, row):
                player.apply_damage(OBSTACLE_DAMAGE.get(kind, 0))
                return

    def _check_pie_collection(self, player: Player):
        head = player.snake[0]
        for i, (col, row, kind) in enumerate(self.pies):
            if head == (col, row):
                player.apply_heal(PIE_HEALTH.get(kind, 0))
                self.pies.pop(i)
                self._pending_respawns.append(_now_ms() + PIE_RESPAWN_MS)
                return

    def _check_self_collision(self, player: Player):
        head = player.snake[0]
        if head in player.snake[1:]:
            player.apply_damage(SELF_HIT_DAMAGE)

    def _check_snake_collision(self, attacker: Player, defender: Player):
        head = attacker.snake[0]
        if head in defender.snake:
            attacker.apply_damage(SNAKE_HIT_DAMAGE)

    # ── Tick ──────────────────────────────────────────────────────────────────

    def tick(self):
        """
        Advance the game by one step.
        Called every SNAKE_MOVE_INTERVAL_MS by the server game loop thread.
        """
        if self.game_over:
            return

        # 1. Move (wall damage handled inside Player.move)
        self.player1.move()
        self.player2.move()

        # 2. Obstacle collisions
        self._check_obstacle_collision(self.player1)
        self._check_obstacle_collision(self.player2)

        # 3. Pie collection
        self._check_pie_collection(self.player1)
        self._check_pie_collection(self.player2)

        # 4. Self collision
        self._check_self_collision(self.player1)
        self._check_self_collision(self.player2)

        # 5. Snake-on-snake collision
        self._check_snake_collision(self.player1, self.player2)
        self._check_snake_collision(self.player2, self.player1)

        # 6. Pie respawns
        self._process_respawns()

        # 7. Game over check
        self._evaluate_game_over()

    # ── Game over ─────────────────────────────────────────────────────────────

    def time_left(self):
        """Seconds remaining in the match (never negative)."""
        elapsed = (_now_ms() - self._start_time_ms) / 1000
        return max(0, GAME_DURATION_S - int(elapsed))

    def _evaluate_game_over(self):
        p1, p2 = self.player1, self.player2

        if not p1.alive and not p2.alive:
            self.game_over = True
            self.winner    = "TIE"
            return
        if not p1.alive:
            self.game_over = True
            self.winner    = p2.username
            return
        if not p2.alive:
            self.game_over = True
            self.winner    = p1.username
            return
        if self.time_left() <= 0:
            self.game_over = True
            if p1.health > p2.health:
                self.winner = p1.username
            elif p2.health > p1.health:
                self.winner = p2.username
            else:
                self.winner = "TIE"

    def check_game_over(self):
        """Returns (is_over, winner_string). winner is username or 'TIE'."""
        return self.game_over, self.winner

    # ── State snapshot ────────────────────────────────────────────────────────

    def get_state(self):
        """
        Returns a dict ready to pass to protocol.game_state().

        protocol.game_state(
            player1   = state["player1"],
            player2   = state["player2"],
            pies      = state["pies"],
            obstacles = state["obstacles"],
            time_left = state["time_left"],
        )
        """
        return {
            "player1":   self.player1.to_dict(),
            "player2":   self.player2.to_dict(),
            "pies":      self.pies,
            "obstacles": self.obstacles,
            "time_left": self.time_left(),
        }