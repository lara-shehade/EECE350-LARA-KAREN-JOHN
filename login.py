import pygame
import sys
import colorsys
import os
pygame.init()

WIDTH = 600
HEIGHT = 500
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("Πthon Arena")
clock = pygame.time.Clock()

# ─── Colors ───
SKY_BLUE = (135, 206, 235)
WHITE    = (255, 255, 255)
BLACK    = (0, 0, 0)
CYAN     = (0, 230, 200)

# ─── Fonts ───
title_font      = pygame.font.SysFont("comicsansms", 58, bold=True)
cust_title_font = pygame.font.SysFont("comicsansms", 30, bold=True)
label_font      = pygame.font.SysFont("Arial", 16)
input_font      = pygame.font.SysFont("tahoma", 20)
button_font     = pygame.font.SysFont("impact", 20)
key_label_font  = pygame.font.SysFont("tahoma", 13)
key_value_font  = pygame.font.SysFont("Arial", 16)

# ─── Assets ───
ground_img = pygame.image.load("assets/ground.png").convert_alpha()
GROUND_HEIGHT = 130
KEY_PRESS_SOUND_PATH = os.path.join("assets", "sound-8.mp3")
ground_img = pygame.transform.scale(ground_img, (WIDTH, GROUND_HEIGHT))

cloud_img = pygame.image.load("assets/cloud.png").convert_alpha()
clouds = [
    {"x": 50.0,  "y": 40,  "speed": 0.3, "scale": 0.50},
    {"x": 350.0, "y": 80,  "speed": 0.2, "scale": 0.35},
    {"x": 600.0, "y": 20,  "speed": 0.4, "scale": 0.45},
]
for c in clouds:
    ow, oh = cloud_img.get_size()
    nw, nh = int(ow * c["scale"]), int(oh * c["scale"])
    c["img"]   = pygame.transform.smoothscale(cloud_img, (nw, nh))
    c["width"] = nw


CUSTOMIZE_MUSIC_PATH = os.path.join("assets", "customizesnakemusic.mp3")


def _play_looping_music(path, volume=0.2):
    if not path or not os.path.exists(path):
        return False
    try:
        if pygame.mixer.get_init() is None:
            pygame.mixer.init()
        pygame.mixer.music.load(path)
        pygame.mixer.music.set_volume(volume)
        pygame.mixer.music.play(-1)
        return True
    except Exception as e:
        print(f"[AUDIO] Could not start music '{path}': {e}")
        return False


def _stop_music():
    try:
        if pygame.mixer.get_init() is not None:
            pygame.mixer.music.stop()
    except Exception:
        pass


def _play_key_press_sound():
    """
    Play a one-shot sound for key/button presses.
    """
    if not os.path.exists(KEY_PRESS_SOUND_PATH):
        return

    try:
        if pygame.mixer.get_init() is None:
            pygame.mixer.init()
        sound = pygame.mixer.Sound(KEY_PRESS_SOUND_PATH)
        sound.set_volume(0.8)
        sound.play()
    except Exception as e:
        print(f"[AUDIO] Could not play key press sound: {e}")


# =============================================================================
# STATE
# =============================================================================

screen_state    = "login"     # "login"  |  "customize"

# Login screen
username        = ""
username_active = False
error_msg       = ""
keys_map        = {"UP": pygame.K_UP, "DOWN": pygame.K_DOWN,
                   "LEFT": pygame.K_LEFT, "RIGHT": pygame.K_RIGHT}
key_names       = {"UP": "", "DOWN": "", "LEFT": "", "RIGHT": ""}
binding_active  = None
key_error_msg   = ""

# Customize screen (persists back to login when saved)
selected_hue    = 0.33
dragging_color  = False
head_style      = "classic"   # "classic"  |  "emoji"
emoji_text      = "^.^"
emoji_active    = False


# =============================================================================
# LAYOUT CONSTANTS
# =============================================================================

CX = WIDTH // 2

# ── Login screen ──────────────────────────────────────────────────────────────
USER_W, USER_H = 350, 40
USER_X = CX - USER_W // 2
USER_Y = 140

KEYS_Y       = USER_Y + USER_H + 70
KEY_BOX_W    = 65
KEY_BOX_H    = 40
KEY_GAP      = 20
KEYS_TOTAL_W = 4 * KEY_BOX_W + 3 * KEY_GAP
KEYS_X       = CX - KEYS_TOTAL_W // 2

CUST_BTN_W = 220
CUST_BTN_H = 44
CUST_BTN_X = CX - CUST_BTN_W // 2
CUST_BTN_Y = KEYS_Y + KEY_BOX_H + 45

BTN_W, BTN_H = 140, 42
BTN_GAP      = 120
BTN_Y        = HEIGHT - GROUND_HEIGHT - BTN_H + 70
EXIT_X       = CX - BTN_GAP // 2 - BTN_W
JOIN_X       = CX + BTN_GAP // 2

# ── Customize screen ──────────────────────────────────────────────────────────
BAR_W, BAR_H = 350, 22
BAR_X        = CX - BAR_W // 2
BAR_Y        = 95

PREVIEW_Y = BAR_Y + 40

TOGGLE_Y    = PREVIEW_Y + 65
TOGGLE_W    = 150
TOGGLE_H    = 36
TOGGLE_GAP  = 10
CLASSIC_X   = CX - TOGGLE_W - TOGGLE_GAP // 2
EMOJI_BTN_X = CX + TOGGLE_GAP // 2

EINPUT_W, EINPUT_H = 200, 40
EINPUT_X = CX - EINPUT_W // 2
EINPUT_Y = TOGGLE_Y + TOGGLE_H + 28

SAVE_BTN_W = 130
SAVE_BTN_H = 42
SAVE_BTN_Y = HEIGHT - GROUND_HEIGHT - SAVE_BTN_H + 70
BACK_X     = CX - BTN_GAP // 2 - SAVE_BTN_W
SAVE_X     = CX + BTN_GAP // 2


# =============================================================================
# HELPERS
# =============================================================================

def create_hue_bar(w, h):
    """Full rainbow hue bar using HSV colour space — same as original login.py."""
    surf = pygame.Surface((w, h))
    for x in range(w):
        hue = x / w
        r, g, b = colorsys.hsv_to_rgb(hue, 0.85, 0.85)
        pygame.draw.line(surf, (int(r*255), int(g*255), int(b*255)), (x, 0), (x, h))
    return surf

hue_bar = create_hue_bar(BAR_W, BAR_H)


def get_color():
    """Return the RGB colour at the current slider position using HSV."""
    r, g, b = colorsys.hsv_to_rgb(selected_hue, 0.85, 0.85)
    return (int(r*255), int(g*255), int(b*255))


def make_gradient(base):
    r, g, b = base
    head = (max(0, r-60), max(0, g-60), max(0, b-60))
    tail = (min(255, r+80), min(255, g+80), min(255, b+80))
    return head, tail


def get_emoji_head_font(text, head_size):
    safe_text  = text or "^.^"
    max_width  = head_size - 6
    max_height = head_size - 8
    for font_size in range(20, 8, -1):
        font  = pygame.font.SysFont("tahoma", font_size, bold=False)
        label = font.render(safe_text, True, BLACK)
        if label.get_width() <= max_width and label.get_height() <= max_height:
            return font
    return pygame.font.SysFont("tahoma", 10, bold=False)


def draw_centered_face(surface, text, center, head_size):
    face_text = text or "^.^"
    font      = get_emoji_head_font(face_text, head_size)
    label     = font.render(face_text, True, BLACK)
    surface.blit(label, label.get_rect(center=center))


def draw_snake_preview(surface, x, y, color, style="classic", emoji="^.^"):
    head_c, tail_c = make_gradient(color)
    segs = 6
    size = 24
    gap  = size - 3

    for i in range(segs - 1, -1, -1):
        t  = i / (segs - 1) if segs > 1 else 0
        cr = int(head_c[0] + (tail_c[0] - head_c[0]) * t)
        cg = int(head_c[1] + (tail_c[1] - head_c[1]) * t)
        cb = int(head_c[2] + (tail_c[2] - head_c[2]) * t)

        sx   = x + i * gap
        rect = pygame.Rect(sx, y, size, size)
        pygame.draw.rect(surface, (cr, cg, cb), rect, border_radius=7)
        pygame.draw.rect(surface,
                         (max(0,cr-30), max(0,cg-30), max(0,cb-30)),
                         rect, 2, border_radius=7)

        if i == 0:
            if style == "classic":
                er = 4
                ey = y + size // 3
                pygame.draw.circle(surface, WHITE, (sx + size//3,     ey), er)
                pygame.draw.circle(surface, BLACK, (sx + size//3 - 1, ey), 2)
                pygame.draw.circle(surface, WHITE, (sx + 2*size//3,     ey), er)
                pygame.draw.circle(surface, BLACK, (sx + 2*size//3 - 1, ey), 2)
            else:
                draw_centered_face(surface, emoji or "^.^",
                                   (sx + size//2, y + size//2), size)


def draw_clouds():
    for c in clouds:
        c["x"] += c["speed"]
        if c["x"] > WIDTH:
            c["x"] = -c["width"]
        screen.blit(c["img"], (int(c["x"]), c["y"]))


def draw_background():
    screen.fill(SKY_BLUE)
    draw_clouds()
    screen.blit(ground_img, (0, HEIGHT - GROUND_HEIGHT))


def draw_button(rect, text, base_color, hover_color, border_color, mouse_pos):
    hover = rect.collidepoint(mouse_pos)
    color = hover_color if hover else base_color
    pygame.draw.rect(screen, color,        rect, border_radius=10)
    pygame.draw.rect(screen, border_color, rect, 2, border_radius=10)
    txt = button_font.render(text, True, WHITE)
    screen.blit(txt, (rect.centerx - txt.get_width()//2,
                      rect.centery - txt.get_height()//2))


# =============================================================================
# DRAW: LOGIN SCREEN
# =============================================================================

def draw_login_screen():
    mouse = pygame.mouse.get_pos()

    # Title
    title  = title_font.render("Πthon Arena", True, BLACK)
    shadow = title_font.render("Πthon Arena", True, (80, 80, 80))
    screen.blit(shadow, (CX - title.get_width()//2 + 2, 16))
    screen.blit(title,  (CX - title.get_width()//2,     14))

    sub = label_font.render("Design your snake, then join the battle!", True, (40, 80, 40))
    screen.blit(sub, (CX - sub.get_width()//2, 90))

    # ── Username ──
    ulabel = label_font.render("Username", True, (40, 60, 40))
    screen.blit(ulabel, (USER_X, USER_Y - 20))

    uborder   = (0, 180, 160) if username_active else (100, 130, 100)
    user_rect = pygame.Rect(USER_X, USER_Y, USER_W, USER_H)
    pygame.draw.rect(screen, WHITE,   user_rect, border_radius=8)
    pygame.draw.rect(screen, uborder, user_rect, 2, border_radius=8)

    utext = input_font.render(username, True, BLACK)
    screen.blit(utext, (USER_X + 12, USER_Y + USER_H//2 - utext.get_height()//2))

    if username_active and pygame.time.get_ticks() % 1000 < 500:
        cur_x = USER_X + 12 + utext.get_width() + 2
        pygame.draw.line(screen, BLACK, (cur_x, USER_Y + 8), (cur_x, USER_Y + USER_H - 8), 2)

    if not username and not username_active:
        ph = input_font.render("Enter your name...", True, (150, 150, 150))
        screen.blit(ph, (USER_X + 12, USER_Y + USER_H//2 - ph.get_height()//2))

    if error_msg:
        err = label_font.render(error_msg, True, (200, 30, 30))
        screen.blit(err, (USER_X, USER_Y + USER_H + 5))

    # ── Key bindings ──
    klabel = label_font.render("Controls  (click to rebind)", True, (40, 60, 40))
    screen.blit(klabel, (KEYS_X, KEYS_Y - 20))

    for idx, key_name in enumerate(["UP", "DOWN", "LEFT", "RIGHT"]):
        bx  = KEYS_X + idx * (KEY_BOX_W + KEY_GAP)
        box = pygame.Rect(bx, KEYS_Y, KEY_BOX_W, KEY_BOX_H)

        is_active = (binding_active == key_name)
        fill   = (0, 180, 160) if is_active else WHITE
        border = CYAN           if is_active else (100, 130, 100)

        pygame.draw.rect(screen, fill,   box, border_radius=6)
        pygame.draw.rect(screen, border, box, 2, border_radius=6)

        dir_txt = key_label_font.render(key_name,            True, (80, 80, 80))
        key_txt = key_value_font.render(key_names[key_name], True, BLACK)
        screen.blit(dir_txt, (box.centerx - dir_txt.get_width()//2, box.y + 5))
        screen.blit(key_txt, (box.centerx - key_txt.get_width()//2, box.y + 22))

    if key_error_msg:
        kerr = label_font.render(key_error_msg, True, (200, 30, 30))
        screen.blit(kerr, (KEYS_X, KEYS_Y + KEY_BOX_H + 5))

    # ── Customize button ──
    cust_rect = pygame.Rect(CUST_BTN_X, CUST_BTN_Y, CUST_BTN_W, CUST_BTN_H)
    draw_button(cust_rect, "CUSTOMIZE SNAKE",
                (45, 95, 185), (70, 125, 225), (120, 170, 255), mouse)

    # ── Exit / Join ──
    exit_rect = pygame.Rect(EXIT_X, BTN_Y, BTN_W, BTN_H)
    draw_button(exit_rect, "EXIT", (140, 40, 40), (180, 50, 50), (200, 60, 60), mouse)

    join_rect = pygame.Rect(JOIN_X, BTN_Y, BTN_W, BTN_H)
    if username.strip():
        draw_button(join_rect, "JOIN", (0, 160, 140), (0, 200, 170), (0, 230, 200), mouse)
    else:
        draw_button(join_rect, "JOIN", (100,100,100), (100,100,100), (130,130,130), mouse)


# =============================================================================
# DRAW: CUSTOMIZE SCREEN
# =============================================================================

def draw_customize_screen():
    mouse = pygame.mouse.get_pos()

    # Title
    t      = cust_title_font.render("Customize Your Snake", True, BLACK)
    shadow = cust_title_font.render("Customize Your Snake", True, (80, 80, 80))
    screen.blit(shadow, (CX - t.get_width()//2 + 1, 21))
    screen.blit(t,      (CX - t.get_width()//2,     20))

    # ── Color picker ──
    clabel = label_font.render("Snake Color", True, (40, 60, 40))
    screen.blit(clabel, (BAR_X, BAR_Y - 20))

    screen.blit(hue_bar, (BAR_X, BAR_Y))
    pygame.draw.rect(screen, (100, 130, 100), (BAR_X, BAR_Y, BAR_W, BAR_H), 2, border_radius=3)

    cur_x = BAR_X + int(selected_hue * BAR_W)
    pygame.draw.rect(screen, WHITE, (cur_x - 3, BAR_Y - 3, 6, BAR_H + 6), border_radius=2)
    pygame.draw.rect(screen, BLACK, (cur_x - 3, BAR_Y - 3, 6, BAR_H + 6), 1, border_radius=2)

    # Live snake preview
    preview_x = CX - (6 * 21) // 2
    draw_snake_preview(screen, preview_x, PREVIEW_Y, get_color(), head_style, emoji_text)

    # ── Head Style toggle ──
    hlabel = label_font.render("Head Style", True, (40, 60, 40))
    screen.blit(hlabel, (CX - hlabel.get_width()//2, TOGGLE_Y - 22))

    classic_rect   = pygame.Rect(CLASSIC_X,   TOGGLE_Y, TOGGLE_W, TOGGLE_H)
    emoji_btn_rect = pygame.Rect(EMOJI_BTN_X, TOGGLE_Y, TOGGLE_W, TOGGLE_H)

    for rect, label, active in [
        (classic_rect,   "Classic Eyes", head_style == "classic"),
        (emoji_btn_rect, "Emoji Head",   head_style == "emoji"),
    ]:
        fill   = (0, 180, 160) if active else WHITE
        border = (0, 180, 160) if active else (100, 130, 100)
        color  = WHITE          if active else (60, 60, 60)
        pygame.draw.rect(screen, fill,   rect, border_radius=8)
        pygame.draw.rect(screen, border, rect, 2, border_radius=8)
        txt = button_font.render(label, True, color)
        screen.blit(txt, (rect.centerx - txt.get_width()//2,
                          rect.centery - txt.get_height()//2))

    # ── Emoji input ──
    if head_style == "emoji":
        elabel = label_font.render("Head Emoji  (3 chars max)", True, (40, 60, 40))
        screen.blit(elabel, (EINPUT_X, EINPUT_Y - 20))

        einput_rect = pygame.Rect(EINPUT_X, EINPUT_Y, EINPUT_W, EINPUT_H)
        eborder = (0, 180, 160) if emoji_active else (100, 130, 100)
        pygame.draw.rect(screen, WHITE,   einput_rect, border_radius=8)
        pygame.draw.rect(screen, eborder, einput_rect, 2, border_radius=8)

        etxt = input_font.render(emoji_text, True, BLACK)
        screen.blit(etxt, (einput_rect.centerx - etxt.get_width()//2,
                           einput_rect.centery - etxt.get_height()//2))

        if emoji_active and pygame.time.get_ticks() % 1000 < 500:
            cx = einput_rect.centerx + etxt.get_width()//2 + 2
            pygame.draw.line(screen, BLACK,
                             (cx, EINPUT_Y + 8), (cx, EINPUT_Y + EINPUT_H - 8), 2)

    # ── Back / Save ──
    back_rect = pygame.Rect(BACK_X, SAVE_BTN_Y, SAVE_BTN_W, SAVE_BTN_H)
    save_rect = pygame.Rect(SAVE_X, SAVE_BTN_Y, SAVE_BTN_W, SAVE_BTN_H)

    draw_button(back_rect, "BACK",
                (122, 73, 92),  (156, 92, 116),  (199, 128, 146), mouse)
    draw_button(save_rect, "SAVE",
                (138, 90, 56),  (168, 111, 73),  (206, 149, 108), mouse)


# =============================================================================
# MAIN LOOP
# =============================================================================

def run_login_screen(initial_error=""):
    """
    Show the login screen and return the result dict when JOIN is clicked.
    Pass initial_error to pre-fill the error message (e.g. USERNAME_TAKEN).
    """
    global username, username_active, error_msg
    global selected_hue, dragging_color
    global head_style, emoji_text, emoji_active
    global binding_active, key_error_msg, keys_map, key_names
    global screen_state

    # Pre-fill error if passed (e.g. server rejected the username)
    error_msg = initial_error

    result  = None
    running = True
    current_music_path = None

    while running:
        desired_music_path = CUSTOMIZE_MUSIC_PATH
        if desired_music_path != current_music_path:
            _stop_music()
            if desired_music_path and _play_looping_music(desired_music_path):
                current_music_path = desired_music_path
            else:
                current_music_path = None

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            elif event.type == pygame.MOUSEBUTTONDOWN:
                _play_key_press_sound()
                mx, my = event.pos

                if screen_state == "login":
                    user_rect = pygame.Rect(USER_X,     USER_Y,     USER_W,     USER_H)
                    join_rect = pygame.Rect(JOIN_X,     BTN_Y,      BTN_W,      BTN_H)
                    exit_rect = pygame.Rect(EXIT_X,     BTN_Y,      BTN_W,      BTN_H)
                    cust_rect = pygame.Rect(CUST_BTN_X, CUST_BTN_Y, CUST_BTN_W, CUST_BTN_H)

                    username_active = user_rect.collidepoint(mx, my)
                    if username_active:
                        binding_active = None

                    for idx, key_name in enumerate(["UP", "DOWN", "LEFT", "RIGHT"]):
                        bx  = KEYS_X + idx * (KEY_BOX_W + KEY_GAP)
                        box = pygame.Rect(bx, KEYS_Y, KEY_BOX_W, KEY_BOX_H)
                        if box.collidepoint(mx, my):
                            binding_active  = key_name
                            username_active = False

                    if cust_rect.collidepoint(mx, my):
                        screen_state    = "customize"
                        username_active = False
                        binding_active  = None

                    if join_rect.collidepoint(mx, my):
                        if username.strip():
                            result = {
                                "username":   username.strip(),
                                "color":      get_color(),
                                "keys":       keys_map,
                                "head_style": head_style,
                                "head_emoji": emoji_text if head_style == "emoji" else None,
                            }
                            running = False
                        else:
                            error_msg = "Please enter a username"

                    if exit_rect.collidepoint(mx, my):
                        running = False

                elif screen_state == "customize":
                    bar_rect     = pygame.Rect(BAR_X,       BAR_Y,      BAR_W,      BAR_H)
                    classic_rect = pygame.Rect(CLASSIC_X,   TOGGLE_Y,   TOGGLE_W,   TOGGLE_H)
                    emoji_b_rect = pygame.Rect(EMOJI_BTN_X, TOGGLE_Y,   TOGGLE_W,   TOGGLE_H)
                    einput_rect  = pygame.Rect(EINPUT_X,    EINPUT_Y,   EINPUT_W,   EINPUT_H)
                    save_rect    = pygame.Rect(SAVE_X,  SAVE_BTN_Y, SAVE_BTN_W, SAVE_BTN_H)
                    back_rect    = pygame.Rect(BACK_X,  SAVE_BTN_Y, SAVE_BTN_W, SAVE_BTN_H)

                    emoji_active = False

                    if bar_rect.collidepoint(mx, my):
                        dragging_color = True
                    elif classic_rect.collidepoint(mx, my):
                        head_style = "classic"
                    elif emoji_b_rect.collidepoint(mx, my):
                        head_style = "emoji"
                    elif head_style == "emoji" and einput_rect.collidepoint(mx, my):
                        emoji_active = True

                    if save_rect.collidepoint(mx, my) or back_rect.collidepoint(mx, my):
                        screen_state = "login"
                        emoji_active = False

            elif event.type == pygame.MOUSEBUTTONUP:
                dragging_color = False

            elif event.type == pygame.MOUSEMOTION and dragging_color:
                mx = max(BAR_X, min(event.pos[0], BAR_X + BAR_W))
                selected_hue = (mx - BAR_X) / BAR_W

            elif event.type == pygame.KEYDOWN:
                _play_key_press_sound()
                if screen_state == "customize" and emoji_active:
                    if event.key == pygame.K_BACKSPACE:
                        emoji_text = emoji_text[:-1]
                    elif len(emoji_text) < 3 and event.unicode.isprintable():
                        emoji_text += event.unicode

                elif binding_active:
                    duplicate = False
                    for dir_name, existing_key in keys_map.items():
                        if dir_name != binding_active and existing_key == event.key:
                            key_error_msg = f"'{pygame.key.name(event.key)}' already used for {dir_name}"
                            duplicate = True
                            break
                    if not duplicate:
                        keys_map[binding_active]  = event.key
                        key_names[binding_active] = pygame.key.name(event.key).upper()
                        key_error_msg = ""
                    binding_active = None

                elif username_active:
                    error_msg = ""
                    if event.key == pygame.K_BACKSPACE:
                        username = username[:-1]
                    elif event.key == pygame.K_RETURN and username.strip():
                        result = {
                            "username":   username.strip(),
                            "color":      get_color(),
                            "keys":       keys_map,
                            "head_style": head_style,
                            "head_emoji": emoji_text if head_style == "emoji" else None,
                        }
                        running = False
                    elif len(username) < 20 and event.unicode.isprintable():
                        username += event.unicode

        draw_background()
        if screen_state == "login":
            draw_login_screen()
        else:
            draw_customize_screen()

        pygame.display.flip()
        clock.tick(60)

    _stop_music()
    return result


# =============================================================================
# ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    pygame.init()
    result = run_login_screen()
    if result:
        print(f"Username:   {result['username']}")
        print(f"Color:      {result['color']}")
        print(f"Keys:       {result['keys']}")
        print(f"Head Style: {result['head_style']}")
        print(f"Head Emoji: {result['head_emoji']}")
    else:
        print("Exited without joining")
    pygame.quit()
    sys.exit()
