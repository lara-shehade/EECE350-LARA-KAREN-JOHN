# Πthon Arena — Project Memory

Multiplayer Snake game. Python client-server over raw TCP sockets, `pygame` UI.
No package manager config yet — dependencies are `pygame` (stdlib otherwise:
`socket`, `threading`, `json`, `queue`).

## Architecture

- `server.py` — authoritative game server. Owns all game state. Runs the
  accept loop + one thread per connected client + a game-tick loop.
- `client.py` — connects to the server, owns the pygame main loop, dispatches
  to whichever screen is active (login → lobby → game).
- `protocol.py` — the wire format. Every message is `HEADER:body\n`. Client
  and server both import this; it is the single source of truth for message
  shapes. **Any new message type must be added here, not inlined elsewhere.**
- `game.py` — `GameState`: core snake/grid logic, collision, scoring. Framework
  agnostic (no pygame, no sockets) — keep it that way so it stays testable.
- `game_screen.py`, `lobby.py`, `login.py`, `chat.py` — pygame screens/widgets.
- `bot.py` — `GreedyBot`, a simple AI opponent used as a stand-in player.
- `constants.py` — grid size, tick interval, speed multipliers, etc. Change
  tuning values here, not hardcoded in gameplay files.

## Conventions

- New client→server or server→client message: define the header constant and
  encode/decode helpers in `protocol.py` first, then wire up call sites.
- Keep `game.py` free of pygame/socket imports — game logic must stay unit
  testable without a display or network connection.
- Tuning constants (speeds, grid size, intervals) go in `constants.py`, never
  as magic numbers in `game.py` / `server.py`.
- Server state is mutated from multiple threads (one per client + game loop);
  when touching `server.py`, check existing locking before adding new shared
  state.

## Running it

```
python server.py 5555
python client.py        # one per player, connects to server
```

## Known gaps (be aware, don't silently "fix" as drive-by cleanup)

- No `requirements.txt` yet — pygame version isn't pinned anywhere.
- No automated tests. `game.py` (pure logic) is the highest-value place to
  start once we add a test setup.
- No linting/formatting config yet.

## Working style

- Prefer small, reviewable changes over broad rewrites — flag anything that
  would require touching more than one of {protocol, game logic, UI} at once.
- Don't add dependencies without calling it out first (no `requirements.txt`
  to lean on yet).
