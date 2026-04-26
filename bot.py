# Each turn, the bot scores its possible next moves and picks the best one.
# It weighs up staying safe, reaching pies before it starves, and hunting a
# weakened enemy while trying to move in straight lines rather than zigzag.

import random
from collections import deque
from constants import GRID_COLS, GRID_ROWS

# Bot identity.

BOT_NAME = "PyBot"
BOT_INFO = {
    "color":      [148, 148, 158],
    "head_style": "robot",
    "head_emoji": None,
}

# How often the bot makes a decision.
THINK_EVERY = 1

# Small chance of choosing the second-best move.
MISTAKE_RATE    = 0.12   # normal play
MISTAKE_RATE_SD = 0.16   # sudden death

# Health values that affect the bot's behavior.
LOW_HP_THRESH  = 40
AGGRO_HP_SELF  = 65
AGGRO_HP_ENEMY = 45

# Values used to estimate how much free space a move leads to.
FLOOD_CAP      = 40
TRAP_THRESHOLD = 6

# Weights used when scoring each move.
W_PIE_DIST    = 10    # penalty for being farther from the nearest pie
W_PIE_URGENT  = 6     # extra pie penalty when health is low
W_CONTINUE    = 15    # reward for continuing in the same direction
W_FLOOD       = 2     # reward for moves with more open space
W_FLOOD_TRAP  = 200   # big penalty for moves that lead into small trapped areas
W_NEAR_FIRE   = 8     # penalty for being close to fire
W_AGGRO       = 3     # reward for moving closer to the enemy when attacking

_DIRS     = [(0, -1), (0, 1), (-1, 0), (1, 0)]
_DIR_NAME = {(0,-1): "UP", (0,1): "DOWN", (-1,0): "LEFT", (1,0): "RIGHT"}


# Main bot class.

class GreedyBot:
    """One instance per game session."""

    def __init__(self, bot_username, human_username):
        self._bot       = bot_username
        self._human     = human_username
        self._tick      = 0
        self._last_dir  = None   # remembers the last direction to reduce zigzagging

    def decide(self, game):
        self._tick += 1
        if self._tick % THINK_EVERY != 0:
            return None

        state  = game.get_state()
        sudden = state.get("sudden_death", False)

        fire_set = {(ft[0], ft[1]) for ft in state.get("fire_tiles", [])}

        p1, p2 = state["player1"], state["player2"]
        if p1["username"] == self._bot:
            bot_data, human_data = p1, p2
        else:
            bot_data, human_data = p2, p1

        snake = bot_data["snake"]
        if not snake:
            return None

        head = (snake[0][0], snake[0][1])

        # Current direction from body geometry
        if len(snake) >= 2:
            neck     = (snake[1][0], snake[1][1])
            cur_dir  = (head[0] - neck[0], head[1] - neck[1])
            anti_dir = (-cur_dir[0], -cur_dir[1])
        else:
            cur_dir  = self._last_dir or (1, 0)
            anti_dir = None

        obs_set = {(o[0], o[1]) for o in state["obstacles"]}
        blocked = self._build_blocked(state, obs_set, fire_set)

        candidates = []
        for dc, dr in _DIRS:
            if (dc, dr) == anti_dir:
                continue
            nc, nr = head[0] + dc, head[1] + dr
            if self._is_wall(nc, nr):
                continue
            if (nc, nr) in blocked:
                continue

            score = self._score(
                nc, nr, (dc, dr), cur_dir,
                state, fire_set, blocked,
                bot_data, human_data, sudden,
            )
            candidates.append((score, (dc, dr)))

        if not candidates:
            # Desperate escape — pick any non-reversal non-wall direction
            for dc, dr in _DIRS:
                if (dc, dr) == anti_dir:
                    continue
                nc, nr = head[0] + dc, head[1] + dr
                if not self._is_wall(nc, nr):
                    self._last_dir = (dc, dr)
                    return _DIR_NAME[(dc, dr)]
            return None

        candidates.sort(key=lambda x: -x[0])

        rate = MISTAKE_RATE_SD if sudden else MISTAKE_RATE
        if len(candidates) >= 2 and random.random() < rate:
            _, direction = candidates[1]
        else:
            _, direction = candidates[0]

        self._last_dir = direction
        return _DIR_NAME[direction]

    ########################################################################################3

    def _is_wall(self, col, row):
        return col < 0 or col >= GRID_COLS or row < 0 or row >= GRID_ROWS

    def _build_blocked(self, state, obs_set, fire_set):
        blocked = set()
        blocked.update(obs_set)
        blocked.update(fire_set)
        for pdata in [state["player1"], state["player2"]]:
            snake = pdata["snake"]
            for seg in snake[1:-1]:
                blocked.add((seg[0], seg[1]))
            if snake:
                blocked.add((snake[0][0], snake[0][1]))
        return blocked

    def _flood_fill(self, start_col, start_row, blocked):
        visited = {(start_col, start_row)}
        queue   = deque([(start_col, start_row)])
        count   = 0
        while queue and count < FLOOD_CAP:
            col, row = queue.popleft()
            count += 1
            for dc, dr in _DIRS:
                nc, nr = col + dc, row + dr
                if self._is_wall(nc, nr):
                    continue
                if (nc, nr) in blocked:
                    continue
                if (nc, nr) in visited:
                    continue
                visited.add((nc, nr))
                queue.append((nc, nr))
        return count

    def _score(self, col, row, direction, cur_dir,
               state, fire_set, blocked,
               bot_data, human_data, sudden):
        score = 0

        # ── Direction commitment ───────────────────────────────────────────────
        # Reward keeping the same heading — makes the bot move purposefully
        # in straight lines rather than zigzagging every tick.
        if direction == cur_dir:
            score += W_CONTINUE

        # ── Flood fill — avoid pockets ─────────────────────────────────────────
        free_cells = self._flood_fill(col, row, blocked)
        if free_cells < TRAP_THRESHOLD:
            score -= W_FLOOD_TRAP
        else:
            score += free_cells * W_FLOOD

        # ── Pie distance ───────────────────────────────────────────────────────
        pies = state["pies"]
        if pies:
            min_dist = min(abs(col - p[0]) + abs(row - p[1]) for p in pies)
            score -= min_dist * W_PIE_DIST
            if bot_data["health"] < LOW_HP_THRESH:
                score -= min_dist * W_PIE_URGENT

        # ── Fire adjacency ─────────────────────────────────────────────────────
        for dc2, dr2 in _DIRS:
            if (col + dc2, row + dr2) in fire_set:
                score -= W_NEAR_FIRE

        # ── Aggression ─────────────────────────────────────────────────────────
        if (bot_data["health"] > AGGRO_HP_SELF
                and human_data["health"] < AGGRO_HP_ENEMY
                and human_data["snake"]):
            human_head = human_data["snake"][0]
            score -= (abs(col - human_head[0])
                      + abs(row - human_head[1])) * W_AGGRO

        return score
