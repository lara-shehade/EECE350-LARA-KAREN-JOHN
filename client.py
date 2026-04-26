import pygame
import socket
import sys
import queue
import threading
import protocol
from login import run_login_screen
from chat import P2PChat
from lobby import run_lobby_screen
from game_screen import run_game_screen, load_assets

# Server connection settings
SERVER_HOST = "10.169.12.107"

# Window settings
WINDOW_WIDTH  = 800
WINDOW_HEIGHT = 600
FPS           = 60
CAPTION       = "Πthon Arena"

def main():
    # Check port argument
    if len(sys.argv) != 2:
        print("Usage: python client.py <port>")
        print("Example: python client.py 5555")
        sys.exit(1)

    try:
        SERVER_PORT = int(sys.argv[1])
    except ValueError:
        print("Error: Port must be a number")
        sys.exit(1)

    # Validate port range
    if SERVER_PORT < 1024 or SERVER_PORT > 65535:
        print("Error: Port must be between 1024 and 65535")
        sys.exit(1)

    # Start pygame
    pygame.init()

    # Load game assets once
    assets = load_assets()

    server_error = ""
    sock         = None

    while True:
        # Show login screen
        result = run_login_screen(initial_error=server_error)

        if result is None:
            break

        # Start chat listener
        chat = P2PChat(result["username"])
        chat.start()

        # Connect to server
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            sock.connect((SERVER_HOST, SERVER_PORT))
            sock.settimeout(None)
        except ConnectionRefusedError:
            server_error = "Cannot connect — is the server running?"
            sock = None
            continue
        except Exception as e:
            server_error = f"Connection failed: {e}"
            sock = None
            continue

        # Send player info to server
        join_msg = protocol.send_join(
            username   = result["username"],
            color      = list(result["color"]),
            head_style = result["head_style"],
            head_emoji = result["head_emoji"],
            chat_port  = chat.get_port(),
        )
        try:
            protocol.send(sock, join_msg)
        except Exception as e:
            server_error = f"Failed to send join: {e}"
            sock.close()
            sock = None
            continue

        # Wait for server reply
        try:
            response = protocol.receive(sock)
        except Exception as e:
            server_error = f"No response from server: {e}"
            sock.close()
            sock = None
            continue

        header, body = protocol.parse(response)

        if header == "PTHON_ARENA":
            header = body

        if header == "USERNAME_TAKEN":
            server_error = "Username already taken"
            sock.close()
            sock = None
            continue

        if header == "USERNAME_OK":
            print(f"[CLIENT] Joined as '{result['username']}'")
            print(f"[CLIENT] Connected to {SERVER_HOST}:{SERVER_PORT}")

            # Queue for server messages
            msg_q = queue.Queue()

            # Receive messages from server
            def _rx_thread():
                while True:
                    try:
                        raw = protocol.receive(sock)
                        if not raw:
                            msg_q.put(("DISCONNECT", None)); break
                        h, b = protocol.parse(raw)
                        msg_q.put((h, b))
                    except Exception:
                        msg_q.put(("DISCONNECT", None)); break

            threading.Thread(target=_rx_thread, daemon=True,
                             name="client-rx").start()

            # Switch between lobby and game
            while True:
                lobby_result = run_lobby_screen(sock, result, chat, msg_q)
                if lobby_result == "game":
                    game_result = run_game_screen(sock, result,
                                                  mode="player",
                                                  assets=assets,
                                                  msg_q=msg_q)
                elif lobby_result == "watch":
                    game_result = run_game_screen(sock, result,
                                                  mode="spectator",
                                                  assets=assets,
                                                  msg_q=msg_q)
                else:
                    break
                if game_result == "quit":
                    break
            break

        # Handle unexpected server reply
        server_error = f"Wrong server reply: {response[:80]}"
        print(f"[CLIENT] Wrong server reply from {SERVER_HOST}:{SERVER_PORT}: {response!r}")
        sock.close()
        sock = None

    # Close connection
    if sock:
        sock.close()
    try:
        chat.stop()
    except Exception:
        pass
    pygame.quit()
    sys.exit()


def _placeholder_connected_screen(sock, player_info):
    screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
    pygame.display.set_caption(CAPTION)
    clock  = pygame.time.Clock()
    font_big   = pygame.font.SysFont("comicsansms", 36, bold=True)
    font_small = pygame.font.SysFont("Arial", 20)

    color = tuple(player_info["color"])

    running = True
    while running:
        # Handle user input
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False

        screen.fill((135, 206, 235))

        # Connected message
        msg    = font_big.render("Connected to server!", True, (20, 100, 20))
        shadow = font_big.render("Connected to server!", True, (60, 60, 60))
        screen.blit(shadow, (WINDOW_WIDTH//2 - msg.get_width()//2 + 2, 202))
        screen.blit(msg,    (WINDOW_WIDTH//2 - msg.get_width()//2,     200))

        sub = font_small.render(
            f"Logged in as:  {player_info['username']}", True, (40, 60, 40))
        screen.blit(sub, (WINDOW_WIDTH//2 - sub.get_width()//2, 270))

        # Show player color
        pygame.draw.rect(screen, color,       (WINDOW_WIDTH//2 - 40, 310, 80, 30), border_radius=6)
        pygame.draw.rect(screen, (0, 0, 0),   (WINDOW_WIDTH//2 - 40, 310, 80, 30), 2, border_radius=6)
        clbl = font_small.render("Your color", True, (40, 60, 40))
        screen.blit(clbl, (WINDOW_WIDTH//2 - clbl.get_width()//2, 350))

        hint = font_small.render("(Lobby coming in Step 2 — press ESC to exit)", True, (100, 100, 100))
        screen.blit(hint, (WINDOW_WIDTH//2 - hint.get_width()//2, 420))

        pygame.display.flip()
        clock.tick(FPS)


if __name__ == "__main__":
    main()