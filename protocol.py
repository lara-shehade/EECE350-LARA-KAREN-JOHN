#this file of the project acts as the communication between the client and the server
#It converts the Python data like lists and dictionaries into text messages thats can be sent through sockets
#Each message  follows the HEADER:body format
import json

# In class we learnt how buffers store data in waiting, meaning it stores unfinished incoming messages for each socket.
#Sometimes messages arrive in pieces, so we keep the partial data here until the full message is received
_buffers = {}

# =============================================================================
# SECTION 0: SOCKET HELPERS
# These handle the actual sending and receiving over the network.
# Every message ends with "\n" so the receiver knows where one message
# ends and the next begins (messages can arrive stuck together).
# =============================================================================



def send(sock, message):
    #we need this function to convert messages into bytes before sending to a socket
    #Sockets can only send bytes not normal Python string
    sock.sendall((message + "\n").encode('utf-8'))

def receive(sock):
    #the function receives message from the socket
    #It keeps reading data until it finds a full message ending with a newline
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
    #This function is used when a player connects to a server for the first time
    #It collects information like username,snake,head style, emoji selection, and chat port.
    #After that, it converts into JSON format and sends it as a JOIN message
    data = {
        "username":   username,
        "color":      color,
        "head_style": head_style,
        "head_emoji": head_emoji,
        "chat_port":  chat_port
    }
    return "JOIN:" + json.dumps(data)

def send_move(direction):
    #We send the player's movement direction to the server using this function
    #It tells the server how the snake should move during the next game update
    return f"MOVE:{direction}"


def send_challenge(opponent):
    #It sends a challenge request to another player
    #It used when the player clicks on the challenge button in the lobby 
    return f"CHALLENGE:{opponent}"


def send_accept(opponent):
    #It sends an accept message which is used when a player gets a challenge request and chooses to accept
    return f"ACCEPT:{opponent}"


def send_decline(opponent):
    #It rejects a challenge, same idea as the above but here it rejects the message.
    return f"DECLINE:{opponent}"


def send_watch():
   #It is used to watch an active match between two players
    return "WATCH"


def send_chat(message):
    #It allows the players to communicate with eachother using built-in chat system
    return f"CHAT:{message}"


def send_play_bot():
    #This is specific for the AI snake where a player can chose to play against
    return "PLAY_BOT"


def send_leave_watch():
    #It gives the spectator option to exit the match 
    return "LEAVE_WATCH"


# =============================================================================
# SECTION 2: SERVER → CLIENT MESSAGES
# These are called by the server to notify players about what's happening.
# =============================================================================

def username_taken():
    #tells the client that the username it typed is already taken
    return "USERNAME_TAKEN"


def username_ok():
    #tells the client that the username is accepted
    return "USERNAME_OK"


def players_list(players):
    #This message is used whenevr the lobby needs to be updated
    #It sends a message containing the current players
    return "PLAYERS_LIST:" + json.dumps(players)


def challenge_from(challenger):
    #it creates a message telling a player that someone challenged them
    return f"CHALLENGE_FROM:{challenger}"


def challenge_accepted(opponent):
   #tells the player that their challenge got accepted 
    return f"CHALLENGE_ACCEPTED:{opponent}"


def challenge_declined(opponent):
    #same as the previous function but instead it gets rejected
    return f"CHALLENGE_DECLINED:{opponent}"


def game_start():
   #it tells both players that the game should start
    return "GAME_START"


def game_state(player1, player2, pies, obstacles, time_left,
               sudden_death=False, fire_tiles=None, move_id=0):
  #this is a very important function because it is sent many times during the match 
  #It allows every player to see the same board, snake positions, healtg values, pies, obstacles, timer, and sudden death effects
    state = {
        "player1": {
            "username":   player1["username"],
            "snake":      player1["snake"],
            "color":      player1["color"],
            "health":     player1["health"],
            "head_style": player1["head_style"],
            "head_emoji": player1["head_emoji"],
            "direction":  player1.get("direction", "RIGHT"),
            "invincible": player1["invincible"]
        },
        "player2": {
            "username":   player2["username"],
            "snake":      player2["snake"],
            "color":      player2["color"],
            "health":     player2["health"],
            "head_style": player2["head_style"],
            "head_emoji": player2["head_emoji"],
            "direction":  player2.get("direction", "LEFT"),
            "invincible": player2["invincible"]
        },
        "pies":         pies,
        "obstacles":    obstacles,
        "time_left":    time_left,
        "move_id":      move_id,
        "sudden_death": sudden_death,
        "fire_tiles":   fire_tiles if fire_tiles is not None else [],
    }
    return "GAME_STATE:" + json.dumps(state)


def game_over(winner, health1, health2, reason="normal"):
   #it creates a message telling that the game has ended 
    data = {
        "winner":  winner,
        "health1": health1,
        "health2": health2,
        "reason":  reason,
    }
    return "GAME_OVER:" + json.dumps(data)


def waiting():
   #creates a message telling the client to wait 
    return "WAITING"


def fan_joined(username):
    #creates a message telling the players that a spectator has joined the match 
    return f"FAN_JOINED:{username}"


def player_disconnected(username):
    #tells the client that the player on the other end disconnected
    return f"DISCONNECTED:{username}"


# ── Rematch ───────────────────────────────────────────────────────────────────

def send_rematch():
   #creates a message from the client asking the server for a rematch 
    return "REMATCH"


def send_decline_rematch():
    #this message is sent when the server does not want a rematch anymore 
    return "DECLINE_REMATCH"


def rematch_from(username):
    #message telling a player that the ir previous opponent wants a rematch
    return f"REMATCH_FROM:{username}"


def rematch_queued(opponent):
    #confirms that the rematch request was saved
    return f"REMATCH_QUEUED:{opponent}"


def rematch_start():
#message telling both players that the rematch is starting 
    return "REMATCH_START"


def rematch_declined(username):
#messsage telling a player that the opponent declined the rematch 
    return f"REMATCH_DECLINED:{username}"


# =============================================================================
# SECTION 3: PARSERS (reading incoming messages)
# When a message arrives, these functions break it apart so we can use the data.
# =============================================================================

def parse(msg):
 #this function splits messages into the header and the body
 #the header tells us the type of message it is and the body contains the actual data 
    if ":" in msg:
        header, body = msg.split(":", 1)
        return header.strip(), body.strip()
    return msg.strip(), None


def parse_game_state(body):
#it converts the game state message body from JSON text back to python dictionary
    return json.loads(body)


def parse_players_list(body):
#it converts players list message body from JSON text back into a python list 
    return json.loads(body)


def parse_join(body):
    #converts the JOIN message body from JSON text back into python dictionary
    return json.loads(body)


def parse_game_over(body):
#converts game over // // // (same as above)
    data = json.loads(body)
    return data["winner"], data["health1"], data["health2"], data.get("reason", "normal")

def parse_chat(body):
   #it splits a chat message body into sender username and the actual message text
    parts = body.split(":", 1)
    return (parts[0], parts[1]) if len(parts) == 2 else (body, "")
