#!/usr/bin/env python3
"""
p2p_chat_test.py — exercise P2PChat (chat.py) directly, two peers,
same machine, no server/login/lobby/game required.

Run from anywhere; it locates the repo root relative to this file and
imports chat.py from there.
"""
import os
import socket
import sys
import time

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
sys.path.insert(0, REPO_ROOT)

from chat import P2PChat  # noqa: E402

PASS = "PASS"
FAIL = "FAIL"
results = []


def check(name, condition, detail=""):
    status = PASS if condition else FAIL
    results.append((name, status, detail))
    print(f"[{status}] {name}" + (f" — {detail}" if detail and status == FAIL else ""))


def wait_for(predicate, timeout=2.0, interval=0.05):
    start = time.time()
    while time.time() - start < timeout:
        if predicate():
            return True
        time.sleep(interval)
    return False


def main():
    alice = P2PChat("Alice")
    bob = P2PChat("Bob")
    alice.start()
    bob.start()

    try:
        # Wire each peer's view of the other, same shape update_players()
        # expects from a PLAYERS_LIST message.
        alice.update_players([
            {"username": "Bob", "chat_port": bob.get_port(), "status": "lobby"},
        ])
        bob.update_players([
            {"username": "Alice", "chat_port": alice.get_port(), "status": "lobby"},
        ])

        # --- Check 1: public message delivery ---------------------------------
        alice.send_public("gl hf")
        got_public = wait_for(
            lambda: any(
                m["from"] == "Alice" and m["message"] == "gl hf" and not m["private"]
                for m in list(bob._messages.queue)
            )
        )
        check("public message delivery", got_public,
              "Bob never received Alice's public message")

        # --- Check 2: private message delivery ---------------------------------
        alice.send_private("Bob", "want to rematch?")
        got_private = wait_for(
            lambda: any(
                m["from"] == "Alice" and m["message"] == "want to rematch?" and m["private"]
                for m in list(bob._messages.queue)
            )
        )
        check("private message delivery", got_private,
              "Bob never received Alice's private message")

        # --- Check 3: malformed input doesn't crash the receive loop ----------
        raw_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            raw_sock.connect(("127.0.0.1", bob.get_port()))
            raw_sock.sendall(b"not-a-valid-message\n")
            time.sleep(0.2)
            # Bob's accept/receive threads should still be alive and Bob
            # should still be reachable for a normal message afterward.
            alice.send_public("still here?")
            still_works = wait_for(
                lambda: any(
                    m["message"] == "still here?" for m in list(bob._messages.queue)
                )
            )
            check("malformed input is ignored, not fatal", still_works,
                  "receive loop appears to have died after malformed input")
        finally:
            raw_sock.close()

        # --- Check 4: peer departure closes the connection + notifies ---------
        bob.update_players([])  # Alice "left"
        got_left_notice = wait_for(
            lambda: any(
                m.get("system") and "Alice" in m["message"] and "left" in m["message"]
                for m in list(bob._messages.queue)
            )
        )
        check("peer departure emits a system message", got_left_notice,
              "Bob never saw an 'Alice left the chat' system message")

    finally:
        alice.stop()
        bob.stop()

    failed = [r for r in results if r[1] == FAIL]
    print()
    print(f"{len(results) - len(failed)}/{len(results)} checks passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
