import socket
import threading
import time
import sys
import protocol
from game import GameState
from constants import (
    SNAKE_MOVE_INTERVAL_MS,
    GAME_STATE_SEND_INTERVAL_MS,
    SUDDEN_DEATH_SPEED_MULT,
)
from bot import GreedyBot, BOT_NAME, BOT_INFO

#This file handles the server of our game
#Its role is to accept client connections, store online players, handles challenges,
#starts matches, updates the game, manages spectators, and supports rematches.
#The below variables help us keep track of the current state of the server
connected_players = {}

#since many client threads may be accessing at the same time, we use the below variable
players_lock = threading.Lock()

#the below variable stores the requests that have not been accepted or declined yet
pending_challenges = {}

#the below variable stores the current active game
active_game = None

# stores usernames of players who requested a rematch after a game ended
pending_rematches = set()   
last_game_pair    = {}      

# BROADCAST HELPERS


def broadcast_player_list():
    #this function sends the updated list of online players to every connected client
    #It is used whenever the lobby changes, such as when a player joins, disconnects, starts a game, becomes a spectator, or returns to the lobby
    with players_lock:
        player_data = []
        sockets     = []
        for uname, info in connected_players.items():
            player_data.append({
                "username":   uname,
                "ip":         info["address"][0],
                "color":      info["color"],
                "head_style": info["head_style"],
                "head_emoji": info["head_emoji"],
                "chat_port":  info["chat_port"],
                "status":     info["status"],
            })
            sockets.append((uname, info["socket"]))

    message = protocol.players_list(player_data)
    for uname, sock in sockets:
        try:
            protocol.send(sock, message)
        except Exception as e:
            print(f"[ERROR] player list to {uname}: {e}")


def _send_to_all(recipients, message):
   #this function sends the same message to multiple users 
    for uname, sock in recipients:
        try:
            protocol.send(sock, message)
        except Exception as e:
            print(f"[ERROR] send to {uname}: {e}")



# GAME LOOP
# Runs in its own daemon thread for the duration of one match.


def game_loop():
   #this function keeps the game moving forward
   #It sends updated game states to clients, handles the bot if the client is playing against the Ai snake, and ends the match when the game is over
    global active_game

    last_move_time = time.monotonic()
    last_send_time = 0

    while True:
        now = time.monotonic()
        move_interval = SNAKE_MOVE_INTERVAL_MS / 1000
        send_interval = GAME_STATE_SEND_INTERVAL_MS / 1000
        # Safely copy the current game information
        with players_lock:
            if active_game is None:
                # If no game exists anymore, stop the loop
                break
            #Get the active gamestate object and player names 
            game       = active_game["game"]
            p1_name    = active_game["player1"]
            p2_name    = active_game["player2"]
            bot_instance = active_game.get("bot")
            spectators = list(active_game["spectators"])   # copy spectator list

            # Store all clients that should receive game updates 
            recipients = []
            for uname in [p1_name, p2_name] + spectators:
                if uname in connected_players:
                    recipients.append(
                        (uname, connected_players[uname]["socket"])
                    )

        # If sudden death is active, make the snakes move faster 
        if game.sudden_death:
            move_interval /= SUDDEN_DEATH_SPEED_MULT

        did_tick = False #tracks whether the game actually moved during this loop cycle
        if now - last_move_time >= move_interval and bot_instance is not None:
            bot_dir = bot_instance.decide(game)
            if bot_dir:
                game.set_direction(BOT_NAME, bot_dir)

        # move the game forward only when enough time has passed
        if now - last_move_time >= move_interval:
            game.tick()
            last_move_time = now
            did_tick = True

        # get the latest game state after movement or for periodic updates
        state     = game.get_state()
        #send game state if the game moved or enough time passed since last update
        if did_tick or now - last_send_time >= send_interval:
            state_msg = protocol.game_state(
                state["player1"],
                state["player2"],
                state["pies"],
                state["obstacles"],
                state["time_left"],
                state["sudden_death"],
                state["fire_tiles"],
                state["move_id"],
            )

        # send the updated game state to both players and all spectators
            _send_to_all(recipients, state_msg)
            last_send_time = now

        # if no movement happened, wait briefly and continue checking
        if not did_tick:
            time.sleep(0.005)
            continue

        over, winner = game.check_game_over()
        if not over:
            time.sleep(0.005)
            continue   

        # get final health values for the game-over message
        h1       = state["player1"]["health"]
        h2       = state["player2"]["health"]
        over_msg = protocol.game_over(winner, h1, h2)

        # send the game-over result to players and spectators
        _send_to_all(recipients, over_msg)
        print(f"[GAME OVER] Winner: {winner} | "
              f"{p1_name}: {h1} HP | {p2_name}: {h2} HP")

        # clean up the game safely
        with players_lock:
            if active_game is not None:
                # save the last match pair so rematch can work
                last_game_pair[p1_name] = p2_name
                last_game_pair[p2_name] = p1_name
                # return both players to the lobby 
                for uname in [p1_name, p2_name]:
                    if uname in connected_players:
                        connected_players[uname]["status"] = "lobby"
                # Return all spectators to lobby
                for uname in spectators:
                    if uname in connected_players:
                        connected_players[uname]["status"] = "lobby"
                active_game = None

        # update everyone's lobby player list after the match ends 
        broadcast_player_list()
        break   # exit the game loop 



# BOT GAME


def handle_play_bot(username):
    #startsa game between a player and the AI snake 
    #here we have a different challenge system because the bot does not need to accept or decline the game. 
    global active_game

    with players_lock:
        if username not in connected_players:
            return
        if connected_players[username]["status"] != "lobby":
            protocol.send(connected_players[username]["socket"],
                          "ERROR:You are not in the lobby")
            return
        if active_game is not None:
            protocol.send(connected_players[username]["socket"],
                          "ERROR:A game is already in progress")
            return

        connected_players[username]["status"] = "in_game"

        game_obj = GameState(
            username, connected_players[username],
            BOT_NAME, BOT_INFO,
        )
        active_game = {
            "player1":    username,
            "player2":    BOT_NAME,
            "spectators": [],
            "game":       game_obj,
            "bot":        GreedyBot(BOT_NAME, username), 
        }
        print(f"[BOT GAME] {username} vs {BOT_NAME}")

    
    sock = connected_players[username]["socket"]
    try:
        protocol.send(sock, protocol.challenge_accepted(BOT_NAME))
        protocol.send(sock, protocol.game_start())
    except Exception as e:
        print(f"[ERROR] bot game start notify: {e}")

    broadcast_player_list()
    threading.Thread(target=game_loop, daemon=True).start()



# CHALLENGE SYSTEM


def handle_challenge(challenger, opponent):
    #this function handles the request between two players 
    #this function checks if both players are available in the lobby, stores the pending challenge, and notifies the opponent
    with players_lock:
        if active_game is not None:
            protocol.send(connected_players[challenger]["socket"],
                          "ERROR:A match is already in progress")
            return
        if opponent not in connected_players:
            protocol.send(connected_players[challenger]["socket"],
                          "ERROR:Player not found")
            return
        if challenger == opponent:
            protocol.send(connected_players[challenger]["socket"],
                          "ERROR:Cannot challenge yourself")
            return
        if connected_players[challenger]["status"] != "lobby":
            protocol.send(connected_players[challenger]["socket"],
                          "ERROR:You are not in the lobby")
            return
        if connected_players[opponent]["status"] != "lobby":
            protocol.send(connected_players[challenger]["socket"],
                          f"ERROR:{opponent} is not available")
            return
        for challenged, chall in pending_challenges.items():
            if chall == challenger:
                protocol.send(connected_players[challenger]["socket"],
                              "ERROR:You already have a pending challenge")
                return
        if opponent in pending_challenges:
            protocol.send(connected_players[challenger]["socket"],
                          f"ERROR:{opponent} already has a pending challenge")
            return

        pending_challenges[opponent] = challenger
        print(f"[CHALLENGE] {challenger} challenged {opponent}")

    try:
        protocol.send(connected_players[opponent]["socket"],
                      protocol.challenge_from(challenger))
    except Exception as e:
        print(f"[ERROR] challenge notify to {opponent}: {e}")


def handle_accept(accepter, challenger):
    #this function handles challenge acceptance
    #When the accepter agrees to the challenge, this function creates
    #the game, marks both players as in-game, starts the game loop,
    #and notifies both players that the match is starting.
    global active_game

    with players_lock:
        if accepter not in pending_challenges:
            protocol.send(connected_players[accepter]["socket"],
                          "ERROR:No pending challenge")
            return
        if pending_challenges[accepter] != challenger:
            protocol.send(connected_players[accepter]["socket"],
                          f"ERROR:No challenge from {challenger}")
            return
        if connected_players[challenger]["status"] != "lobby":
            protocol.send(connected_players[accepter]["socket"],
                          f"ERROR:{challenger} is no longer available")
            del pending_challenges[accepter]
            return
        if connected_players[accepter]["status"] != "lobby":
            protocol.send(connected_players[accepter]["socket"],
                          "ERROR:You are not in the lobby")
            del pending_challenges[accepter]
            return
        if active_game is not None:
            protocol.send(connected_players[accepter]["socket"],
                          "ERROR:A game is already in progress")
            del pending_challenges[accepter]
            return

        # Mark both as in-game
        connected_players[challenger]["status"] = "in_game"
        connected_players[accepter]["status"]   = "in_game"

        del pending_challenges[accepter]

        # Clear other pending challenges for these two players
        to_remove = [
            k for k, v in pending_challenges.items()
            if v == challenger or v == accepter or k == challenger
        ]
        for key in to_remove:
            del pending_challenges[key]

        # Create GameState — username is the key, info dict is the value
        active_game = {
            "player1":    challenger,
            "player2":    accepter,
            "spectators": [],
            "game":       GameState(
                              challenger, connected_players[challenger],
                              accepter,   connected_players[accepter],
                          ),
        }
        print(f"[GAME START] {challenger} vs {accepter}")

    # Notify both players outside the lock
    try:
        protocol.send(connected_players[challenger]["socket"],
                      protocol.challenge_accepted(accepter))
        protocol.send(connected_players[accepter]["socket"],
                      protocol.challenge_accepted(challenger))
        protocol.send(connected_players[challenger]["socket"],
                      protocol.game_start())
        protocol.send(connected_players[accepter]["socket"],
                      protocol.game_start())
    except Exception as e:
        print(f"[ERROR] game start notify: {e}")

    # Lobby sees updated statuses
    broadcast_player_list()

    # Spawn the game loop thread
    threading.Thread(target=game_loop, daemon=True).start()


def handle_decline(decliner, challenger):
    #it handles challenge rejection. If the player declines the challenge 
    #the pending request is removed and the callenger is notified that their request was rejected.
    with players_lock:
        if decliner not in pending_challenges:
            return
        if pending_challenges[decliner] != challenger:
            return
        del pending_challenges[decliner]
        print(f"[DECLINE] {decliner} declined {challenger}")

    try:
        if challenger in connected_players:
            protocol.send(connected_players[challenger]["socket"],
                          protocol.challenge_declined(decliner))
    except Exception as e:
        print(f"[ERROR] decline notify to {challenger}: {e}")



# SPECTATOR SYSTEM


def handle_watch(username):
    #this function handles a player's request to watch the current active game
    #The player must be in the lobby, and there must already be
    #a match running. If both conditions are true, the player is added
    #to the spectators list.
    global active_game

    with players_lock:
        if active_game is None:
            protocol.send(connected_players[username]["socket"],
                          "ERROR:No game in progress to watch")
            return
        if connected_players[username]["status"] != "lobby":
            protocol.send(connected_players[username]["socket"],
                          "ERROR:You cannot spectate right now")
            return

        connected_players[username]["status"] = "spectating"
        active_game["spectators"].append(username)
        p1 = active_game["player1"]
        p2 = active_game["player2"]
        print(f"[SPECTATOR] {username} watching {p1} vs {p2}")

    # Notify players + other spectators that a fan joined (outside the lock)
    fan_msg = protocol.fan_joined(username)
    with players_lock:
        # Bot has no socket — only add a player if they're in connected_players
        recipients = []
        for uname in [p1, p2]:
            if uname in connected_players:
                recipients.append((uname, connected_players[uname]["socket"]))
        for spec in active_game.get("spectators", []):
            if spec != username and spec in connected_players:
                recipients.append((spec, connected_players[spec]["socket"]))
    try:
        for uname, sock in recipients:
            protocol.send(sock, fan_msg)
    except Exception as e:
        print(f"[ERROR] fan joined notify: {e}")

    broadcast_player_list()



# DISCONNECT CLEANUP


def remove_player(username):
   #Removes a player from the server and cleans up anything related to them.

    #This function handles different cases:
    #1. If the player was in the lobby, they are simply removed.
    #2. If they were playing a match, the opponent automatically wins.
    #3. If they were spectating, they are removed from the spectators list.
    #4. Any pending challenges or rematch requests involving them are deleted.
    
    global active_game

    # These will be populated inside the lock, then used outside it
    game_over_recipients = []
    game_over_msg        = None

    with players_lock:
        if username not in connected_players:
            return

        player_status = connected_players[username]["status"]

        # Pending challenges 
        if username in pending_challenges:
            del pending_challenges[username]
        to_remove = [k for k, v in pending_challenges.items() if v == username]
        for key in to_remove:
            del pending_challenges[key]

        #Pending rematch 
        pending_rematches.discard(username)

        # Was in a game 
        if player_status == "in_game" and active_game:
            opponent = None
            if active_game["player1"] == username:
                opponent = active_game["player2"]
            elif active_game["player2"] == username:
                opponent = active_game["player1"]

            winner = opponent if opponent else username

            # Opponent gets GAME_OVER and returns to lobby
            if opponent and opponent in connected_players:
                game_over_recipients.append(
                    (opponent, connected_players[opponent]["socket"])
                )
                connected_players[opponent]["status"] = "lobby"

            # Every spectator also gets GAME_OVER and returns to lobby
            for spec in active_game.get("spectators", []):
                if spec in connected_players:
                    game_over_recipients.append(
                        (spec, connected_players[spec]["socket"])
                    )
                    connected_players[spec]["status"] = "lobby"

            game_over_msg = protocol.game_over(winner, 0, 0)
            active_game   = None
            print(f"[GAME END] {username} disconnected — {winner} wins")

        # ── Was spectating ────────────────────────────────────────────────────
        elif player_status == "spectating" and active_game:
            if username in active_game.get("spectators", []):
                active_game["spectators"].remove(username)

        # ── Remove ────────────────────────────────────────────────────────────
        del connected_players[username]
        print(f"[LEFT] {username} disconnected. Online: {len(connected_players)}")

    # Send GAME_OVER outside the lock
    if game_over_msg and game_over_recipients:
        _send_to_all(game_over_recipients, game_over_msg)

    broadcast_player_list()



# REMATCH SYSTEM


def handle_rematch(username):
    #Handles a rematch request after a game ends.

    #If one player asks first, the request is saved and the opponent is notified.
    #If the second player also asks for a rematch, the new game starts immediately.

    #Special case:
    #If the last opponent was the bot, the rematch starts instantly
    #without waiting for confirmation.
    global active_game

    with players_lock:
        opponent = last_game_pair.get(username)
        if not opponent:
            return
        if active_game is not None:
            return

        # ── Bot rematch — instant restart, no handshake needed ────────────────
        if opponent == BOT_NAME:
            if username not in connected_players:
                return
            connected_players[username]["status"] = "in_game"
            active_game = {
                "player1":    username,
                "player2":    BOT_NAME,
                "spectators": [],
                "game":       GameState(
                                  username, connected_players[username],
                                  BOT_NAME, BOT_INFO,
                              ),
                "bot":        GreedyBot(BOT_NAME, username),
            }
            my_sock = connected_players[username]["socket"]
            print(f"[BOT REMATCH] {username} vs {BOT_NAME}")

    if opponent == BOT_NAME:
        try:
            protocol.send(my_sock, protocol.rematch_start())
        except Exception as e:
            print(f"[ERROR] bot rematch start: {e}")
        broadcast_player_list()
        threading.Thread(target=game_loop, daemon=True).start()
        return

    with players_lock:
        if opponent not in connected_players:
            return
        # Don't allow double-request from same player
        if username in pending_rematches:
            return

        if opponent in pending_rematches:
            # Both want rematch — start the game
            pending_rematches.discard(opponent)

            connected_players[username]["status"] = "in_game"
            connected_players[opponent]["status"]  = "in_game"

            active_game = {
                "player1":    username,
                "player2":    opponent,
                "spectators": [],
                "game":       GameState(
                                  username, connected_players[username],
                                  opponent,  connected_players[opponent],
                              ),
            }
            print(f"[REMATCH] {username} vs {opponent}")
            start_now = True
            opp_sock  = connected_players[opponent]["socket"]
            my_sock   = connected_players[username]["socket"]
        else:
            # Record and notify both sides
            pending_rematches.add(username)
            start_now  = False
            my_sock    = connected_players[username]["socket"]
            opp_sock   = connected_players[opponent]["socket"]

    if start_now:
        try:
            protocol.send(my_sock,  protocol.rematch_start())
            protocol.send(opp_sock, protocol.rematch_start())
        except Exception as e:
            print(f"[ERROR] rematch start notify: {e}")
        broadcast_player_list()
        threading.Thread(target=game_loop, daemon=True).start()
    else:
        try:
            # Confirm to requester that server recorded their request
            protocol.send(my_sock,  protocol.rematch_queued(opponent))
            # Notify opponent
            protocol.send(opp_sock, protocol.rematch_from(username))
        except Exception as e:
            print(f"[ERROR] rematch notify: {e}")


def handle_decline_rematch(username):
    #it handles rematch cancellation 
   # This happens when a player leaves instead of accepting a rematch.
   # The server removes any pending rematch request and notifies
    #the opponent that the rematch was declined.
    notify_opponent = None

    with players_lock:
        opponent = last_game_pair.get(username)

        # Case 1 — this player had requested a rematch
        if username in pending_rematches:
            pending_rematches.discard(username)
            if opponent and opponent in connected_players:
                notify_opponent = (opponent,
                                   connected_players[opponent]["socket"])

        # Case 2 — opponent requested a rematch and is waiting for this player
        elif opponent and opponent in pending_rematches:
            pending_rematches.discard(opponent)
            if opponent in connected_players:
                notify_opponent = (opponent,
                                   connected_players[opponent]["socket"])

    if notify_opponent:
        opp_name, opp_sock = notify_opponent
        try:
            protocol.send(opp_sock, protocol.rematch_declined(username))
        except Exception as e:
            print(f"[ERROR] rematch decline notify to {opp_name}: {e}")


def handle_leave_watch(username):
    #Handles a spectator leaving the current game.

    #The spectator is removed from the spectators list
    #and their status changes back to lobby.
    with players_lock:
        if username not in connected_players:
            return
        if connected_players[username]["status"] != "spectating":
            return
        connected_players[username]["status"] = "lobby"
        if active_game and username in active_game.get("spectators", []):
            active_game["spectators"].remove(username)
        print(f"[SPECTATOR LEFT] {username} returned to lobby")

    broadcast_player_list()


# CLIENT HANDLER


def handle_client(client_socket, client_address):
    #it handles one connected client

   # Each client runs in its own thread, so this function is responsible for
   # receiving that client's messages, checking what type of message it is,
    #and calling the correct handler.
    username = None

    try:
        print(f"[CONNECT] {client_address}")

        # Clear any stale buffer for this socket id before first read.
        # The OS may reuse a memory address from a previously closed socket,
        # causing protocol._buffers to contain leftover data from that socket.
        protocol._buffers.pop(id(client_socket), None)

        raw_message = protocol.receive(client_socket)
        if not raw_message:
            print(f"[DISCONNECT] {client_address} before joining")
            client_socket.close()
            return

        header, body = protocol.parse(raw_message)
        if header != "JOIN":
            print(f"[ERROR] Expected JOIN from {client_address}, got {header}")
            client_socket.close()
            return

        join_data          = protocol.parse_join(body)
        requested_username = join_data["username"]
        player_color       = join_data["color"]
        player_head_style  = join_data.get("head_style", "classic")
        player_head_emoji  = join_data.get("head_emoji", None)
        player_chat_port   = join_data.get("chat_port", 0)

        with players_lock:
            if requested_username in connected_players:
                print(f"[REJECTED] '{requested_username}' already in use")
                protocol.send(client_socket, protocol.username_taken())
                client_socket.close()
                return
            if requested_username == BOT_NAME:
                print(f"[REJECTED] '{requested_username}' is reserved for the bot")
                protocol.send(client_socket, protocol.username_taken())
                client_socket.close()
                return

            username = requested_username
            connected_players[username] = {
                "socket":     client_socket,
                "color":      player_color,
                "head_style": player_head_style,
                "head_emoji": player_head_emoji,
                "chat_port":  player_chat_port,
                "address":    client_address,
                "status":     "lobby",
            }
            print(f"[JOINED] {username}. Online: {len(connected_players)}")

        protocol.send(client_socket, protocol.username_ok())
        broadcast_player_list()

        # ── Message loop ──────────────────────────────────────────────────────
        while True:
            raw_message = protocol.receive(client_socket)
            if not raw_message:
                print(f"[DISCONNECT] {username}")
                break

            header, body = protocol.parse(raw_message)

            if header == "CHALLENGE":
                handle_challenge(username, body)

            elif header == "ACCEPT":
                handle_accept(username, body)

            elif header == "DECLINE":
                handle_decline(username, body)

            elif header == "WATCH":
                handle_watch(username)

            elif header == "REMATCH":
                handle_rematch(username)

            elif header == "DECLINE_REMATCH":
                handle_decline_rematch(username)

            elif header == "PLAY_BOT":
                handle_play_bot(username)

            elif header == "LEAVE_WATCH":
                handle_leave_watch(username)

            elif header == "MOVE":
                # Only in-game players can move — spectators blocked explicitly
                with players_lock:
                    is_player = (
                        connected_players.get(username, {}).get("status") == "in_game"
                    )
                    game = active_game["game"] if active_game is not None else None
                if game is not None and is_player:
                    game.set_direction(username, body)

            elif header == "CHAT":
                # Spectator cheering — forwarded to players + all other spectators.
                # Limited to 30 characters. Only spectators can send cheers.
                with players_lock:
                    is_spectator = (
                        connected_players.get(username, {}).get("status") == "spectating"
                    )
                    if active_game is not None and is_spectator:
                        # Both players + all other spectators receive the cheer
                        cheer_recipients = []
                        for uname in (
                            [active_game["player1"], active_game["player2"]]
                            + active_game["spectators"]
                        ):
                            if uname != username and uname in connected_players:
                                cheer_recipients.append(
                                    (uname, connected_players[uname]["socket"])
                                )
                    else:
                        cheer_recipients = []

                if cheer_recipients:
                    # Format: CHAT:username:message so client knows who cheered
                    cheer_msg = f"CHAT:{username}:{body[:30]}"
                    _send_to_all(cheer_recipients, cheer_msg)
                    print(f"[CHEER] {username}: {body[:30]}")

            else:
                print(f"[UNKNOWN] {username}: {header}")

    except ConnectionResetError:
        print(f"[DISCONNECT] {username or client_address} connection reset")

    except Exception as e:
        print(f"[ERROR] {username or client_address}: {e}")

    finally:
        # Clean up BEFORE close — prevents id() reuse from polluting a new
        # socket's buffer if the OS recycles this socket's memory address.
        protocol._buffers.pop(id(client_socket), None)
        if username:
            remove_player(username)
        try:
            client_socket.close()
        except:
            pass



# SERVER STARTUP


def start_server(port):
    """Create listening socket and spawn a thread per client."""
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind(("0.0.0.0", port))
    server_socket.listen(5)

    print(f"[SERVER] Πthon Arena started on port {port}")
    print(f"[SERVER] Waiting for players...")
    print(f"[SERVER] Ctrl+C to stop")
    print()

    try:
        while True:
            client_socket, client_address = server_socket.accept()
            threading.Thread(
                target=handle_client,
                args=(client_socket, client_address),
                daemon=True,
            ).start()
    except KeyboardInterrupt:
        print("\n[SERVER] Shutting down...")
    finally:
        server_socket.close()
        print("[SERVER] Stopped.")


# ENTRY POINT


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python server.py <port>")
        print("Example: python server.py 5555")
        sys.exit(1)

    try:
        port = int(sys.argv[1])
    except ValueError:
        print("Error: Port must be a number")
        sys.exit(1)

    if port < 1024 or port > 65535:
        print("Error: Port must be between 1024 and 65535")
        sys.exit(1)

    start_server(port)
