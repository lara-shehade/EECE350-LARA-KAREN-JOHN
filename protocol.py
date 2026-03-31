# protocol.py
# =============================================================================
# This file is the "translator" for our multiplayer snake game.
#
# WHY DO WE NEED THIS?
# Sockets can ONLY send plain text (strings). You can't send a Python list
# or dictionary through a socket directly. So every time we want to send
# data between the client and server, we need to:
#   1. Convert it into a string  →  send it over the network
#   2. Receive the string        →  convert it back into usable Python data
#
# HOW MESSAGES WORK:
# Every message follows this format:  HEADER:body
#   - HEADER tells you what KIND of message it is (like MOVE, CHALLENGE, etc.)
#   - body carries the actual DATA (like "UP", "john", or a JSON string)
#   - Example: "MOVE:UP" means "this is a MOVE message, and the direction is UP"
#
# This file is split into 4 sections:
#   1. Socket helpers   (send and receive over the network)
#   2. Client → Server  (messages the player's app sends)
#   3. Server → Client  (messages the server sends back)
#   4. Parsers          (functions that read and decode incoming messages)
# =============================================================================

import json

# buffer dictionary 
_buffers = {}

# =============================================================================
# SECTION 0: SOCKET HELPERS
# These handle the actual sending and receiving over the network.
# Every message ends with "\n" so the receiver knows where one message
# ends and the next begins (messages can arrive stuck together).
# =============================================================================



def send(sock, message):
    """
    Send a message through a socket, with newline delimiter, then encodes to bytes.
    Parameters:
        sock:    the socket to send through
        message: the string to send (e.g. "USERNAME_OK" or "MOVE:UP")
    """
    sock.sendall((message + "\n").encode('utf-8'))

def receive(sock):
    """
    Receive exactly ONE message from a socket.
    Uses the newline delimiter to split messages properly,
    even if multiple messages arrive in one recv() call.
    """
    # Get or create a buffer for this socket
    sock_id = id(sock)
    if sock_id not in _buffers:
        _buffers[sock_id] = ""
    
    # Keep reading until we have a complete line
    while "\n" not in _buffers[sock_id]:
        data = sock.recv(4096)
        if not data:
            # Connection closed
            _buffers.pop(sock_id, None)
            return ""
        _buffers[sock_id] += data.decode('utf-8')
    
    # Split on the first newline: take one message, keep the rest
    line, _buffers[sock_id] = _buffers[sock_id].split("\n", 1)
    return line.strip()


# =============================================================================
# SECTION 1: CLIENT → SERVER MESSAGES
# These are called by the client app when the player does something.
# =============================================================================

def send_join(username, color, head_style="classic", head_emoji=None, chat_port=0):
    """
    Player wants to join the server with a username, snake color, head style,
    and P2P chat port.

    Parameters:
        username:   string like "Lara"
        color:      list like [0, 180, 50] (RGB values)
        head_style: "classic" or "emoji"
        head_emoji: string like "^.^" (only used when head_style == "emoji"), or None
        chat_port:  the port this client is listening on for P2P chat connections.
                    0 means chat is not available (e.g. spectator who skipped setup).

    Returns:
        Formatted message string like:
        JOIN:{"username":"Lara","color":[0,180,50],"head_style":"emoji",
              "head_emoji":"^.^","chat_port":49832}
    """
    data = {
        "username":   username,
        "color":      color,
        "head_style": head_style,
        "head_emoji": head_emoji,
        "chat_port":  chat_port
    }
    return "JOIN:" + json.dumps(data)

def send_move(direction):
    """Player sends their snake's direction. direction = UP, DOWN, LEFT, or RIGHT."""
    return f"MOVE:{direction}"


def send_challenge(opponent):
    """Player wants to challenge another player to a game."""
    return f"CHALLENGE:{opponent}"


def send_accept(opponent):
    """Player accepts a challenge from someone."""
    return f"ACCEPT:{opponent}"


def send_decline(opponent):
    """Player declines a challenge from someone."""
    return f"DECLINE:{opponent}"


def send_watch():
    """A fan/spectator wants to watch the current game (advanced feature)."""
    return "WATCH"


def send_chat(message):
    """Player sends a chat message to the other player (advanced feature)."""
    return f"CHAT:{message}"


# =============================================================================
# SECTION 2: SERVER → CLIENT MESSAGES
# These are called by the server to notify players about what's happening.
# =============================================================================

def username_taken():
    """Server tells the client: 'sorry, that name is already in use'."""
    return "USERNAME_TAKEN"


def username_ok():
    """Server tells the client: 'your name was accepted, you're in'."""
    return "USERNAME_OK"


def players_list(players):
    """
    Server sends the list of online players.

    Parameters:
        players: list of dicts, e.g.:
            [{"username": "Lara", "color": [0,180,50],
              "head_style": "emoji", "head_emoji": "^.^", "status": "lobby"}, ...]

    Returns:
        Formatted message string like: PLAYERS_LIST:[{...}]
    """
    return "PLAYERS_LIST:" + json.dumps(players)


def challenge_from(challenger):
    """Server tells a player: 'hey, this person wants to fight you'."""
    return f"CHALLENGE_FROM:{challenger}"


def challenge_accepted(opponent):
    """Server tells the challenger: 'your opponent said yes, get ready'."""
    return f"CHALLENGE_ACCEPTED:{opponent}"


def challenge_declined(opponent):
    """Server tells the challenger: 'your opponent said no'."""
    return f"CHALLENGE_DECLINED:{opponent}"


def game_start():
    """Server tells both players: 'the game is starting NOW'."""
    return "GAME_START"


def game_state(player1, player2, pies, obstacles, time_left):
    """
    Server sends a full snapshot of the game to both players.
    This gets called every time the game updates (many times per second).

    Each player dict looks like:
        {"username": "john", "snake": [(col, row), ...],   # grid coordinates e.g. (3, 7)
         "color": [0,180,50], "health": 80}

    pies:       list of (x, y, type) for each pie on the board
    obstacles:  list of (x, y, type) for each obstacle
    time_left:  seconds remaining in the game (int)
    """
    state = {
        "player1": {
            "username":   player1["username"],
            "snake":      player1["snake"],
            "color":      player1["color"],
            "health":     player1["health"],
            "head_style": player1["head_style"],
            "head_emoji": player1["head_emoji"],
            "invincible": player1["invincible"]
        },
        "player2": {
            "username":   player2["username"],
            "snake":      player2["snake"],
            "color":      player2["color"],
            "health":     player2["health"],
            "head_style": player2["head_style"],
            "head_emoji": player2["head_emoji"],
            "invincible": player2["invincible"]
        },
        "pies":      pies,
        "obstacles": obstacles,
        "time_left": time_left
    }
    return "GAME_STATE:" + json.dumps(state)


def game_over(winner, health1, health2):
    """
    Server tells both players the game ended.
    winner is a username string, or "TIE" if it's a draw.
    """
    data = {
        "winner": winner,
        "health1": health1,
        "health2": health2
    }
    return "GAME_OVER:" + json.dumps(data)


def waiting():
    """Server tells a player: 'hang tight, waiting for another player'."""
    return "WAITING"


def fan_joined(username):
    """Server tells the players: 'a spectator just joined to watch'."""
    return f"FAN_JOINED:{username}"


def player_disconnected(username):
    """Server tells everyone: 'this player just disconnected'."""
    return f"DISCONNECTED:{username}"


# =============================================================================
# SECTION 3: PARSERS (reading incoming messages)
# When a message arrives, these functions break it apart so we can use the data.
# =============================================================================

def parse(msg):
    """
    Takes any raw message string and splits it into (header, body).

    Example:
        parse("MOVE:UP")            → ("MOVE", "UP")
        parse("GAME_STATE:{...}")   → ("GAME_STATE", "{...}")
        parse("WAITING")            → ("WAITING", None)
    """
    if ":" in msg:
        header, body = msg.split(":", 1)
        return header.strip(), body.strip()
    return msg.strip(), None


def parse_game_state(body):
    """Converts GAME_STATE JSON body back into a Python dictionary."""
    return json.loads(body)


def parse_players_list(body):
    """Converts PLAYERS_LIST JSON body back into a Python list."""
    return json.loads(body)


def parse_join(body):
    """Converts JOIN JSON body back into a Python dictionary.
    Returns dict with keys: username, color, head_style, head_emoji."""
    return json.loads(body)


def parse_game_over(body):
    """Converts GAME_OVER JSON body back into winner, health1, health2."""
    data = json.loads(body)
    return data["winner"], data["health1"], data["health2"]

def parse_chat(body):
    """Splits 'username:message' from a CHAT body.
    Returns (sender_username, message)."""
    parts = body.split(":", 1)
    return (parts[0], parts[1]) if len(parts) == 2 else (body, "")