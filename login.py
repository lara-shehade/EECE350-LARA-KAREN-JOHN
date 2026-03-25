import pygame
import sys
import colorsys

pygame.init()

WIDTH = 600
HEIGHT = 500
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("Πthon Arena")
clock = pygame.time.Clock()

# Colors
SKY_BLUE = (135, 206, 235)
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
GRAY = (200, 200, 200)
DARK_GRAY = (60, 60, 65)
CYAN = (0, 230, 200)
BORDER = (80, 80, 85)
PANEL_BG = (30, 30, 35, 180)  # semi-transparent

# Fonts
title_font = pygame.font.SysFont("comicsansms", 58, bold=True ,)
label_font = pygame.font.SysFont("Arial", 16)  #the label above username
input_font = pygame.font.SysFont("tahoma", 20)  #the actual input field
button_font = pygame.font.SysFont("impact", 20)
#key binding stuff
key_label_font = pygame.font.SysFont("tahoma", 13)   # small font for "UP", "DOWN" etc labels
key_value_font = pygame.font.SysFont("Arial", 16)   # slightly bigger font for the actual key shown

# ─── Load Assets ───
ground_img = pygame.image.load("assets/ground.png").convert_alpha()
GROUND_HEIGHT = 130
ground_img = pygame.transform.scale(ground_img, (WIDTH, GROUND_HEIGHT))

cloud_img = pygame.image.load("assets/cloud.png").convert_alpha()

# Three clouds at different sizes, heights, and speeds
clouds = [
    {"x": 50.0,  "y": 40,  "speed": 0.3, "scale": 0.5},
    {"x": 350.0, "y": 80,  "speed": 0.2, "scale": 0.35},
    {"x": 600.0, "y": 20,  "speed": 0.4, "scale": 0.45},
]

# Pre-scale cloud images
for c in clouds:
    orig_w, orig_h = cloud_img.get_size()
    new_w = int(orig_w * c["scale"])
    new_h = int(orig_h * c["scale"])
    c["img"] = pygame.transform.smoothscale(cloud_img, (new_w, new_h))
    c["width"] = new_w

# ─── State ───
username = ""
username_active = False
selected_hue = 0.33
dragging_color = False
error_msg = ""

# keys bindings 

keys_map = {"UP": pygame.K_UP, "DOWN": pygame.K_DOWN, "LEFT": pygame.K_LEFT, "RIGHT": pygame.K_RIGHT}
key_names = {"UP": "↑", "DOWN": "↓", "LEFT": "←", "RIGHT": "→"}
binding_active = None
key_error_msg = ""

# ─── Layout (centered) ───
CX = WIDTH // 2
CONTENT_TOP = 160  # below title

# Username
USER_W = 350
USER_H = 40
USER_X = CX - USER_W // 2
USER_Y = CONTENT_TOP

# Color bar
BAR_W = 350
BAR_H = 22
BAR_X = CX - BAR_W // 2
BAR_Y = USER_Y + USER_H + 50

# Snake preview
PREVIEW_Y = BAR_Y + 35

#buttons
KEYS_Y = PREVIEW_Y + 40          # vertical position, sits below the snake preview
KEY_BOX_W = 65                    # width of each key box
KEY_BOX_H = 40                    # height of each key box  
KEY_GAP = 20                      # space between boxes
KEYS_TOTAL_W = 4 * KEY_BOX_W + 3 * KEY_GAP   # total width of all 4 boxes + gaps
KEYS_X = CX - KEYS_TOTAL_W // 2              # starting x, centers the whole row

# Buttons (above the ground, same size, side by side)
BTN_W = 140
BTN_H = 42
BTN_GAP = 120
BTN_Y = HEIGHT - GROUND_HEIGHT - BTN_H +50  #+50 pushes the buttons lower 
EXIT_X = CX - BTN_GAP // 2 - BTN_W
JOIN_X = CX + BTN_GAP // 2


# ─── Hue Bar ───
def create_hue_bar(w, h):
    surf = pygame.Surface((w, h))
    for x in range(w):
        hue = x / w
        r, g, b = colorsys.hsv_to_rgb(hue, 0.85, 0.85)
        pygame.draw.line(surf, (int(r*255), int(g*255), int(b*255)), (x, 0), (x, h))
    return surf


hue_bar = create_hue_bar(BAR_W, BAR_H)


def get_color():
    r, g, b = colorsys.hsv_to_rgb(selected_hue, 0.85, 0.85)
    return (int(r*255), int(g*255), int(b*255))


def make_gradient(base):
    r, g, b = base
    head = (max(0, r-60), max(0, g-60), max(0, b-60))
    tail = (min(255, r+80), min(255, g+80), min(255, b+80))
    return head, tail


def draw_snake_preview(surface, x, y, color):
    head_c, tail_c = make_gradient(color)
    segs = 6
    size = 24
    gap = size - 3

    for i in range(segs - 1, -1, -1):
        t = i / (segs - 1) if segs > 1 else 0
        cr = int(head_c[0] + (tail_c[0] - head_c[0]) * t)
        cg = int(head_c[1] + (tail_c[1] - head_c[1]) * t)
        cb = int(head_c[2] + (tail_c[2] - head_c[2]) * t)

        sx = x + i * gap
        rect = pygame.Rect(sx, y, size, size)
        pygame.draw.rect(surface, (cr, cg, cb), rect, border_radius=7)
        pygame.draw.rect(surface, (max(0,cr-30), max(0,cg-30), max(0,cb-30)), rect, 2, border_radius=7)

        if i == 0:
            er = 4
            ey = y + size // 3
            pygame.draw.circle(surface, WHITE, (sx + size//3, ey), er)
            pygame.draw.circle(surface, BLACK, (sx + size//3 - 1, ey), 2)
            pygame.draw.circle(surface, WHITE, (sx + 2*size//3, ey), er)
            pygame.draw.circle(surface, BLACK, (sx + 2*size//3 - 1, ey), 2)


def draw_clouds():
    for c in clouds:
        c["x"] += c["speed"]
        if c["x"] > WIDTH:
            c["x"] = -c["width"]
        screen.blit(c["img"], (int(c["x"]), c["y"]))


# ─── Main Loop ───
result = None
running = True

while running:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False

        elif event.type == pygame.MOUSEBUTTONDOWN:
            mx, my = event.pos
            bar_rect = pygame.Rect(BAR_X, BAR_Y, BAR_W, BAR_H)
            user_rect = pygame.Rect(USER_X, USER_Y, USER_W, USER_H)
            join_rect = pygame.Rect(JOIN_X, BTN_Y, BTN_W, BTN_H)
            exit_rect = pygame.Rect(EXIT_X, BTN_Y, BTN_W, BTN_H)

            if bar_rect.collidepoint(mx, my):
                dragging_color = True
            if user_rect.collidepoint(mx, my):
                username_active = True
            else:
                username_active = False
            if join_rect.collidepoint(mx, my):
                if username.strip():
                    result = {"username": username.strip(), "color": get_color()}
                    running = False
                else:
                    error_msg = "Please enter a username"
            if exit_rect.collidepoint(mx, my):
                running = False

        elif event.type == pygame.MOUSEBUTTONUP:
            dragging_color = False

        elif event.type == pygame.MOUSEMOTION and dragging_color:
            mx = max(BAR_X, min(event.pos[0], BAR_X + BAR_W))
            selected_hue = (mx - BAR_X) / BAR_W

        elif event.type == pygame.KEYDOWN and username_active:
            error_msg = ""
            if event.key == pygame.K_BACKSPACE:
                username = username[:-1]
            elif event.key == pygame.K_RETURN and username.strip():
                result = {"username": username.strip(), "color": get_color()}
                running = False
            elif len(username) < 15 and event.unicode.isprintable():
                username += event.unicode

    # ─── Draw ───

    # Sky
    screen.fill(SKY_BLUE)

    # Clouds (behind everything)
    draw_clouds()

    # Ground at bottom
    screen.blit(ground_img, (0, HEIGHT - GROUND_HEIGHT))

    # ─── Title ───
    title = title_font.render("Πthon Arena", True, (0, 0, 0)) #black color
    shadow = title_font.render("Πthon Arena", True, (80, 80, 80)) #gray shadow
    screen.blit(shadow, (CX - title.get_width()//2 + 2, 24))  #lower the 30 and 28 to get the title higher on the screen
    screen.blit(title, (CX - title.get_width()//2, 22))   

    subtitle = label_font.render("Design your snake, then join the battle!", True, (40, 80, 40))
    screen.blit(subtitle, (CX - subtitle.get_width()//2, 96))

    # ─── Username ───
    ulabel = label_font.render("Username", True, (40, 60, 40))
    screen.blit(ulabel, (USER_X, USER_Y - 20))

    uborder = (0, 180, 160) if username_active else (100, 130, 100)
    user_rect = pygame.Rect(USER_X, USER_Y, USER_W, USER_H)
    pygame.draw.rect(screen, (255, 255, 255, 200), user_rect, border_radius=8)
    pygame.draw.rect(screen, uborder, user_rect, 2, border_radius=8)

    utext = input_font.render(username, True, BLACK)
    screen.blit(utext, (USER_X + 12, USER_Y + USER_H//2 - utext.get_height()//2))

    if username_active and pygame.time.get_ticks() % 1000 < 500:
        cur_x = USER_X + 12 + utext.get_width() + 2
        pygame.draw.line(screen, BLACK, (cur_x, USER_Y + 8), (cur_x, USER_Y + USER_H - 8), 2)

    if not username and not username_active:
        ph = input_font.render("Enter your name...", True, (150, 150, 150))
        screen.blit(ph, (USER_X + 12, USER_Y + USER_H//2 - ph.get_height()//2))

    # Error message
    if error_msg:
        err = label_font.render(error_msg, True, (200, 30, 30))
        screen.blit(err, (USER_X, USER_Y + USER_H + 5))

    # ─── Color Picker ───
    clabel = label_font.render("Snake Color", True, (40, 60, 40))
    screen.blit(clabel, (BAR_X, BAR_Y - 20))

    screen.blit(hue_bar, (BAR_X, BAR_Y))
    pygame.draw.rect(screen, (100, 130, 100), (BAR_X, BAR_Y, BAR_W, BAR_H), 2, border_radius=3)

    # Cursor
    cx = BAR_X + int(selected_hue * BAR_W)
    pygame.draw.rect(screen, WHITE, (cx - 3, BAR_Y - 3, 6, BAR_H + 6), border_radius=2)
    pygame.draw.rect(screen, BLACK, (cx - 3, BAR_Y - 3, 6, BAR_H + 6), 1, border_radius=2)

    # Snake preview
    preview_x = CX - (6 * 21) // 2
    draw_snake_preview(screen, preview_x, PREVIEW_Y, get_color())

    # ─── Buttons ───
    mouse = pygame.mouse.get_pos()

    # Exit (left)
    exit_rect = pygame.Rect(EXIT_X, BTN_Y, BTN_W, BTN_H)
    ehover = exit_rect.collidepoint(mouse)
    ecolor = (180, 50, 50) if ehover else (140, 40, 40)
    pygame.draw.rect(screen, ecolor, exit_rect, border_radius=10)
    pygame.draw.rect(screen, (200, 60, 60), exit_rect, 2, border_radius=10)
    etxt = button_font.render("EXIT", True, WHITE)
    screen.blit(etxt, (exit_rect.centerx - etxt.get_width()//2,
                        exit_rect.centery - etxt.get_height()//2))

    # Join (right)
    join_rect = pygame.Rect(JOIN_X, BTN_Y, BTN_W, BTN_H)
    jhover = join_rect.collidepoint(mouse) and username.strip()
    if username.strip():
        jcolor = (0, 200, 170) if jhover else (0, 160, 140)
        jborder = (0, 230, 200)
    else:
        jcolor = (100, 100, 100)
        jborder = (130, 130, 130)
    pygame.draw.rect(screen, jcolor, join_rect, border_radius=10)
    pygame.draw.rect(screen, jborder, join_rect, 2, border_radius=10)
    jtxt = button_font.render("JOIN", True, WHITE)
    screen.blit(jtxt, (join_rect.centerx - jtxt.get_width()//2,
                        join_rect.centery - jtxt.get_height()//2))

    pygame.display.flip()
    clock.tick(60)

if result:
    print(f"Username: {result['username']}")
    print(f"Color: {result['color']}")
    print(f"Gradient: {make_gradient(result['color'])}")
else:
    print("Exited without joining")

pygame.quit()
sys.exit()