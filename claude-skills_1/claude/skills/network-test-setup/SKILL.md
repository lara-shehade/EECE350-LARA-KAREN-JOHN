---
name: network-test-setup
description: Detect this machine's LAN IP and prepare Πthon Arena for a multi-machine test session, instead of manually running ipconfig/ip-addr and hand-editing client.py's SERVER_HOST. Use when the user wants to test the game across machines, mentions LAN IP, multiplayer testing, or SERVER_HOST.
---

# Network Test Setup

`client.py` currently hardcodes the server address:
`SERVER_HOST = "127.0.0.1"  # change to LAN IP for multi-machine play`.
Every LAN test session has meant: find this machine's IP manually, edit the
constant, test, then remember to revert it before committing. This skill
replaces that with one script plus a small one-time code change.

## Part 1 — detect the IP (works today, no code change needed)

Run `scripts/lan_ip.py`. It finds the LAN-facing IP the same way `ip route` /
`ipconfig` would (opening a UDP socket toward a public address and reading
back the local address the OS chose — no packets actually need to leave the
network for this to work), then prints it and writes it to `local_config.py`
at the repo root:

```bash
python .claude/skills/network-test-setup/scripts/lan_ip.py
```

This produces `local_config.py`:
```python
SERVER_HOST = "192.168.1.42"
```

`local_config.py` is meant to be **gitignored** — it's per-machine, not
committed. Add `local_config.py` to `.gitignore` if it isn't already there.

## Part 2 — make client.py use it (one-time, needs approval)

This part edits real source (`client.py`), so treat it as a single reviewable
stage (see the `stage-change-delivery` skill) rather than doing it silently:

Replace the hardcoded line in `client.py`:
```python
SERVER_HOST = "127.0.0.1"   # change to LAN IP for multi-machine play
```
with a fallback import:
```python
try:
    from local_config import SERVER_HOST
except ImportError:
    SERVER_HOST = "127.0.0.1"  # default: same-machine testing
```

After this one change, testing across machines becomes: run
`scripts/lan_ip.py` on the server machine, run the client anywhere on the
same LAN, no code edits and nothing to remember to revert.

## Workflow

1. Run `scripts/lan_ip.py` to get/refresh the current LAN IP.
2. If `client.py` hasn't been patched yet (Part 2), propose that as one
   small stage, get approval, then apply it.
3. Confirm `local_config.py` is in `.gitignore` so it's never committed.
