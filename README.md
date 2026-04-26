# EECE350-LARA-KAREN-JOHN
# Πthon Arena 

A multiplayer snake battle game built with Python and Pygame.

## How to Run

1. Start the server:
   python server.py 5000

2. Start a client (one per player):
   python client.py 5000

## Notes
- The port can be any number between 1024 and 65535, not necessarily 5000.
- Each client must be run in a separate terminal.
- For same-machine testing, use IP `127.0.0.1` 
- For LAN play, update `SERVER_HOST` in `client.py` to the server machine's IP (line 13). 

## Requirements
- Python 3.x
- Pygame