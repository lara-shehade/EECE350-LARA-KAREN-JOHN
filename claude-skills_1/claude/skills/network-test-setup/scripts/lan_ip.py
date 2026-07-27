#!/usr/bin/env python3
"""
lan_ip.py — detect this machine's LAN-facing IP and write it to
local_config.py at the repo root, for use by client.py during multi-machine
testing.

No packets need to actually be sent for this to work: opening a UDP socket
and "connecting" it to a public address just asks the OS to pick which local
interface/IP it would use to route there, which is exactly the LAN IP you'd
otherwise get from `ip addr` / `ipconfig`.
"""
import os
import socket
import sys

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
OUTPUT_PATH = os.path.join(REPO_ROOT, "local_config.py")


def detect_lan_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except OSError:
        ip = "127.0.0.1"
        print("Warning: could not detect a LAN IP, falling back to 127.0.0.1", file=sys.stderr)
    finally:
        s.close()
    return ip


def main():
    ip = detect_lan_ip()
    with open(OUTPUT_PATH, "w") as f:
        f.write(f'SERVER_HOST = "{ip}"\n')
    print(f"Detected LAN IP: {ip}")
    print(f"Wrote {OUTPUT_PATH}")
    print("Make sure local_config.py is in .gitignore (it's per-machine, not committed).")


if __name__ == "__main__":
    main()
