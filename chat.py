import socket
import threading
import queue

# Each player opens a small listening socket and shares that port through the server's player list. 
# The server is only used to tell clients who is online and how to reach them. 
# The actual chat messages are then sent directly between clients over TCP.
# One background thread listens for new chat connections.
# Each incoming connection is then handled by its own receive thread.

#───────────────────────────────────────────────────────────────
# Shared framing settings for P2P chat messages.

DELIMITER = "\n"
ENCODING  = "utf-8"
BUFFER    = 4096


class P2PChat:
    """
    Manages peer-to-peer chat for one client.
    It tracks who is reachable, opens connections when needed, accepts
    incoming ones, and stores received messages in a queue for the UI.
    """

    def __init__(self, my_username):
        self._username    = my_username

        # Socket that listens for incoming chat connections.
        self._server_sock = None
        self._port        = 0

        # Outgoing sockets, keyed by username.
        self._connections = {}
        self._conn_lock   = threading.Lock()

        # Latest player connection info received from the server
        self._players     = {}
        self._players_lock = threading.Lock()

        # Messages waiting to be shown in the UI
        self._messages    = queue.Queue()

        # Background state
        self._accept_thread  = None
        self._running        = False

    # Start and stop

    def start(self):
        """
        Open the listening socket and start accepting chat connections
        """
        self._server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        # Let the OS choose an available local port. When you bind to 0, you're asking os to choose any available port
        self._server_sock.bind(("0.0.0.0", 0))
        self._server_sock.listen(10)
        self._port   = self._server_sock.getsockname()[1]
        self._running = True

        # Accept incoming chat connections in the background.
        self._accept_thread = threading.Thread(
            target=self._accept_loop,
            daemon=True,
            name="P2PChat-accept"
        )
        self._accept_thread.start()
        print(f"[CHAT] Listening for P2P connections on port {self._port}")

    def stop(self): #when the client shuts down
        """
        Stop the chat system and close all open sockets.
        """
        self._running = False

        # Closing the listening socket makes the accept loop stop
        try:
            self._server_sock.close()
        except Exception:
            pass

        # Close all cached outgoing connections
        with self._conn_lock:
            for uname, sock in self._connections.items():
                try:
                    sock.close()
                except Exception:
                    pass
            self._connections.clear()

        print("[CHAT] P2P chat stopped")

    def get_port(self):
        """Return this client's chat port."""
        return self._port

    # Player list updates.

    def update_players(self, players_list):
        """
        Refresh the list of reachable players using the latest server snapshot.
        If someone disappeared, their socket is closed and a system message is
        queued so the UI can show that they left.
        """
        with self._players_lock:
            new_usernames = {
                p["username"]
                for p in players_list
                if p["username"] != self._username
            }
            old_usernames = set(self._players.keys())

            # Players who left 
            for gone in old_usernames - new_usernames:
                self._messages.put({
                    "from":    gone,
                    "message": f"{gone} left the chat",
                    "private": False,
                    "system":  True,
                })
                # Drop any cached connection to that player.
                with self._conn_lock:
                    sock = self._connections.pop(gone, None)
                    if sock:
                        try:
                            sock.close()
                        except Exception:
                            pass

            # Update player info 
            self._players = {}
            for p in players_list:
                if p["username"] != self._username:
                    self._players[p["username"]] = {
                        "ip":        p.get("ip", "127.0.0.1"),
                        "chat_port": p.get("chat_port", 0),
                    }

    # ──── Sending ───────────────────────────────────────────────────────────────

    def send_public(self, message):
        """
        Send a message to every other player in the lobby.
        """
        with self._players_lock:
            targets = dict(self._players)

        for uname, info in targets.items():
            self._send_to(uname, info, message, private=False)

    def send_private(self, target_username, message):
        """
        Send a message to one specific player.
        """
        with self._players_lock:
            info = self._players.get(target_username)

        if info is None:
            print(f"[CHAT] Cannot send to {target_username} — not in player list")
            return

        self._send_to(target_username, info, message, private=True)

    def _send_to(self, username, info, message, private):
        """
        Send one formatted chat message to one player.
        The socket is opened only when it is first needed.
        """
        chat_port = info.get("chat_port", 0)
        if chat_port == 0:
            # Skip players who are not accepting P2P chat.
            return

        sock = self._get_or_connect(username, info["ip"], chat_port)
        if sock is None:
            return

        # Messages use a simple type|sender|message format.
        kind = "private" if private else "public"
        raw  = f"{kind}|{self._username}|{message}{DELIMITER}"
        try:
            sock.sendall(raw.encode(ENCODING))
        except Exception as e:
            print(f"[CHAT] Send to {username} failed: {e}")
            # Remove broken sockets so a later send can reconnect.
            with self._conn_lock:
                self._connections.pop(username, None)

    def _get_or_connect(self, username, ip, port):
        """
        Reuse an existing socket or open a new connection to that player.
        """
        with self._conn_lock:
            if username in self._connections:
                return self._connections[username]

        # Open new sockets outside the lock because connecting can block.
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(3)
            sock.connect((ip, port))
            sock.settimeout(None)
            with self._conn_lock:
                self._connections[username] = sock
            print(f"[CHAT] Connected to {username} at {ip}:{port}")
            return sock
        except Exception as e:
            print(f"[CHAT] Could not connect to {username}: {e}")
            return None

    # ──── Receiving ───────────────────────────────────────────────────────────────

    def _accept_loop(self):
        """
        Accept incoming chat connections and hand each one to a receive thread.
        """
        while self._running:
            try:
                conn, addr = self._server_sock.accept()
                # Handle each peer connection independently.
                t = threading.Thread(
                    target=self._receive_loop,
                    args=(conn, addr),
                    daemon=True,
                    name=f"P2PChat-recv-{addr}"
                )
                t.start()
            except Exception:
                # The listening socket was closed during shutdown.
                break

    def _receive_loop(self, conn, addr):
        """
        Read messages from one incoming socket until it closes.
        """
        buffer = ""
        try:
            while self._running:
                data = conn.recv(BUFFER)
                if not data:
                    break
                buffer += data.decode(ENCODING)

                # Split the stream into complete newline-terminated messages.
                while DELIMITER in buffer:
                    line, buffer = buffer.split(DELIMITER, 1)
                    line = line.strip()
                    if line:
                        self._handle_incoming(line)
        except Exception:
            pass
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def _handle_incoming(self, raw):
        """
        Parse one received line and add it to the message queue.
        """
        parts = raw.split("|", 2)
        if len(parts) != 3:
            return   # ignore malformed input

        kind, sender, message = parts

        msg = {
            "from":    sender,
            "message": message,
            "private": kind == "private",
            "system":  False,
        }
        if kind == "private":
            msg["to"] = self._username

        self._messages.put(msg)

    # Reading queued messages.

    def get_messages(self):
        """
        Return all queued messages since the last call.
        """
        messages = []
        while not self._messages.empty():
            try:
                messages.append(self._messages.get_nowait())
            except queue.Empty:
                break
        return messages

# bind() gives the socket an IP address/port
#listen() sets the socket into listening mode, ie ready for others to connect
# accept() waits for one of these connections