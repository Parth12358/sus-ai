"""Pygame rendering — reads GameState and event_queue."""

import os
import random
import pygame

from engine.game_state import GameState
from config import ROSTER, MAP, NODE_POSITIONS

WIDTH = 1200
HEIGHT = 800

ASSETS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets")
BG_PATH = os.path.join(ASSETS_DIR, "bg.jpg")

DARK_BG = (6, 6, 22)
WHITE = (255, 255, 255)
CYAN = (90, 212, 212)
GRAY = (130, 130, 145)
DARK_GRAY = (35, 35, 50)
LIGHT_GRAY = (180, 180, 195)
PANEL_BG = (14, 14, 36, 180)

COLOR_HEX: dict[str, tuple[int, int, int]] = {
    "red": (215, 40, 40),
    "blue": (40, 100, 215),
    "green": (0, 180, 80),
    "orange": (240, 130, 20),
    "purple": (130, 60, 200),
    "yellow": (240, 240, 30),
    "pink": (230, 100, 160),
    "teal": (30, 200, 180),
}

COLOR_ORDER = [r["color"] for r in ROSTER]

MODEL_DISPLAY: dict[str, str] = {
    "anthropic/claude-sonnet-4-6": "Claude Sonnet 4.6",
    "openai/gpt-4o": "GPT-4o",
    "google/gemini-2.5-flash": "Gemini 2.5 Flash",
    "deepseek/deepseek-v4-flash": "DeepSeek V4 Flash",
    "x-ai/grok-4.3": "Grok 4.3",
    "qwen/qwen3.7-plus": "Qwen 3.7 Plus",
    "minimax/minimax-m3": "MiniMax M3",
    "nvidia/nemotron-3-super": "Nemotron 3 Super",
}

START_COLOR = (0, 200, 100)
START_HOVER = (30, 235, 130)
SETTINGS_COLOR = (255, 200, 50)
SETTINGS_HOVER = (255, 230, 100)
QUIT_COLOR = (220, 50, 50)
QUIT_HOVER = (255, 80, 80)
TOGGLE_ON = (70, 70, 140)
TOGGLE_OFF = (35, 35, 55)
TOGGLE_HOVER = (50, 50, 100)

BUTTON_W = 300
BUTTON_H = 60
BUTTON_R = 14
BUTTON_GAP = 22
BUTTON_TOP = 370

LEFT_PANEL_X = 50
RIGHT_PANEL_X = 680
PANEL_W = 560
SLOT_H = 50
SLOT_GAP = 4
SLOT_TOP = 150
SLOT_COLOR_R = 13

MAX_SLOTS = 8
MIN_SLOTS = 4
MAX_IMPOSTORS = 3
MIN_IMPOSTORS = 1

_stars: list[dict] = []
_bg_image: pygame.Surface | None = None
_title_font: pygame.font.Font | None = None
_subtitle_font: pygame.font.Font | None = None
_button_font: pygame.font.Font | None = None
_lobby_title_font: pygame.font.Font | None = None
_small_font: pygame.font.Font | None = None
_start_rect: pygame.Rect | None = None
_settings_rect: pygame.Rect | None = None
_quit_rect: pygame.Rect | None = None
_last_tick: int = 0
_screen: str = "menu"

_lobby: dict = {
    "mode": "full_ai",
    "slot_count": 8,
    "slots": [],
    "num_impostors": 2,
    "kill_cooldown": 3,
    "task_count": 4,
}

SETTINGS_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "settings.json")

RESOLUTION_OPTS = ["1280x720", "1920x1080", "2560x1440"]
FPS_OPTS = [30, 60, 120]

_settings: dict = {
    "api_key": "",
    "default_model": ROSTER[0]["model"],
    "resolution": "1920x1080",
    "fps_cap": 60,
    "mock_mode": False,
}

_open_dropdown: str | None = None
_focused_field: str | None = None
_show_api_key: bool = False
_saved_flash: int = 0
_event_log: list[str] = []
_pause_menu_open: bool = False
_pause_was_paused: bool = False


def _init_stars() -> list[dict]:
    stars: list[dict] = []
    for _ in range(220):
        stars.append({
            "x": random.random() * WIDTH,
            "y": random.random() * HEIGHT,
            "size": random.uniform(0.4, 2.6),
            "speed": random.uniform(8, 35),
            "brightness": random.uniform(0.2, 1.0),
            "tint": random.choices([None, "cyan"], weights=[0.88, 0.12])[0],
        })
    return stars


def _load_bg() -> pygame.Surface | None:
    try:
        img = pygame.image.load(BG_PATH)
        iw, ih = img.get_size()
        scale = max(WIDTH / iw, HEIGHT / ih)
        nw, nh = int(iw * scale), int(ih * scale)
        img = pygame.transform.smoothscale(img, (nw, nh))
        x_off = (nw - WIDTH) // 2
        y_off = (nh - HEIGHT) // 2
        img = img.subsurface((x_off, y_off, WIDTH, HEIGHT))
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 55))
        img.blit(overlay, (0, 0))
        return img
    except (pygame.error, FileNotFoundError):
        return None


def _draw_stars(screen: pygame.Surface) -> None:
    for s in _stars:
        alpha = int(70 + 185 * s["brightness"])
        if s["tint"] == "cyan":
            c = (alpha // 3, alpha, alpha)
        else:
            c = (alpha, alpha, alpha)
        r = max(1, int(s["size"]))
        pygame.draw.circle(screen, c, (int(s["x"]), int(s["y"])), r)


def _draw_button(
    screen: pygame.Surface,
    text: str,
    rect: pygame.Rect,
    color: tuple[int, int, int],
    hover_color: tuple[int, int, int],
    hovered: bool,
    font: pygame.font.Font | None = None,
    radius: int = BUTTON_R,
    text_color: tuple[int, int, int] = WHITE,
) -> None:
    f = font or _button_font
    c = hover_color if hovered else color
    border = tuple(min(255, v + 70) for v in c)
    if hovered:
        glow_rect = pygame.Rect(0, 0, rect.w + 26, rect.h + 26)
        glow = pygame.Surface(glow_rect.size, pygame.SRCALPHA)
        pygame.draw.rect(glow, (*c, 50), glow_rect, border_radius=radius + 10)
        screen.blit(glow, (rect.x - 13, rect.y - 13))
    pygame.draw.rect(screen, c, rect, border_radius=radius)
    pygame.draw.rect(screen, border, rect, 2, border_radius=radius)
    ts = f.render(text, True, text_color)
    tr = ts.get_rect(center=rect.center)
    screen.blit(ts, tr)


def _draw_panel(screen: pygame.Surface, x: int, y: int, w: int, h: int) -> pygame.Rect:
    panel = pygame.Surface((w, h), pygame.SRCALPHA)
    panel.fill(PANEL_BG)
    screen.blit(panel, (x, y))
    pygame.draw.rect(screen, (60, 60, 100), (x, y, w, h), 1, border_radius=6)
    return pygame.Rect(x, y, w, h)


def _draw_menu(screen: pygame.Surface) -> None:
    mx, my = pygame.mouse.get_pos()
    shadow = _title_font.render("sus-ai", True, (0, 0, 0, 120))
    screen.blit(shadow, shadow.get_rect(center=(WIDTH // 2 + 4, 184)))
    title = _title_font.render("sus-ai", True, WHITE)
    tr = title.get_rect(center=(WIDTH // 2, 180))
    screen.blit(title, tr)
    sub = _subtitle_font.render("AI models play Among Us", True, CYAN)
    sr = sub.get_rect(center=(WIDTH // 2, 260))
    screen.blit(sub, sr)
    _draw_button(screen, "Start", _start_rect, START_COLOR, START_HOVER,
                 _start_rect.collidepoint(mx, my))
    _draw_button(screen, "Settings", _settings_rect, SETTINGS_COLOR, SETTINGS_HOVER,
                 _settings_rect.collidepoint(mx, my))
    _draw_button(screen, "Quit", _quit_rect, QUIT_COLOR, QUIT_HOVER,
                 _quit_rect.collidepoint(mx, my))


def _init_lobby() -> None:
    slots = []
    for i in range(MAX_SLOTS):
        if i < len(ROSTER):
            slots.append({
                "color": ROSTER[i]["color"],
                "model": ROSTER[i]["model"],
                "human": False,
            })
        else:
            slots.append({"color": COLOR_ORDER[0], "model": ROSTER[0]["model"], "human": False})
    _lobby.update({
        "mode": "full_ai",
        "slot_count": MAX_SLOTS,
        "slots": slots,
        "num_impostors": 2,
        "kill_cooldown": 3,
        "task_count": 4,
    })


def _random_fill_slots() -> None:
    models = [r["model"] for r in ROSTER]
    for s in _lobby["slots"]:
        if not s.get("human"):
            s["model"] = random.choice(models)


def _cycle_color(slot: dict) -> None:
    used = {s["color"] for s in _lobby["slots"] if s is not slot}
    cur = slot["color"]
    idx = COLOR_ORDER.index(cur) if cur in COLOR_ORDER else 0
    for _ in range(len(COLOR_ORDER)):
        idx = (idx + 1) % len(COLOR_ORDER)
        if COLOR_ORDER[idx] not in used:
            slot["color"] = COLOR_ORDER[idx]
            return
    nxt = (COLOR_ORDER.index(cur) + 1) % len(COLOR_ORDER)
    slot["color"] = COLOR_ORDER[nxt]


def _cycle_model(slot: dict) -> None:
    if _lobby["mode"] == "human_ai":
        if slot.get("human"):
            slot["human"] = False
            slot["model"] = ROSTER[0]["model"]
        else:
            idx = _model_index(slot["model"])
            nxt = (idx + 1) % (len(ROSTER) + 1)
            if nxt == len(ROSTER):
                slot["human"] = True
                slot["model"] = ""
            else:
                slot["human"] = False
                slot["model"] = ROSTER[nxt]["model"]
    else:
        idx = _model_index(slot["model"])
        nxt = (idx + 1) % len(ROSTER)
        slot["model"] = ROSTER[nxt]["model"]
        slot["human"] = False


def _model_index(model: str) -> int:
    for i, r in enumerate(ROSTER):
        if r["model"] == model:
            return i
    return 0


def _load_settings() -> None:
    import json
    try:
        with open(SETTINGS_PATH) as f:
            data = json.load(f)
        _settings["api_key"] = data.get("api_key", "")
        _settings["default_model"] = data.get("default_model", ROSTER[0]["model"])
        _settings["resolution"] = data.get("resolution", "1920x1080")
        _settings["fps_cap"] = data.get("fps_cap", 60)
        _settings["mock_mode"] = data.get("mock_mode", False)
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        pass


def _save_settings() -> None:
    import json
    with open(SETTINGS_PATH, "w") as f:
        json.dump(_settings, f, indent=2)


def _draw_lobby(screen: pygame.Surface) -> None:
    mx, my = pygame.mouse.get_pos()
    lx, rx = LEFT_PANEL_X, RIGHT_PANEL_X

    back_rect = pygame.Rect(lx, 16, 110, 36)
    _draw_button(screen, "<  Back", back_rect, (50, 50, 70), (70, 70, 100),
                 back_rect.collidepoint(mx, my), _small_font, 8)

    title = _lobby_title_font.render("LOBBY", True, WHITE)
    screen.blit(title, title.get_rect(center=(WIDTH // 2, 34)))

    _draw_lobby_left(screen, mx, my, lx)
    _draw_lobby_right(screen, mx, my, rx)


def _draw_lobby_left(screen: pygame.Surface, mx: int, my: int, x: int) -> None:
    y = 70
    label = _small_font.render("Game Mode", True, GRAY)
    screen.blit(label, (x + 4, y - 18))

    mode_full = pygame.Rect(x, y, 150, 34)
    mode_human = pygame.Rect(x + 158, y, 150, 34)
    is_full = _lobby["mode"] == "full_ai"

    for rect, active, text in [
        (mode_full, is_full, "Full AI"),
        (mode_human, not is_full, "Human + AI"),
    ]:
        h = rect.collidepoint(mx, my)
        c = TOGGLE_ON if active else (TOGGLE_HOVER if h else TOGGLE_OFF)
        border = tuple(min(255, v + 80) for v in c) if active else tuple(min(255, v + 40) for v in c)
        pygame.draw.rect(screen, c, rect, border_radius=6)
        pygame.draw.rect(screen, border, rect, 1, border_radius=6)
        ts = _small_font.render(text, True, WHITE if active else GRAY)
        screen.blit(ts, ts.get_rect(center=rect.center))

    count_y = y + 48
    count_label = _small_font.render(f"Players: {_lobby['slot_count']}", True, LIGHT_GRAY)
    screen.blit(count_label, (x, count_y))

    minus_r = pygame.Rect(x + 115, count_y - 2, 26, 26)
    plus_r = pygame.Rect(x + 144, count_y - 2, 26, 26)
    can_minus = _lobby["slot_count"] > MIN_SLOTS
    can_plus = _lobby["slot_count"] < MAX_SLOTS

    for rct, enabled, sym in [(minus_r, can_minus, "-"), (plus_r, can_plus, "+")]:
        h = rct.collidepoint(mx, my) and enabled
        bg = (60, 60, 100) if h else (DARK_GRAY[0], DARK_GRAY[1], DARK_GRAY[2])
        txt_color = WHITE if enabled else GRAY
        pygame.draw.rect(screen, bg, rct, border_radius=4)
        pygame.draw.rect(screen, (100, 100, 130) if enabled else (60, 60, 80), rct, 1, border_radius=4)
        ts = _small_font.render(sym, True, txt_color)
        screen.blit(ts, ts.get_rect(center=rct.center))

    _draw_lobby_slots(screen, mx, my, x, SLOT_TOP)


def _draw_lobby_slots(screen: pygame.Surface, mx: int, my: int, x: int, top: int) -> None:
    slot_count = _lobby["slot_count"]
    for i in range(slot_count):
        slot = _lobby["slots"][i]
        row_y = top + i * (SLOT_H + SLOT_GAP)

        cr = pygame.Rect(x + 8, row_y + 11, SLOT_COLOR_R * 2, SLOT_COLOR_R * 2)
        ch = cr.collidepoint(mx, my)
        hex_color = COLOR_HEX.get(slot["color"], GRAY)
        pygame.draw.circle(screen, hex_color, cr.center, SLOT_COLOR_R)
        if ch:
            pygame.draw.circle(screen, WHITE, cr.center, SLOT_COLOR_R + 2, 2)

        idx_label = _small_font.render(f"{i + 1}.", True, GRAY)
        screen.blit(idx_label, (cr.right + 4, row_y + 15))

        mr = pygame.Rect(cr.right + 25, row_y + 8, 340, 34)
        mh = mr.collidepoint(mx, my)
        model_bg = (50, 50, 80) if mh else DARK_GRAY
        pygame.draw.rect(screen, model_bg, mr, border_radius=6)
        pygame.draw.rect(screen, (80, 80, 120) if mh else (60, 60, 85), mr, 1, border_radius=6)

        if slot.get("human"):
            disp = "Human"
            disp_color = CYAN
        else:
            disp = MODEL_DISPLAY.get(slot["model"], slot["model"])
            disp_color = WHITE
        disp_surf = _small_font.render(disp, True, disp_color)
        screen.blit(disp_surf, (mr.x + 8, mr.y + 7))

        caret = _small_font.render(">", True, GRAY)
        screen.blit(caret, (mr.right - 20, mr.y + 7))


def _draw_lobby_right(screen: pygame.Surface, mx: int, my: int, x: int) -> None:
    panel = _draw_panel(screen, x, 70, 470, 500)

    hdr = _lobby_title_font.render("Game Settings", True, WHITE)
    screen.blit(hdr, hdr.get_rect(center=(x + 235, 100)))

    _draw_spinner(screen, mx, my, x + 30, 140, "Impostors",
                  _lobby["num_impostors"], MIN_IMPOSTORS, MAX_IMPOSTORS)
    _draw_spinner(screen, mx, my, x + 30, 195, "Kill Cooldown",
                  _lobby["kill_cooldown"], 1, 5)
    _draw_spinner(screen, mx, my, x + 30, 250, "Tasks per Player",
                  _lobby["task_count"], 1, 5)

    rf_rect = pygame.Rect(x + 30, 325, 200, 40)
    _draw_button(screen, "Random Fill", rf_rect, (50, 50, 100), (80, 80, 150),
                 rf_rect.collidepoint(mx, my), _small_font, 8)

    start_rect = pygame.Rect(x + 30, 430, 410, 64)
    _draw_button(screen, "Start Game", start_rect, START_COLOR, START_HOVER,
                 start_rect.collidepoint(mx, my), _button_font, 12)

    imp_rect = pygame.Rect(x + 30, 520, 410, 30)
    imp_count = sum(1 for s in _lobby["slots"] if not s.get("human"))
    info = _small_font.render(
        f"{imp_count} AI players  |  {_lobby['slot_count'] - imp_count} human",
        True, GRAY,
    )
    screen.blit(info, info.get_rect(center=imp_rect.center))


def _draw_spinner(
    screen: pygame.Surface, mx: int, my: int,
    x: int, y: int, label: str, value: int, vmin: int, vmax: int,
) -> None:
    lb = _small_font.render(label, True, LIGHT_GRAY)
    screen.blit(lb, (x, y))

    dec_r = pygame.Rect(x + 200, y, 30, 28)
    inc_r = pygame.Rect(x + 270, y, 30, 28)

    for rct, enabled in [(dec_r, value > vmin), (inc_r, value < vmax)]:
        h = rct.collidepoint(mx, my) and enabled
        bg = (60, 60, 100) if h else DARK_GRAY
        tc = WHITE if enabled else GRAY
        pygame.draw.rect(screen, bg, rct, border_radius=4)
        pygame.draw.rect(screen, (100, 100, 130) if enabled else (60, 60, 80),
                         rct, 1, border_radius=4)

    dec_ts = _small_font.render("<", True, WHITE if value > vmin else GRAY)
    inc_ts = _small_font.render(">", True, WHITE if value < vmax else GRAY)
    screen.blit(dec_ts, dec_ts.get_rect(center=dec_r.center))
    screen.blit(inc_ts, inc_ts.get_rect(center=inc_r.center))

    val_surf = _small_font.render(str(value), True, WHITE)
    val_rect = val_surf.get_rect(center=(x + 245, y + 14))
    pygame.draw.rect(screen, DARK_GRAY, val_rect.inflate(20, 10), border_radius=4)
    screen.blit(val_surf, val_rect)


def _draw_settings(screen: pygame.Surface) -> None:
    mx, my = pygame.mouse.get_pos()

    back_rect = pygame.Rect(50, 16, 110, 36)
    _draw_button(screen, "<  Back", back_rect, (50, 50, 70), (70, 70, 100),
                 back_rect.collidepoint(mx, my), _small_font, 8)

    title = _lobby_title_font.render("SETTINGS", True, WHITE)
    screen.blit(title, title.get_rect(center=(WIDTH // 2, 34)))

    px, py, pw, ph = 250, 85, 700, 470
    _draw_panel(screen, px, py, pw, ph)

    row_h = 65
    label_x = px + 30
    field_x = px + 230
    field_w = 380
    field_h = 36

    y = py + 40
    screen.blit(_small_font.render("OpenRouter API Key", True, LIGHT_GRAY), (label_x, y + 8))
    api_rect = pygame.Rect(field_x, y, field_w - 44, field_h)
    _draw_text_input(screen, api_rect, _settings["api_key"], _focused_field == "api_key",
                     _show_api_key, mx, my)

    eye_rect = pygame.Rect(field_x + field_w - 38, y, 32, field_h)
    eye_char = "o" if not _show_api_key else "-"
    _draw_button(screen, eye_char, eye_rect, (50, 50, 70), (70, 70, 100),
                 eye_rect.collidepoint(mx, my), _small_font, 6)

    y += row_h
    screen.blit(_small_font.render("Default Model", True, LIGHT_GRAY), (label_x, y + 8))
    _draw_dropdown(screen, mx, my, field_x, y, field_w, field_h,
                   _settings["default_model"], _open_dropdown == "model",
                   [r["model"] for r in ROSTER], "model")

    y += row_h
    screen.blit(_small_font.render("Resolution", True, LIGHT_GRAY), (label_x, y + 8))
    _draw_dropdown(screen, mx, my, field_x, y, field_w, field_h,
                   _settings["resolution"], _open_dropdown == "resolution",
                   RESOLUTION_OPTS, "resolution")

    y += row_h
    screen.blit(_small_font.render("FPS Cap", True, LIGHT_GRAY), (label_x, y + 8))
    _draw_dropdown(screen, mx, my, field_x, y, field_w, field_h,
                   str(_settings["fps_cap"]), _open_dropdown == "fps",
                   [str(o) for o in FPS_OPTS], "fps")

    y += row_h
    screen.blit(_small_font.render("Mock Mode", True, LIGHT_GRAY), (label_x, y + 8))
    _draw_toggle_switch(screen, mx, my, field_x, y + 2, field_w, field_h,
                        _settings["mock_mode"], "mock_toggle")

    save_rect = pygame.Rect(px + (pw - 280) // 2, py + ph - 80, 280, 50)
    _draw_button(screen, "Save", save_rect, START_COLOR, START_HOVER,
                 save_rect.collidepoint(mx, my), _button_font, 10)

    if _saved_flash > 0:
        flash = _small_font.render("Settings saved!", True, START_COLOR)
        screen.blit(flash, flash.get_rect(center=(WIDTH // 2, py + ph - 30)))


def _draw_text_input(
    screen: pygame.Surface, rect: pygame.Rect,
    value: str, focused: bool, show: bool, mx: int, my: int,
) -> None:
    hovered = rect.collidepoint(mx, my)
    bg = (55, 55, 85) if focused else ((50, 50, 75) if hovered else DARK_GRAY)
    border = (100, 100, 140) if focused else ((80, 80, 120) if hovered else (60, 60, 85))
    pygame.draw.rect(screen, bg, rect, border_radius=6)
    pygame.draw.rect(screen, border, rect, 1, border_radius=6)

    if show or not value:
        disp = value
    else:
        disp = "*" * len(value)
    disp_surf = _small_font.render(disp, True, WHITE if value else GRAY)
    screen.blit(disp_surf, (rect.x + 8, rect.y + 9))

    if focused and (pygame.time.get_ticks() // 500) % 2 == 0:
        cursor_x = rect.x + 8 + (disp_surf.get_width() if disp else 0)
        pygame.draw.line(screen, WHITE, (cursor_x, rect.y + 8), (cursor_x, rect.y + rect.h - 8), 2)


def _draw_dropdown(
    screen: pygame.Surface, mx: int, my: int,
    x: int, y: int, w: int, h: int,
    value: str, is_open: bool, options: list[str], key: str,
) -> None:
    btn_rect = pygame.Rect(x, y, w, h)
    hovered = btn_rect.collidepoint(mx, my)
    bg = (55, 55, 85) if is_open else ((50, 50, 75) if hovered else DARK_GRAY)
    pygame.draw.rect(screen, bg, btn_rect, border_radius=6)
    pygame.draw.rect(screen, (80, 80, 120) if hovered or is_open else (60, 60, 85),
                     btn_rect, 1, border_radius=6)

    display_val = MODEL_DISPLAY.get(value, value)
    val_surf = _small_font.render(str(display_val), True, WHITE)
    screen.blit(val_surf, (x + 8, y + 9))

    arrow = _small_font.render("v" if not is_open else "^", True, GRAY)
    screen.blit(arrow, (x + w - 24, y + 9))

    if is_open:
        for i, opt in enumerate(options):
            oy = y + h + i * (h - 2)
            or_ = pygame.Rect(x, oy, w, h)
            oh = or_.collidepoint(mx, my)
            ot = MODEL_DISPLAY.get(opt, opt) if key == "model" else str(opt)
            _draw_button(screen, str(ot), or_, (40, 40, 65) if oh else (30, 30, 48),
                         (50, 50, 85), oh, _small_font, 4)


def _draw_toggle_switch(
    screen: pygame.Surface, mx: int, my: int,
    x: int, y: int, w: int, h: int, on: bool, key: str,
) -> None:
    tw, th = 160, 32
    tx, ty = x + (w - tw) // 2, y

    off_rect = pygame.Rect(tx, ty, 75, th)
    on_rect = pygame.Rect(tx + 85, ty, 75, th)

    for rect, active, text in [(off_rect, not on, "OFF"), (on_rect, on, "ON")]:
        hov = rect.collidepoint(mx, my)
        c = TOGGLE_ON if active else (TOGGLE_HOVER if hov else TOGGLE_OFF)
        bd = tuple(min(255, v + 80) for v in c) if active else tuple(min(255, v + 40) for v in c)
        pygame.draw.rect(screen, c, rect, border_radius=6)
        pygame.draw.rect(screen, bd, rect, 1, border_radius=6)
        ts = _small_font.render(text, True, WHITE if active else GRAY)
        screen.blit(ts, ts.get_rect(center=rect.center))


def init_display(width: int = WIDTH, height: int = HEIGHT, title: str = "sus-ai") -> pygame.Surface:
    global _stars, _bg_image, _title_font, _subtitle_font, _button_font
    global _lobby_title_font, _small_font
    global _start_rect, _settings_rect, _quit_rect, _last_tick, _screen

    pygame.init()
    pygame.display.set_caption(title)
    screen = pygame.display.set_mode((width, height))

    _stars = _init_stars()
    _bg_image = _load_bg()

    _title_font = pygame.font.Font(None, 90)
    _subtitle_font = pygame.font.Font(None, 26)
    _button_font = pygame.font.Font(None, 32)
    _lobby_title_font = pygame.font.Font(None, 36)
    _small_font = pygame.font.Font(None, 20)

    cx = width // 2
    _start_rect = pygame.Rect(cx - BUTTON_W // 2, BUTTON_TOP, BUTTON_W, BUTTON_H)
    _settings_rect = pygame.Rect(cx - BUTTON_W // 2, BUTTON_TOP + BUTTON_H + BUTTON_GAP, BUTTON_W, BUTTON_H)
    _quit_rect = pygame.Rect(cx - BUTTON_W // 2, BUTTON_TOP + 2 * (BUTTON_H + BUTTON_GAP), BUTTON_W, BUTTON_H)

    _last_tick = pygame.time.get_ticks()
    _screen = "menu"
    _load_settings()

    return screen


def render(screen: pygame.Surface, game_state: GameState) -> None:
    global _last_tick, _saved_flash
    now = pygame.time.get_ticks()
    dt = (now - _last_tick) / 1000.0 if _last_tick else 0.016
    _last_tick = now

    if _saved_flash > 0:
        _saved_flash -= 1

    for s in _stars:
        s["y"] = (s["y"] + s["speed"] * dt) % HEIGHT

    if _bg_image is not None:
        screen.blit(_bg_image, (0, 0))
    else:
        screen.fill(DARK_BG)
        _draw_stars(screen)

    if game_state.phase in ("movement", "meeting", "voting", "ended"):
        _drain_events(game_state)
        _draw_game(screen, game_state)
    elif _screen == "menu":
        _draw_menu(screen)
    elif _screen == "lobby":
        _draw_lobby(screen)
    elif _screen == "settings":
        _draw_settings(screen)


def handle_events(event: pygame.event.Event, game_state: GameState) -> str | None:
    global _screen, _saved_flash, _pause_menu_open, _pause_was_paused

    if game_state.phase == "ended":
        if event.type == pygame.KEYDOWN and event.key == pygame.K_q:
            return "quit"
        return None

    if game_state.phase in ("movement", "meeting", "voting"):
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            if _pause_menu_open:
                _pause_menu_open = False
                game_state.paused = _pause_was_paused
            else:
                _pause_was_paused = game_state.paused
                _pause_menu_open = True
                game_state.paused = True
            return None

        if _pause_menu_open:
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                return _handle_pause_menu_click(*event.pos, game_state)
            return None

        if event.type == pygame.KEYDOWN and event.key in (pygame.K_SPACE, pygame.K_p):
            game_state.paused = not game_state.paused
            return None
        return None

    if _screen == "settings":
        if event.type == pygame.KEYDOWN:
            _handle_settings_keydown(event)
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            return _handle_settings_click(*event.pos)
        return None

    if event.type != pygame.MOUSEBUTTONDOWN or event.button != 1:
        return None
    mx, my = event.pos

    if _screen == "menu":
        if _start_rect.collidepoint(mx, my):
            _screen = "lobby"
            _init_lobby()
            return None
        if _settings_rect.collidepoint(mx, my):
            _screen = "settings"
            return None
        if _quit_rect.collidepoint(mx, my):
            return "quit"

    elif _screen == "lobby":
        return _handle_lobby_click(mx, my)

    return None


def _handle_lobby_click(mx: int, my: int) -> str | None:
    global _screen
    lx, rx = LEFT_PANEL_X, RIGHT_PANEL_X

    back_rect = pygame.Rect(lx, 16, 110, 36)
    if back_rect.collidepoint(mx, my):
        _screen = "menu"
        return None

    mode_full = pygame.Rect(lx, 70, 150, 34)
    mode_human = pygame.Rect(lx + 158, 70, 150, 34)
    if mode_full.collidepoint(mx, my):
        _lobby["mode"] = "full_ai"
        for s in _lobby["slots"]:
            s["human"] = False
            if not s["model"]:
                s["model"] = ROSTER[0]["model"]
        return None
    if mode_human.collidepoint(mx, my):
        _lobby["mode"] = "human_ai"
        return None

    minus_r = pygame.Rect(lx + 115, 116, 26, 26)
    plus_r = pygame.Rect(lx + 144, 116, 26, 26)
    if minus_r.collidepoint(mx, my) and _lobby["slot_count"] > MIN_SLOTS:
        _lobby["slot_count"] -= 1
        return None
    if plus_r.collidepoint(mx, my) and _lobby["slot_count"] < MAX_SLOTS:
        if _lobby["slot_count"] < len(_lobby["slots"]):
            _lobby["slot_count"] += 1
        return None

    for i in range(_lobby["slot_count"]):
        slot = _lobby["slots"][i]
        row_y = SLOT_TOP + i * (SLOT_H + SLOT_GAP)

        cr = pygame.Rect(lx + 8, row_y + 11, SLOT_COLOR_R * 2, SLOT_COLOR_R * 2)
        if cr.collidepoint(mx, my):
            _cycle_color(slot)
            return None

        mr = pygame.Rect(lx + 60, row_y + 8, 340, 34)
        if mr.collidepoint(mx, my):
            _cycle_model(slot)
            return None

    for base_y, cur_val, k, lo, hi in [
        (140, _lobby["num_impostors"], "num_impostors", MIN_IMPOSTORS, MAX_IMPOSTORS),
        (195, _lobby["kill_cooldown"], "kill_cooldown", 1, 5),
        (250, _lobby["task_count"], "task_count", 1, 5),
    ]:
        dec_r = pygame.Rect(rx + 30 + 200, base_y, 30, 28)
        inc_r = pygame.Rect(rx + 30 + 270, base_y, 30, 28)
        if dec_r.collidepoint(mx, my) and cur_val > lo:
            _lobby[k] -= 1
            return None
        if inc_r.collidepoint(mx, my) and cur_val < hi:
            _lobby[k] += 1
            return None

    rf_rect = pygame.Rect(rx + 30, 325, 200, 40)
    if rf_rect.collidepoint(mx, my):
        _random_fill_slots()
        return None

    start_rect = pygame.Rect(rx + 30, 430, 410, 64)
    if start_rect.collidepoint(mx, my):
        return "start_game"

    return None


def _handle_settings_click(mx: int, my: int) -> str | None:
    global _screen, _open_dropdown, _focused_field, _show_api_key, _saved_flash

    back_rect = pygame.Rect(50, 16, 110, 36)
    if back_rect.collidepoint(mx, my):
        _screen = "menu"
        _open_dropdown = None
        _focused_field = None
        return None

    px, py, pw, ph = 250, 85, 700, 470
    field_x = px + 230
    field_w = 380
    field_h = 36
    row_h = 65

    dd_model = _rect_for_row(px, py, 0, row_h)
    dd_res = _rect_for_row(px, py, 1, row_h)
    dd_fps = _rect_for_row(px, py, 2, row_h)
    dd_keys = ["model", "resolution", "fps"]

    for dd_key, (dx, dy) in zip(dd_keys, [dd_model, dd_res, dd_fps]):
        dd_rect = pygame.Rect(dx + 230, dy, field_w, field_h)
        if _open_dropdown == dd_key:
            opts = _dd_options(dd_key)
            for i, _ in enumerate(opts):
                or_ = pygame.Rect(dd_rect.x, dd_rect.y + field_h + i * (field_h - 2), field_w, field_h)
                if or_.collidepoint(mx, my):
                    _select_dropdown(dd_key, i)
                    return None
            _open_dropdown = None if dd_rect.collidepoint(mx, my) else dd_key
            if _open_dropdown is None:
                return None
        elif dd_rect.collidepoint(mx, my):
            _open_dropdown = dd_key
            _focused_field = None
            return None
        else:
            if dd_rect.collidepoint(mx, my):
                _open_dropdown = dd_key
                _focused_field = None
                return None

    api_rect = pygame.Rect(field_x, py + 40, field_w - 44, field_h)
    eye_rect = pygame.Rect(field_x + field_w - 38, py + 40, 32, field_h)

    if api_rect.collidepoint(mx, my):
        _focused_field = "api_key"
        _open_dropdown = None
        return None
    if eye_rect.collidepoint(mx, my):
        _show_api_key = not _show_api_key
        return None

    y = py + 40 + 4 * row_h
    off_rect = pygame.Rect(field_x, y + 2, 75, 32)
    on_rect = pygame.Rect(field_x + 85, y + 2, 75, 32)
    if off_rect.collidepoint(mx, my):
        _settings["mock_mode"] = False
        return None
    if on_rect.collidepoint(mx, my):
        _settings["mock_mode"] = True
        return None

    save_rect = pygame.Rect(px + (pw - 280) // 2, py + ph - 80, 280, 50)
    if save_rect.collidepoint(mx, my):
        _save_settings()
        _saved_flash = 60
        return None

    if not _any_dd_hit(mx, my, px, py, field_x, field_w, field_h, row_h):
        _open_dropdown = None
        _focused_field = None

    return None


def _handle_settings_keydown(event: pygame.event.Event) -> None:
    global _open_dropdown, _focused_field
    if event.type == pygame.KEYDOWN:
        if event.key == pygame.K_ESCAPE:
            _open_dropdown = None
            _focused_field = None
        elif _focused_field == "api_key":
            if event.key == pygame.K_BACKSPACE:
                _settings["api_key"] = _settings["api_key"][:-1]
            elif event.unicode and event.unicode.isprintable():
                _settings["api_key"] += event.unicode


def _rect_for_row(px: int, py: int, row: int, row_h: int) -> tuple[int, int]:
    return (px, py + 40 + row * row_h)


def _dd_options(key: str) -> list[str]:
    if key == "model":
        return [r["model"] for r in ROSTER]
    if key == "resolution":
        return RESOLUTION_OPTS
    if key == "fps":
        return [str(o) for o in FPS_OPTS]
    return []


def _select_dropdown(key: str, idx: int) -> None:
    global _open_dropdown
    if key == "model":
        _settings["default_model"] = ROSTER[idx]["model"]
    elif key == "resolution":
        _settings["resolution"] = RESOLUTION_OPTS[idx]
    elif key == "fps":
        _settings["fps_cap"] = FPS_OPTS[idx]
    _open_dropdown = None


def _any_dd_hit(mx: int, my: int, px: int, py: int, fx: int, fw: int, fh: int, rh: int) -> bool:
    for row in range(3):
        r = pygame.Rect(fx, py + 40 + row * rh + fh, fw, fh * 4)
        if r.collidepoint(mx, my):
            return True
    return False


def _drain_events(game_state: GameState) -> None:
    while not game_state.event_queue.empty():
        try:
            ev = game_state.event_queue.get_nowait()
            _event_log.append(_format_event(ev))
            if len(_event_log) > 100:
                _event_log[:] = _event_log[-80:]
        except Exception:
            break


def _format_event(ev: dict) -> str:
    t = ev.get("type", "?")
    if t == "move":
        return f"{ev['color']} moved {ev['from']} -> {ev['to']}"
    if t == "kill":
        return f"   {ev['color']} KILLED {ev['victim']} in {ev['location']}"
    if t == "body_found":
        return f"   {ev['reporter']} found {ev['victim']}'s body in {ev['location']}"
    if t == "task_complete":
        return f"{ev['color']} completed {ev['task']}"
    if t == "vent":
        return f"{ev['color']} vented to {ev['to']}"
    if t == "vent_spotted":
        return f"   {ev['witness']} saw {ev['color']} appear from vent in {ev['location']}"
    if t == "meeting_called":
        reason = ev.get("reason", "?")
        return f"--- MEETING called by {ev['caller']} ({reason}) ---"
    if t == "ejected":
        return f"   {ev['color']} was EJECTED"
    if t == "game_over":
        return f"=== GAME OVER: {ev['winner']} win! ==="
    if t == "stay":
        return f"{ev['color']} stayed in {ev['location']}"
    return str(ev)


def _draw_game(screen: pygame.Surface, game_state: GameState) -> None:
    _draw_game_map(screen, game_state)
    _draw_game_players(screen, game_state)
    _draw_game_hud(screen, game_state)
    if _pause_menu_open:
        _draw_pause_menu(screen)
    elif game_state.phase == "meeting":
        _draw_meeting_overlay(screen, game_state)
    elif game_state.phase == "voting":
        _draw_voting_overlay(screen, game_state)
    elif game_state.phase == "ended":
        _draw_game_over(screen, game_state)


def _draw_game_map(screen: pygame.Surface, game_state: GameState) -> None:
    drawn: set[tuple[str, str]] = set()
    for room, neighbors in MAP.items():
        rx, ry = NODE_POSITIONS[room]
        for nb in neighbors:
            if (nb, room) not in drawn:
                nx, ny = NODE_POSITIONS[nb]
                pygame.draw.line(screen, (40, 40, 60), (rx, ry), (nx, ny), 2)
                drawn.add((room, nb))

    for room, (rx, ry) in NODE_POSITIONS.items():
        is_hall = room.startswith("hallway")
        r = 13 if is_hall else 20
        bg = (45, 45, 68) if is_hall else (30, 30, 50)
        if room in game_state.bodies:
            bg = (70, 25, 25)
        pygame.draw.circle(screen, bg, (rx, ry), r)
        pygame.draw.circle(screen, (80, 80, 110), (rx, ry), r, 1)
        label = room.replace("_", " ").title()[:12]
        lbl = _small_font.render(label, True, (90, 90, 115))
        screen.blit(lbl, (rx - lbl.get_width() // 2, ry + r + 3))

    for loc, color in game_state.bodies.items():
        if loc in NODE_POSITIONS:
            bx, by = NODE_POSITIONS[loc]
            bc = COLOR_HEX.get(color, WHITE)
            pygame.draw.line(screen, bc, (bx - 9, by - 9), (bx + 9, by + 9), 3)
            pygame.draw.line(screen, bc, (bx - 9, by + 9), (bx + 9, by - 9), 3)


def _player_offsets(n: int) -> list[tuple[int, int]]:
    import math
    if n <= 1:
        return [(0, 0)]
    if n == 2:
        return [(-16, 0), (16, 0)]
    if n == 3:
        return [(0, -14), (-16, 8), (16, 8)]
    offsets: list[tuple[int, int]] = []
    for i in range(n):
        a = 2 * math.pi * i / n - math.pi / 2
        offsets.append((int(math.cos(a) * 18), int(math.sin(a) * 18)))
    return offsets


def _draw_game_players(screen: pygame.Surface, game_state: GameState) -> None:
    rooms: dict[str, list[tuple[str, object]]] = {}
    for color, p in game_state.players.items():
        rooms.setdefault(p.location, []).append((color, p))

    for loc, occupants in rooms.items():
        if loc not in NODE_POSITIONS:
            continue
        rx, ry = NODE_POSITIONS[loc]
        offs = _player_offsets(len(occupants))
        for (color, player), (ox, oy) in zip(occupants, offs):
            px, py = rx + ox, ry + oy
            pc = COLOR_HEX.get(color, GRAY)
            if not player.alive:
                pc = tuple(max(20, c - 90) for c in pc)
                r = 7
                pygame.draw.circle(screen, pc, (px, py), r)
                pygame.draw.circle(screen, (70, 70, 70), (px, py), r, 1)
            else:
                r = 12
                pygame.draw.circle(screen, pc, (px, py), r)
                pygame.draw.circle(screen, WHITE, (px, py), r, 2)
            if player.role == "impostor" and player.alive:
                pygame.draw.circle(screen, (180, 30, 30), (px - r, py - r), 3)
            lbl = _small_font.render(color[:4].title(), True, WHITE)
            screen.blit(lbl, (px - lbl.get_width() // 2, py - r - 16))


def _draw_game_hud(screen: pygame.Surface, game_state: GameState) -> None:
    hx = 900
    pygame.draw.rect(screen, (15, 15, 35), (hx, 0, 300, HEIGHT))
    pygame.draw.line(screen, (50, 50, 80), (hx, 0), (hx, HEIGHT), 2)

    y = 10
    hdr = _small_font.render(f"Round {game_state.round}  Turn {game_state.turn}", True, CYAN)
    screen.blit(hdr, (hx + 10, y))
    y += 22
    ph = _small_font.render(f"Phase: {game_state.phase}", True, LIGHT_GRAY)
    screen.blit(ph, (hx + 10, y))
    y += 28

    pct = game_state.task_pct * 100
    bar_w, bar_h = 270, 16
    pygame.draw.rect(screen, (30, 30, 50), (hx + 10, y, bar_w, bar_h), border_radius=4)
    fill_w = int(bar_w * game_state.task_pct)
    if fill_w > 0:
        pygame.draw.rect(screen, CYAN, (hx + 10, y, fill_w, bar_h), border_radius=4)
    pct_lbl = _small_font.render(f"Tasks: {pct:.0f}%", True, WHITE)
    screen.blit(pct_lbl, (hx + bar_w // 2 - pct_lbl.get_width() // 2, y))
    y += 28

    y += 4
    pygame.draw.line(screen, (50, 50, 80), (hx + 10, y), (hx + 290, y))
    y += 8

    screen.blit(_small_font.render("Players", True, WHITE), (hx + 10, y))
    y += 20

    for color, p in game_state.players.items():
        pc = COLOR_HEX.get(color, GRAY)
        if not p.alive:
            pc = tuple(max(30, c - 100) for c in pc)
        r = 5
        pygame.draw.circle(screen, pc, (hx + 20, y + 6), r)
        status = "[G] " if p.role == "ghost" else "[I] " if p.role == "impostor" else ""
        if p.role == "ejected":
            status = "[X] "
        loc_short = p.location.replace("_", " ")[:14]
        txt = f"{status}{color[:6].title():6s} {loc_short}"
        c_txt = LIGHT_GRAY if p.alive else (80, 80, 90)
        lbl = _small_font.render(txt, True, c_txt)
        screen.blit(lbl, (hx + 30, y))
        y += 17

    y += 6
    pygame.draw.line(screen, (50, 50, 80), (hx + 10, y), (hx + 290, y))
    y += 8

    screen.blit(_small_font.render("Events", True, WHITE), (hx + 10, y))
    y += 18
    shown = [e for e in _event_log[-20:] if any(
        kw in e.lower() for kw in ("kill", "body", "meeting", "eject", "vent", "game over")
    )]
    if not shown:
        shown = _event_log[-8:]
    for ev in shown[-12:]:
        c = CYAN if "meeting" in ev.lower() or "game over" in ev.lower() else (
            (255, 120, 100) if "kill" in ev.lower() else GRAY)
        lbl = _small_font.render(ev[:45], True, c)
        screen.blit(lbl, (hx + 10, y))
        y += 14


def _draw_meeting_overlay(screen: pygame.Surface, game_state: GameState) -> None:
    overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, 180))
    screen.blit(overlay, (0, 0))

    py = 60
    hdr = _button_font.render("MEETING IN PROGRESS", True, WHITE)
    screen.blit(hdr, hdr.get_rect(center=(WIDTH // 2, py)))

    y = 110
    for entry in game_state.meeting_log[-30:]:
        kind = entry.get("type", "statement")
        color = entry.get("color", "?")
        text = entry.get("text", "")
        prefix = f"[{color.upper()}]"
        if kind == "rebuttal":
            prefix = f"[{color.upper()} rebuttal]"
        full = f"{prefix} {text}"
        wrapped = _wrap_text(full, _small_font, 800)
        for line in wrapped:
            c = CYAN if color.lower() in ("cyan",) else LIGHT_GRAY
            lbl = _small_font.render(line, True, c)
            screen.blit(lbl, (200, y))
            y += 16
        if y > HEIGHT - 40:
            break

    note = _small_font.render("Waiting for voting...", True, GRAY)
    screen.blit(note, note.get_rect(center=(WIDTH // 2, HEIGHT - 30)))


def _draw_voting_overlay(screen: pygame.Surface, game_state: GameState) -> None:
    vr = game_state.vote_results
    if not vr:
        return

    overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, 180))
    screen.blit(overlay, (0, 0))

    hdr = _button_font.render("VOTE RESULTS", True, WHITE)
    screen.blit(hdr, hdr.get_rect(center=(WIDTH // 2, 60)))

    y = 110
    votes = vr.get("votes", {})
    tally = vr.get("tally", {})
    ejected = vr.get("ejected")

    screen.blit(_small_font.render("Votes cast:", True, LIGHT_GRAY), (300, y))
    y += 24
    for voter, voted in sorted(votes.items()):
        txt = f"{voter:>8s}  ->  {voted}"
        lbl = _small_font.render(txt, True, WHITE)
        screen.blit(lbl, (350, y))
        y += 18

    y += 10
    screen.blit(_small_font.render("Tally:", True, LIGHT_GRAY), (300, y))
    y += 22
    max_votes = max(tally.values()) if tally else 0
    for target, count in sorted(tally.items(), key=lambda x: -x[1]):
        bar_w = count * 40
        c = (0, 200, 100) if count == max_votes and count > 0 else (100, 100, 100)
        pygame.draw.rect(screen, c, (350, y, bar_w, 18), border_radius=3)
        lbl = _small_font.render(f"{target}: {count}", True, WHITE)
        screen.blit(lbl, (350 + bar_w + 10, y))
        y += 20

    y += 14
    if ejected:
        ec = COLOR_HEX.get(ejected, WHITE)
        ej_lbl = _button_font.render(f"{ejected.upper()} WAS EJECTED", True, ec)
        screen.blit(ej_lbl, ej_lbl.get_rect(center=(WIDTH // 2, y)))
    else:
        no_lbl = _button_font.render("NO ONE WAS EJECTED (tie or skip)", True, GRAY)
        screen.blit(no_lbl, no_lbl.get_rect(center=(WIDTH // 2, y)))


def _draw_game_over(screen: pygame.Surface, game_state: GameState) -> None:
    overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, 200))
    screen.blit(overlay, (0, 0))

    winner = game_state.winner or "?"
    wc = START_COLOR if winner == "crewmates" else QUIT_COLOR
    hdr = _title_font.render(f"{winner.upper()} WIN!", True, wc)
    screen.blit(hdr, hdr.get_rect(center=(WIDTH // 2, 250)))

    sub = _subtitle_font.render("Press Q or close window to exit", True, GRAY)
    screen.blit(sub, sub.get_rect(center=(WIDTH // 2, 330)))

    y = 400
    screen.blit(_small_font.render("Final Player Status:", True, LIGHT_GRAY), (350, y))
    y += 24
    for color, p in game_state.players.items():
        pc = COLOR_HEX.get(color, GRAY)
        role = p.role
        alive_text = "alive" if p.alive else "dead"
        txt = f"  {color:>8s}  {role:>8s}  {alive_text}"
        lbl = _small_font.render(txt, True, pc)
        screen.blit(lbl, (350, y))
        y += 18

    lbl2 = _small_font.render(f"Rounds: {game_state.round}  Turns: {game_state.turn}  Tasks: {game_state.task_pct*100:.0f}%", True, GRAY)
    screen.blit(lbl2, lbl2.get_rect(center=(WIDTH // 2, y + 10)))


def _draw_pause_menu(screen: pygame.Surface) -> None:
    mx, my = pygame.mouse.get_pos()

    overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, 180))
    screen.blit(overlay, (0, 0))

    pw, ph = 400, 360
    px, py = (WIDTH - pw) // 2, (HEIGHT - ph) // 2
    _draw_panel(screen, px, py, pw, ph)

    title = _button_font.render("PAUSED", True, WHITE)
    screen.blit(title, title.get_rect(center=(WIDTH // 2, py + 45)))

    btn_w, btn_h, gap = 280, 50, 16
    bx = px + (pw - btn_w) // 2
    by = py + 100

    resume_rect = pygame.Rect(bx, by, btn_w, btn_h)
    _draw_button(screen, "Resume", resume_rect, START_COLOR, START_HOVER,
                 resume_rect.collidepoint(mx, my), _button_font, 10)

    settings_rect = pygame.Rect(bx, by + btn_h + gap, btn_w, btn_h)
    _draw_button(screen, "Settings", settings_rect, SETTINGS_COLOR, SETTINGS_HOVER,
                 settings_rect.collidepoint(mx, my), _button_font, 10)

    to_menu_rect = pygame.Rect(bx, by + 2 * (btn_h + gap), btn_w, btn_h)
    _draw_button(screen, "Quit to Menu", to_menu_rect, QUIT_COLOR, QUIT_HOVER,
                 to_menu_rect.collidepoint(mx, my), _button_font, 10)

    quit_rect = pygame.Rect(bx, by + 3 * (btn_h + gap), btn_w, btn_h)
    _draw_button(screen, "Quit to Desktop", quit_rect, (140, 30, 30), (180, 50, 50),
                 quit_rect.collidepoint(mx, my), _button_font, 10)


def _wrap_text(text: str, font: pygame.font.Font, max_w: int) -> list[str]:
    words = text.split(" ")
    lines: list[str] = []
    current = ""
    for word in words:
        test = current + (" " if current else "") + word
        if font.size(test)[0] <= max_w:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _handle_pause_menu_click(mx: int, my: int, game_state: GameState) -> str | None:
    global _pause_menu_open, _pause_was_paused

    pw, ph = 400, 360
    px, py = (WIDTH - pw) // 2, (HEIGHT - ph) // 2
    btn_w, btn_h, gap = 280, 50, 16
    bx = px + (pw - btn_w) // 2
    by = py + 100

    resume_rect = pygame.Rect(bx, by, btn_w, btn_h)
    settings_rect = pygame.Rect(bx, by + btn_h + gap, btn_w, btn_h)
    to_menu_rect = pygame.Rect(bx, by + 2 * (btn_h + gap), btn_w, btn_h)
    quit_rect = pygame.Rect(bx, by + 3 * (btn_h + gap), btn_w, btn_h)

    if resume_rect.collidepoint(mx, my):
        _pause_menu_open = False
        game_state.paused = _pause_was_paused
        return None
    if settings_rect.collidepoint(mx, my):
        _pause_menu_open = False
        _screen = "settings"
        _event_log.clear()
        return "to_menu"
    if to_menu_rect.collidepoint(mx, my):
        _pause_menu_open = False
        _screen = "menu"
        _event_log.clear()
        return "to_menu"
    if quit_rect.collidepoint(mx, my):
        return "quit"
    return None


def get_lobby_config() -> dict | None:
    if _screen != "lobby":
        return None
    return {
        "mode": _lobby["mode"],
        "players": [
            {
                "color": s["color"],
                "model": s["model"],
                "human": s.get("human", False),
            }
            for s in _lobby["slots"][:_lobby["slot_count"]]
        ],
        "num_impostors": _lobby["num_impostors"],
        "kill_cooldown": _lobby["kill_cooldown"],
        "task_count": _lobby["task_count"],
    }


def is_mock_mode() -> bool:
    return _settings.get("mock_mode", False)
