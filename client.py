import pygame
import socket
import sys
import protocol
from login import run_login_screen
from chat import P2PChat
from lobby import run_lobby_screen

# =============================================================================

# How to run:
#   python client.py 5555
# =============================================================================

# =============================================================================
# CLIENT-SIDE CONSTANTS
# =============================================================================

SERVER_HOST = "127.0.0.1"   # change to LAN IP for multi-machine play

WINDOW_WIDTH  = 800
WINDOW_HEIGHT = 600
FPS           = 60
CAPTION       = "Πthon Arena"

# =============================================================================
# ENTRY POINT
# =============================================================================

def main():
    # ── Validate command line argument ────────────────────────────────────────
    if len(sys.argv) != 2:
        print("Usage: python client.py <port>")
        print("Example: python client.py 5555")
        sys.exit(1)

    try:
        SERVER_PORT = int(sys.argv[1])
    except ValueError:
        print("Error: Port must be a number")
        sys.exit(1)

    if SERVER_PORT < 1024 or SERVER_PORT > 65535:
        print("Error: Port must be between 1024 and 65535")
        sys.exit(1)

    # ── Init pygame ───────────────────────────────────────────────────────────
    pygame.init()

    # ── Login loop ────────────────────────────────────────────────────────────
    # We loop here so that if the server rejects the username,
    # we come back to the login screen with an error message.
    server_error = ""
    sock         = None

    while True:
        # Show login screen — if server rejected last attempt, show the error
        result = run_login_screen(initial_error=server_error)

        if result is None:
            # Player clicked EXIT
            break

        # ── Start P2P chat listener ───────────────────────────────────────────
        # Must be created AFTER login so we know the username,
        # and BEFORE connect so we have the port ready for JOIN.
        chat = P2PChat(result["username"])
        chat.start()

        # ── Try to connect to the server ──────────────────────────────────────
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            sock.connect((SERVER_HOST, SERVER_PORT))
            sock.settimeout(None)   # blocking mode after connect
        except ConnectionRefusedError:
            server_error = "Cannot connect — is the server running?"
            sock = None
            continue
        except Exception as e:
            server_error = f"Connection failed: {e}"
            sock = None
            continue

        # ── Send JOIN ─────────────────────────────────────────────────────────
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

        # ── Wait for server response ──────────────────────────────────────────
        try:
            response = protocol.receive(sock)
        except Exception as e:
            server_error = f"No response from server: {e}"
            sock.close()
            sock = None
            continue

        header, _ = protocol.parse(response)

        if header == "USERNAME_TAKEN":
            # Server rejected — show error on login screen
            server_error = "Username already taken"
            sock.close()
            sock = None
            continue

        if header == "USERNAME_OK":
            print(f"[CLIENT] Joined as '{result['username']}'")
            print(f"[CLIENT] Connected to {SERVER_HOST}:{SERVER_PORT}")
            lobby_result = run_lobby_screen(sock, result, chat)
            if lobby_result == "game":
                pass   # TODO: Step 3 — game screen
            elif lobby_result == "watch":
                pass   # TODO: Step 5 — spectator screen
            break

        # Unexpected response
        server_error = f"Unexpected response: {header}"
        sock.close()
        sock = None

    # ── Cleanup ───────────────────────────────────────────────────────────────
    if sock:
        sock.close()
    try:
        chat.stop()
    except Exception:
        pass
    pygame.quit()
    sys.exit()


def _placeholder_connected_screen(sock, player_info):
    """
    Temporary screen shown after successful login.
    Displays 'Connected!' until we build the lobby in Step 2.
    Press ESC or close window to exit.
    """
    screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
    pygame.display.set_caption(CAPTION)
    clock  = pygame.time.Clock()
    font_big   = pygame.font.SysFont("comicsansms", 36, bold=True)
    font_small = pygame.font.SysFont("Arial", 20)

    color = tuple(player_info["color"])

    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False

        screen.fill((135, 206, 235))

        # Green tick + connected message
        msg    = font_big.render("Connected to server!", True, (20, 100, 20))
        shadow = font_big.render("Connected to server!", True, (60, 60, 60))
        screen.blit(shadow, (WINDOW_WIDTH//2 - msg.get_width()//2 + 2, 202))
        screen.blit(msg,    (WINDOW_WIDTH//2 - msg.get_width()//2,     200))

        sub = font_small.render(
            f"Logged in as:  {player_info['username']}", True, (40, 60, 40))
        screen.blit(sub, (WINDOW_WIDTH//2 - sub.get_width()//2, 270))

        # Snake color swatch
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