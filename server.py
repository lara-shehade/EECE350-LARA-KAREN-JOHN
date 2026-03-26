import socket
import threading
import sys
import protocol

# =============================================================================
# SERVER — Πthon Arena
#
# STEP 1 (done): Connections + Usernames + Player List
# STEP 2 (done): Player Status + Challenge System + Spectators
# STEP 3 (todo): Game Logic (snake movement, pies, obstacles, collisions)
#
# How to run:
#   python server.py 5555
#
# How to test:
#   Terminal 1: python server.py 5555
#   Terminal 2: python test_client.py
# =============================================================================


# =============================================================================
# GLOBAL STATE
# These variables are shared across all client threads.
# Always use players_lock when reading/writing to prevent race conditions.
# =============================================================================

# Dictionary of all connected players.
# Key = username (string)
# Value = dictionary:
#   {
#       "socket":  socket object for sending messages to this player,
#       "color":   the snake color they chose (list of 3 ints, RGB),
#       "address": tuple of (IP, port),
#       "status":  one of "lobby", "in_game", "spectating"
#   }
connected_players = {}

# A lock to prevent two threads from modifying connected_players at the same time.
# Without this, if two players join at the exact same moment, the dictionary
# could get corrupted. The lock makes sure only one thread touches it at a time.
players_lock = threading.Lock()

# Tracks pending challenges that haven't been accepted or declined yet.
# Key   = username of the player who RECEIVED the challenge
# Value = username of the player who SENT the challenge
# Example: {"Ali": "Lara"} means Lara challenged Ali, waiting for Ali's response.
pending_challenges = {}

# Tracks the current active game session.
# Only ONE game can be active at a time (per the project spec).
# None means no game is happening right now.
# When active, format is:
#   {
#       "player1":    username of the first player (the one who sent the challenge),
#       "player2":    username of the second player (the one who accepted),
#       "spectators": list of usernames watching the game
#   }
active_game = None


# =============================================================================
# BROADCAST FUNCTIONS
# These send messages to multiple clients at once.
# =============================================================================

def broadcast_player_list():
    """
    Send the updated list of online players to EVERY connected client.
    
    Called whenever:
      - A new player joins
      - A player disconnects
      - A game starts (statuses change to "in_game")
      - A game ends (statuses change back to "lobby")
      - A spectator joins (status changes to "spectating")
    
    Each player entry includes username, color, and status so the
    lobby screen can show:
      - Who is available to challenge (status = "lobby")
      - Who is currently playing (status = "in_game")
      - Who is watching (status = "spectating")

    
    We snapshot the data under the lock, then send OUTSIDE the lock.
    This prevents crashes if a player disconnects mid-broadcast, (because the size of the dictionary changes mid iteration)
    and avoids holding the lock during slow network sends.
    """
    # Step 1: snapshot data under the lock (fast)
    with players_lock:
        player_data = []
        sockets = []
        for username, info in connected_players.items():
            player_data.append({
                "username": username,
                "color": info["color"],
                "status": info["status"]
            })
            sockets.append((username, info["socket"]))
    
    # Step 2: send to everyone OUTSIDE the lock (slow, but safe)
    message = protocol.players_list(player_data)
    
    for username, sock in sockets:
        try:
            protocol.send(sock, message)
        except Exception as e:
            print(f"[ERROR] Could not send player list to {username}: {e}")

# =============================================================================
# CHALLENGE SYSTEM
# Handles challenging, accepting, and declining.
# =============================================================================

def handle_challenge(challenger, opponent):
    """
    A player wants to challenge someone to a game.
    
    Validation rules:
      - Opponent must exist (still connected)
      - Can't challenge yourself
      - Challenger must be in the lobby (not in a game or spectating)
      - Opponent must be in the lobby (not in a game or spectating)
      - Challenger can't have another pending challenge already
    
    If all checks pass:
      - Records the challenge in pending_challenges
      - Sends a CHALLENGE_FROM message to the opponent
    
    Parameters:
        challenger: username of the player sending the challenge
        opponent:   username of the player being challenged
    """
    with players_lock:
        # Check: does the opponent exist?
        if opponent not in connected_players:
            protocol.send(connected_players[challenger]["socket"],
                         "ERROR:Player not found")
            return
        
        # Check: can't challenge yourself
        if challenger == opponent:
            protocol.send(connected_players[challenger]["socket"],
                         "ERROR:Cannot challenge yourself")
            return
        
        # Check: challenger must be in the lobby
        if connected_players[challenger]["status"] != "lobby":
            protocol.send(connected_players[challenger]["socket"],
                         "ERROR:You are not in the lobby")
            return
        
        # Check: opponent must be in the lobby
        if connected_players[opponent]["status"] != "lobby":
            protocol.send(connected_players[challenger]["socket"],
                         f"ERROR:{opponent} is not available")
            return
        
        # Check: challenger can't have another pending challenge
        for challenged, chall in pending_challenges.items():
            if chall == challenger:
                protocol.send(connected_players[challenger]["socket"],
                             "ERROR:You already have a pending challenge")
                return
        # Check: opponent already has a pending challenge from someone else
        if opponent in pending_challenges:
            protocol.send(connected_players[challenger]["socket"],
                         f"ERROR:{opponent} already has a pending challenge")
            return
        
        # All checks passed — record the challenge
        pending_challenges[opponent] = challenger
        print(f"[CHALLENGE] {challenger} challenged {opponent}")
    
    # Notify the opponent about the challenge (outside the lock to avoid deadlocks)
    try:
        protocol.send(connected_players[opponent]["socket"],
                     protocol.challenge_from(challenger))
    except Exception as e:
        print(f"[ERROR] Could not send challenge to {opponent}: {e}")


def handle_accept(accepter, challenger):
    """
    A player accepts a challenge, which starts a game.
    
    Validation:
      - The challenge must exist in pending_challenges
      - The challenger must match
      - Both players must still be in the lobby
      - No other game can be active (only one game at a time)
    
    If all checks pass:
      - Sets both players' status to "in_game"
      - Creates the active_game session
      - Clears all pending challenges involving these two players
      - Sends CHALLENGE_ACCEPTED and GAME_START to both players
      - Broadcasts updated player list so everyone sees the status change
    
    Parameters:
        accepter:   username of the player accepting (the one who was challenged)
        challenger: username of the player who sent the challenge
    """
    global active_game
    
    with players_lock:
        # Verify: does this challenge exist?
        if accepter not in pending_challenges:
            protocol.send(connected_players[accepter]["socket"],
                         "ERROR:No pending challenge")
            return
        
        # Verify: does the challenger match?
        if pending_challenges[accepter] != challenger:
            protocol.send(connected_players[accepter]["socket"],
                         f"ERROR:No challenge from {challenger}")
            return
        
        # Verify: is the challenger still in the lobby?
        if connected_players[challenger]["status"] != "lobby":
            protocol.send(connected_players[accepter]["socket"],
                         f"ERROR:{challenger} is no longer available")
            del pending_challenges[accepter]
            return
        
        # Verify: is the accepter still in the lobby?
        if connected_players[accepter]["status"] != "lobby":
            protocol.send(connected_players[accepter]["socket"],
                         "ERROR:You are not in the lobby")
            del pending_challenges[accepter]
            return
        
        # Verify: no other game is already running
        if active_game is not None:
            protocol.send(connected_players[accepter]["socket"],
                         "ERROR:A game is already in progress")
            del pending_challenges[accepter]
            return
        
        # ── All checks passed — start the game! ──
        
        # Update both players' status to "in_game"
        connected_players[challenger]["status"] = "in_game"
        connected_players[accepter]["status"] = "in_game"
        
        # Remove the accepted challenge from pending
        del pending_challenges[accepter]
        
        # Clear any OTHER pending challenges involving these two players.
        # They can't accept or send challenges while in a game.
        to_remove = []
        for challenged, chall in pending_challenges.items():
            if chall == challenger or chall == accepter or challenged == challenger:
                to_remove.append(challenged)
        for key in to_remove:
            del pending_challenges[key]
        
        # Create the active game session
        # spectators list starts empty — fans can join using WATCH
        active_game = {
            "player1": challenger,
            "player2": accepter,
            "spectators": []
        }
        
        print(f"[GAME START] {challenger} vs {accepter}")
    
    # Notify both players (outside the lock)
    try:
        # Tell both who their opponent is
        protocol.send(connected_players[challenger]["socket"],
                     protocol.challenge_accepted(accepter))
        protocol.send(connected_players[accepter]["socket"],
                     protocol.challenge_accepted(challenger))
        
        # Tell both the game is starting
        protocol.send(connected_players[challenger]["socket"],
                     protocol.game_start())
        protocol.send(connected_players[accepter]["socket"],
                     protocol.game_start())
    except Exception as e:
        print(f"[ERROR] Could not notify players about game start: {e}")
    
    # Update everyone's player list so lobby shows correct statuses
    broadcast_player_list()


def handle_decline(decliner, challenger):
    """
    A player declines a challenge.
    
    Removes the pending challenge and notifies the challenger that
    their challenge was declined.
    
    Parameters:
        decliner:   username of the player who is declining
        challenger: username of the player who sent the challenge
    """
    with players_lock:
        # Verify the challenge exists
        if decliner not in pending_challenges:
            return
        
        # Verify the challenger matches
        if pending_challenges[decliner] != challenger:
            return
        
        # Remove the pending challenge
        del pending_challenges[decliner]
        print(f"[DECLINE] {decliner} declined challenge from {challenger}")
    
    # Notify the challenger that they were declined
    try:
        if challenger in connected_players:
            protocol.send(connected_players[challenger]["socket"],
                         protocol.challenge_declined(decliner))
    except Exception as e:
        print(f"[ERROR] Could not notify {challenger} about decline: {e}")


# =============================================================================
# SPECTATOR SYSTEM
# Allows lobby players to watch an ongoing game.
# =============================================================================

def handle_watch(username):
    """
    A player wants to spectate the current game.
    
    Validation:
      - There must be an active game to watch
      - The player must be in the lobby (can't spectate if already playing)
    
    If valid:
      - Changes their status to "spectating"
      - Adds them to active_game["spectators"]
      - Notifies both players that a fan joined
      - Broadcasts updated player list
    
    Later, when the game loop runs (Step 3), it will send GAME_STATE
    to spectators in addition to the two players.
    
    Parameters:
        username: the player who wants to watch
    """
    global active_game
    
    with players_lock:
        # Check: is there a game happening?
        if active_game is None:
            protocol.send(connected_players[username]["socket"],
                         "ERROR:No game in progress to watch")
            return
        
        # Check: player must be in the lobby
        if connected_players[username]["status"] != "lobby":
            protocol.send(connected_players[username]["socket"],
                         "ERROR:You cannot spectate right now")
            return
        
        # Add them as a spectator
        connected_players[username]["status"] = "spectating"
        active_game["spectators"].append(username)
        
        print(f"[SPECTATOR] {username} is now watching "
              f"{active_game['player1']} vs {active_game['player2']}")
    
    # Notify both players that a fan joined (outside the lock)
    try:
        p1 = active_game["player1"]
        p2 = active_game["player2"]
        fan_msg = protocol.fan_joined(username)
        
        protocol.send(connected_players[p1]["socket"], fan_msg)
        protocol.send(connected_players[p2]["socket"], fan_msg)
    except Exception as e:
        print(f"[ERROR] Could not notify players about spectator: {e}")
    
    # Update everyone's player list so lobby shows this player as spectating
    broadcast_player_list()


# =============================================================================
# PLAYER DISCONNECT CLEANUP
# Handles everything that needs to happen when a player leaves.
# =============================================================================

def remove_player(username):
    """
    Remove a player from the server and clean up all their state.
    
    This handles EVERY scenario:
      1. Player was in the lobby
         → Just remove them, broadcast updated list
      2. Player was in a game
         → End the game, opponent wins by disconnect
         → Move opponent back to lobby
         → Move all spectators back to lobby
      3. Player was spectating
         → Remove from spectator list
      4. Player had pending challenges (sent or received)
         → Remove those challenges
    
    Called from handle_client's finally block, so it always runs
    even if the client crashes or force-closes.
    
    Parameters:
        username: the player who disconnected
    """
    global active_game
    
    with players_lock:
        if username not in connected_players:
            return
        
        player_status = connected_players[username]["status"]
        
        # ── Clean up pending challenges ──
        # Remove any challenge this player RECEIVED
        if username in pending_challenges:
            del pending_challenges[username]
        
        # Remove any challenges this player SENT
        to_remove = [k for k, v in pending_challenges.items() if v == username]
        for key in to_remove:
            del pending_challenges[key]
        
        # ── Handle if player was in a game ──
        if player_status == "in_game" and active_game:
            # Figure out who the opponent is
            opponent = None
            if active_game["player1"] == username:
                opponent = active_game["player2"]
            elif active_game["player2"] == username:
                opponent = active_game["player1"]
            
            # Tell the opponent they won because the other player disconnected
            if opponent and opponent in connected_players:
                try:
                    protocol.send(connected_players[opponent]["socket"],
                                 protocol.game_over(opponent, 0, 0))
                except:
                    pass
                # Move opponent back to lobby so they can play again
                connected_players[opponent]["status"] = "lobby"
            
            # Move ALL spectators back to lobby since the game is over
            for spec in active_game.get("spectators", []):
                if spec in connected_players:
                    connected_players[spec]["status"] = "lobby"
            
            # Clear the active game
            active_game = None
            print(f"[GAME END] Game ended because {username} disconnected")
        
        # ── Handle if player was spectating ──
        if player_status == "spectating" and active_game:
            if username in active_game["spectators"]:
                active_game["spectators"].remove(username)
        
        # ── Remove from connected players ──
        del connected_players[username]
        print(f"[LEFT] {username} disconnected. Online: {len(connected_players)}")
    
    # Tell everyone about the changes
    broadcast_player_list()


# =============================================================================
# CLIENT HANDLER
# One instance runs per connected client, in its own thread.
# =============================================================================

def handle_client(client_socket, client_address):
    """
    Handle one client connection from start to finish.
    
    This function runs in its own thread — one thread per client.
    
    Lifecycle:
      1. Receive JOIN message with username and color
      2. Validate username (must be unique)
      3. Add player to connected list with status "lobby"
      4. Listen for messages in a loop (CHALLENGE, ACCEPT, DECLINE, MOVE, etc.)
      5. When the client disconnects, clean up everything
    
    Parameters:
        client_socket:  the socket object for talking to this specific client
        client_address: tuple of (IP, port) for this client
    """
    username = None  # We don't know their name yet
    
    try:
        print(f"[CONNECT] New connection from {client_address}")
        
        # ── Step 1: Wait for the JOIN message ──
        # The client sends: JOIN:{"username": "Lara", "color": [0, 180, 50]}
        raw_message = protocol.receive(client_socket)
        
        if not raw_message:
            # Client disconnected before sending anything
            print(f"[DISCONNECT] {client_address} disconnected before joining")
            client_socket.close()
            return
        
        # Parse the message into header and body
        header, body = protocol.parse(raw_message)
        
        # We expect a JOIN message. Anything else at this point is invalid.
        if header != "JOIN":
            print(f"[ERROR] Expected JOIN from {client_address}, got: {header}")
            client_socket.close()
            return
        
        # Extract username and color from the JOIN body
        join_data = protocol.parse_join(body)
        requested_username = join_data["username"]
        player_color = join_data["color"]
        
        # ── Step 2: Check if username is unique ──
        with players_lock:
            if requested_username in connected_players:
                # Username is taken — reject and close
                print(f"[REJECTED] Username '{requested_username}' is already in use")
                protocol.send(client_socket, protocol.username_taken())
                client_socket.close()
                return
            
            # Username is available — add them to connected players
            username = requested_username
            connected_players[username] = {
                "socket": client_socket,
                "color": player_color,
                "address": client_address,
                "status": "lobby"  # new players always start in the lobby
            }
            print(f"[JOINED] {username} joined. Online: {len(connected_players)}")
        
        # Tell this client their username was accepted
        protocol.send(client_socket, protocol.username_ok())
        
        # Tell everyone (including the new player) about the updated player list
        broadcast_player_list()
        
        # ── Step 3: Listen for messages ──
        # This loop runs until the client disconnects.
        # Each message type is routed to its handler function.
        while True:
            raw_message = protocol.receive(client_socket)
            
            if not raw_message:
                # Empty message = client disconnected
                print(f"[DISCONNECT] {username} disconnected")
                break
            
            # Split the message into header and body
            header, body = protocol.parse(raw_message)
            
            # ── Route to the correct handler ──
            
            if header == "CHALLENGE":
                # Player wants to challenge someone
                # body = opponent's username
                handle_challenge(username, body)
            
            elif header == "ACCEPT":
                # Player accepts a challenge
                # body = challenger's username
                handle_accept(username, body)
            
            elif header == "DECLINE":
                # Player declines a challenge
                # body = challenger's username
                handle_decline(username, body)
            
            elif header == "WATCH":
                # Player wants to spectate the current game
                handle_watch(username)
            
            elif header == "MOVE":
                # Player sends a movement command during a game
                # body = direction (UP, DOWN, LEFT, RIGHT)
                # TODO: Step 3 — forward to game logic
                print(f"[MOVE] {username} moved {body}")
            
            elif header == "CHAT":
                # Player sends a chat message
                # body = the message text
                # TODO: Advanced feature — peer-to-peer chat
                print(f"[CHAT] {username}: {body}")
            
            else:
                # Unknown message type — log it but don't crash
                print(f"[UNKNOWN] {username} sent unknown message: {header}")
    
    except ConnectionResetError:
        # Client force-closed their window (e.g., Alt+F4)
        print(f"[DISCONNECT] {username or client_address} connection reset")
    
    except Exception as e:
        # Catch any unexpected errors so the server keeps running
        print(f"[ERROR] Error with {username or client_address}: {e}")
    
    finally:
        # ── Cleanup ──
        # This ALWAYS runs, no matter how the client disconnected.
        # It removes the player, ends any games they were in,
        # cleans up challenges, and notifies everyone.
        if username:
            remove_player(username)
        
        try:
            client_socket.close()
        except:
            pass


# =============================================================================
# SERVER STARTUP
# Creates the listening socket and spawns threads for each client.
# =============================================================================

def start_server(port):
    """
    Start the server and listen for incoming connections forever.
    
    Steps:
      1. Create a TCP socket
      2. Bind it to the given port on all interfaces
      3. Listen for connections
      4. For each new connection, spawn a thread running handle_client
    
    Runs until Ctrl+C is pressed.
    
    Parameters:
        port: the port number to listen on (integer, 1024-65535)
    """
    # Create a TCP socket (IPv4)
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    
    # Allow the port to be reused immediately after the server stops.
    # Without this, restarting the server quickly gives "Address already in use".
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    
    # Bind to all network interfaces ("0.0.0.0") on the given port.
    # This means the server accepts connections from any IP, not just localhost.
    server_socket.bind(("0.0.0.0", port))
    
    # Start listening. Backlog of 5 = up to 5 connections can queue.
    server_socket.listen(5)
    
    print(f"[SERVER] Πthon Arena server started on port {port}")
    print(f"[SERVER] Waiting for players to connect...")
    print(f"[SERVER] Press Ctrl+C to stop the server")
    print()
    
    try:
        while True:
            # Wait for a new client to connect (this blocks until someone does)
            client_socket, client_address = server_socket.accept()
            
            # Spawn a new thread for this client
            # daemon=True = thread dies automatically when main program exits
            client_thread = threading.Thread(
                target=handle_client,
                args=(client_socket, client_address),
                daemon=True
            )
            client_thread.start()
    
    except KeyboardInterrupt:
        print("\n[SERVER] Shutting down...")
    
    finally:
        server_socket.close()
        print("[SERVER] Server stopped.")


# =============================================================================
# ENTRY POINT
# Reads the port from command line arguments and starts the server.
# Usage: python server.py <port>
# =============================================================================

if __name__ == "__main__":
    # Check that the user provided a port number
    if len(sys.argv) != 2:
        print("Usage: python server.py <port>")
        print("Example: python server.py 5555")
        sys.exit(1)
    
    # Convert port from string to integer
    try:
        port = int(sys.argv[1])
    except ValueError:
        print("Error: Port must be a number")
        sys.exit(1)
    
    # Validate port range (1024-65535, below 1024 is reserved by the OS)
    if port < 1024 or port > 65535:
        print("Error: Port must be between 1024 and 65535")
        sys.exit(1)
    
    # Start the server
    start_server(port)