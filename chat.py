import socket
import threading
import queue

# Message delimiter — same principle as the server protocol
DELIMITER = "\n"
ENCODING  = "utf-8"
BUFFER    = 4096


class P2PChat:
    """
    Manages all peer-to-peer chat connections for one client.

    Usage:
        chat = P2PChat("Lara")
        chat.start()

        # After JOIN is accepted:
        port = chat.get_port()   # include in JOIN message

        # When PLAYERS_LIST arrives:
        chat.update_players(players)

        # When user sends a message:
        chat.send_public("gl hf")
        chat.send_private("Ali", "hey want to rematch?")

        # Every frame in the lobby:
        for msg in chat.get_messages():
            display(msg)   # {"from": "Lara", "message": "...", "private": False}

        # On exit:
        chat.stop()
    """

    def __init__(self, my_username):
        self._username    = my_username

        # Listening socket — accepts incoming P2P connections
        self._server_sock = None
        self._port        = 0

        # Outgoing connections — lazily opened, keyed by username
        # { username: socket }
        self._connections = {}
        self._conn_lock   = threading.Lock()

        # Player info from PLAYERS_LIST — needed to know who to connect to
        # { username: {"ip": str, "chat_port": int} }
        self._players     = {}
        self._players_lock = threading.Lock()

        # Thread-safe queue of incoming (and sent) messages
        # Each item: {"from": str, "message": str, "private": bool}
        self._messages    = queue.Queue()

        # Background threads
        self._accept_thread  = None
        self._running        = False

    # =========================================================================
    # START / STOP
    # =========================================================================

    def start(self):
        """
        Open the listening socket and start the accept thread.
        Call this before sending JOIN to the server.
        """
        self._server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        # Bind to port 0 — OS picks a free port automatically
        self._server_sock.bind(("0.0.0.0", 0))
        self._server_sock.listen(10)
        self._port   = self._server_sock.getsockname()[1]
        self._running = True

        # Start background thread to accept incoming connections
        self._accept_thread = threading.Thread(
            target=self._accept_loop,
            daemon=True,
            name="P2PChat-accept"
        )
        self._accept_thread.start()
        print(f"[CHAT] Listening for P2P connections on port {self._port}")

    def stop(self):
        """
        Close all sockets and stop all threads cleanly.
        Call this when the client exits.
        """
        self._running = False

        # Close listening socket — causes accept() to raise and exit the loop
        try:
            self._server_sock.close()
        except Exception:
            pass

        # Close all outgoing connections
        with self._conn_lock:
            for uname, sock in self._connections.items():
                try:
                    sock.close()
                except Exception:
                    pass
            self._connections.clear()

        print("[CHAT] P2P chat stopped")

    def get_port(self):
        """Return the port clients should connect to for P2P chat."""
        return self._port

    # =========================================================================
    # PLAYER LIST
    # =========================================================================

    def update_players(self, players_list):
        """
        Called every time a PLAYERS_LIST message arrives from the server.

        players_list: list of dicts from protocol.parse_players_list()
            [{"username": "Ali", "chat_port": 51204, "status": "lobby", ...}, ...]

        This updates our knowledge of who is online and where to reach them.
        Players who left are detected here — we close their connection and
        post a "left the chat" message.
        """
        with self._players_lock:
            new_usernames = {
                p["username"]
                for p in players_list
                if p["username"] != self._username
            }
            old_usernames = set(self._players.keys())

            # ── Players who left ──────────────────────────────────────────────
            for gone in old_usernames - new_usernames:
                self._messages.put({
                    "from":    gone,
                    "message": f"{gone} left the chat",
                    "private": False,
                    "system":  True,   # UI can style this differently
                })
                # Close their outgoing connection if we have one
                with self._conn_lock:
                    sock = self._connections.pop(gone, None)
                    if sock:
                        try:
                            sock.close()
                        except Exception:
                            pass

            # ── Update player info ────────────────────────────────────────────
            self._players = {}
            for p in players_list:
                if p["username"] != self._username:
                    self._players[p["username"]] = {
                        "ip":        "127.0.0.1",   # same machine for now
                        "chat_port": p.get("chat_port", 0),
                    }

    # =========================================================================
    # SENDING
    # =========================================================================

    def send_public(self, message):
        """
        Send a message to every connected player.
        The lobby handles local display — we only send to others here.
        """
        # Send to everyone
        with self._players_lock:
            targets = dict(self._players)

        for uname, info in targets.items():
            self._send_to(uname, info, message, private=False)

    def send_private(self, target_username, message):
        """
        Send a message to one specific player.
        The lobby handles local display — we only send to the target here.
        """
        with self._players_lock:
            info = self._players.get(target_username)

        if info is None:
            print(f"[CHAT] Cannot send to {target_username} — not in player list")
            return

        self._send_to(target_username, info, message, private=True)

    def _send_to(self, username, info, message, private):
        """
        Internal — send a raw message to one player.
        Opens the connection lazily if not already open.
        """
        chat_port = info.get("chat_port", 0)
        if chat_port == 0:
            # This player has no P2P port — skip silently
            return

        sock = self._get_or_connect(username, info["ip"], chat_port)
        if sock is None:
            return

        # Format: "private|from|message\n" or "public|from|message\n"
        kind = "private" if private else "public"
        raw  = f"{kind}|{self._username}|{message}{DELIMITER}"
        try:
            sock.sendall(raw.encode(ENCODING))
        except Exception as e:
            print(f"[CHAT] Send to {username} failed: {e}")
            # Remove broken connection so it gets reopened next time
            with self._conn_lock:
                self._connections.pop(username, None)

    def _get_or_connect(self, username, ip, port):
        """
        Return existing socket to username, or open a new one.
        Returns None if connection fails.
        """
        with self._conn_lock:
            if username in self._connections:
                return self._connections[username]

        # Open new connection outside the lock (slow operation)
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

    # =========================================================================
    # RECEIVING
    # =========================================================================

    def _accept_loop(self):
        """
        Background thread — accepts incoming P2P connections.
        For each new connection, spawns a receive thread.
        """
        while self._running:
            try:
                conn, addr = self._server_sock.accept()
                # Spawn a thread to handle this connection
                t = threading.Thread(
                    target=self._receive_loop,
                    args=(conn, addr),
                    daemon=True,
                    name=f"P2PChat-recv-{addr}"
                )
                t.start()
            except Exception:
                # Server socket closed — exit loop
                break

    def _receive_loop(self, conn, addr):
        """
        Background thread — receives messages from one incoming connection.
        Runs until the connection closes.
        """
        buffer = ""
        try:
            while self._running:
                data = conn.recv(BUFFER)
                if not data:
                    break
                buffer += data.decode(ENCODING)

                # Process all complete messages in the buffer
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
        Parse and queue one incoming message.
        Format: "public|sender|message" or "private|sender|message"
        """
        parts = raw.split("|", 2)
        if len(parts) != 3:
            return   # malformed — ignore

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

    # =========================================================================
    # READING MESSAGES
    # =========================================================================

    def get_messages(self):
        """
        Return all new messages since the last call.
        Call this every frame in the lobby.

        Returns a list of dicts:
            {
                "from":    str,          # sender username
                "message": str,          # message text
                "private": bool,         # True if private
                "system":  bool,         # True if system message (e.g. "Ali left")
                "to":      str | None,   # only present for private messages
            }
        """
        messages = []
        while not self._messages.empty():
            try:
                messages.append(self._messages.get_nowait())
            except queue.Empty:
                break
        return messages