# =============================================================================
# lobby.py — Πthon Arena
# =============================================================================

import pygame
import pygame.gfxdraw
import threading
import queue
import time
import os
import protocol

BOT_NAME = "PyBot"     # must match bot.BOT_NAME
LOBBY_MUSIC_PATH = os.path.join("assets", "lobby.mp3")
KEY_PRESS_SOUND_PATH = os.path.join("assets", "sound-8.mp3")
BUTTON_SOUND_PATH = os.path.join("assets", "button_lara.mp3")

# =============================================================================
# THEME  (matches login.py exactly)
# =============================================================================

SKY_BLUE    = (135, 206, 235)
WHITE       = (255, 255, 255)
BLACK       = (0,   0,   0)
TEAL        = (0,  180, 160)
TEAL_HOV    = (0,  210, 185)
TEAL_DARK   = (0,  115, 100)
SOFT_WHITE  = (244, 251, 248)
CARD_BG     = (236, 249, 244)
CARD_HOV    = (222, 244, 238)
CARD_BORDER = (188, 226, 216)

S_WAIT  = (38,  188,  82)    # green  — Waiting
S_MATCH = (212,  52,  52)    # red    — In Match
S_WATCH = (208, 142,  28)    # orange — Watching

TEXT_DARK   = (22,  42,  35)
TEXT_MID    = (82, 108,  94)
TEXT_LIGHT  = (152, 176, 165)

BTN_DIS     = (192, 202, 200)
BTN_DIS_T   = (142, 152, 150)
BTN_BLUE    = (68,  122, 210)
BTN_BLUE_H  = (84,  142, 228)

# =============================================================================
# LAYOUT
# =============================================================================

W, H        = 1100, 640
HEADER_H    = 64
LEFT_W      = 700       # player list
RIGHT_W     = W - LEFT_W  # 400 — chat
FPS         = 60

SEARCH_Y    = HEADER_H + 6
SEARCH_H    = 28
LIST_TOP    = SEARCH_Y + SEARCH_H + 4   # = HEADER_H + 38  — less than original 52
ROW_H       = 74
ROW_PAD     = 8
AVA_R       = 24

MATCH_H     = 44
MATCH_Y     = H - MATCH_H

CP_X        = LEFT_W
CP_PAD      = 12
CHAT_HDR_H  = 48
CHAT_MSG_T  = HEADER_H + CHAT_HDR_H + 6
CHAT_INP_H  = 42
CHAT_INP_Y  = H - CHAT_INP_H - 8
CHAT_MSG_B  = CHAT_INP_Y - 6


# =============================================================================
# RECEIVER THREAD
# =============================================================================

def _start_receiver(sock, q):
    def _run():
        while True:
            try:
                raw = protocol.receive(sock)
                if not raw:
                    q.put(("DISCONNECT", None)); break
                h, b = protocol.parse(raw)
                q.put((h, b))
            except Exception:
                q.put(("DISCONNECT", None)); break
    threading.Thread(target=_run, daemon=True, name="lobby-rx").start()


# =============================================================================
# UTILITIES
# =============================================================================

def _rrect(surf, color, rect, r=10, bw=0, bc=None):
    pygame.draw.rect(surf, color, rect, border_radius=r)
    if bw and bc:
        pygame.draw.rect(surf, bc, rect, bw, border_radius=r)


def _wrap(font, text, max_w):
    words, lines, line = text.split(), [], ""
    for w in words:
        t = (line + " " + w).strip()
        if font.size(t)[0] <= max_w:
            line = t
        else:
            if line: lines.append(line)
            line = w
    if line: lines.append(line)
    return lines


def _load_clouds():
    img = pygame.image.load(
        os.path.join("assets", "cloud.png")).convert_alpha()
    defs = [
        {"x": 30.0,  "y": 14, "speed": 0.25, "scale": 0.38},
        {"x": 420.0, "y": 42, "speed": 0.14, "scale": 0.27},
        {"x": 780.0, "y":  7, "speed": 0.32, "scale": 0.34},
    ]
    for c in defs:
        ow, oh = img.get_size()
        nw, nh = int(ow * c["scale"]), int(oh * c["scale"])
        c["img"]   = pygame.transform.smoothscale(img, (nw, nh))
        c["width"] = nw
    return defs


def _scroll_clouds(screen, clouds):
    for c in clouds:
        c["x"] += c["speed"]
        if c["x"] > W: c["x"] = -c["width"]
        screen.blit(c["img"], (int(c["x"]), c["y"]))


def _start_lobby_music():
    if not os.path.exists(LOBBY_MUSIC_PATH):
        return False
    try:
        if pygame.mixer.get_init() is None:
            pygame.mixer.init()
        pygame.mixer.music.load(LOBBY_MUSIC_PATH)
        pygame.mixer.music.set_volume(0.2)
        pygame.mixer.music.play(-1)
        return True
    except Exception as e:
        print(f"[AUDIO] Could not start lobby music: {e}")
        return False


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


def _play_button_sound():
    """
    Play the main action-button sound.
    """
    if not os.path.exists(BUTTON_SOUND_PATH):
        return

    try:
        if pygame.mixer.get_init() is None:
            pygame.mixer.init()
        sound = pygame.mixer.Sound(BUTTON_SOUND_PATH)
        sound.set_volume(0.45)
        sound.play()
    except Exception as e:
        print(f"[AUDIO] Could not play button sound: {e}")


def _draw_avatar(surf, cx, cy, r, color, style, emoji, f_em):
    """
    Smooth anti-aliased snake-head avatar.
    Classic mode: colored circle with proper snake eyes.
    Emoji mode:   colored circle with the emoji centred inside.
    """
    # --- filled circle (smooth via gfxdraw) ---
    try:
        pygame.gfxdraw.filled_circle(surf, cx, cy, r, color)
        dark = (max(0, color[0]-52), max(0, color[1]-52), max(0, color[2]-52))
        pygame.gfxdraw.aacircle(surf, cx, cy, r,     dark)
        pygame.gfxdraw.aacircle(surf, cx, cy, r - 1, dark)
    except Exception:
        dark = (max(0, color[0]-52), max(0, color[1]-52), max(0, color[2]-52))
        pygame.draw.circle(surf, color, (cx, cy), r)
        pygame.draw.circle(surf, dark,  (cx, cy), r, 2)

    if style == "emoji" and emoji:
        # render at a bigger size then scale for quality
        big_font = pygame.font.SysFont("tahoma", max(14, r))
        lbl = big_font.render(emoji, True, WHITE)
        lbl = pygame.transform.smoothscale(
            lbl, (min(lbl.get_width(),  r * 2 - 6),
                  min(lbl.get_height(), r * 2 - 6)))
        surf.blit(lbl, (cx - lbl.get_width()//2, cy - lbl.get_height()//2))
    else:
        # Classic snake eyes
        er  = max(3, r // 5)
        off = max(4, r // 3)
        for ex in [cx - off, cx + off]:
            try:
                pygame.gfxdraw.filled_circle(surf, ex, cy - 2, er,     WHITE)
                pygame.gfxdraw.aacircle(     surf, ex, cy - 2, er,     WHITE)
                kp = max(1, er - 1)
                pygame.gfxdraw.filled_circle(surf, ex - 1, cy - 2, kp, BLACK)
                pygame.gfxdraw.aacircle(     surf, ex - 1, cy - 2, kp, BLACK)
            except Exception:
                pygame.draw.circle(surf, WHITE, (ex, cy - 2), er)
                pygame.draw.circle(surf, BLACK, (ex - 1, cy - 2), max(1, er-1))


# =============================================================================
# MAIN
# =============================================================================

def run_lobby_screen(sock, player_info, chat, msg_q):
    """Returns: 'game' | 'watch' | 'quit'"""

    pygame.display.set_mode((W, H))
    pygame.display.set_caption("Πthon Arena — Lobby")
    screen = pygame.display.get_surface()
    clock  = pygame.time.Clock()
    music_started = _start_lobby_music()

    # ── Fonts ─────────────────────────────────────────────────────────────────
    f_title = pygame.font.SysFont("comicsansms", 28, bold=True)
    f_count = pygame.font.SysFont("Arial", 13)
    f_sec   = pygame.font.SysFont("Arial", 11, bold=True)
    f_sec_big = pygame.font.SysFont("Arial", 15, bold=True)  # ONLINE PLAYERS heading
    f_name  = pygame.font.SysFont("tahoma", 15, bold=True)
    f_stat  = pygame.font.SysFont("Arial",  12)
    f_btn   = pygame.font.SysFont("impact", 14)
    f_em    = pygame.font.SysFont("tahoma", 12)
    f_chat  = pygame.font.SysFont("tahoma", 13)
    f_chd   = pygame.font.SysFont("tahoma", 13, bold=True)
    f_inp   = pygame.font.SysFont("tahoma", 13)
    f_match = pygame.font.SysFont("segoeuiemoji,segoe ui emoji,tahoma", 12)

    # ── Assets ────────────────────────────────────────────────────────────────
    try:    clouds = _load_clouds()
    except: clouds = []

    # Search icon
    _search_icon = None
    try:
        _si = pygame.image.load(os.path.join("assets", "search.png")).convert_alpha()
        _search_icon = pygame.transform.smoothscale(_si, (20, 20))
    except Exception:
        pass

    ICON_SZ = 20
    try:
        raw_icon  = pygame.image.load(
            os.path.join("assets", "chat.png")).convert_alpha()
        chat_icon = pygame.transform.smoothscale(raw_icon, (ICON_SZ, ICON_SZ))
        # Tinted version for active state (white-ish)
        chat_icon_active = chat_icon.copy()
        chat_icon_active.fill((255, 255, 255, 200),
                               special_flags=pygame.BLEND_RGBA_MULT)
    except Exception:
        chat_icon        = None
        chat_icon_active = None

    # ── State ─────────────────────────────────────────────────────────────────
    players        = []
    scroll_off     = 0
    chat_mode      = "public"
    chat_target    = None
    chat_msgs      = []
    input_text     = ""
    input_active   = False
    challenge_from = None
    challenge_ts   = 0
    match_start_ts = None
    result         = "quit"
    unread         = {}   # {username: count} — unread private messages per sender

    # Search + filter state
    search_text      = ""
    search_active    = False
    filter_mode      = "username"   # "username" | "status"
    filter_dropdown  = False        # dropdown open

    my_name  = player_info["username"]
    my_color = tuple(int(c) for c in player_info.get("color", TEAL))
    my_style = player_info.get("head_style", "classic")
    my_emoji = player_info.get("head_emoji") or ""

    # Store chat button rects — updated every draw frame, used in event handler
    _chat_rects = [None, None, None, None]   # pub, priv, inp, snd

    # msg_q is the shared queue from client.py — single receiver thread for all screens

    # ── Small helpers ─────────────────────────────────────────────────────────
    def _sc(s):
        return {"lobby": S_WAIT, "in_game": S_MATCH,
                "spectating": S_WATCH}.get(s, TEXT_LIGHT)

    def _sl(s):
        return {"lobby": "Waiting", "in_game": "In Match",
                "spectating": "Watching"}.get(s, s.capitalize())

    def _who():
        m = [p["username"] for p in players if p.get("status") == "in_game"]
        return (m[0] if len(m) > 0 else None,
                m[1] if len(m) > 1 else None)

    def _elapsed():
        if match_start_ts is None: return "—"
        s = int(time.time() - match_start_ts)
        return f"{s//60:02d}:{s%60:02d}"

    def _visible_players():
        # Bot always appears at the top of the list — not from server
        bot_entry = {
            "username":   BOT_NAME,
            "color":      [148, 148, 158],   # steel gray
            "head_style": "robot",
            "head_emoji": None,
            "status":     "lobby",
            "is_bot":     True,
        }
        base = [p for p in players if p["username"] != my_name]
        # Only show bot when no game is active and player is in lobby
        # Always show the bot — server rejects Play if a game is already running
        prefix = [bot_entry]
        if not search_text:
            return prefix + base
        q = search_text.lower().strip()
        if filter_mode == "username":
            return prefix + [p for p in base if q in p["username"].lower()]
        # Status mode — map partial input to status keys
        status_map = {
            "lobby":       ["waiting", "wait"],
            "in_game":     ["in match", "match", "in"],
            "spectating":  ["watching", "watch"],
        }
        # Which statuses does this query plausibly match?
        matching = {s for s, kws in status_map.items()
                    if any(kw.startswith(q) for kw in kws)}
        # If nothing matches at all → immediate no results
        return prefix + [p for p in base if p.get("status") in matching]

    # =========================================================================
    # DRAW FUNCTIONS
    # =========================================================================

    # ── Search bar with mode selector ─────────────────────────────────────────
    def draw_search_bar():
        ICON_D  = SEARCH_H
        GAP     = 6
        BAR_X   = 10
        BAR_W   = LEFT_W - 20 - ICON_D - GAP
        PILL_W  = 110
        PILL_M  = 6

        bar_r  = pygame.Rect(BAR_X, SEARCH_Y, BAR_W, SEARCH_H)
        icon_r = pygame.Rect(BAR_X + BAR_W + GAP, SEARCH_Y, ICON_D, ICON_D)

        # Input bar
        bar_col = (234, 246, 250) if not search_active else WHITE
        bc      = TEAL if search_active else (198, 225, 232)
        _rrect(screen, bar_col, bar_r, r=SEARCH_H//2, bw=1, bc=bc)

        # Divider
        div_x = bar_r.right - PILL_W - PILL_M - 10
        pygame.draw.line(screen, (198, 225, 232),
                         (div_x, bar_r.y + 5), (div_x, bar_r.bottom - 5), 1)

        # Mode pill
        pill_r = pygame.Rect(bar_r.right - PILL_W - PILL_M,
                             bar_r.y + (SEARCH_H - 22) // 2,
                             PILL_W, 22)
        _rrect(screen, WHITE, pill_r, r=11, bw=1, bc=(198, 225, 232))

        mode_label = "By Username" if filter_mode == "username" else "By Status"
        pt = f_stat.render(mode_label, True, TEXT_DARK)
        tx = pill_r.x + 8
        screen.blit(pt, (tx, pill_r.centery - pt.get_height()//2))

        # Drawn triangle arrow (avoids font rendering issues)
        ax = pill_r.right - 12
        ay = pill_r.centery
        if filter_dropdown:
            # Up triangle
            pts = [(ax, ay + 3), (ax - 4, ay - 2), (ax + 4, ay - 2)]
        else:
            # Down triangle
            pts = [(ax, ay - 3), (ax - 4, ay + 2), (ax + 4, ay + 2)]
        pygame.draw.polygon(screen, TEXT_MID, pts)

        # Placeholder / typed text
        if search_text:
            tl = f_stat.render(search_text[:40], True, TEXT_DARK)
            screen.blit(tl, (bar_r.x + 16, bar_r.centery - tl.get_height()//2))
            if search_active and pygame.time.get_ticks() % 1000 < 500:
                cx = bar_r.x + 16 + f_stat.size(search_text[:40])[0] + 1
                pygame.draw.line(screen, TEXT_DARK,
                                 (cx, bar_r.y + 5), (cx, bar_r.bottom - 5), 1)
        else:
            ph = ("Search for username..." if filter_mode == "username"
                  else "Waiting  /  In Match  /  Watching")
            pl = f_stat.render(ph, True, TEXT_LIGHT)
            screen.blit(pl, (bar_r.x + 16, bar_r.centery - pl.get_height()//2))

        # Circular icon — medium blue matching reference
        ICON_COL     = (100, 160, 220)
        ICON_COL_HOV = (120, 180, 235)
        hover_icon = icon_r.collidepoint(pygame.mouse.get_pos())
        pygame.draw.circle(screen, ICON_COL_HOV if hover_icon else ICON_COL,
                           icon_r.center, ICON_D // 2)
        if _search_icon:
            screen.blit(_search_icon, _search_icon.get_rect(center=icon_r.center))
        else:
            lb = f_stat.render("S", True, WHITE)
            screen.blit(lb, (icon_r.centerx - lb.get_width()//2,
                              icon_r.centery - lb.get_height()//2))

        # Dropdown — connected directly to bar (no gap), top corners flush
        opt1_r = opt2_r = None
        if filter_dropdown:
            DW, OPT_H = pill_r.width + 12, 26
            DX = pill_r.x - 6
            DY = bar_r.bottom          # flush connection — no gap

            sh = pygame.Surface((DW + 6, OPT_H * 2 + 6), pygame.SRCALPHA)
            pygame.draw.rect(sh, (0, 0, 0, 35),
                             (3, 3, DW, OPT_H * 2), border_radius=8)
            screen.blit(sh, (DX - 1, DY - 1))

            _rrect(screen, WHITE,
                   pygame.Rect(DX, DY, DW, OPT_H * 2), r=8,
                   bw=1, bc=CARD_BORDER)

            for i, (key, label2) in enumerate([("username", "By Username"),
                                                ("status",   "By Status")]):
                opt_r = pygame.Rect(DX + 1, DY + i * OPT_H, DW - 2, OPT_H)
                if i == 0:
                    opt1_r = opt_r
                else:
                    opt2_r = opt_r
                sel     = filter_mode == key
                hover_o = opt_r.collidepoint(pygame.mouse.get_pos())
                bg = TEAL if sel else (CARD_HOV if hover_o else WHITE)
                pygame.draw.rect(screen, bg, opt_r,
                                 border_radius=7 if (i == 0 or i == 1) else 0)
                lt = f_stat.render(label2, True, WHITE if sel else TEXT_DARK)
                screen.blit(lt, (opt_r.x + 10, opt_r.centery - lt.get_height()//2))

        return bar_r, pill_r, icon_r, opt1_r, opt2_r

    # ── Header ────────────────────────────────────────────────────────────────
    def draw_header():
        strip = pygame.Surface((W, HEADER_H), pygame.SRCALPHA)
        strip.fill((255, 255, 255, 148))
        screen.blit(strip, (0, 0))
        pygame.draw.line(screen, (162, 216, 206),
                         (0, HEADER_H), (W, HEADER_H), 2)

        # "ONLINE PLAYERS" + count on the left of header
        ol = f_sec_big.render("ONLINE PLAYERS", True, TEXT_DARK)
        screen.blit(ol, (14, 10))
        wc2 = sum(1 for p in players
                  if p.get("status") == "lobby" and p["username"] != my_name)
        cl = f_count.render(
            f"{len(players)} online  ·  {wc2} waiting", True, TEXT_MID)
        screen.blit(cl, (14, 10 + ol.get_height() + 2))

        # Title centered in the left panel
        f_title_big = pygame.font.SysFont("comicsansms", 38, bold=True)
        sh = f_title_big.render("Πthon Arena", True, TEAL_DARK)
        ts = f_title_big.render("Πthon Arena", True, (30, 120, 200))
        tx = LEFT_W // 2 - ts.get_width() // 2
        ty = HEADER_H // 2 - ts.get_height() // 2
        screen.blit(sh, (tx + 2, ty + 2))
        screen.blit(ts, (tx, ty))

    # ── Player row ────────────────────────────────────────────────────────────
    def draw_row(p, ry, hov):
        uname  = p["username"]
        color  = tuple(int(c) for c in p.get("color", TEAL))
        status = p.get("status", "lobby")
        style  = p.get("head_style", "classic")
        emoji  = p.get("head_emoji") or ""
        is_me  = (uname == my_name)
        is_bot = p.get("is_bot", False)

        # Card
        cr = pygame.Rect(10, ry, LEFT_W - 20, ROW_H - ROW_PAD)
        _rrect(screen, CARD_HOV if hov else CARD_BG, cr,
               r=12, bw=1, bc=CARD_BORDER)

        # Avatar
        ax = cr.x + 14 + AVA_R
        ay = cr.centery
        _draw_avatar(screen, ax, ay, AVA_R, color, style, emoji, f_em)

        # Username
        nx = ax + AVA_R + 14
        nm = f_name.render(uname + (" (you)" if is_me else ""), True, TEXT_DARK)
        screen.blit(nm, (nx, cr.y + 12))

        # Status dot + label — hidden for bot, replaced with "AI Opponent"
        if is_bot:
            bot_lbl = f_stat.render("AI Opponent", True, (120, 120, 130))
            screen.blit(bot_lbl, (nx + 14, cr.y + 36))
        else:
            sc_col = _sc(status)
            dot_cx = nx + 5
            dot_cy = cr.y + 42
            try:
                pygame.gfxdraw.filled_circle(screen, dot_cx, dot_cy, 4, sc_col)
                pygame.gfxdraw.aacircle(screen, dot_cx, dot_cy, 4, sc_col)
            except Exception:
                pygame.draw.circle(screen, sc_col, (dot_cx, dot_cy), 4)
            screen.blit(f_stat.render(_sl(status), True, TEXT_MID),
                        (nx + 14, dot_cy - f_stat.get_height()//2))

        if is_me:
            return None, None, None

        right = cr.right - 10

        # ── Action button ─────────────────────────────────────────────────────
        BW, BH = 94, 30
        bx = right - BW
        by = cr.centery - BH // 2
        btn_r = pygame.Rect(bx, by, BW, BH)

        # Bot: Play when idle, Busy when any game is active (only one session allowed)
        if is_bot:
            bot_busy = any(p2.get("status") == "in_game" for p2 in players)
            if bot_busy:
                _rrect(screen, BTN_DIS, btn_r, r=8)
                bt = f_btn.render("Busy", True, BTN_DIS_T)
            else:
                _rrect(screen, TEAL_HOV if hov else TEAL, btn_r, r=8)
                bt = f_btn.render("Play", True, WHITE)
        elif status == "lobby":
            _rrect(screen, TEAL_HOV if hov else TEAL, btn_r, r=8)
            bt = f_btn.render("Challenge", True, WHITE)
        elif status == "in_game":
            _rrect(screen, BTN_BLUE_H if hov else BTN_BLUE, btn_r, r=8)
            bt = f_btn.render("Watch", True, WHITE)
        else:
            _rrect(screen, BTN_DIS, btn_r, r=8)
            bt = f_btn.render("Busy", True, BTN_DIS_T)

        screen.blit(bt, (btn_r.centerx - bt.get_width()//2,
                         btn_r.centery - bt.get_height()//2))

        # ── Chat icon button (hidden for bot) ────────────────────────────────────
        chat_r = None
        if not is_bot:
            CIW   = 30
            chat_r = pygame.Rect(bx - CIW - 8, by, CIW, BH)
            active = (uname == chat_target)
            _rrect(screen, TEAL if active else (208, 232, 226), chat_r,
                   r=8, bw=1, bc=TEAL if active else CARD_BORDER)
            if chat_icon:
                icon = chat_icon_active if active else chat_icon
                ix   = chat_r.centerx - ICON_SZ // 2
                iy   = chat_r.centery - ICON_SZ // 2
                screen.blit(icon, (ix, iy))
            else:
                fb = f_btn.render("💬", True, WHITE if active else TEXT_MID)
                screen.blit(fb, (chat_r.centerx - fb.get_width()//2,
                                  chat_r.centery - fb.get_height()//2))
            # Unread badge
            count = unread.get(uname, 0)
            if count > 0:
                badge_r = pygame.Rect(chat_r.right - 10, chat_r.top - 6, 16, 16)
                pygame.draw.circle(screen, (220, 50, 50),
                                   badge_r.center, 8)
                bl2 = f_stat.render(str(count), True, WHITE)
                screen.blit(bl2, (badge_r.centerx - bl2.get_width()//2,
                                  badge_r.centery - bl2.get_height()//2))

        return btn_r, chat_r, status

    # ── Self card (separate rounded card above chat panel) ────────────────────
    def draw_self_card():
        PAD    = 8
        card_h = 52
        card   = pygame.Rect(CP_X + PAD, PAD, RIGHT_W - PAD*2, card_h)

        # Shadow
        sh = pygame.Surface((card.width + 6, card.height + 6), pygame.SRCALPHA)
        pygame.draw.rect(sh, (0, 0, 0, 45),
                         (3, 3, card.width, card.height), border_radius=14)
        screen.blit(sh, (card.x - 1, card.y - 1))

        # Card background
        _rrect(screen, (230, 245, 252), card, r=14, bw=2, bc=(160, 210, 232))

        # Avatar
        SELF_R = 18
        ava_cx = card.x + CP_PAD + SELF_R
        ava_cy = card.centery
        _draw_avatar(screen, ava_cx, ava_cy, SELF_R,
                     my_color, my_style, my_emoji, f_em)

        # Username
        nm_s = f_name.render(my_name, True, TEXT_DARK)
        screen.blit(nm_s, (ava_cx + SELF_R + 10,
                            ava_cy - nm_s.get_height()//2))

    # ── Chat panel (starts below the self card) ───────────────────────────────
    def draw_chat():
        PAD        = 8
        SELF_H     = 52           # height of self card above
        SELF_GAP   = 6            # gap between self card and chat panel
        chat_top   = PAD + SELF_H + SELF_GAP
        panel      = pygame.Rect(CP_X + PAD, chat_top,
                                 RIGHT_W - PAD*2, H - chat_top - PAD)

        # Shadow
        shadow_surf = pygame.Surface((panel.width + 6, panel.height + 6),
                                     pygame.SRCALPHA)
        pygame.draw.rect(shadow_surf, (0, 0, 0, 55),
                         (3, 3, panel.width, panel.height), border_radius=16)
        screen.blit(shadow_surf, (panel.x - 1, panel.y - 1))

        # Panel background
        _rrect(screen, (230, 245, 252), panel, r=16, bw=2, bc=(160, 210, 232))

        # ── Tabs row at top of chat panel ─────────────────────────────────────
        TAB_Y  = panel.y + 10
        pub_r  = pygame.Rect(panel.x + CP_PAD,          TAB_Y, 80, 26)
        priv_r = pygame.Rect(panel.x + CP_PAD + 80 + 8, TAB_Y, 88, 26)
        for r, label, active in [
            (pub_r,  "Public",  chat_mode == "public"),
            (priv_r, "Private", chat_mode == "private"),
        ]:
            _rrect(screen, TEAL if active else (178, 216, 232), r, r=7)
            lt = f_stat.render(label, True, WHITE if active else TEXT_MID)
            screen.blit(lt, (r.centerx - lt.get_width()//2,
                              r.centery - lt.get_height()//2))

        # Chat mode label beside tabs
        if chat_mode == "public":
            mode_lbl = f_stat.render("Everyone in the lobby", True, TEXT_LIGHT)
        else:
            mode_lbl = f_stat.render(
                f"with  {chat_target}" if chat_target else "select a player",
                True, TEXT_LIGHT)
        screen.blit(mode_lbl, (priv_r.right + 10,
                                TAB_Y + 13 - mode_lbl.get_height()//2))

        # Divider below tabs
        div_y = TAB_Y + 26 + 8
        pygame.draw.line(screen, (180, 215, 230),
                         (panel.x + 8, div_y), (panel.right - 8, div_y), 1)

        # Messages area
        msg_top = div_y + 6
        msg_bot = panel.bottom - CHAT_INP_H - 14
        ma      = pygame.Rect(panel.x + 4, msg_top,
                              panel.width - 8, msg_bot - msg_top)
        clip    = pygame.Surface((ma.width, ma.height), pygame.SRCALPHA)
        clip.fill((0, 0, 0, 0))

        if chat_mode == "public":
            visible = [m for m in chat_msgs if not m.get("private")]
        else:
            visible = [
                m for m in chat_msgs
                if m.get("private") and (
                    (m.get("from") == my_name and m.get("to") == chat_target) or
                    (m.get("from") == chat_target)
                )
            ]

        yo = ma.height - 4
        for msg in reversed(visible[-50:]):
            is_me2 = msg["from"] == my_name
            is_sys = msg.get("system", False)
            txt    = msg["message"]
            sndr   = msg["from"]
            mxw    = ma.width - 22

            if is_sys:
                for line in reversed(_wrap(f_stat, txt, mxw)):
                    ls = f_stat.render(line, True, TEXT_LIGHT)
                    yo -= ls.get_height() + 2
                    clip.blit(ls, (ma.width//2 - ls.get_width()//2, yo))
                yo -= 5
            else:
                lines = _wrap(f_chat, txt, mxw - 16)
                bh2   = sum(f_chat.get_height() + 2 for _ in lines) + 10
                bw2   = min(max(f_chat.size(l)[0] for l in lines) + 18, mxw)
                bx2   = (ma.width - bw2 - 4) if is_me2 else 4
                by2   = yo - bh2

                pygame.draw.rect(clip, TEAL if is_me2 else WHITE,
                                 (bx2, by2, bw2, bh2), border_radius=11)
                if not is_me2:
                    pygame.draw.rect(clip, (172, 216, 230),
                                     (bx2, by2, bw2, bh2), 1, border_radius=11)

                ty2 = by2 + 5
                for line in lines:
                    ls = f_chat.render(line, True,
                                       WHITE if is_me2 else TEXT_DARK)
                    clip.blit(ls, (bx2 + 9, ty2))
                    ty2 += f_chat.get_height() + 2

                if not is_me2:
                    sn = f_stat.render(sndr, True, TEAL_DARK)
                    yo = by2 - sn.get_height() - 3
                    clip.blit(sn, (4, yo))
                    yo -= 4
                else:
                    yo = by2 - 6

        screen.blit(clip, (ma.x, ma.y))

        # Input row
        inp_y2 = panel.bottom - CHAT_INP_H - 6
        inp_r  = pygame.Rect(panel.x + CP_PAD, inp_y2,
                              panel.width - CP_PAD*2 - 64, CHAT_INP_H)
        snd_r  = pygame.Rect(inp_r.right + 6, inp_y2, 56, CHAT_INP_H)

        ib = TEAL if input_active else (164, 206, 222)
        _rrect(screen, WHITE, inp_r, r=9, bw=2, bc=ib)
        disp = input_text if input_text else "Type a message..."
        tc   = TEXT_DARK  if input_text else TEXT_LIGHT
        it   = f_inp.render(disp, True, tc)
        screen.blit(it, (inp_r.x + 9, inp_r.centery - it.get_height()//2))

        if input_active and pygame.time.get_ticks() % 1000 < 500:
            cx3 = inp_r.x + 9 + f_inp.size(input_text)[0] + 1
            pygame.draw.line(screen, TEXT_DARK,
                             (cx3, inp_r.y + 7), (cx3, inp_r.bottom - 7), 1)

        can = bool(input_text.strip())
        _rrect(screen, TEAL_HOV if can else BTN_DIS, snd_r, r=9)
        st2 = f_btn.render("Send", True, WHITE if can else BTN_DIS_T)
        screen.blit(st2, (snd_r.centerx - st2.get_width()//2,
                           snd_r.centery - st2.get_height()//2))

        _chat_rects[0] = pub_r
        _chat_rects[1] = priv_r
        _chat_rects[2] = inp_r
        _chat_rects[3] = snd_r
        return pub_r, priv_r, inp_r, snd_r

    # ── Match bar ─────────────────────────────────────────────────────────────
    def draw_match_bar():
        bs = pygame.Surface((LEFT_W, MATCH_H), pygame.SRCALPHA)
        bs.fill((178, 228, 216, 212))
        screen.blit(bs, (0, MATCH_Y))
        pygame.draw.line(screen, (148, 208, 196),
                         (0, MATCH_Y), (LEFT_W, MATCH_Y), 1)

        p1, p2 = _who()
        if p1 and p2:
            txt = f_match.render(
                f"⚔  {p1}  vs  {p2}   —   {_elapsed()}", True, TEAL_DARK)
        elif p1:
            txt = f_match.render(
                f"⚔  {p1} is in a match   —   {_elapsed()}", True, TEAL_DARK)
        else:
            txt = f_match.render(
                "No active match right now.", True, TEXT_LIGHT)

        screen.blit(txt, (16, MATCH_Y + MATCH_H//2 - txt.get_height()//2))

    # ── Challenge popup ───────────────────────────────────────────────────────
    def draw_popup():
        if not challenge_from: return None, None
        ov = pygame.Surface((W, H), pygame.SRCALPHA)
        ov.fill((0, 0, 0, 110))
        screen.blit(ov, (0, 0))

        pw, ph = 360, 168
        px, py = W//2 - pw//2, H//2 - ph//2
        _rrect(screen, WHITE, pygame.Rect(px, py, pw, ph),
               r=18, bw=2, bc=TEAL)

        tt = f_name.render("⚔  Challenge Received!", True, TEXT_DARK)
        screen.blit(tt, (px + pw//2 - tt.get_width()//2, py + 18))
        ft = f_stat.render(f"{challenge_from} wants to battle you",
                           True, TEXT_MID)
        screen.blit(ft, (px + pw//2 - ft.get_width()//2, py + 46))

        bw3, bh3 = 112, 34
        acc = pygame.Rect(px + 38,            py + ph - bh3 - 18, bw3, bh3)
        dec = pygame.Rect(px + pw - 38 - bw3, py + ph - bh3 - 18, bw3, bh3)
        _rrect(screen, TEAL,          acc, r=10)
        _rrect(screen, (188, 46, 46), dec, r=10)
        for r2, label in [(acc, "Accept"), (dec, "Decline")]:
            lt = f_btn.render(label, True, WHITE)
            screen.blit(lt, (r2.centerx - lt.get_width()//2,
                              r2.centery - lt.get_height()//2))
        return acc, dec

    # =========================================================================
    # MAIN LOOP
    # =========================================================================

    running = True
    # Pre-initialize rects — populated each draw frame, used in event handler
    _bar_r = _pill_r = _icon_r = _opt1_r = _opt2_r = None
    while running:
        clock.tick(FPS)
        mouse = pygame.mouse.get_pos()

        # Server messages
        while not msg_q.empty():
            try: hdr, body = msg_q.get_nowait()
            except queue.Empty: break

            if hdr == "PLAYERS_LIST":
                players = protocol.parse_players_list(body)
                chat.update_players(players)
                in_game_now = any(p.get("status") == "in_game" for p in players)
                if match_start_ts is None and in_game_now:
                    # Game already running when we joined — approximate start as now
                    match_start_ts = time.time()
                elif not in_game_now:
                    # Game ended — reset timer for next match
                    match_start_ts = None
            elif hdr == "CHALLENGE_FROM":
                challenge_from = body
                challenge_ts   = pygame.time.get_ticks()
            elif hdr == "CHALLENGE_DECLINED":
                chat_msgs.append({
                    "from": "System",
                    "message": f"{body} declined your challenge.",
                    "private": False, "system": True})
            elif hdr == "GAME_START":
                match_start_ts = time.time()
                result  = "game"; running = False; break
            elif hdr == "DISCONNECT":
                result  = "quit"; running = False; break

        # P2P messages
        for msg in chat.get_messages():
            chat_msgs.append(msg)
            # Track unread private messages
            if (msg.get("private") and not msg.get("system")
                    and msg["from"] != my_name
                    and msg["from"] != chat_target):
                unread[msg["from"]] = unread.get(msg["from"], 0) + 1

        if challenge_from and pygame.time.get_ticks() - challenge_ts > 30000:
            challenge_from = None

        # Events
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                result = "quit"; running = False

            elif event.type == pygame.MOUSEWHEEL:
                scroll_off = max(0, scroll_off - event.y * 22)

            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                mx, my2 = event.pos

                # Popup first
                if challenge_from:
                    acc_r, dec_r = draw_popup()
                    if acc_r and acc_r.collidepoint(mx, my2):
                        _play_button_sound()
                        protocol.send(sock, protocol.send_accept(challenge_from))
                        challenge_from = None
                    elif dec_r and dec_r.collidepoint(mx, my2):
                        _play_button_sound()
                        protocol.send(sock, protocol.send_decline(challenge_from))
                        challenge_from = None
                    continue

                # Dropdown options
                if filter_dropdown and _opt1_r and _opt1_r.collidepoint(mx, my2):
                    _play_key_press_sound()
                    filter_mode = "username"; filter_dropdown = False
                    search_text = ""; continue
                if filter_dropdown and _opt2_r and _opt2_r.collidepoint(mx, my2):
                    _play_key_press_sound()
                    filter_mode = "status"; filter_dropdown = False
                    search_text = ""; continue
                if filter_dropdown:
                    filter_dropdown = False

                # Mode pill — toggle dropdown
                if _pill_r and _pill_r.collidepoint(mx, my2):
                    _play_key_press_sound()
                    filter_dropdown = not filter_dropdown
                    search_active   = False; continue

                # Input bar or icon btn — activate search typing
                if ((_bar_r and _bar_r.collidepoint(mx, my2)) or
                        (_icon_r and _icon_r.collidepoint(mx, my2))):
                    search_active   = True
                    filter_dropdown = False
                    input_active    = False; continue

                # Chat panel
                pub_r2, priv_r2, inp_r2, snd_r2 = _chat_rects
                if None not in (pub_r2, priv_r2, inp_r2, snd_r2) and mx >= LEFT_W:
                    if pub_r2.collidepoint(mx, my2):
                        _play_key_press_sound()
                        chat_mode = "public"; chat_target = None
                    elif priv_r2.collidepoint(mx, my2):
                        _play_key_press_sound()
                        chat_mode = "private"
                    elif inp_r2.collidepoint(mx, my2):
                        input_active  = True
                        search_active = False
                    elif snd_r2.collidepoint(mx, my2) and input_text.strip():
                        _play_key_press_sound()
                        m = input_text.strip()
                        if chat_mode == "public":
                            chat_msgs.append({
                                "from": my_name, "message": m,
                                "private": False, "system": False})
                            chat.send_public(m)
                        elif chat_target:
                            chat_msgs.append({
                                "from": my_name, "message": m,
                                "private": True, "system": False,
                                "to": chat_target})
                            chat.send_private(chat_target, m)
                        input_text = ""

                if mx < LEFT_W:
                    if not (_bar_r and _bar_r.collidepoint(mx, my2)):
                        search_active = False
                    input_active = False
                    # Player row clicks — use filtered list
                    ry = LIST_TOP - scroll_off
                    for p in _visible_players():
                        un  = p["username"]
                        cr2 = pygame.Rect(10, ry, LEFT_W - 20, ROW_H - ROW_PAD)
                        if cr2.collidepoint(mx, my2):
                            st  = p.get("status", "lobby")
                            BW, BH = 94, 30
                            bx  = cr2.right - 10 - BW
                            by  = cr2.centery - BH // 2
                            b3  = pygame.Rect(bx, by, BW, BH)
                            c3  = pygame.Rect(bx - 38, by, 30, BH)
                            if b3.collidepoint(mx, my2):
                                if p.get("is_bot"):
                                    bot_busy = any(p2.get("status") == "in_game" for p2 in players)
                                    if not bot_busy:
                                        _play_button_sound()
                                        protocol.send(sock, protocol.send_play_bot())
                                elif st == "lobby":
                                    _play_button_sound()
                                    protocol.send(sock, protocol.send_challenge(un))
                                elif st == "in_game":
                                    _play_button_sound()
                                    protocol.send(sock, "WATCH")
                                    result = "watch"; running = False
                            elif c3 and c3.collidepoint(mx, my2) and not p.get("is_bot"):
                                _play_key_press_sound()
                                if chat_target == un:
                                    chat_target = None
                                    chat_mode   = "public"
                                else:
                                    chat_target  = un
                                    chat_mode    = "private"
                                    input_active = True
                                    search_active = False
                                    unread[un]   = 0
                        ry += ROW_H

            elif event.type == pygame.KEYDOWN:
                if search_active:
                    if event.key == pygame.K_ESCAPE:
                        search_active = False
                        search_text   = ""
                    elif event.key == pygame.K_BACKSPACE:
                        search_text = search_text[:-1]
                    elif event.unicode.isprintable():
                        search_text += event.unicode
                elif input_active:
                    if event.key == pygame.K_RETURN and input_text.strip():
                        m = input_text.strip()
                        if chat_mode == "public":
                            chat_msgs.append({
                                "from": my_name, "message": m,
                                "private": False, "system": False})
                            chat.send_public(m)
                        elif chat_target:
                            chat_msgs.append({
                                "from": my_name, "message": m,
                                "private": True, "system": False,
                                "to": chat_target})
                            chat.send_private(chat_target, m)
                        input_text = ""
                    elif event.key == pygame.K_BACKSPACE:
                        input_text = input_text[:-1]
                    elif event.unicode.isprintable():
                        input_text += event.unicode

        # ── DRAW ─────────────────────────────────────────────────────────────
        screen.fill(SKY_BLUE)
        _scroll_clouds(screen, clouds)
        pygame.draw.line(screen, (142, 205, 222),
                         (LEFT_W, 0), (LEFT_W, H), 2)

        draw_header()

        vis = _visible_players()

        # Player list
        screen.set_clip(
            pygame.Rect(0, LIST_TOP, LEFT_W, MATCH_Y - LIST_TOP))

        ry = LIST_TOP - scroll_off
        for p in vis:
            if LIST_TOP - ROW_H < ry < MATCH_Y + ROW_H:
                hov = pygame.Rect(10, ry, LEFT_W - 20,
                                  ROW_H - ROW_PAD).collidepoint(mouse)
                draw_row(p, ry, hov)
            ry += ROW_H

        screen.set_clip(None)

        # Scrollbar
        total_px = len(vis) * ROW_H
        vis_h    = MATCH_Y - LIST_TOP
        if total_px > vis_h:
            sb_h = max(24, int(vis_h * vis_h / total_px))
            sb_y = LIST_TOP + int(
                scroll_off * (vis_h - sb_h) / max(1, total_px - vis_h))
            pygame.draw.rect(screen, (142, 206, 196),
                             (LEFT_W - 7, sb_y, 5, sb_h), border_radius=3)

        draw_match_bar()
        draw_self_card()
        draw_chat()
        if challenge_from:
            draw_popup()

        # Search bar + mode dropdown drawn LAST — floats over player cards
        _bar_r, _pill_r, _icon_r, _opt1_r, _opt2_r = draw_search_bar()

        pygame.display.flip()

    if music_started:
        try:
            pygame.mixer.music.stop()
        except Exception:
            pass

    return result
