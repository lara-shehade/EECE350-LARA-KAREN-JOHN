---
name: p2p-chat-testing
description: Test Πthon Arena's peer-to-peer chat (chat.py / P2PChat) in isolation — public messages, private messages, malformed input, and disconnect handling — without launching two full game clients and a server. Use when the user reports chat/P2P issues, wants to test messaging, or mentions dropped/missing/garbled peer messages.
---

# P2P Chat Testing

`P2PChat` (in `chat.py`) is testable on its own: it only needs a username and
a real TCP port, not the server, login screen, or lobby UI. Normally
reproducing a chat bug meant running two full clients plus the server.
This skill spins up two `P2PChat` instances directly in a script instead.

## Known limitation to flag, not silently "fix"

In `chat.py`, `update_players()` stores peer info as:
```python
self._players[p["username"]] = {
    "ip": "127.0.0.1",   # same machine for now
    "chat_port": p.get("chat_port", 0),
}
```
The peer IP is **hardcoded to `127.0.0.1`**, regardless of the peer's actual
address. This means P2P chat can currently only work between processes on
the *same* machine — cross-machine chat will try to connect to localhost and
fail or hit the wrong process. This is very likely the source of
intermittent "frequent issues" reported when testing across machines, not a
timing bug. Flag this to the user; don't patch it without confirming scope,
since the real fix means the server needs to start including each peer's
real IP in `PLAYERS_LIST`, which touches `server.py` and `protocol.py` too.

## How to run the test harness

```bash
python .claude/skills/p2p-chat-testing/scripts/p2p_chat_test.py
```

This runs, same-machine (which is what the current code supports), and
checks:
1. **Public message delivery** — Alice's public message reaches Bob.
2. **Private message delivery** — a private message is marked private and
   addressed only to the intended recipient.
3. **Malformed input** — a raw line that doesn't match `kind|sender|message`
   is dropped, not crashing the receive loop.
4. **Peer departure** — removing a peer from the player list closes its
   connection and emits a "left the chat" system message.

Each check prints `PASS`/`FAIL` with details on failure.

## Workflow

1. Run the script after any change to `chat.py` or before investigating a
   reported chat bug — it isolates whether the bug is in `P2PChat` itself
   versus in how the lobby/game wires it up.
2. If everything here passes but the user's real bug is cross-machine, point
   to the "Known limitation" section above rather than guessing further.
3. Extend `scripts/p2p_chat_test.py` with a new check the same way if a new
   kind of chat bug shows up — it's meant to grow with real bugs found.
