# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import hashlib
import hmac
import math
import os
import random
import re
import secrets
import shutil
import sys
import uuid
import ctypes
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


def configure_windows_dpi_awareness() -> None:
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def configure_tcl_tk_runtime() -> None:
    base_dir = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    candidates = [
        (base_dir / "RuntimeTcl" / "tcl8.6", base_dir / "RuntimeTcl" / "tk8.6"),
        (base_dir / "_tcl_data" / "tcl8.6", base_dir / "_tk_data" / "tk8.6"),
        (base_dir / "_tcl_data", base_dir / "_tk_data"),
    ]
    for tcl_dir, tk_dir in candidates:
        if tcl_dir.exists() and tk_dir.exists():
            os.environ["TCL_LIBRARY"] = str(tcl_dir)
            os.environ["TK_LIBRARY"] = str(tk_dir)
            return


configure_tcl_tk_runtime()
configure_windows_dpi_awareness()

import tkinter as tk
from tkinter import messagebox, ttk

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageTk


@dataclass(frozen=True)
class TicketType:
    face_value: int
    name: str
    max_prize: int
    description: str
    source_note: str = "本地模拟票面"


DEFAULT_TICKET_PRICE = 10
TICKET_PRICE = DEFAULT_TICKET_PRICE
LOTTERY_FACE_VALUES = (2, 3, 5, 10, 20, 30, 50)
TICKET_TYPES = {
    2: TicketType(2, "本地模拟 2元票", 50_000, "本地模拟小面值刮刮乐。"),
    3: TicketType(3, "本地模拟 3元票", 80_000, "本地模拟小面值刮刮乐。"),
    5: TicketType(5, "午马", 100_000, "马年马力全开！"),
    10: TicketType(10, "骏马贺岁", 300_000, "骏马贺新岁！"),
    20: TicketType(20, "马到成功", 1_000_000, "新的一年，马到成功！"),
    30: TicketType(30, "抢头彩2026", 1_000_000, "马年新春抢头彩！"),
    50: TicketType(50, "新春大吉2026", 1_000_000, "马年新春大吉！"),
}
MIN_TICKET_PRICE = min(LOTTERY_FACE_VALUES)
STARTING_BALANCE = 200
AUTO_REVEAL_RATIO = 0.80
TICKET_ROTATION_SENSITIVITY = 0.010
TICKET_FRONT_SCRATCH_COS_MIN = 0.72
TICKET_3D_STRIP_WIDTH = 2
TICKET_FLAT_SNAP_SIN = 0.18
TICKET_FLAT_SNAP_PITCH = 0.08
TICKET_CAMERA_DISTANCE = 1500.0
TICKET_PITCH_SENSITIVITY = 0.006
TICKET_PITCH_LIMIT = 0.58
TICKET_ZOOM_MIN = 0.30
TICKET_ZOOM_MAX = 1.20
TICKET_ZOOM_STEP = 0.08
TICKET_RENDER_SCALE = 2
WIN_CHANCE = 0.05
PRIZE_WEIGHT_TOTAL = 100000
PASSWORD_HASH_SCHEME = "pbkdf2_sha256"
PASSWORD_HASH_ITERATIONS = 200_000


def normalize_ticket_angle(angle: float) -> float:
    return math.atan2(math.sin(angle), math.cos(angle))


def visible_ticket_render_state(angle: float) -> tuple[bool, float]:
    normalized = normalize_ticket_angle(angle)
    if math.cos(normalized) >= 0:
        return True, normalized
    if normalized >= 0:
        return False, normalized - math.pi
    return False, normalized + math.pi


def ticket_uses_flat_render(angle: float, pitch: float) -> bool:
    return abs(math.sin(angle)) < TICKET_FLAT_SNAP_SIN and abs(pitch) < TICKET_FLAT_SNAP_PITCH


def flat_ticket_display_rect(
    source_size: tuple[int, int],
    zoom: float,
    viewport_size: tuple[int, int],
) -> tuple[int, int, int, int]:
    source_width, source_height = source_size
    zoom = max(0.001, float(zoom))
    display_width = max(1, int(source_width * zoom))
    display_height = max(1, int(source_height * zoom))
    left = int(viewport_size[0] / 2 - display_width / 2)
    top = int(viewport_size[1] / 2 - display_height / 2)
    return left, top, display_width, display_height


def screen_to_flat_ticket_source_point(
    pos: tuple[int, int],
    source_size: tuple[int, int],
    zoom: float,
    viewport_size: tuple[int, int],
) -> tuple[int, int] | None:
    source_width, source_height = source_size
    if source_width <= 0 or source_height <= 0:
        return None

    left, top, display_width, display_height = flat_ticket_display_rect(source_size, zoom, viewport_size)
    if not (left <= pos[0] < left + display_width and top <= pos[1] < top + display_height):
        return None

    local_x = round((pos[0] - left) * source_width / display_width)
    local_y = round((pos[1] - top) * source_height / display_height)
    return min(source_width - 1, max(0, local_x)), min(source_height - 1, max(0, local_y))


def screen_to_ticket_source_point(
    pos: tuple[int, int],
    source_size: tuple[int, int],
    zoom: float,
    angle: float,
    pitch: float,
    viewport_size: tuple[int, int],
) -> tuple[int, int] | None:
    source_width, source_height = source_size
    if source_width <= 0 or source_height <= 0:
        return None

    zoom = max(0.001, float(zoom))
    display_width = max(1, int(source_width * zoom))
    display_height = max(1, int(source_height * zoom))
    half_width = display_width / 2
    half_height = display_height / 2
    center_x = viewport_size[0] / 2
    center_y = viewport_size[1] / 2
    u = pos[0] - center_x
    v = pos[1] - center_y

    sin_yaw = math.sin(angle)
    cos_yaw = math.cos(angle)
    sin_pitch = math.sin(pitch)
    cos_pitch = math.cos(pitch)

    axis_x = (cos_yaw, sin_yaw * sin_pitch, -sin_yaw * cos_pitch)
    axis_y = (0.0, cos_pitch, sin_pitch)
    normal = (sin_yaw, -cos_yaw * sin_pitch, cos_yaw * cos_pitch)
    denominator = normal[0] * u + normal[1] * v + normal[2] * TICKET_CAMERA_DISTANCE
    if abs(denominator) < 1e-6:
        return None

    t = normal[2] * TICKET_CAMERA_DISTANCE / denominator
    if t <= 0:
        return None

    world = (
        u * t,
        v * t,
        TICKET_CAMERA_DISTANCE * (t - 1),
    )
    local_x = world[0] * axis_x[0] + world[1] * axis_x[1] + world[2] * axis_x[2]
    local_y = world[0] * axis_y[0] + world[1] * axis_y[1] + world[2] * axis_y[2]
    display_x = local_x + half_width
    display_y = local_y + half_height
    if not (0 <= display_x < display_width and 0 <= display_y < display_height):
        return None
    return int(display_x / zoom), int(display_y / zoom)


PRIZE_WEIGHTS = [
    ("20", 70000),
    ("30", 18000),
    ("50", 8000),
    ("100", 3000),
    ("600", 750),
    ("1,000", 180),
    ("1,200", 55),
    ("1,500", 12),
    ("10,000", 2),
    ("250,000", 1),
]
PRIZE_WEIGHTS_BY_FACE_VALUE = {
    2: [
        ("2", 70000),
        ("4", 18000),
        ("6", 8000),
        ("10", 3000),
        ("20", 750),
        ("50", 180),
        ("100", 55),
        ("500", 12),
        ("1,000", 2),
        ("50,000", 1),
    ],
    3: [
        ("3", 70000),
        ("6", 18000),
        ("9", 8000),
        ("15", 3000),
        ("30", 750),
        ("60", 180),
        ("150", 55),
        ("600", 12),
        ("3,000", 2),
        ("80,000", 1),
    ],
    5: [
        ("5", 70000),
        ("10", 18000),
        ("20", 8000),
        ("50", 3000),
        ("100", 750),
        ("200", 180),
        ("500", 55),
        ("1,000", 12),
        ("5,000", 2),
        ("100,000", 1),
    ],
    10: PRIZE_WEIGHTS,
    20: [
        ("20", 70000),
        ("40", 18000),
        ("100", 8000),
        ("200", 3000),
        ("600", 750),
        ("1,000", 180),
        ("5,000", 55),
        ("10,000", 12),
        ("50,000", 2),
        ("1,000,000", 1),
    ],
    30: [
        ("30", 70000),
        ("60", 18000),
        ("150", 8000),
        ("300", 3000),
        ("1,000", 750),
        ("3,000", 180),
        ("10,000", 55),
        ("30,000", 12),
        ("100,000", 2),
        ("1,000,000", 1),
    ],
    50: [
        ("50", 70000),
        ("100", 18000),
        ("200", 8000),
        ("500", 3000),
        ("1,000", 750),
        ("5,000", 180),
        ("10,000", 55),
        ("50,000", 12),
        ("100,000", 2),
        ("1,000,000", 1),
    ],
}
PRIZE_PINYIN = {
    "2": "ER",
    "3": "SAN",
    "4": "SI",
    "5": "WU",
    "6": "LIU",
    "9": "JIU",
    "10": "SHI",
    "15": "SHIWU",
    "20": "ERSHI",
    "30": "SANSHI",
    "40": "SISHI",
    "50": "WUSHI",
    "60": "LIUSHI",
    "100": "YIBAI",
    "150": "YIBAIWU",
    "200": "ERBAI",
    "300": "SANBAI",
    "500": "WUBAI",
    "600": "LIUBAI",
    "1,000": "YIQIAN",
    "1,200": "YIQIANER",
    "1,500": "YIQIANWU",
    "3,000": "SANQIAN",
    "5,000": "WUQIAN",
    "10,000": "YIWAN",
    "30,000": "SANWAN",
    "50,000": "WUWAN",
    "80,000": "BAWAN",
    "100,000": "SHIWAN",
    "250,000": "ERSHIWUWAN",
    "1,000,000": "YIBAIWAN",
}
FIREWORK_DURATION_MS = 3000
FIREWORK_PARTICLE_COUNT_PER_SIDE = 72

APP_TITLE = "彩票刮刮乐"

UI_HEX = {
    "window_bg": "#eef4f8",
    "window_bg_top": "#f7fafc",
    "window_bg_bottom": "#e7eef5",
    "card": "#ffffff",
    "card_soft": "#f6f8fb",
    "surface": "#eef3f8",
    "border": "#d7e0ea",
    "text": "#182230",
    "muted": "#667085",
    "primary": "#214365",
    "primary_hover": "#2b557e",
    "gold": "#d49a31",
    "gold_hover": "#e0aa43",
    "gold_soft": "#fff4d6",
    "red": "#b72d34",
    "red_soft": "#fff0f0",
    "green": "#1f7a5a",
    "disabled": "#aeb7c4",
    "shadow": "#d8e2ec",
    "white": "#ffffff",
}

PLAY_COORDINATES = [
    (147, 27), (219, 27), (291, 27), (363, 27), (435, 27),
    (147, 92), (219, 92), (291, 92), (363, 92), (435, 92),
]
WIN_COORDINATES = [(72, 42), (72, 100)]


def hex_to_rgb(value: str) -> tuple[int, int, int]:
    value = value.strip().lstrip("#")
    if len(value) != 6:
        raise ValueError("hex color must contain 6 characters")
    return tuple(int(value[index:index + 2], 16) for index in (0, 2, 4))


def blend_color(start: tuple[int, int, int], end: tuple[int, int, int], ratio: float) -> tuple[int, int, int]:
    ratio = max(0.0, min(1.0, float(ratio)))
    return tuple(int(start[index] + (end[index] - start[index]) * ratio) for index in range(3))


def clean_placeholder_value(value: str, placeholder: str) -> str:
    value = value.strip()
    return "" if value == placeholder else value


def build_celebration_particles(width: int, height: int, rng=None) -> list[CelebrationParticle]:
    rng = rng or random
    palette = [
        hex_to_rgb(UI_HEX["red"]),
        hex_to_rgb(UI_HEX["gold"]),
        hex_to_rgb(UI_HEX["green"]),
        (255, 244, 214),
        (255, 255, 255),
    ]
    origins = {
        "left": (34.0, height - 120.0),
        "right": (float(width - 34), height - 120.0),
    }
    particles: list[CelebrationParticle] = []

    for side, (origin_x, origin_y) in origins.items():
        direction = 1 if side == "left" else -1
        for _ in range(FIREWORK_PARTICLE_COUNT_PER_SIDE):
            particles.append(
                CelebrationParticle(
                    x=origin_x + rng.uniform(-5.0, 5.0),
                    y=origin_y + rng.uniform(-10.0, 10.0),
                    vx=direction * rng.uniform(170.0, 430.0),
                    vy=-rng.uniform(300.0, 620.0),
                    size=rng.randint(3, 7),
                    color=rng.choice(palette),
                    side=side,
                    birth_delay_ms=rng.randint(0, 900),
                    life_ms=rng.randint(1600, FIREWORK_DURATION_MS),
                )
            )

    return particles


class AccountError(Exception):
    """Base error for account operations."""


class DuplicateUserError(AccountError):
    """Raised when a username is already registered."""


class AuthenticationError(AccountError):
    """Raised when username or password validation fails."""


class InsufficientBalanceError(AccountError):
    """Raised when the account cannot pay for a new ticket."""


class UserDataError(AccountError):
    """Raised when the user data file is unreadable."""


@dataclass
class TicketState:
    prize: int
    face_value: int = TICKET_PRICE
    product_name: str = ""
    max_prize: int = 0
    image_path: str = ""
    cover_path: str = ""
    back_path: str = ""
    scratch_rect: tuple[int, int, int, int] = (0, 0, 0, 0)
    ticket_id: int | None = None
    theme_index: int = 0
    visual_style: str = "legacy"
    rule_summary: str = ""
    game_rule: str = ""
    play_numbers: list[str] | None = None
    win_numbers: list[str] | None = None
    claimed: bool = False


@dataclass
class GeneratedTicketVisual:
    prize: int
    face_value: int
    product_name: str
    max_prize: int
    base_path: str
    cover_path: str
    scratch_rect: tuple[int, int, int, int]
    back_path: str = ""
    ticket_id: int | None = None
    theme_index: int = 0
    visual_style: str = "legacy"
    rule_summary: str = ""
    game_rule: str = ""
    play_numbers: list[str] | None = None
    win_numbers: list[str] | None = None


@dataclass(frozen=True)
class TicketSelection:
    face_value: int
    ticket_id: int | None = None
    theme_index: int = 0
    product_name: str = ""


@dataclass(frozen=True)
class ScratchLayout:
    kind: str
    play_count: int
    win_count: int
    cols: int
    rows: int
    outlined_text: bool = False


@dataclass
class CelebrationParticle:
    x: float
    y: float
    vx: float
    vy: float
    size: int
    color: tuple[int, int, int]
    side: str
    birth_delay_ms: int
    life_ms: int


def bundled_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return Path(__file__).resolve().parent


def runtime_root() -> Path:
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        project_data_dir = exe_dir.parent / "Datarecourses"
        if exe_dir.name.lower() == "dist" and project_data_dir.exists():
            return exe_dir.parent
        return exe_dir
    return Path(__file__).resolve().parent


def resource_path(*parts: str) -> Path:
    return bundled_root().joinpath(*parts)


def runtime_data_dir() -> Path:
    data_dir = runtime_root() / "Datarecourses"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def default_user_data_file() -> Path:
    return runtime_data_dir() / "UserData.json"


def default_login_preferences_file() -> Path:
    return runtime_data_dir() / "LoginPreferences.json"


def default_ticket_output_file() -> Path:
    return runtime_data_dir() / "current_scratch_card.png"


def default_ticket_base_file() -> Path:
    return runtime_data_dir() / "current_ticket_base.png"


def default_ticket_cover_file() -> Path:
    return runtime_data_dir() / "current_ticket_cover.png"


def default_ticket_back_output_file() -> Path:
    return runtime_data_dir() / "current_ticket_back.png"


def default_ticket_back_file() -> Path:
    return resource_path("Picture", "frontPicture", "i_love_china_back.jpg")


def default_app_icon_png_file() -> Path:
    return resource_path("Picture", "app_icon.png")


def ensure_user_data_file(data_file: str | Path | None = None) -> Path:
    path = Path(data_file) if data_file is not None else default_user_data_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return path
    if data_file is not None:
        path.write_text("[]", encoding="utf-8")
        return path

    seed = resource_path("Datarecourses", "UserData.json")
    try:
        same_file = seed.resolve() == path.resolve()
    except FileNotFoundError:
        same_file = False
    if seed.exists() and not same_file:
        shutil.copyfile(seed, path)
    else:
        path.write_text("[]", encoding="utf-8")
    return path


def load_users(data_file: str | Path | None = None) -> list[dict]:
    path = ensure_user_data_file(data_file)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise UserDataError("用户数据文件格式错误。") from exc
    if not isinstance(data, list):
        raise UserDataError("用户数据文件必须是用户列表。")
    return data


def save_users(users: Iterable[dict], data_file: str | Path | None = None) -> None:
    path = ensure_user_data_file(data_file)
    path.write_text(
        json.dumps(list(users), ensure_ascii=False, indent=4),
        encoding="utf-8",
    )


def load_login_preferences(path: str | Path | None = None) -> dict:
    prefs_path = Path(path) if path is not None else default_login_preferences_file()
    if not prefs_path.exists():
        return {"username": "", "remember_password": False, "password": ""}
    try:
        data = json.loads(prefs_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"username": "", "remember_password": False, "password": ""}
    if not isinstance(data, dict):
        return {"username": "", "remember_password": False, "password": ""}
    return {
        "username": str(data.get("username", "")),
        "remember_password": bool(data.get("remember_password", False)),
        "password": str(data.get("password", "")) if data.get("remember_password") else "",
    }


def save_login_preferences(username: str, remember_password: bool, password: str = "", path: str | Path | None = None) -> None:
    prefs_path = Path(path) if path is not None else default_login_preferences_file()
    prefs_path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "username": username.strip(),
        "remember_password": bool(remember_password),
        "password": "",
    }
    prefs_path.write_text(json.dumps(data, ensure_ascii=False, indent=4), encoding="utf-8")


def validate_credentials(username: str, password: str) -> None:
    if not username or re.search(r"\s", username):
        raise AuthenticationError("用户名不能为空，且不能包含空格。")
    if not password:
        raise AuthenticationError("密码不能为空。")
    if not re.fullmatch(r"[A-Za-z0-9]+", password):
        raise AuthenticationError("密码只能包含英文字母和数字。")


def normalize_optional_email(email: str) -> str:
    email = email.strip()
    if email and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise AuthenticationError("邮箱格式不正确。")
    return email


def find_user(users: list[dict], username: str) -> dict | None:
    for user in users:
        if user.get("username") == username:
            return user
    return None


def hash_password(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        bytes.fromhex(salt),
        PASSWORD_HASH_ITERATIONS,
    ).hex()
    return f"{PASSWORD_HASH_SCHEME}${PASSWORD_HASH_ITERATIONS}${salt}${digest}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        scheme, iterations, salt, digest = stored_hash.split("$", 3)
        if scheme != PASSWORD_HASH_SCHEME:
            return False
        candidate = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            bytes.fromhex(salt),
            int(iterations),
        ).hex()
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(candidate, digest)


def user_password_matches(user: dict, password: str) -> tuple[bool, bool]:
    stored_hash = user.get("password_hash")
    if isinstance(stored_hash, str) and verify_password(password, stored_hash):
        return True, False

    legacy_password = user.get("password")
    if isinstance(legacy_password, str) and hmac.compare_digest(legacy_password, password):
        user["password_hash"] = hash_password(password)
        user.pop("password", None)
        return True, True

    return False, False


def normalize_face_value(face_value: int | str) -> int:
    try:
        value = int(str(face_value).replace("元", "").strip())
    except (TypeError, ValueError) as exc:
        raise ValueError("彩票面值必须是数字。") from exc
    if value not in TICKET_TYPES:
        available = "、".join(f"{price}元" for price in LOTTERY_FACE_VALUES)
        raise ValueError(f"不支持的面值：{value}元。可选面值：{available}。")
    return value


def get_ticket_type(face_value: int | str = TICKET_PRICE) -> TicketType:
    return TICKET_TYPES[normalize_face_value(face_value)]


def get_prize_weights(face_value: int | str = TICKET_PRICE) -> list[tuple[str, int]]:
    value = normalize_face_value(face_value)
    return PRIZE_WEIGHTS_BY_FACE_VALUE[value]


def register_account(
    username: str,
    password: str,
    data_file: str | Path | None = None,
    *,
    email: str = "",
    confirm_password: str | None = None,
) -> dict:
    validate_credentials(username, password)
    email = normalize_optional_email(email)
    if confirm_password is not None and password != confirm_password:
        raise AuthenticationError("两次输入的密码不一致。")

    users = load_users(data_file)
    if find_user(users, username):
        raise DuplicateUserError("该用户名已存在。")

    user = {
        "UID": str(uuid.uuid4()),
        "username": username,
        "email": email,
        "password_hash": hash_password(password),
        "balance": STARTING_BALANCE,
    }
    users.append(user)
    save_users(users, data_file)
    return user.copy()


def authenticate_account(
    username: str,
    password: str,
    data_file: str | Path | None = None,
) -> dict:
    if not username or not password:
        raise AuthenticationError("用户名和密码不能为空。")
    users = load_users(data_file)
    user = find_user(users, username)
    if not user:
        raise AuthenticationError("用户名或密码错误。")
    matched, upgraded = user_password_matches(user, password)
    if not matched:
        raise AuthenticationError("用户名或密码错误。")
    if upgraded:
        save_users(users, data_file)
    return user.copy()


def get_account_balance(username: str, data_file: str | Path | None = None) -> int:
    users = load_users(data_file)
    user = find_user(users, username)
    if not user:
        raise AuthenticationError("用户不存在。")
    return int(user.get("balance", 0))


def change_account_balance(
    username: str,
    amount: int,
    data_file: str | Path | None = None,
) -> int:
    users = load_users(data_file)
    user = find_user(users, username)
    if not user:
        raise AuthenticationError("用户不存在。")
    user["balance"] = int(user.get("balance", 0)) + int(amount)
    save_users(users, data_file)
    return int(user["balance"])


def charge_scratch_card(
    username: str,
    data_file: str | Path | None = None,
    *,
    face_value: int | str = TICKET_PRICE,
) -> int:
    ticket_price = normalize_face_value(face_value)
    users = load_users(data_file)
    user = find_user(users, username)
    if not user:
        raise AuthenticationError("用户不存在。")

    balance = int(user.get("balance", 0))
    if balance < ticket_price:
        raise InsufficientBalanceError(f"余额不足，无法购买 ¥{ticket_price} 面值刮刮乐。")

    user["balance"] = balance - ticket_price
    save_users(users, data_file)
    return int(user["balance"])


def claim_ticket_prize(
    username: str,
    ticket: TicketState,
    data_file: str | Path | None = None,
) -> int:
    if ticket.claimed:
        return get_account_balance(username, data_file)

    ticket.claimed = True
    if ticket.prize <= 0:
        return get_account_balance(username, data_file)
    return change_account_balance(username, ticket.prize, data_file)


def scratch_card_fee(username: str, face_value: int | str = TICKET_PRICE):
    ticket_price = normalize_face_value(face_value)
    try:
        return charge_scratch_card(username, face_value=ticket_price), f"-{ticket_price}"
    except InsufficientBalanceError:
        return get_account_balance(username), "余额不足"


def reward_fee(username: str, amount: int) -> None:
    change_account_balance(username, int(amount))


def load_json_resource(*parts: str) -> dict:
    path = resource_path(*parts)
    return json.loads(path.read_text(encoding="utf-8"))


_OFFICIAL_TICKET_CATALOG: list[dict] | None = None


def load_official_ticket_catalog() -> list[dict]:
    global _OFFICIAL_TICKET_CATALOG
    if _OFFICIAL_TICKET_CATALOG is not None:
        return _OFFICIAL_TICKET_CATALOG

    path = resource_path("Datarecourses", "TicketTypes.json")
    if not path.exists():
        _OFFICIAL_TICKET_CATALOG = []
        return _OFFICIAL_TICKET_CATALOG

    data = json.loads(path.read_text(encoding="utf-8"))
    _OFFICIAL_TICKET_CATALOG = list(data.get("tickets", []))
    return _OFFICIAL_TICKET_CATALOG


def official_tickets_for_face_value(face_value: int | str) -> list[dict]:
    value = normalize_face_value(face_value)
    return [ticket for ticket in load_official_ticket_catalog() if int(ticket.get("money", 0)) == value]


def find_official_ticket(ticket_id: int | None) -> dict | None:
    if ticket_id is None:
        return None
    for ticket in load_official_ticket_catalog():
        if int(ticket.get("id", 0)) == int(ticket_id):
            return ticket
    return None


def official_ticket_count(face_value: int | str) -> int:
    return len(official_tickets_for_face_value(face_value))


def ticket_style_options(face_value: int | str) -> list[TicketSelection]:
    value = normalize_face_value(face_value)
    ticket_type = get_ticket_type(value)
    return [TicketSelection(face_value=value, product_name=f"{ticket_type.name}（本地模拟）")]


def ticket_asset_path(relative_path: str) -> Path:
    return resource_path(*Path(relative_path).parts)


def open_ticket_asset(relative_path: str) -> Image.Image:
    return Image.open(ticket_asset_path(relative_path)).convert("RGBA")


def average_image_color(image: Image.Image, fallback: tuple[int, int, int] = (244, 232, 218)) -> tuple[int, int, int]:
    try:
        return image.convert("RGB").resize((1, 1), Image.Resampling.BOX).getpixel((0, 0))
    except Exception:
        return fallback


def average_border_color(image: Image.Image | None, fallback: tuple[int, int, int] = (224, 136, 18)) -> tuple[int, int, int]:
    if image is None:
        return fallback
    try:
        rgb = image.convert("RGB")
        width, height = rgb.size
        if width <= 0 or height <= 0:
            return fallback
        pixels = []
        step_x = max(1, width // 24)
        step_y = max(1, height // 24)
        for x in range(0, width, step_x):
            pixels.append(rgb.getpixel((x, 0)))
            pixels.append(rgb.getpixel((x, height - 1)))
        for y in range(0, height, step_y):
            pixels.append(rgb.getpixel((0, y)))
            pixels.append(rgb.getpixel((width - 1, y)))
        if not pixels:
            return fallback
        return tuple(sorted(pixel[channel] for pixel in pixels)[len(pixels) // 2] for channel in range(3))
    except Exception:
        return fallback


def fit_cover_to_size(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    target_w, target_h = size
    scale = max(target_w / image.width, target_h / image.height)
    resized = image.resize((max(1, int(image.width * scale)), max(1, int(image.height * scale))), Image.Resampling.LANCZOS)
    left = max(0, (resized.width - target_w) // 2)
    top = max(0, (resized.height - target_h) // 2)
    return resized.crop((left, top, left + target_w, top + target_h)).convert("RGBA")


def build_clean_header_part(ticket: dict, size: tuple[int, int], reference: Image.Image) -> Image.Image:
    width, height = size
    bg = average_image_color(reference)
    image = Image.new("RGBA", size, (*bg, 255))
    draw = ImageDraw.Draw(image)
    for y in range(0, height, max(20, height // 8 if height else 20)):
        draw.line((0, y, width, y + max(6, height // 10 if height else 6)), fill=tuple(min(245, c + 18) for c in bg), width=1)
    if width > 120 and height > 36:
        accent = clamp_color(tuple(max(35, channel - 88) for channel in bg), 35, 205)
        title_font = load_ticket_font(max(16, min(46, height // 5)), bold=True)
        small_font = load_ticket_font(max(8, min(16, height // 12)), bold=True)
        name = str(ticket.get("name") or "顶呱刮")
        face_value = int(ticket.get("money", 0) or 0)
        max_award = int(ticket.get("maxAward", 0) or 0)
        draw_text_center_at(draw, (width // 2, max(title_font.size, height // 2)), name, title_font, accent)
        if face_value:
            draw.text((max(8, width // 30), max(6, height // 14)), f"面值{face_value}元", font=small_font, fill=(202, 35, 30))
        if max_award:
            award = f"最高奖金{max_award:,}元"
            bbox = draw.textbbox((0, 0), award, font=small_font)
            draw.text((max(8, width - (bbox[2] - bbox[0]) - max(8, width // 30)), max(6, height // 14)), award, font=small_font, fill=(202, 35, 30))
    return image


def build_clean_footer_part(ticket: dict, size: tuple[int, int], reference: Image.Image) -> Image.Image:
    width, height = size
    bg = average_image_color(reference)
    image = Image.new("RGBA", size, (*bg, 255))
    draw = ImageDraw.Draw(image)
    accent = clamp_color(tuple(max(35, channel - 78) for channel in bg), 35, 205)
    for y in range(0, height, max(18, height // 5)):
        draw.line((0, y, width, y + max(6, height // 6)), fill=tuple(min(245, c + 18) for c in bg), width=1)
    if width <= 40 or height <= 24:
        return image

    name_font = load_ticket_font(max(10, min(24, height // 4)), bold=True)
    small_font = load_ticket_font(max(7, min(14, height // 7)), bold=True)
    max_award = int(ticket.get("maxAward", 0) or 0)
    left_text = str(ticket.get("name") or "顶呱刮")
    award_text = f"最高奖金{max_award:,}元" if max_award else "顶呱刮"
    footer_text = "公益体彩 乐善人生  理性投注"
    draw.text((max(8, width // 28), max(4, height // 8)), left_text, font=name_font, fill=accent)
    draw.text((max(8, width // 28), max(24, height // 2)), award_text, font=small_font, fill=(202, 35, 30))
    text_bbox = draw.textbbox((0, 0), footer_text, font=small_font)
    draw.text((max(8, width - (text_bbox[2] - text_bbox[0]) - max(8, width // 28)), max(4, height - (text_bbox[3] - text_bbox[1]) - max(5, height // 10))), footer_text, font=small_font, fill=accent)
    return image


def official_ticket_frame_parts(
    ticket: dict,
    theme: dict,
    middle_size: tuple[int, int],
) -> tuple[Image.Image, Image.Image]:
    return open_ticket_asset(theme["backgroundA"]), open_ticket_asset(theme["backgroundC"])


def clean_ticket_frame_parts(
    ticket: dict,
    theme: dict,
    middle_size: tuple[int, int],
) -> tuple[Image.Image, Image.Image]:
    return official_ticket_frame_parts(ticket, theme, middle_size)


def fit_ticket_image(image: Image.Image, target_size: tuple[int, int]) -> tuple[Image.Image, float, int, int]:
    target_width, target_height = target_size
    source_width, source_height = image.size
    scale = min(target_width / source_width, target_height / source_height)
    resized_size = (max(1, int(source_width * scale)), max(1, int(source_height * scale)))
    resized = image.resize(resized_size, Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", target_size, (255, 255, 255, 255))
    offset_x = (target_width - resized_size[0]) // 2
    offset_y = (target_height - resized_size[1]) // 2
    canvas.alpha_composite(resized, (offset_x, offset_y))
    return canvas, scale, offset_x, offset_y


def fit_cover_image(image: Image.Image, target_size: tuple[int, int], scale: float, offset_x: int, offset_y: int) -> Image.Image:
    resized_size = (max(1, int(image.width * scale)), max(1, int(image.height * scale)))
    resized = image.resize(resized_size, Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", target_size, (255, 255, 255, 0))
    canvas.alpha_composite(resized, (offset_x, offset_y))
    return canvas


def scale_rect(rect: tuple[int, int, int, int], scale: float, offset_x: int, offset_y: int) -> tuple[int, int, int, int]:
    x, y, width, height = rect
    return (
        offset_x + int(x * scale),
        offset_y + int(y * scale),
        max(1, int(width * scale)),
        max(1, int(height * scale)),
    )


def detect_reveal_scratch_area(revealed: Image.Image, fallback_size: tuple[int, int]) -> tuple[int, int, int, int]:
    fallback = (0, 0, fallback_size[0], fallback_size[1])
    if "A" not in revealed.getbands():
        return fallback
    alpha = revealed.getchannel("A")
    mask = alpha.point(lambda value: 255 if value > 8 else 0)
    bbox = mask.getbbox()
    if bbox is None:
        return fallback
    x1, y1, x2, y2 = bbox
    width = max(1, x2 - x1)
    height = max(1, y2 - y1)
    if width >= fallback_size[0] * 0.98 and height >= fallback_size[1] * 0.98:
        return fallback
    return (x1, y1, width, height)


def compose_ticket_sections(
    ticket: dict,
    theme: dict,
    reveal_key: str,
    target_size: tuple[int, int] = (520, 780),
) -> tuple[Image.Image, Image.Image, tuple[int, int, int, int]]:
    covered = open_ticket_asset(theme["backgroundB"])
    revealed = open_ticket_asset(theme.get(reveal_key) or theme["notAwardImg"])
    part_a, part_c = clean_ticket_frame_parts(ticket, theme, covered.size)

    layout = int(ticket.get("layout", 2))
    if layout == 1:
        mid_width = max(covered.width, revealed.width)
        mid_height = max(covered.height, revealed.height)
        width = part_a.width + mid_width + part_c.width
        height = max(part_a.height, mid_height, part_c.height)
        base = Image.new("RGBA", (width, height), (255, 255, 255, 255))
        cover = Image.new("RGBA", (width, height), (255, 255, 255, 0))
        mid_x = part_a.width
        revealed_x = mid_x + (mid_width - revealed.width) // 2
        covered_x = mid_x + (mid_width - covered.width) // 2
        base.alpha_composite(part_a, (0, 0))
        base.alpha_composite(revealed, (revealed_x, 0))
        base.alpha_composite(part_c, (mid_x + mid_width, 0))
        cover.alpha_composite(covered, (covered_x, 0))
        scratch_rect = (covered_x, 0, covered.width, covered.height)
    else:
        mid_width = max(covered.width, revealed.width)
        mid_height = max(covered.height, revealed.height)
        width = max(part_a.width, mid_width, part_c.width)
        height = part_a.height + mid_height + part_c.height
        base = Image.new("RGBA", (width, height), (255, 255, 255, 255))
        cover = Image.new("RGBA", (width, height), (255, 255, 255, 0))
        top_x = (width - part_a.width) // 2
        revealed_x = (width - revealed.width) // 2
        covered_x = (width - covered.width) // 2
        bottom_x = (width - part_c.width) // 2
        mid_y = part_a.height
        base.alpha_composite(part_a, (top_x, 0))
        base.alpha_composite(revealed, (revealed_x, mid_y + (mid_height - revealed.height) // 2))
        base.alpha_composite(part_c, (bottom_x, mid_y + mid_height))
        cover.alpha_composite(covered, (covered_x, mid_y + (mid_height - covered.height) // 2))
        scratch_rect = (covered_x, mid_y + (mid_height - covered.height) // 2, covered.width, covered.height)

    fitted_base, scale, offset_x, offset_y = fit_ticket_image(base, target_size)
    fitted_cover = fit_cover_image(cover, target_size, scale, offset_x, offset_y)
    return fitted_base, fitted_cover, scale_rect(scratch_rect, scale, offset_x, offset_y)


def compose_ticket_with_generated_middle(
    ticket: dict,
    theme: dict,
    target_size: tuple[int, int] = (520, 780),
) -> tuple[Image.Image, Image.Image, tuple[int, int, int, int]]:
    middle = theme["generatedMiddle"].convert("RGBA")
    middle_cover = theme["generatedCover"].convert("RGBA")
    part_a, part_c = clean_ticket_frame_parts(ticket, theme, middle_cover.size)
    scratch_area = theme.get("scratchArea") or (0, 0, middle_cover.width, middle_cover.height)
    scratch_x, scratch_y, scratch_w, scratch_h = (int(value) for value in scratch_area)

    layout = int(ticket.get("layout", 2))
    if layout == 1:
        mid_width = max(middle.width, middle_cover.width)
        mid_height = max(middle.height, middle_cover.height)
        width = part_a.width + mid_width + part_c.width
        height = max(part_a.height, mid_height, part_c.height)
        base = Image.new("RGBA", (width, height), (255, 255, 255, 255))
        cover = Image.new("RGBA", (width, height), (255, 255, 255, 0))
        mid_x = part_a.width
        middle_x = mid_x + (mid_width - middle.width) // 2
        cover_x = mid_x + (mid_width - middle_cover.width) // 2
        base.alpha_composite(part_a, (0, 0))
        base.alpha_composite(middle, (middle_x, 0))
        base.alpha_composite(part_c, (mid_x + mid_width, 0))
        cover.alpha_composite(middle_cover, (cover_x, 0))
        scratch_rect = (cover_x + scratch_x, scratch_y, scratch_w, scratch_h)
    else:
        mid_width = max(middle.width, middle_cover.width)
        mid_height = max(middle.height, middle_cover.height)
        width = max(part_a.width, mid_width, part_c.width)
        height = part_a.height + mid_height + part_c.height
        base = Image.new("RGBA", (width, height), (255, 255, 255, 255))
        cover = Image.new("RGBA", (width, height), (255, 255, 255, 0))
        top_x = (width - part_a.width) // 2
        middle_x = (width - middle.width) // 2
        cover_x = (width - middle_cover.width) // 2
        bottom_x = (width - part_c.width) // 2
        mid_y = part_a.height
        middle_y = mid_y + (mid_height - middle.height) // 2
        cover_y = mid_y + (mid_height - middle_cover.height) // 2
        base.alpha_composite(part_a, (top_x, 0))
        base.alpha_composite(middle, (middle_x, middle_y))
        base.alpha_composite(part_c, (bottom_x, mid_y + mid_height))
        cover.alpha_composite(middle_cover, (cover_x, cover_y))
        scratch_rect = (cover_x + scratch_x, cover_y + scratch_y, scratch_w, scratch_h)

    fitted_base, scale, offset_x, offset_y = fit_ticket_image(base, target_size)
    fitted_cover = fit_cover_image(cover, target_size, scale, offset_x, offset_y)
    return fitted_base, fitted_cover, scale_rect(scratch_rect, scale, offset_x, offset_y)


def choose_official_prize(ticket: dict, rng=None) -> int:
    rng = rng or random
    grades = sorted({int(amount) for amount in ticket.get("awardGrade", []) if int(amount) > 0})
    if not grades:
        grades = [normalize_money(amount) for amount, _weight in get_prize_weights(ticket.get("money", TICKET_PRICE))]

    weights = [max(1, (len(grades) - index) ** 2) for index, _amount in enumerate(grades)]
    total = sum(weights)
    threshold = rng.random() * total
    cumulative = 0
    for amount, weight in zip(grades, weights):
        cumulative += weight
        if threshold < cumulative:
            return amount
    return grades[0]


def choose_official_sample_prize(ticket: dict, rng=None) -> int:
    rng = rng or random
    samples = []
    for amount in ticket.get("awardSampleMoney", []):
        try:
            value = int(amount)
        except (TypeError, ValueError):
            continue
        if value > 0:
            samples.append(value)
    if not samples:
        return choose_official_prize(ticket, rng)
    return samples[min(len(samples) - 1, int(rng.random() * len(samples)))]


def load_ticket_font(size: int, bold: bool = False, role: str | None = None):
    if role == "number":
        names = ["Number.ttf"]
    elif role == "pinyin":
        names = ["Pinyin.ttf"]
    else:
        names = ["MSYHBD.TTC" if bold else "MSYH.TTC", "MSYHBD.TTC"]

    for name in names:
        path = resource_path("Front", name)
        if path.exists():
            try:
                return ImageFont.truetype(str(path), size)
            except OSError:
                continue

    system_candidates = [
        "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf",
        "Arial Bold.ttf" if bold else "Arial.ttf",
        "arialbd.ttf" if bold else "arial.ttf",
    ]
    for name in system_candidates:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue

    return ImageFont.load_default()


def draw_text_center(
    draw: ImageDraw.ImageDraw,
    rect: tuple[int, int, int, int],
    text: str,
    font,
    fill: tuple[int, int, int] | str,
) -> None:
    bbox = draw.textbbox((0, 0), text, font=font)
    width = bbox[2] - bbox[0]
    height = bbox[3] - bbox[1]
    x1, y1, x2, y2 = rect
    draw.text((x1 + (x2 - x1 - width) // 2, y1 + (y2 - y1 - height) // 2), text, font=font, fill=fill)


def ticket_accent_color(*images: Image.Image) -> tuple[int, int, int]:
    samples = []
    for image in images:
        thumb = image.convert("RGB").resize((1, 1), Image.Resampling.BOX)
        samples.append(thumb.getpixel((0, 0)))
    if not samples:
        return hex_to_rgb(UI_HEX["primary"])
    return tuple(sum(color[index] for color in samples) // len(samples) for index in range(3))


def clamp_color(color: tuple[int, int, int], minimum: int = 35, maximum: int = 220) -> tuple[int, int, int]:
    return tuple(max(minimum, min(maximum, int(channel))) for channel in color)


def official_prize_pool(ticket: dict, face_value: int) -> list[int]:
    grades = sorted({int(amount) for amount in ticket.get("awardGrade", []) if int(amount) > 0})
    if grades:
        return grades
    return [normalize_money(amount) for amount, _weight in get_prize_weights(face_value)]


def choose_display_prize(prize_pool: list[int], rng=None) -> int:
    rng = rng or random
    if not prize_pool:
        return 0
    low_to_high = sorted(prize_pool)
    weights = [max(1, (len(low_to_high) - index) ** 2) for index, _amount in enumerate(low_to_high)]
    total = sum(weights)
    threshold = rng.random() * total
    cumulative = 0
    for amount, weight in zip(low_to_high, weights):
        cumulative += weight
        if threshold < cumulative:
            return amount
    return low_to_high[0]


def build_middle_entries(
    ticket: dict,
    prize: int,
    rng=None,
    play_count: int = 10,
    win_count: int = 2,
) -> tuple[list[dict], list[str]]:
    rng = rng or random
    face_value = int(ticket.get("money", TICKET_PRICE))
    prize_pool = official_prize_pool(ticket, face_value)
    valid_numbers = [f"{number:02d}" for number in range(100)]
    win_count = max(1, min(int(win_count), len(valid_numbers) - 1))
    win_numbers = rng.sample(valid_numbers, win_count)
    excluded = [number for number in valid_numbers if number not in win_numbers]
    play_count = max(1, min(int(play_count), len(excluded) + 1))

    if prize > 0:
        matched_number = rng.choice(win_numbers)
        play_numbers = rng.sample(excluded, play_count - 1) + [matched_number]
    else:
        play_numbers = rng.sample(excluded, play_count)
    rng.shuffle(play_numbers)

    entries = []
    for number in play_numbers:
        matched = number in win_numbers
        amount = prize if matched and prize > 0 else choose_display_prize(prize_pool, rng)
        entries.append({"number": number, "amount": int(amount), "matched": matched})
    return entries, win_numbers


def paired_symbol_prize_symbol(ticket: dict) -> str:
    rule = str(ticket.get("gameRule") or "")
    for symbol in ("马", "龙", "蛇"):
        if f"{symbol}标志" in rule or f"“{symbol}”标志" in rule:
            return symbol
    match = re.search(r"两个相同的[“\"]?([^“”\"，。]{1,3})[”\"]?标志", rule)
    if match:
        return match.group(1)
    return "马"


def is_paired_symbol_prize_ticket(ticket: dict) -> bool:
    introduce = str(ticket.get("introduce") or "")
    rule = str(ticket.get("gameRule") or "")
    return "两同" in introduce and "两个相同" in rule and "右方所示" in rule and "灯笼" in rule


def random_losing_scene_symbols(rng=None, paired_symbol: str = "马") -> list[str]:
    rng = rng or random
    numbers = [f"{rng.randrange(100):02d}" for _ in range(3)]
    if rng.random() < 0.35:
        numbers[rng.randrange(3)] = paired_symbol
    rng.shuffle(numbers)
    return numbers


def build_paired_symbol_prize_entries(ticket: dict, prize: int, rng=None) -> list[dict]:
    rng = rng or random
    paired_symbol = paired_symbol_prize_symbol(ticket)
    prize_pool = official_prize_pool(ticket, int(ticket.get("money", TICKET_PRICE)))
    amounts = [amount for amount in prize_pool if amount > 0]
    if not amounts:
        amounts = [10, 20, 30, 50, 100, 200, 500, 1000, 5000, 10000]

    winning_index = rng.randrange(12) if prize > 0 else -1
    scenes = []
    for index in range(12):
        matched = index == winning_index
        if matched:
            use_lantern = prize % 3 == 0 and (prize // 3) in amounts and rng.random() < 0.35
            if use_lantern:
                amount = prize // 3
                symbols = ["灯笼", f"{rng.randrange(100):02d}", f"{rng.randrange(100):02d}"]
                multiplier = 3
            else:
                amount = prize
                symbols = [paired_symbol, paired_symbol, f"{rng.randrange(100):02d}"]
                multiplier = 1
            rng.shuffle(symbols)
        else:
            amount = choose_display_prize(amounts, rng)
            symbols = random_losing_scene_symbols(rng, paired_symbol)
            multiplier = 0
        scenes.append(
            {
                "scene": index + 1,
                "symbols": symbols,
                "amount": int(amount),
                "matched": matched,
                "multiplier": multiplier,
            }
        )
    return scenes


def is_symbol_prize_ticket(ticket: dict) -> bool:
    return has_symbol_prize_game(ticket) and not has_number_match_game(ticket) and not has_multi_same_game(ticket)


def ticket_introduce(ticket: dict) -> str:
    return str(ticket.get("introduce") or "").strip()


def ticket_rule(ticket: dict) -> str:
    return str(ticket.get("gameRule") or "")


def has_number_match_game(ticket: dict) -> bool:
    introduce = ticket_introduce(ticket)
    rule = ticket_rule(ticket)
    return "数字匹配" in introduce or "匹配中奖数字" in introduce or "你的号码" in rule or "中奖号码" in rule


def has_prize_amount_game(ticket: dict) -> bool:
    introduce = ticket_introduce(ticket)
    rule = ticket_rule(ticket)
    return "找奖金符号" in introduce or "刮奖金符号" in introduce or "奖金标志" in rule or "金额标志" in rule


def has_multi_same_game(ticket: dict) -> bool:
    introduce = ticket_introduce(ticket)
    rule = ticket_rule(ticket)
    return "多同" in introduce or "两个相同" in rule or "3个相同" in rule or "三个相同" in rule


def has_collect_symbol_game(ticket: dict) -> bool:
    introduce = ticket_introduce(ticket)
    return "集中奖符号" in introduce or "收集中奖符号" in introduce or "搜集中奖符号" in introduce


def has_symbol_prize_game(ticket: dict) -> bool:
    introduce = ticket_introduce(ticket)
    return "找中奖符号" in introduce or "刮中奖符号" in introduce or "刮中奖标志" in introduce or "刮中奖标志" in ticket_rule(ticket)


def normalize_symbol_label(label: str) -> str:
    return re.sub(r"\s+", "", str(label).strip(" “”。；;，,"))


def valid_prize_symbol(label: str) -> bool:
    if not label:
        return False
    if label.startswith(("￥", "¥")):
        return False
    if len(label) > 6:
        return False
    if label.endswith("倍") and re.search(r"\d", label):
        return True
    blocked_terms = ("奖金", "金额", "中奖", "倍数", "覆盖膜", "所示")
    return not any(term in label for term in blocked_terms)


def multiplier_from_rule_context(rule: str, symbol: str) -> int:
    position = rule.find(symbol)
    if position >= 0:
        following = rule[position : position + 90]
        stops = [following.find(mark) for mark in ("；", "。", "\n") if following.find(mark) >= 0]
        context = following[: min(stops)] if stops else following
    else:
        context = ""
    numeric = re.search(r"(\d+)\s*倍", context)
    if numeric:
        return max(1, int(numeric.group(1)))
    word_multipliers = {
        "两倍": 2,
        "二倍": 2,
        "三倍": 3,
        "四倍": 4,
        "五倍": 5,
        "十倍": 10,
    }
    for word, multiplier in word_multipliers.items():
        if word in context:
            return multiplier
    return 1


def symbol_prize_specs(ticket: dict) -> list[dict]:
    rule = str(ticket.get("gameRule") or "")
    labels: list[str] = []
    for raw in re.findall(r"[“\"]\s*([^”\"]+?)\s*[”\"]", rule):
        labels.append(normalize_symbol_label(raw))
    for raw in re.findall(r"出现\s*([^，；。\n“”\"]{1,6})标志", rule):
        label = normalize_symbol_label(raw)
        label = re.sub(r"^(如果|在|任意|一个|5个)", "", label)
        labels.append(normalize_symbol_label(label))

    specs = []
    seen = set()
    for label in labels:
        if not valid_prize_symbol(label) or label in seen:
            continue
        seen.add(label)
        specs.append({"symbol": label, "multiplier": multiplier_from_rule_context(rule, label)})
    if specs:
        return specs
    return [{"symbol": str(ticket.get("name") or "奖"), "multiplier": 1}]


def random_decoy_symbol(rng, disallowed: set[str]) -> str:
    candidates = [
        "福", "喜", "乐", "旺", "星", "花", "鼓", "旗", "云", "火", "球", "冠",
        "鼎", "宝", "彩", "顺", "安", "吉", "春", "风", "梦", "光", "力", "美",
    ]
    choices = [symbol for symbol in candidates if symbol not in disallowed]
    return rng.choice(choices or candidates)


def build_symbol_prize_entries(ticket: dict, prize: int, rng=None, play_count: int = 25) -> list[dict]:
    rng = rng or random
    specs = symbol_prize_specs(ticket)
    winning_symbols = {spec["symbol"] for spec in specs}
    prize_pool = official_prize_pool(ticket, int(ticket.get("money", TICKET_PRICE)))
    amounts = [amount for amount in prize_pool if amount > 0] or [int(ticket.get("money", TICKET_PRICE))]
    play_count = max(1, int(play_count))
    winning_index = rng.randrange(play_count) if prize > 0 else -1
    preferred_winner = next((spec for spec in specs if int(spec.get("multiplier", 1)) == 1), specs[0])
    multiplier = max(1, int(preferred_winner.get("multiplier", 1)))
    winning_amount = max(1, int(prize) // multiplier) if prize > 0 else 0

    entries = []
    for index in range(play_count):
        matched = index == winning_index
        if matched:
            symbol = preferred_winner["symbol"]
            amount = winning_amount
        else:
            symbol = random_decoy_symbol(rng, winning_symbols)
            amount = choose_display_prize(amounts, rng)
        entries.append(
            {
                "symbol": symbol,
                "amount": int(amount),
                "matched": matched,
                "multiplier": multiplier if matched else 1,
            }
        )
    return entries


def build_prize_amount_entries(ticket: dict, prize: int, rng=None, play_count: int = 12) -> list[dict]:
    rng = rng or random
    prize_pool = official_prize_pool(ticket, int(ticket.get("money", TICKET_PRICE)))
    amounts = [amount for amount in prize_pool if amount > 0] or [int(ticket.get("money", TICKET_PRICE))]
    play_count = max(1, int(play_count))
    winning_index = rng.randrange(play_count) if prize > 0 else -1
    entries = []
    for index in range(play_count):
        matched = index == winning_index
        amount = int(prize) if matched and prize > 0 else choose_display_prize(amounts, rng)
        entries.append({"amount": int(amount), "matched": matched})
    return entries


def distinct_decoy_symbols(rng, count: int = 3, disallowed: set[str] | None = None) -> list[str]:
    disallowed = disallowed or set()
    symbols = []
    attempts = 0
    while len(symbols) < count and attempts < 80:
        attempts += 1
        symbol = random_decoy_symbol(rng, disallowed | set(symbols))
        if symbol not in symbols:
            symbols.append(symbol)
    while len(symbols) < count:
        symbols.append(f"{rng.randrange(100):02d}")
    return symbols


def build_multi_same_prize_entries(ticket: dict, prize: int, rng=None, scene_count: int = 12) -> list[dict]:
    rng = rng or random
    prize_pool = official_prize_pool(ticket, int(ticket.get("money", TICKET_PRICE)))
    amounts = [amount for amount in prize_pool if amount > 0] or [int(ticket.get("money", TICKET_PRICE))]
    use_numbers = "号码" in ticket_rule(ticket)
    scene_count = max(1, int(scene_count))
    winning_index = rng.randrange(scene_count) if prize > 0 else -1
    scenes = []
    for index in range(scene_count):
        matched = index == winning_index
        amount = int(prize) if matched and prize > 0 else choose_display_prize(amounts, rng)
        if use_numbers:
            if matched:
                winner = f"{rng.randrange(100):02d}"
                extra = f"{rng.randrange(100):02d}"
                while extra == winner:
                    extra = f"{rng.randrange(100):02d}"
                symbols = [winner, winner, extra]
            else:
                symbols = rng.sample([f"{number:02d}" for number in range(100)], 3)
        elif matched:
            winner = random_decoy_symbol(rng, set())
            extra = random_decoy_symbol(rng, {winner})
            symbols = [winner, winner, extra]
        else:
            symbols = distinct_decoy_symbols(rng, 3)
        rng.shuffle(symbols)
        scenes.append(
            {
                "scene": index + 1,
                "symbols": symbols,
                "amount": int(amount),
                "matched": matched,
                "multiplier": 1 if matched else 0,
            }
        )
    return scenes


_NUMBER_PINYIN_TABLE: dict | None = None


def number_pinyin_text(number: str) -> str:
    global _NUMBER_PINYIN_TABLE
    if _NUMBER_PINYIN_TABLE is None:
        try:
            _NUMBER_PINYIN_TABLE = load_json_resource("Datarecourses", "Number.txt")
        except (OSError, json.JSONDecodeError):
            _NUMBER_PINYIN_TABLE = {}
    return str(_NUMBER_PINYIN_TABLE.get(number, number)).upper()


def amount_pinyin_text(amount: int) -> str:
    return prize_pinyin(f"{int(amount):,}").upper()


def format_print_yuan(amount: int | str) -> str:
    return f"￥{int(amount):,}"


def official_scratch_layout(ticket: dict, size: tuple[int, int]) -> ScratchLayout:
    width, height = size
    ratio = width / max(1, height)
    layout = int(ticket.get("layout", 2))
    tpl = int(ticket.get("tpl", 2))
    ticket_id = int(ticket.get("id", 0))

    if is_paired_symbol_prize_ticket(ticket):
        return ScratchLayout("paired-symbol-prize", play_count=12, win_count=0, cols=2, rows=6, outlined_text=True)

    if layout == 1:
        if tpl == 2:
            return ScratchLayout("vertical-list", play_count=10, win_count=3, cols=1, rows=10, outlined_text=True)
        return ScratchLayout("vertical-grid", play_count=10, win_count=2, cols=2, rows=5, outlined_text=True)

    if tpl == 7 and ticket_id == 211:
        return ScratchLayout("wide-symbol-grid", play_count=24, win_count=2, cols=6, rows=4)
    if tpl == 7:
        cols = 8 if width >= 850 else 6
        rows = 1 if height < 240 else 2
        return ScratchLayout("wide-bonus-strip", play_count=cols * rows, win_count=2, cols=cols, rows=rows, outlined_text=True)

    if height > width * 1.15:
        return ScratchLayout("tall-sheet", play_count=40, win_count=2, cols=5, rows=8, outlined_text=True)

    if tpl == 1 or ratio >= 2.5:
        cols = 5 if width < 760 else 8
        rows = max(1, min(3, round(height / max(48, width / max(cols, 1)))))
        return ScratchLayout("wide-match", play_count=cols * rows, win_count=2, cols=cols, rows=rows, outlined_text=True)

    return ScratchLayout("compact-grid", play_count=25, win_count=2, cols=5, rows=5)


def build_reference_middle_background(size: tuple[int, int], reference: Image.Image | None = None) -> Image.Image:
    tone = 226
    if reference is not None:
        sample_size = (min(72, max(1, reference.width)), min(72, max(1, reference.height)))
        sample = reference.convert("RGB").resize(sample_size, Image.Resampling.BOX)
        data_getter = getattr(sample, "get_flattened_data", None)
        pixels = list(data_getter() if data_getter is not None else sample.getdata())
        neutral_pixels = []
        bright_pixels = []
        for pixel in pixels:
            brightness = sum(pixel) / 3
            spread = max(pixel) - min(pixel)
            if brightness >= 155:
                bright_pixels.append(pixel)
            if brightness >= 165 and spread <= 28:
                neutral_pixels.append(pixel)
        candidates = neutral_pixels or bright_pixels or pixels
        channel_medians = []
        for channel in range(3):
            values = sorted(pixel[channel] for pixel in candidates)
            channel_medians.append(values[len(values) // 2])
        tone = max(220, min(238, int(sum(channel_medians) / 3)))

    base = Image.new("RGBA", size, (tone, tone, max(0, tone - 2), 255))
    draw = ImageDraw.Draw(base)
    width, height = size
    line_color = (min(244, tone + 5), min(244, tone + 5), min(244, tone + 4), 120)
    dot_color = (max(212, tone - 8), max(212, tone - 8), max(210, tone - 10), 120)
    for y in range(max(18, height // 14), height, max(28, height // 8)):
        draw.line((0, y, width, y), fill=line_color, width=1)
    for x in range(max(18, width // 18), width, max(34, width // 10)):
        draw.line((x, 0, x, height), fill=line_color, width=1)
    for y in range(8, height, max(22, height // 12)):
        for x in range((y // 3) % 18, width, max(24, width // 18)):
            draw.point((x, y), fill=dot_color)
    return base


def fit_ticket_font(
    draw: ImageDraw.ImageDraw,
    text: str,
    max_width: int,
    start_size: int,
    min_size: int = 6,
    bold: bool = True,
    role: str | None = None,
):
    for size in range(max(min_size, int(start_size)), min_size - 1, -1):
        font = load_ticket_font(size, bold=bold, role=role)
        bbox = draw.textbbox((0, 0), text, font=font)
        if bbox[2] - bbox[0] <= max_width:
            return font
    return load_ticket_font(min_size, bold=bold, role=role)


def draw_text_center_at(
    draw: ImageDraw.ImageDraw,
    center: tuple[int, int],
    text: str,
    font,
    fill: tuple[int, int, int] | str,
    stroke_width: int = 0,
    stroke_fill: tuple[int, int, int] | str | None = None,
) -> None:
    bbox = draw.textbbox((0, 0), text, font=font)
    width = bbox[2] - bbox[0]
    height = bbox[3] - bbox[1]
    draw.text(
        (center[0] - width // 2 - bbox[0], center[1] - height // 2 - bbox[1]),
        text,
        font=font,
        fill=fill,
        stroke_width=stroke_width,
        stroke_fill=stroke_fill,
    )


def draw_dotted_line(
    draw: ImageDraw.ImageDraw,
    x1: int,
    y: int,
    x2: int,
    fill: tuple[int, int, int],
    dot: int = 4,
    gap: int = 5,
    width: int = 2,
) -> None:
    for x in range(x1, x2, dot + gap):
        draw.line((x, y, min(x + dot, x2), y), fill=fill, width=width)


def draw_security_pattern(draw: ImageDraw.ImageDraw, size: tuple[int, int], dark: tuple[int, int, int]) -> None:
    width, height = size
    small_font = load_ticket_font(max(6, min(13, height // 24)))
    pale = tuple(min(238, channel + 58) for channel in dark)
    for y in range(-height, height * 2, max(34, height // 5)):
        draw.line((0, y, width, y + height // 2), fill=pale, width=1)
    for y in range(8, height, max(30, height // 5)):
        for x in range(6, width, max(92, width // 6)):
            draw.text((x, y), "SPORT LOTTERY", font=small_font, fill=pale)
    stamp_font = load_ticket_font(max(9, min(24, height // 13)), bold=True)
    for x in range(width // 5, width, max(160, width // 4)):
        draw.text((x, height - max(32, height // 7)), "顶呱刮", font=stamp_font, fill=tuple(max(140, c) for c in pale))


def soften_cover_sample_marks(cover: Image.Image) -> Image.Image:
    image = cover.convert("RGBA")
    width, height = image.size
    if width <= 0 or height <= 0:
        return image

    rgb = image.convert("RGB")
    boxes = [
        (int(width * 0.34), int(height * 0.76), int(width * 0.68), height),
        (int(width * 0.24), int(height * 0.38), int(width * 0.58), int(height * 0.62)),
        (int(width * 0.58), int(height * 0.38), width, int(height * 0.72)),
        (int(width * 0.16), 0, int(width * 0.48), int(height * 0.18)),
    ]
    if width > height:
        boxes.extend(
            [
                (int(width * 0.18), 0, int(width * 0.62), int(height * 0.28)),
                (int(width * 0.42), 0, int(width * 0.86), int(height * 0.28)),
                (0, int(height * 0.76), int(width * 0.52), height),
            ]
        )
    pixels = image.load()
    rgb_pixels = rgb.load()
    cover_bg = average_image_color(image)
    for x1, y1, x2, y2 in boxes:
        x1 = max(0, min(width, x1))
        y1 = max(0, min(height, y1))
        x2 = max(0, min(width, x2))
        y2 = max(0, min(height, y2))
        if x2 <= x1 or y2 <= y1:
            continue
        ring = []
        for x in range(x1, x2, max(1, (x2 - x1) // 18)):
            for y in (max(0, y1 - 2), min(height - 1, y2 + 1)):
                ring.append(rgb_pixels[x, y])
        for y in range(y1, y2, max(1, (y2 - y1) // 18)):
            for x in (max(0, x1 - 2), min(width - 1, x2 + 1)):
                ring.append(rgb_pixels[x, y])
        if not ring:
            continue
        bg = cover_bg
        for y in range(y1, y2):
            for x in range(x1, x2):
                r, g, b, a = pixels[x, y]
                spread = max(r, g, b) - min(r, g, b)
                brightness = (r + g + b) / 3
                bg_distance = abs(r - bg[0]) + abs(g - bg[1]) + abs(b - bg[2])
                if a and spread < 60 and brightness < 205 and bg_distance > 28:
                    pixels[x, y] = (*bg, a)
    if height > width * 1.2:
        x1, y1, x2, y2 = int(width * 0.30), int(height * 0.88), int(width * 0.72), int(height * 0.995)
        bg = average_border_color(image, average_image_color(image))
        for y in range(max(0, y1), min(height, y2)):
            for x in range(max(0, x1), min(width, x2)):
                r, g, b, a = pixels[x, y]
                spread = max(r, g, b) - min(r, g, b)
                brightness = (r + g + b) / 3
                bg_distance = abs(r - bg[0]) + abs(g - bg[1]) + abs(b - bg[2])
                if a and spread < 80 and brightness < 190 and bg_distance > 18:
                    pixels[x, y] = (*bg, a)
    right_start = int(width * 0.66)
    if width > height * 1.8 and right_start < width:
        for y in range(0, height):
            for x in range(right_start, width):
                r, g, b, a = pixels[x, y]
                if not a:
                    continue
                red_dominance = r - max(g, b)
                brightness = (r + g + b) / 3
                if red_dominance > 28 and 70 < brightness < 245:
                    bg = (246, 246, 246) if brightness > 150 else (232, 232, 232)
                    pixels[x, y] = (*bg, a)
                elif max(r, g, b) - min(r, g, b) < 22 and 150 < brightness < 244:
                    pixels[x, y] = (246, 246, 246, a)
    return image


def draw_generated_cover(size: tuple[int, int], reference: Image.Image | None = None) -> Image.Image:
    if reference is not None and reference.size == size:
        return soften_cover_sample_marks(reference)

    width, height = size
    cover = Image.new("RGBA", size, (212, 212, 210, 245))
    draw = ImageDraw.Draw(cover)
    line_color = (170, 170, 166, 180)
    for y in range(-height, height * 2, max(26, height // 8)):
        draw.line((0, y, width, y + height // 3), fill=line_color, width=1)
    for y in range(0, height, max(22, height // 9)):
        draw_dotted_line(draw, 0, y, width, (172, 172, 168), dot=3, gap=7, width=1)
    notice_font = load_ticket_font(max(10, min(20, height // 12)), bold=True)
    draw_text_center_at(draw, (width // 2, height // 2), "刮开覆盖膜", notice_font, (112, 112, 108))
    return cover


def draw_official_entry(
    draw: ImageDraw.ImageDraw,
    rect: tuple[int, int, int, int],
    entry: dict,
    dark: tuple[int, int, int],
    red: tuple[int, int, int],
    outlined: bool = False,
) -> None:
    x1, y1, x2, y2 = rect
    cell_w = max(1, x2 - x1)
    cell_h = max(1, y2 - y1)
    cx = (x1 + x2) // 2
    number = str(entry["number"])
    amount = int(entry["amount"])
    amount_text = format_print_yuan(amount)
    number_font = fit_ticket_font(draw, number, int(cell_w * 0.78), max(10, int(cell_h * 0.38)), 7, bold=True, role="number")
    amount_font = fit_ticket_font(draw, amount_text, int(cell_w * 0.92), max(9, int(cell_h * 0.27)), 6, bold=True, role="number")
    pinyin_font = fit_ticket_font(draw, amount_pinyin_text(amount), int(cell_w * 0.90), max(5, int(cell_h * 0.12)), 5, role="pinyin")
    main_fill = dark
    stroke_width = 1 if outlined and min(cell_w, cell_h) >= 30 else 0
    stroke_fill = (248, 248, 244) if outlined else dark

    draw_text_center_at(draw, (cx, y1 + int(cell_h * 0.21)), number, number_font, main_fill, stroke_width, stroke_fill)
    draw_text_center_at(draw, (cx, y1 + int(cell_h * 0.34)), number_pinyin_text(number), pinyin_font, dark)
    draw_text_center_at(draw, (cx, y1 + int(cell_h * 0.58)), amount_text, amount_font, main_fill, stroke_width, stroke_fill)
    draw_text_center_at(draw, (cx, y1 + int(cell_h * 0.79)), amount_pinyin_text(amount), pinyin_font, dark)

    if entry.get("matched"):
        inset_x = max(3, cell_w // 12)
        inset_y = max(3, cell_h // 9)
        draw.ellipse((x1 + inset_x, y1 + inset_y, x2 - inset_x, y2 - inset_y), outline=red, width=max(2, min(cell_w, cell_h) // 18))


def draw_symbol_panel(draw: ImageDraw.ImageDraw, rect: tuple[int, int, int, int], dark: tuple[int, int, int]) -> None:
    symbols = list("瑞祥庆昌吉安美鸿欢运乐旺康兴喜")
    x1, y1, x2, y2 = rect
    cols, rows = 3, 5
    cell_w = max(1, (x2 - x1) // cols)
    cell_h = max(1, (y2 - y1) // rows)
    font = load_ticket_font(max(8, min(22, cell_h // 2)), bold=True)
    pinyin_font = load_ticket_font(max(5, min(8, cell_h // 5)), role="pinyin")
    pinyin = {
        "瑞": "RUI", "祥": "XIANG", "庆": "QING", "昌": "CHANG", "吉": "JI",
        "安": "AN", "美": "MEI", "鸿": "HONG", "欢": "HUAN", "运": "YUN",
        "乐": "LE", "旺": "WANG", "康": "KANG", "兴": "XING", "喜": "XI",
    }
    for index, symbol in enumerate(symbols):
        row = index // cols
        col = index % cols
        cx = x1 + col * cell_w + cell_w // 2
        cy = y1 + row * cell_h + cell_h // 2
        radius = max(8, min(cell_w, cell_h) // 3)
        draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), outline=dark, width=2)
        draw_text_center_at(draw, (cx, cy - 2), symbol, font, dark)
        draw_text_center_at(draw, (cx, cy + radius + max(5, pinyin_font.size // 2)), pinyin[symbol], pinyin_font, dark)


def draw_wide_official_middle(
    draw: ImageDraw.ImageDraw,
    size: tuple[int, int],
    entries: list[dict],
    win_numbers: list[str],
    dark: tuple[int, int, int],
    line: tuple[int, int, int],
    red: tuple[int, int, int],
    outlined: bool = False,
) -> None:
    width, height = size
    margin = max(14, width // 58)
    split_x = max(190, int(width * 0.22))
    draw_symbol_panel(draw, (margin, margin + 4, split_x - margin, height - margin), dark)
    draw.line((split_x, margin, split_x, height - margin), fill=dark, width=max(2, width // 420))

    right_x1 = split_x + max(20, width // 38)
    right_x2 = width - margin
    win_y = margin + max(18, height // 15)
    title_font = load_ticket_font(max(9, min(16, height // 20)), bold=True)
    number_font = load_ticket_font(max(16, min(28, height // 10)), bold=True, role="number")
    pinyin_font = load_ticket_font(max(5, min(8, height // 34)), role="pinyin")
    center_x = (right_x1 + right_x2) // 2
    draw_text_center_at(draw, (center_x, win_y), "中奖号码", title_font, dark)
    draw.line((center_x - 70, win_y + 14, center_x + 70, win_y + 14), fill=dark, width=2)
    for offset, number in zip((-62, 62), win_numbers):
        x = center_x + offset
        draw_text_center_at(draw, (x, win_y - 2), number, number_font, dark)
        draw_text_center_at(draw, (x, win_y + 19), number_pinyin_text(number), pinyin_font, dark)

    label_font = load_ticket_font(max(7, min(11, height // 28)), bold=True)
    draw_text_center_at(draw, (center_x, win_y + 36), "你的号码", label_font, dark)
    grid_top = win_y + max(46, height // 6)
    grid_bottom = height - margin
    cols, rows = 6, 4
    cell_w = max(1, (right_x2 - right_x1) // cols)
    cell_h = max(1, (grid_bottom - grid_top) // rows)
    for row in range(1, rows):
        draw_dotted_line(draw, right_x1, grid_top + row * cell_h, right_x2, line, dot=4, gap=6, width=2)
    for index, entry in enumerate(entries[: cols * rows]):
        row = index // cols
        col = index % cols
        rect = (
            right_x1 + col * cell_w,
            grid_top + row * cell_h + 1,
            right_x1 + (col + 1) * cell_w,
            grid_top + (row + 1) * cell_h - 1,
        )
        draw_official_entry(draw, rect, entry, dark, red, outlined)


def draw_compact_official_middle(
    draw: ImageDraw.ImageDraw,
    size: tuple[int, int],
    entries: list[dict],
    dark: tuple[int, int, int],
    line: tuple[int, int, int],
    red: tuple[int, int, int],
    outlined: bool = False,
) -> None:
    width, height = size
    margin = max(8, min(width, height) // 28)
    cols, rows = 5, 5
    grid_x1 = margin
    grid_x2 = width - margin
    grid_y1 = margin
    grid_y2 = height - margin
    cell_w = max(1, (grid_x2 - grid_x1) // cols)
    cell_h = max(1, (grid_y2 - grid_y1) // rows)
    for row in range(1, rows):
        draw_dotted_line(draw, grid_x1, grid_y1 + row * cell_h, grid_x2, line, dot=4, gap=6, width=2)
    for index, entry in enumerate(entries[: cols * rows]):
        row = index // cols
        col = index % cols
        rect = (
            grid_x1 + col * cell_w,
            grid_y1 + row * cell_h + 1,
            grid_x1 + (col + 1) * cell_w,
            grid_y1 + (row + 1) * cell_h - 1,
        )
        draw_official_entry(draw, rect, entry, dark, red, outlined)


def draw_vertical_official_middle(
    draw: ImageDraw.ImageDraw,
    size: tuple[int, int],
    entries: list[dict],
    win_numbers: list[str],
    dark: tuple[int, int, int],
    line: tuple[int, int, int],
    red: tuple[int, int, int],
    outlined: bool = False,
) -> None:
    width, height = size
    margin = max(8, width // 18)
    header_h = max(70, height // 7)
    title_font = load_ticket_font(max(11, min(20, width // 11)), bold=True)
    number_font = load_ticket_font(max(16, min(30, width // 7)), bold=True, role="number")
    pinyin_font = load_ticket_font(max(5, min(9, width // 28)), role="pinyin")
    draw_text_center_at(draw, (width // 2, margin + 12), "中奖号码", title_font, dark)
    for index, number in enumerate(win_numbers):
        cx = margin + (index + 1) * (width - margin * 2) // 3
        draw_text_center_at(draw, (cx, margin + 42), number, number_font, dark)
        draw_text_center_at(draw, (cx, margin + 63), number_pinyin_text(number), pinyin_font, dark)

    cols = 2
    rows = max(1, (len(entries) + cols - 1) // cols)
    grid_x1 = margin
    grid_x2 = width - margin
    grid_y1 = header_h
    grid_y2 = height - margin
    cell_w = max(1, (grid_x2 - grid_x1) // cols)
    cell_h = max(1, (grid_y2 - grid_y1) // rows)
    draw_dotted_line(draw, grid_x1, grid_y1, grid_x2, line, dot=4, gap=6, width=2)
    for row in range(1, rows):
        draw_dotted_line(draw, grid_x1, grid_y1 + row * cell_h, grid_x2, line, dot=4, gap=6, width=2)
    for index, entry in enumerate(entries):
        row = index // cols
        col = index % cols
        rect = (
            grid_x1 + col * cell_w,
            grid_y1 + row * cell_h + 1,
            grid_x1 + (col + 1) * cell_w,
            grid_y1 + (row + 1) * cell_h - 1,
        )
        draw_official_entry(draw, rect, entry, dark, red, outlined)


def draw_wide_match_official_middle(
    draw: ImageDraw.ImageDraw,
    size: tuple[int, int],
    layout: ScratchLayout,
    entries: list[dict],
    win_numbers: list[str],
    dark: tuple[int, int, int],
    line: tuple[int, int, int],
    red: tuple[int, int, int],
) -> None:
    width, height = size
    margin = max(8, min(width, height) // 18)
    left_w = max(74, min(int(width * 0.24), 128))
    label_font = load_ticket_font(max(7, min(13, height // 12)), bold=True)
    number_font = load_ticket_font(max(13, min(25, height // 5)), bold=True, role="number")
    pinyin_font = load_ticket_font(max(5, min(8, height // 25)), role="pinyin")

    draw_text_center_at(draw, (margin + left_w // 2, margin + max(9, height // 10)), "中奖号码", label_font, dark)
    for index, number in enumerate(win_numbers):
        cy = margin + max(30, height // 4) + index * max(32, height // 4)
        draw_text_center_at(draw, (margin + left_w // 2, cy), number, number_font, dark, 1, (248, 248, 244))
        draw_text_center_at(draw, (margin + left_w // 2, cy + max(12, height // 12)), number_pinyin_text(number), pinyin_font, dark)

    grid_x1 = margin + left_w + max(12, width // 45)
    grid_x2 = width - margin
    grid_y1 = margin + max(16, height // 10)
    grid_y2 = height - margin
    draw.line((grid_x1 - max(8, margin // 2), grid_y1, grid_x1 - max(8, margin // 2), grid_y2), fill=line, width=2)
    draw_text_center_at(draw, ((grid_x1 + grid_x2) // 2, margin + max(9, height // 10)), "你的号码", label_font, dark)

    grid_y1 += max(18, height // 7)
    cell_w = max(1, (grid_x2 - grid_x1) // layout.cols)
    cell_h = max(1, (grid_y2 - grid_y1) // layout.rows)
    for row in range(1, layout.rows):
        draw_dotted_line(draw, grid_x1, grid_y1 + row * cell_h, grid_x2, line, dot=4, gap=6, width=2)
    for index, entry in enumerate(entries[: layout.cols * layout.rows]):
        row = index // layout.cols
        col = index % layout.cols
        rect = (
            grid_x1 + col * cell_w,
            grid_y1 + row * cell_h + 1,
            grid_x1 + (col + 1) * cell_w,
            grid_y1 + (row + 1) * cell_h - 1,
        )
        draw_official_entry(draw, rect, entry, dark, red, layout.outlined_text)


def draw_wide_bonus_strip_middle(
    draw: ImageDraw.ImageDraw,
    size: tuple[int, int],
    layout: ScratchLayout,
    entries: list[dict],
    win_numbers: list[str],
    dark: tuple[int, int, int],
    line: tuple[int, int, int],
    red: tuple[int, int, int],
) -> None:
    width, height = size
    margin = max(7, min(width, height) // 22)
    top_h = max(46, int(height * 0.42))
    bonus_count = 4
    bonus_w = max(1, (width - margin * 2) // bonus_count)
    icon_font = load_ticket_font(max(10, min(18, height // 9)), bold=True)
    small_font = load_ticket_font(max(5, min(9, height // 24)))
    symbols = ["花朵", "太阳", "海螺", "螃蟹"]
    for index, symbol in enumerate(symbols):
        x1 = margin + index * bonus_w
        x2 = margin + (index + 1) * bonus_w
        if index:
            draw.line((x1, margin, x1, margin + top_h - 8), fill=dark, width=2)
        draw_text_center_at(draw, ((x1 + x2) // 2, margin + top_h // 3), symbol, icon_font, dark, 1, (248, 248, 244))
        draw_text_center_at(draw, ((x1 + x2) // 2, margin + top_h - 14), "游戏奖金区", small_font, dark)

    lower_y1 = margin + top_h
    left_w = max(62, int(width * 0.12))
    label_font = load_ticket_font(max(6, min(10, height // 23)), bold=True)
    number_font = load_ticket_font(max(12, min(22, height // 7)), bold=True, role="number")
    draw_text_center_at(draw, (margin + left_w // 2, lower_y1 + 18), "中奖号码", label_font, dark)
    for index, number in enumerate(win_numbers):
        cy = lower_y1 + max(36, height // 4) + index * max(24, height // 7)
        draw_text_center_at(draw, (margin + left_w // 2, cy), number, number_font, dark, 1, (248, 248, 244))
    grid_x1 = margin + left_w + 8
    grid_x2 = width - margin
    grid_y1 = lower_y1 + max(8, height // 18)
    grid_y2 = height - margin
    draw.line((grid_x1 - 5, grid_y1, grid_x1 - 5, grid_y2), fill=line, width=2)
    cell_w = max(1, (grid_x2 - grid_x1) // layout.cols)
    cell_h = max(1, (grid_y2 - grid_y1) // layout.rows)
    for row in range(1, layout.rows):
        draw_dotted_line(draw, grid_x1, grid_y1 + row * cell_h, grid_x2, line, dot=4, gap=6, width=2)
    for index, entry in enumerate(entries[: layout.cols * layout.rows]):
        row = index // layout.cols
        col = index % layout.cols
        rect = (
            grid_x1 + col * cell_w,
            grid_y1 + row * cell_h + 1,
            grid_x1 + (col + 1) * cell_w,
            grid_y1 + (row + 1) * cell_h - 1,
        )
        draw_official_entry(draw, rect, entry, dark, red, layout.outlined_text)


def draw_tall_sheet_middle(
    draw: ImageDraw.ImageDraw,
    size: tuple[int, int],
    layout: ScratchLayout,
    entries: list[dict],
    win_numbers: list[str],
    dark: tuple[int, int, int],
    line: tuple[int, int, int],
    red: tuple[int, int, int],
) -> None:
    width, height = size
    margin = max(10, width // 22)
    bonus_h = max(84, int(height * 0.22))
    bonus_count = 4
    bonus_w = max(1, (width - margin * 2) // bonus_count)
    title_font = load_ticket_font(max(7, min(12, width // 38)), bold=True)
    amount_font = load_ticket_font(max(11, min(20, width // 20)), bold=True, role="number")
    bonus_labels = [100, 150, 600, 800]
    for index, amount in enumerate(bonus_labels):
        x1 = margin + index * bonus_w + 4
        x2 = margin + (index + 1) * bonus_w - 4
        box = (x1, margin, x2, margin + bonus_h // 2)
        draw.rounded_rectangle(box, radius=max(5, width // 55), fill=(225, 225, 222), outline=line, width=1)
        draw_text_center_at(draw, ((x1 + x2) // 2, margin + bonus_h // 4), format_print_yuan(amount), amount_font, dark, 1, (248, 248, 244))
        draw_text_center_at(draw, ((x1 + x2) // 2, margin + bonus_h - 18), f"游戏{index + 1}", title_font, dark)

    win_y1 = margin + bonus_h + max(8, height // 80)
    win_h = max(70, int(height * 0.14))
    panel_x1 = margin
    panel_x2 = width - margin
    draw.rounded_rectangle((panel_x1, win_y1, panel_x2, win_y1 + win_h), radius=max(8, width // 45), fill=(218, 218, 216), outline=line, width=1)
    draw.line(((panel_x1 + panel_x2) // 2, win_y1 + 8, (panel_x1 + panel_x2) // 2, win_y1 + win_h - 8), fill=dark, width=2)
    header_font = load_ticket_font(max(8, min(15, width // 30)), bold=True)
    number_font = load_ticket_font(max(17, min(31, width // 13)), bold=True, role="number")
    pinyin_font = load_ticket_font(max(5, min(9, width // 42)), role="pinyin")
    labels = ("中奖号码", "翻倍号码")
    for index, number in enumerate(win_numbers[:2]):
        left = panel_x1 + index * (panel_x2 - panel_x1) // 2
        right = panel_x1 + (index + 1) * (panel_x2 - panel_x1) // 2
        cx = (left + right) // 2
        draw_text_center_at(draw, (cx, win_y1 + 18), labels[index], header_font, dark)
        draw_text_center_at(draw, (cx, win_y1 + win_h // 2 + 6), number, number_font, dark, 1, (248, 248, 244))
        draw_text_center_at(draw, (cx, win_y1 + win_h - 14), number_pinyin_text(number), pinyin_font, dark)

    grid_y1 = win_y1 + win_h + max(18, height // 45)
    grid_y2 = height - margin
    draw_text_center_at(draw, (width // 2, grid_y1 - max(8, height // 90)), "你的号码", header_font, dark)
    cell_w = max(1, (panel_x2 - panel_x1) // layout.cols)
    cell_h = max(1, (grid_y2 - grid_y1) // layout.rows)
    for row in range(1, layout.rows):
        draw_dotted_line(draw, panel_x1, grid_y1 + row * cell_h, panel_x2, line, dot=4, gap=6, width=2)
    for index, entry in enumerate(entries[: layout.cols * layout.rows]):
        row = index // layout.cols
        col = index % layout.cols
        rect = (
            panel_x1 + col * cell_w,
            grid_y1 + row * cell_h + 1,
            panel_x1 + (col + 1) * cell_w,
            grid_y1 + (row + 1) * cell_h - 1,
        )
        draw_official_entry(draw, rect, entry, dark, red, layout.outlined_text)


def draw_number_only_cell(
    draw: ImageDraw.ImageDraw,
    rect: tuple[int, int, int, int],
    number: str,
    dark: tuple[int, int, int],
    outlined: bool,
) -> None:
    x1, y1, x2, y2 = rect
    cell_w = max(1, x2 - x1)
    cell_h = max(1, y2 - y1)
    cx = (x1 + x2) // 2
    number_font = fit_ticket_font(draw, number, int(cell_w * 0.78), max(12, int(cell_h * 0.48)), 7, bold=True, role="number")
    pinyin_font = load_ticket_font(max(5, min(9, cell_h // 5)), role="pinyin")
    stroke_width = 1 if outlined and min(cell_w, cell_h) >= 30 else 0
    stroke_fill = (248, 248, 244) if outlined else dark
    draw_text_center_at(draw, (cx, y1 + int(cell_h * 0.40)), number, number_font, dark, stroke_width, stroke_fill)
    draw_text_center_at(draw, (cx, y1 + int(cell_h * 0.68)), number_pinyin_text(number), pinyin_font, dark)


def draw_amount_only_cell(
    draw: ImageDraw.ImageDraw,
    rect: tuple[int, int, int, int],
    amount: int,
    matched: bool,
    dark: tuple[int, int, int],
    red: tuple[int, int, int],
    outlined: bool,
) -> None:
    x1, y1, x2, y2 = rect
    cell_w = max(1, x2 - x1)
    cell_h = max(1, y2 - y1)
    cx = (x1 + x2) // 2
    amount_text = format_print_yuan(amount)
    amount_font = fit_ticket_font(draw, amount_text, int(cell_w * 0.92), max(11, int(cell_h * 0.36)), 7, bold=True, role="number")
    pinyin_font = fit_ticket_font(draw, amount_pinyin_text(amount), int(cell_w * 0.82), max(5, int(cell_h * 0.14)), 5, role="pinyin")
    stroke_width = 1 if outlined and min(cell_w, cell_h) >= 30 else 0
    stroke_fill = (248, 248, 244) if outlined else dark
    draw_text_center_at(draw, (cx, y1 + int(cell_h * 0.42)), amount_text, amount_font, dark, stroke_width, stroke_fill)
    draw_text_center_at(draw, (cx, y1 + int(cell_h * 0.70)), amount_pinyin_text(amount), pinyin_font, dark)
    if matched:
        inset_x = max(4, cell_w // 9)
        inset_y = max(3, cell_h // 8)
        draw.ellipse((x1 + inset_x, y1 + inset_y, x2 - inset_x, y2 - inset_y), outline=red, width=max(2, min(cell_w, cell_h) // 16))


def draw_prize_amount_grid_middle(
    draw: ImageDraw.ImageDraw,
    size: tuple[int, int],
    entries: list[dict],
    dark: tuple[int, int, int],
    line: tuple[int, int, int],
    red: tuple[int, int, int],
    title: str = "奖金区",
) -> None:
    width, height = size
    margin = max(8, min(width, height) // 22)
    panel = (margin, margin, width - margin, height - margin)
    draw.rounded_rectangle(panel, radius=max(8, min(width, height) // 26), fill=(224, 224, 222), outline=line, width=1)
    title_h = max(24, min(46, height // 8))
    title_font = load_ticket_font(max(10, min(18, title_h // 2)), bold=True)
    draw_text_center_at(draw, (width // 2, margin + title_h // 2), title, title_font, dark)

    count = max(1, len(entries))
    if width >= height * 1.55:
        cols = min(6, count)
    elif width >= height:
        cols = min(4, count)
    else:
        cols = min(3, count)
    rows = max(1, (count + cols - 1) // cols)
    grid_x1 = margin + max(4, width // 80)
    grid_x2 = width - margin - max(4, width // 80)
    grid_y1 = margin + title_h
    grid_y2 = height - margin - max(4, height // 80)
    cell_w = max(1, (grid_x2 - grid_x1) // cols)
    cell_h = max(1, (grid_y2 - grid_y1) // rows)

    for row in range(1, rows):
        draw_dotted_line(draw, grid_x1, grid_y1 + row * cell_h, grid_x2, line, dot=4, gap=6, width=2)
    for col in range(1, cols):
        x = grid_x1 + col * cell_w
        draw.line((x, grid_y1, x, grid_y2), fill=line, width=1)

    for index, entry in enumerate(entries[: cols * rows]):
        row = index // cols
        col = index % cols
        rect = (
            grid_x1 + col * cell_w,
            grid_y1 + row * cell_h + 1,
            grid_x1 + (col + 1) * cell_w,
            grid_y1 + (row + 1) * cell_h - 1,
        )
        draw_amount_only_cell(draw, rect, int(entry["amount"]), bool(entry.get("matched")), dark, red, True)


def draw_mixed_prize_match_middle(
    draw: ImageDraw.ImageDraw,
    size: tuple[int, int],
    layout: ScratchLayout,
    bonus_entries: list[dict],
    entries: list[dict],
    win_numbers: list[str],
    symbol_specs: list[dict],
    dark: tuple[int, int, int],
    line: tuple[int, int, int],
    red: tuple[int, int, int],
) -> None:
    width, height = size
    margin = max(8, min(width, height) // 24)
    panel = (margin, margin, width - margin, height - margin)
    draw.rounded_rectangle(panel, radius=max(8, min(width, height) // 28), fill=(224, 224, 222), outline=line, width=1)

    bonus_h = max(62, min(int(height * 0.28), 112))
    bonus_count = max(1, min(len(bonus_entries), 4 if width >= height else 3))
    title_font = load_ticket_font(max(8, min(15, height // 24)), bold=True)
    small_font = load_ticket_font(max(6, min(10, height // 34)), bold=True)
    draw_text_center_at(draw, (width // 2, margin + 14), "奖金玩法", title_font, dark)
    if symbol_specs:
        labels = []
        for spec in symbol_specs[:3]:
            multiplier = int(spec.get("multiplier", 1))
            label = str(spec["symbol"])
            labels.append(f"{label}×{multiplier}" if multiplier > 1 else label)
        draw_text_center_at(draw, (width // 2, margin + 34), "标志：" + " / ".join(labels), small_font, dark)

    bonus_top = margin + max(38, bonus_h // 3)
    bonus_w = max(1, (width - margin * 2) // bonus_count)
    for index, entry in enumerate(bonus_entries[:bonus_count]):
        x1 = margin + index * bonus_w + 3
        x2 = margin + (index + 1) * bonus_w - 3
        draw_amount_only_cell(draw, (x1, bonus_top, x2, margin + bonus_h - 2), int(entry["amount"]), bool(entry.get("matched")), dark, red, True)

    match_y = margin + bonus_h + max(8, height // 52)
    header_h = max(54, min(82, int(height * 0.18)))
    header_font = load_ticket_font(max(8, min(15, height // 24)), bold=True)
    number_font = load_ticket_font(max(14, min(28, height // 12)), bold=True, role="number")
    pinyin_font = load_ticket_font(max(5, min(8, height // 38)), role="pinyin")
    draw_text_center_at(draw, (width // 2, match_y + 12), "中奖号码", header_font, dark)
    for index, number in enumerate(win_numbers):
        cx = margin + (index + 1) * (width - margin * 2) // (len(win_numbers) + 1)
        draw_text_center_at(draw, (cx, match_y + 38), number, number_font, dark, 1, (248, 248, 244))
        draw_text_center_at(draw, (cx, match_y + 59), number_pinyin_text(number), pinyin_font, dark)

    grid_x1 = margin + max(4, width // 90)
    grid_x2 = width - margin - max(4, width // 90)
    grid_y1 = match_y + header_h
    grid_y2 = height - margin - max(4, height // 90)
    cols = max(3, min(layout.cols if layout.cols else 5, 6 if width >= 640 else 5))
    rows = max(1, min(4, (len(entries) + cols - 1) // cols))
    cell_w = max(1, (grid_x2 - grid_x1) // cols)
    cell_h = max(1, (grid_y2 - grid_y1) // rows)
    draw_text_center_at(draw, (width // 2, grid_y1 - 8), "你的号码", header_font, dark)
    for row in range(1, rows):
        draw_dotted_line(draw, grid_x1, grid_y1 + row * cell_h, grid_x2, line, dot=4, gap=6, width=2)
    for col in range(1, cols):
        x = grid_x1 + col * cell_w
        draw.line((x, grid_y1, x, grid_y2), fill=line, width=1)
    for index, entry in enumerate(entries[: cols * rows]):
        row = index // cols
        col = index % cols
        rect = (
            grid_x1 + col * cell_w,
            grid_y1 + row * cell_h + 1,
            grid_x1 + (col + 1) * cell_w,
            grid_y1 + (row + 1) * cell_h - 1,
        )
        draw_official_entry(draw, rect, entry, dark, red, layout.outlined_text)


def draw_horse_token_icon(draw: ImageDraw.ImageDraw, cx: int, cy: int, scale: int, dark: tuple[int, int, int]) -> None:
    radius = max(8, scale // 2)
    width = max(1, radius // 8)
    draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), outline=dark, width=width)
    head_w = max(14, int(radius * 1.05))
    head_h = max(16, int(radius * 1.25))
    top = cy - head_h // 2
    head = [
        (cx - head_w // 4, top + head_h // 4),
        (cx - head_w // 10, top + head_h // 10),
        (cx + head_w // 5, top + head_h // 6),
        (cx + head_w // 3, cy - head_h // 12),
        (cx + head_w // 5, cy + head_h // 3),
        (cx - head_w // 7, cy + head_h // 2),
        (cx - head_w // 3, cy + head_h // 4),
    ]
    draw.line(head, fill=dark, width=max(1, width), joint="curve")
    draw.polygon(
        [(cx - head_w // 9, top + 2), (cx - head_w // 12, top - head_h // 7), (cx + head_w // 12, top + head_h // 9)],
        outline=dark,
    )
    draw.polygon(
        [(cx + head_w // 9, top + 4), (cx + head_w // 5, top - head_h // 8), (cx + head_w // 4, top + head_h // 6)],
        outline=dark,
    )
    for offset in range(4):
        y = top + head_h // 5 + offset * max(2, head_h // 10)
        draw.arc((cx - head_w // 2, y - 3, cx - head_w // 7, y + max(5, head_h // 6)), 120, 240, fill=dark, width=max(1, width - 1))
    eye_r = max(1, radius // 8)
    draw.ellipse((cx + head_w // 9 - eye_r, cy - head_h // 9 - eye_r, cx + head_w // 9 + eye_r, cy - head_h // 9 + eye_r), fill=dark)


def draw_star_token_icon(draw: ImageDraw.ImageDraw, cx: int, cy: int, radius: int, dark: tuple[int, int, int]) -> None:
    points = []
    for index in range(10):
        angle = -90 + index * 36
        r = radius if index % 2 == 0 else max(3, radius // 2)
        points.append((cx + int(r * math.cos(math.radians(angle))), cy + int(r * math.sin(math.radians(angle)))))
    draw.polygon(points, outline=dark)


def draw_fish_token_icon(draw: ImageDraw.ImageDraw, cx: int, cy: int, radius: int, dark: tuple[int, int, int]) -> None:
    body = (cx - radius, cy - radius // 2, cx + radius // 2, cy + radius // 2)
    draw.ellipse(body, outline=dark, width=max(1, radius // 7))
    draw.polygon([(cx + radius // 2, cy), (cx + radius, cy - radius // 2), (cx + radius, cy + radius // 2)], outline=dark)
    eye_r = max(1, radius // 9)
    draw.ellipse((cx - radius // 2 - eye_r, cy - eye_r, cx - radius // 2 + eye_r, cy + eye_r), fill=dark)


def draw_symbol_token(
    draw: ImageDraw.ImageDraw,
    rect: tuple[int, int, int, int],
    symbol: str,
    dark: tuple[int, int, int],
) -> None:
    x1, y1, x2, y2 = rect
    cell_w = max(1, x2 - x1)
    cell_h = max(1, y2 - y1)
    cx = (x1 + x2) // 2
    cy = y1 + int(cell_h * 0.42)
    pinyin_font = load_ticket_font(max(5, min(9, cell_h // 5)), role="pinyin")
    symbol_pinyin = {
        "马": "MA",
        "龙": "LONG",
        "蛇": "SHE",
        "运": "YUN",
        "康": "KANG",
        "幸运星": "XINGYUNXING",
        "锦鲤": "JINLI",
    }
    if symbol in symbol_pinyin:
        radius = max(9, min(cell_w, cell_h) // 4)
        if symbol == "马":
            draw_horse_token_icon(draw, cx, cy, radius * 2, dark)
        elif symbol == "幸运星":
            draw_star_token_icon(draw, cx, cy, radius, dark)
        elif symbol == "锦鲤":
            draw_fish_token_icon(draw, cx, cy, radius, dark)
        else:
            draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), outline=dark, width=max(2, radius // 5))
            icon_font = fit_ticket_font(draw, symbol, radius * 2 - 6, max(12, radius), 8, bold=True)
            draw_text_center_at(draw, (cx, cy), symbol, icon_font, dark)
        draw_text_center_at(draw, (cx, y1 + int(cell_h * 0.75)), symbol_pinyin[symbol], pinyin_font, dark)
        return
    if symbol == "灯笼":
        icon_w = max(16, int(cell_w * 0.34))
        icon_h = max(16, int(cell_h * 0.34))
        lamp = (cx - icon_w // 2, cy - icon_h // 2, cx + icon_w // 2, cy + icon_h // 2)
        draw.ellipse(lamp, outline=dark, width=max(2, min(icon_w, icon_h) // 8))
        draw.line((cx, lamp[1] - 4, cx, lamp[1] + 3), fill=dark, width=2)
        draw.line((cx, lamp[3] - 3, cx, lamp[3] + 5), fill=dark, width=2)
        draw.line((lamp[0] + icon_w // 3, lamp[1] + 3, lamp[0] + icon_w // 3, lamp[3] - 3), fill=dark, width=1)
        draw.line((lamp[2] - icon_w // 3, lamp[1] + 3, lamp[2] - icon_w // 3, lamp[3] - 3), fill=dark, width=1)
        draw_text_center_at(draw, (cx, y1 + int(cell_h * 0.75)), "DENGLONG", pinyin_font, dark)
        return

    if not re.fullmatch(r"\d+", symbol):
        label = symbol[:4]
        radius = max(9, min(cell_w, cell_h) // 4)
        draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), outline=dark, width=max(1, radius // 6))
        icon_font = fit_ticket_font(draw, label, radius * 2 - 4, max(10, radius), 7, bold=True)
        draw_text_center_at(draw, (cx, cy), label, icon_font, dark)
        return

    number_font = fit_ticket_font(draw, symbol, int(cell_w * 0.78), max(12, int(cell_h * 0.46)), 7, bold=True, role="number")
    draw_text_center_at(draw, (cx, cy), symbol, number_font, dark, 1, (248, 248, 244))
    draw_text_center_at(draw, (cx, y1 + int(cell_h * 0.75)), number_pinyin_text(symbol), pinyin_font, dark)


def draw_symbol_prize_entry(
    draw: ImageDraw.ImageDraw,
    rect: tuple[int, int, int, int],
    entry: dict,
    dark: tuple[int, int, int],
    red: tuple[int, int, int],
) -> None:
    x1, y1, x2, y2 = rect
    cell_w = max(1, x2 - x1)
    cell_h = max(1, y2 - y1)
    symbol_rect = (x1, y1 + 1, x2, y1 + int(cell_h * 0.58))
    amount = int(entry["amount"])
    amount_text = format_print_yuan(amount)
    amount_font = fit_ticket_font(draw, amount_text, int(cell_w * 0.88), max(9, int(cell_h * 0.21)), 6, bold=True, role="number")
    pinyin_font = fit_ticket_font(draw, amount_pinyin_text(amount), int(cell_w * 0.84), max(5, int(cell_h * 0.10)), 5, role="pinyin")
    cx = (x1 + x2) // 2

    draw_symbol_token(draw, symbol_rect, str(entry["symbol"]), dark)
    draw_text_center_at(draw, (cx, y1 + int(cell_h * 0.68)), amount_text, amount_font, dark, 0, (248, 248, 244))
    draw_text_center_at(draw, (cx, y1 + int(cell_h * 0.84)), amount_pinyin_text(amount), pinyin_font, dark)
    multiplier = int(entry.get("multiplier", 1))
    if multiplier > 1:
        badge_font = load_ticket_font(max(6, min(11, cell_h // 6)), bold=True)
        draw_text_center_at(draw, (x2 - max(12, cell_w // 6), y1 + max(10, cell_h // 6)), f"{multiplier}倍", badge_font, red)
    if entry.get("matched"):
        inset_x = max(3, cell_w // 10)
        inset_y = max(3, cell_h // 9)
        draw.ellipse((x1 + inset_x, y1 + inset_y, x2 - inset_x, y2 - inset_y), outline=red, width=max(2, min(cell_w, cell_h) // 16))


def draw_symbol_prize_grid_middle(
    draw: ImageDraw.ImageDraw,
    size: tuple[int, int],
    layout: ScratchLayout,
    entries: list[dict],
    dark: tuple[int, int, int],
    line: tuple[int, int, int],
    red: tuple[int, int, int],
) -> None:
    width, height = size
    margin = max(8, min(width, height) // 24)
    cols = max(1, layout.cols)
    rows = max(1, layout.rows)
    if layout.kind == "vertical-list":
        cols = 1
        rows = max(1, min(layout.rows, len(entries)))
    grid_x1 = margin
    grid_y1 = margin
    grid_x2 = width - margin
    grid_y2 = height - margin
    cell_w = max(1, (grid_x2 - grid_x1) // cols)
    cell_h = max(1, (grid_y2 - grid_y1) // rows)

    for row in range(1, rows):
        draw_dotted_line(draw, grid_x1, grid_y1 + row * cell_h, grid_x2, line, dot=4, gap=6, width=2)
    for col in range(1, cols):
        x = grid_x1 + col * cell_w
        draw.line((x, grid_y1, x, grid_y2), fill=line, width=1)

    for index, entry in enumerate(entries[: cols * rows]):
        row = index // cols
        col = index % cols
        rect = (
            grid_x1 + col * cell_w,
            grid_y1 + row * cell_h + 1,
            grid_x1 + (col + 1) * cell_w,
            grid_y1 + (row + 1) * cell_h - 1,
        )
        draw_symbol_prize_entry(draw, rect, entry, dark, red)


def draw_scene_prize_amount(
    draw: ImageDraw.ImageDraw,
    rect: tuple[int, int, int, int],
    amount: int,
    matched: bool,
    dark: tuple[int, int, int],
    red: tuple[int, int, int],
) -> None:
    x1, y1, x2, y2 = rect
    cell_w = max(1, x2 - x1)
    cell_h = max(1, y2 - y1)
    amount_text = format_print_yuan(amount)
    amount_font = fit_ticket_font(draw, amount_text, int(cell_w * 0.90), max(11, int(cell_h * 0.34)), 7, bold=True, role="number")
    pinyin_font = fit_ticket_font(draw, amount_pinyin_text(amount), int(cell_w * 0.88), max(5, int(cell_h * 0.14)), 5, role="pinyin")
    cx = (x1 + x2) // 2
    draw_text_center_at(draw, (cx, y1 + int(cell_h * 0.42)), amount_text, amount_font, dark, 0, (248, 248, 244))
    draw_text_center_at(draw, (cx, y1 + int(cell_h * 0.74)), amount_pinyin_text(amount), pinyin_font, dark)
    if matched:
        inset_x = max(4, cell_w // 12)
        inset_y = max(3, cell_h // 8)
        draw.ellipse((x1 + inset_x, y1 + inset_y, x2 - inset_x, y2 - inset_y), outline=red, width=max(2, min(cell_w, cell_h) // 14))


def draw_paired_symbol_prize_middle(
    draw: ImageDraw.ImageDraw,
    size: tuple[int, int],
    scenes: list[dict],
    dark: tuple[int, int, int],
    line: tuple[int, int, int],
    red: tuple[int, int, int],
) -> None:
    width, height = size
    margin = max(8, min(width, height) // 22)
    panel = (margin, margin, width - margin, height - margin)
    draw.rounded_rectangle(panel, radius=max(8, min(width, height) // 24), fill=(222, 222, 220), outline=(232, 148, 74), width=max(1, min(width, height) // 120))

    inner_x1 = panel[0] + max(8, width // 50)
    inner_y1 = panel[1] + max(6, height // 50)
    inner_x2 = panel[2] - max(8, width // 50)
    inner_y2 = panel[3] - max(6, height // 50)
    visible_count = min(len(scenes), 12)
    cols = 1 if width < 360 else 2
    rows = max(1, (visible_count + cols - 1) // cols)
    col_w = max(1, (inner_x2 - inner_x1) // cols)
    row_h = max(1, (inner_y2 - inner_y1) // rows)
    label_w = max(30 if cols == 1 else 22, int(col_w * (0.16 if cols == 1 else 0.13)))
    amount_w = max(70 if cols == 1 else 78, int(col_w * (0.34 if cols == 1 else 0.36)))
    label_font = load_ticket_font(max(7, min(13, row_h // 4)), bold=True)
    number_font = load_ticket_font(max(8, min(15, row_h // 3)), bold=True, role="number")

    for col in range(1, cols):
        x = inner_x1 + col * col_w
        draw.line((x, inner_y1, x, inner_y2), fill=line, width=2)
    for row in range(1, rows):
        y = inner_y1 + row * row_h
        draw_dotted_line(draw, inner_x1, y, inner_x2, line, dot=4, gap=6, width=2)

    for index, scene in enumerate(scenes[:visible_count]):
        col = index // rows
        row = index % rows
        x1 = inner_x1 + col * col_w
        x2 = x1 + col_w
        y1 = inner_y1 + row * row_h
        y2 = inner_y1 + (row + 1) * row_h
        label_x = x1 + label_w // 2
        label_center_y = (y1 + y2) // 2
        draw_text_center_at(draw, (label_x, label_center_y - row_h // 6), "第", label_font, dark)
        draw_text_center_at(draw, (label_x, label_center_y), str(scene["scene"]), number_font, dark)
        draw_text_center_at(draw, (label_x, label_center_y + row_h // 6), "场", label_font, dark)

        symbols_x1 = x1 + label_w
        symbols_x2 = x2 - amount_w
        symbol_w = max(1, (symbols_x2 - symbols_x1) // 3)
        for symbol_index, symbol in enumerate(scene["symbols"]):
            rect = (
                symbols_x1 + symbol_index * symbol_w,
                y1 + 1,
                symbols_x1 + (symbol_index + 1) * symbol_w,
                y2 - 1,
            )
            draw_symbol_token(draw, rect, str(symbol), dark)
        amount_rect = (x2 - amount_w, y1 + 1, x2, y2 - 1)
        draw_scene_prize_amount(draw, amount_rect, int(scene["amount"]), bool(scene.get("matched")), dark, red)


def draw_clean_paired_symbol_cover(size: tuple[int, int], ticket: dict, reference: Image.Image | None = None) -> Image.Image:
    width, height = size
    bg = average_image_color(reference, (220, 68, 24))
    cover = Image.new("RGBA", size, (*bg, 255))
    draw = ImageDraw.Draw(cover)
    dark = clamp_color(tuple(max(28, channel - 90) for channel in bg), 28, 150)
    light = tuple(min(255, channel + 118) for channel in bg)
    gold = (252, 210, 84)
    symbol = paired_symbol_prize_symbol(ticket)

    margin = max(8, min(width, height) // 28)
    panel = (margin, margin, width - margin, height - margin)
    draw.rounded_rectangle(panel, radius=max(8, min(width, height) // 24), outline=gold, width=max(1, min(width, height) // 90))
    cols = 2 if width >= 360 else 1
    rows = 6 if cols == 2 else 12
    col_w = max(1, (panel[2] - panel[0]) // cols)
    row_h = max(1, (panel[3] - panel[1]) // rows)
    label_font = load_ticket_font(max(6, min(12, row_h // 3)), bold=True)
    prize_font = load_ticket_font(max(12, min(28, row_h // 2)), bold=True)

    for index in range(12):
        col = index // rows
        row = index % rows
        x1 = panel[0] + col * col_w
        x2 = panel[0] + (col + 1) * col_w
        y1 = panel[1] + row * row_h
        y2 = panel[1] + (row + 1) * row_h
        label_x = x1 + max(12, col_w // 12)
        draw_text_center_at(draw, (label_x, (y1 + y2) // 2), f"第{index + 1}场", label_font, light)
        icon_area_x1 = x1 + max(28, col_w // 7)
        icon_area_x2 = x2 - max(54, col_w // 5)
        icon_w = max(1, (icon_area_x2 - icon_area_x1) // 3)
        for icon_index in range(3):
            rect = (
                icon_area_x1 + icon_index * icon_w,
                y1 + max(3, row_h // 12),
                icon_area_x1 + (icon_index + 1) * icon_w,
                y2 - max(3, row_h // 12),
            )
            token = symbol if (index + icon_index) % 2 == 0 else "祥云"
            if token == "祥云":
                cx = (rect[0] + rect[2]) // 2
                cy = (rect[1] + rect[3]) // 2
                radius = max(5, min(rect[2] - rect[0], rect[3] - rect[1]) // 5)
                draw.arc((cx - radius * 2, cy - radius, cx, cy + radius), 180, 360, fill=dark, width=max(1, radius // 3))
                draw.arc((cx - radius, cy - radius, cx + radius, cy + radius), 180, 360, fill=dark, width=max(1, radius // 3))
                draw.arc((cx, cy - radius, cx + radius * 2, cy + radius), 180, 360, fill=dark, width=max(1, radius // 3))
            else:
                draw_symbol_token(draw, rect, token, light)
        draw_text_center_at(draw, (x2 - max(26, col_w // 8), (y1 + y2) // 2), "奖金", prize_font, light if index % 2 == 0 else dark)
    return cover


def draw_clean_wide_symbol_cover(size: tuple[int, int], ticket: dict, reference: Image.Image | None = None) -> Image.Image:
    width, height = size
    bg = average_image_color(reference, (205, 16, 22))
    cover = Image.new("RGBA", size, (*bg, 255))
    draw = ImageDraw.Draw(cover)
    gold = (252, 214, 80)
    light = (255, 238, 160)
    dark = clamp_color(tuple(max(28, channel - 95) for channel in bg), 28, 145)
    margin = max(10, min(width, height) // 26)
    split_x = max(int(width * 0.34), margin + 120)
    left_panel = (margin, margin, split_x - margin, height - margin)
    right_panel = (split_x + margin, margin, width - margin, height - margin)
    for panel in (left_panel, right_panel):
        draw.rounded_rectangle(panel, radius=max(8, min(width, height) // 32), outline=gold, width=max(1, min(width, height) // 100))

    left_cols, left_rows = 3, 4
    token_font = load_ticket_font(max(8, min(18, height // 18)), bold=True)
    cell_w = max(1, (left_panel[2] - left_panel[0] - 18) // left_cols)
    cell_h = max(1, (left_panel[3] - left_panel[1] - 18) // left_rows)
    for row in range(left_rows):
        for col in range(left_cols):
            cx = left_panel[0] + 9 + col * cell_w + cell_w // 2
            cy = left_panel[1] + 9 + row * cell_h + cell_h // 2
            radius = max(10, min(cell_w, cell_h) // 4)
            draw.rounded_rectangle((cx - radius, cy - radius, cx + radius, cy + radius), radius=max(4, radius // 3), outline=gold, width=max(1, radius // 6))
            draw_text_center_at(draw, (cx, cy), "吉", token_font, gold)

    title_font = load_ticket_font(max(7, min(13, height // 26)), bold=True)
    draw_text_center_at(draw, ((right_panel[0] + right_panel[2]) // 2, right_panel[1] + max(15, height // 18)), "中奖号码", title_font, light)
    symbol = paired_symbol_prize_symbol(ticket) if "马" in ticket_rule(ticket) else "马"
    top_y = right_panel[1] + max(28, height // 10)
    for index in range(2):
        rect = (
            right_panel[0] + (index + 1) * (right_panel[2] - right_panel[0]) // 3 - max(18, width // 48),
            top_y,
            right_panel[0] + (index + 1) * (right_panel[2] - right_panel[0]) // 3 + max(18, width // 48),
            top_y + max(30, height // 7),
        )
        draw_symbol_token(draw, rect, symbol, light)

    draw_text_center_at(draw, ((right_panel[0] + right_panel[2]) // 2, top_y + max(42, height // 6)), "你的号码", title_font, light)
    grid_top = top_y + max(58, height // 5)
    grid_bottom = right_panel[3] - max(8, height // 50)
    cols, rows = 6, 4
    cell_w = max(1, (right_panel[2] - right_panel[0] - 20) // cols)
    cell_h = max(1, (grid_bottom - grid_top) // rows)
    for row in range(rows):
        for col in range(cols):
            rect = (
                right_panel[0] + 10 + col * cell_w,
                grid_top + row * cell_h,
                right_panel[0] + 10 + (col + 1) * cell_w,
                grid_top + (row + 1) * cell_h,
            )
            draw_symbol_token(draw, rect, symbol, light)
    for y in range(0, height, max(48, height // 5)):
        draw.arc((width - y // 2, y - 40, width + 70, y + 70), 90, 220, fill=gold, width=2)
    return cover


def draw_qiang_tou_cai_clean_cover(size: tuple[int, int], ticket: dict, reference: Image.Image | None = None) -> Image.Image:
    width, height = size
    bg = average_image_color(reference, (202, 18, 28))
    red = clamp_color(bg, 120, 225)
    cover = Image.new("RGBA", size, (*red, 255))
    draw = ImageDraw.Draw(cover)
    gold = (248, 205, 72)
    dark_gold = (181, 112, 24)
    light = (255, 234, 150)
    margin = max(8, min(width, height) // 24)
    panel = (margin, margin + max(8, height // 16), width - margin, height - margin)
    draw.rounded_rectangle(panel, radius=max(8, width // 28), outline=gold, width=max(1, width // 95))
    draw.rounded_rectangle(
        (panel[0] + max(4, width // 70), panel[1] + max(4, height // 70), panel[2] - max(4, width // 70), panel[3] - max(4, height // 70)),
        radius=max(7, width // 34),
        outline=(182, 34, 30),
        width=max(1, width // 120),
    )

    rose_count = 5
    rose_y = margin + max(7, height // 24)
    for index in range(rose_count):
        cx = margin + (index + 1) * (width - margin * 2) // (rose_count + 1)
        radius = max(9, min(width, height) // 20)
        for petal in range(8):
            angle = math.radians(petal * 45)
            px = cx + int(math.cos(angle) * radius * 0.38)
            py = rose_y + int(math.sin(angle) * radius * 0.38)
            draw.ellipse((px - radius // 3, py - radius // 3, px + radius // 3, py + radius // 3), outline=dark_gold, width=max(1, radius // 8))
        draw.ellipse((cx - radius, rose_y - radius, cx + radius, rose_y + radius), outline=gold, width=max(1, radius // 7))

    label_font = load_ticket_font(max(6, min(11, width // 30)), bold=True)
    title_font = load_ticket_font(max(7, min(13, width // 25)), bold=True)
    draw_text_center_at(draw, (width // 2, panel[1] + max(18, height // 14)), "中奖号码", label_font, light)
    ingot_y = panel[1] + max(34, height // 9)
    for cx in (width // 2 - max(28, width // 9), width // 2 + max(28, width // 9)):
        draw.ellipse((cx - max(10, width // 28), ingot_y - max(5, height // 60), cx + max(10, width // 28), ingot_y + max(5, height // 60)), outline=gold, width=max(1, width // 115))
        draw.arc((cx - max(9, width // 34), ingot_y - max(8, height // 50), cx + max(9, width // 34), ingot_y + max(8, height // 50)), 25, 155, fill=gold, width=max(1, width // 120))
    draw_text_center_at(draw, (width // 2, panel[1] + max(58, height // 6)), "你的号码", label_font, light)
    prize_font = load_ticket_font(max(10, min(18, width // 18)), bold=True)
    draw_text_center_at(draw, (width - margin - max(42, width // 7), panel[1] + max(38, height // 8)), "最高奖金\n100万元", title_font, light)

    grid_top = panel[1] + max(76, height // 4)
    grid_bottom = panel[3] - max(10, height // 40)
    cols, rows = 5, 5
    cell_w = max(1, (panel[2] - panel[0] - max(18, width // 14)) // cols)
    cell_h = max(1, (grid_bottom - grid_top) // rows)
    for row in range(rows):
        for col in range(cols):
            cx = panel[0] + max(10, width // 28) + col * cell_w + cell_w // 2
            cy = grid_top + row * cell_h + cell_h // 2
            icon_w = max(13, min(cell_w, cell_h) // 3)
            draw.rounded_rectangle(
                (cx - icon_w // 2, cy - icon_w // 2, cx + icon_w // 2, cy + icon_w // 2),
                radius=max(2, icon_w // 5),
                outline=gold,
                width=max(1, icon_w // 8),
            )
            draw.line((cx - icon_w // 3, cy - icon_w // 6, cx + icon_w // 3, cy - icon_w // 6), fill=gold, width=max(1, icon_w // 10))

    for offset in range(-height // 2, height, max(46, height // 5)):
        draw.arc((width - max(70, width // 3), offset, width + max(55, width // 4), offset + max(70, height // 4)), 110, 235, fill=(235, 151, 45), width=max(1, width // 130))
    draw_text_center_at(draw, (margin + max(28, width // 8), height - margin - max(12, height // 24)), "刮开区", prize_font, gold)
    return cover


def draw_jie_hao_yun_clean_cover(size: tuple[int, int], ticket: dict, reference: Image.Image | None = None) -> Image.Image:
    width, height = size
    bg = average_image_color(reference, (221, 138, 22))
    cover = Image.new("RGBA", size, (*bg, 255))
    draw = ImageDraw.Draw(cover)
    gold = (248, 210, 92)
    purple = (160, 34, 144)
    dark = (80, 48, 28)
    margin = max(8, min(width, height) // 24)
    top_h = max(42, min(64, height // 7))
    draw.rounded_rectangle((margin, margin, width - margin, margin + top_h), radius=max(6, width // 35), outline=gold, width=1)
    amount_font = load_ticket_font(max(14, min(28, width // 8)), bold=True)
    for index in range(5):
        cx = margin + (index + 1) * (width - margin * 2) // 6
        draw_text_center_at(draw, (cx, margin + top_h // 2), "￥", amount_font, gold, 1, dark)
    main_top = margin + top_h + max(16, height // 38)
    draw.rounded_rectangle((margin, main_top, width - margin, height - margin), radius=max(6, width // 35), outline=gold, width=1)
    label_font = load_ticket_font(max(5, min(9, width // 34)), bold=True)
    draw_text_center_at(draw, (width // 2, main_top + max(14, height // 28)), "中奖号码", label_font, gold)
    for index in range(3):
        cx = margin + (index + 1) * (width - margin * 2) // 5
        cy = main_top + max(38, height // 9)
        draw_clover(draw, cx, cy, max(8, width // 18), gold, dark)
    draw_text_center_at(draw, (width - margin - max(38, width // 7), main_top + max(38, height // 9)), "全中", amount_font, (35, 118, 230), 1, (255, 255, 255))
    draw_text_center_at(draw, (width // 2, main_top + max(66, height // 6)), "你的号码", label_font, gold)
    grid_top = main_top + max(82, height // 5)
    grid_bottom = height - margin - max(6, height // 60)
    cols, rows = 5, 7
    cell_w = max(1, (width - margin * 2) // cols)
    cell_h = max(1, (grid_bottom - grid_top) // rows)
    for row in range(rows):
        for col in range(cols):
            cx = margin + col * cell_w + cell_w // 2
            cy = grid_top + row * cell_h + cell_h // 2
            draw_diamond_icon(draw, cx, cy, max(8, min(cell_w, cell_h) // 3), purple, dark)
    return cover


def draw_clover(draw: ImageDraw.ImageDraw, cx: int, cy: int, radius: int, fill: tuple[int, int, int], outline: tuple[int, int, int]) -> None:
    for dx, dy in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
        draw.ellipse((cx + dx * radius // 3 - radius // 2, cy + dy * radius // 3 - radius // 2, cx + dx * radius // 3 + radius // 2, cy + dy * radius // 3 + radius // 2), fill=fill, outline=outline, width=max(1, radius // 7))
    draw.line((cx, cy + radius // 2, cx + radius // 2, cy + radius), fill=outline, width=max(1, radius // 7))


def draw_diamond_icon(draw: ImageDraw.ImageDraw, cx: int, cy: int, radius: int, fill: tuple[int, int, int], outline: tuple[int, int, int]) -> None:
    points = [(cx, cy - radius), (cx + radius, cy - radius // 4), (cx + radius * 2 // 3, cy + radius), (cx - radius * 2 // 3, cy + radius), (cx - radius, cy - radius // 4)]
    draw.polygon(points, fill=fill, outline=outline)
    draw.line((cx - radius, cy - radius // 4, cx + radius, cy - radius // 4), fill=outline, width=max(1, radius // 8))
    draw.line((cx, cy - radius, cx, cy + radius), fill=outline, width=max(1, radius // 9))


def rect_is_full(rect: tuple[int, int, int, int], size: tuple[int, int]) -> bool:
    return rect[0] <= 0 and rect[1] <= 0 and rect[2] >= size[0] and rect[3] >= size[1]


def clip_image_to_rect(image: Image.Image, rect: tuple[int, int, int, int]) -> Image.Image:
    result = Image.new("RGBA", image.size, (255, 255, 255, 0))
    x, y, width, height = rect
    result.alpha_composite(image.crop((x, y, x + width, y + height)), (x, y))
    return result


def compose_clean_middle_layers(
    ticket: dict,
    layout: ScratchLayout,
    generated_middle: Image.Image,
    covered_reference: Image.Image,
    scratch_area: tuple[int, int, int, int],
) -> tuple[Image.Image, Image.Image]:
    size = covered_reference.size
    if rect_is_full(scratch_area, size):
        base = generated_middle.convert("RGBA")
    else:
        base = soften_cover_sample_marks(covered_reference)
        x, y, width, height = scratch_area
        base.alpha_composite(generated_middle.crop((x, y, x + width, y + height)), (x, y))

    x, y, width, height = scratch_area
    cover = Image.new("RGBA", size, (255, 255, 255, 0))
    scratch_reference = covered_reference.crop((x, y, x + width, y + height))
    cover.alpha_composite(draw_ticket_clean_cover((width, height), ticket, layout, scratch_reference), (x, y))
    return base, cover


def draw_ticket_clean_cover(size: tuple[int, int], ticket: dict, layout: ScratchLayout, reference: Image.Image | None = None) -> Image.Image:
    ticket_id = int(ticket.get("id", 0) or 0)
    if ticket_id == 210 or "抢头彩" in str(ticket.get("name") or ""):
        return draw_qiang_tou_cai_clean_cover(size, ticket, reference)
    if is_jie_hao_yun_ticket(ticket):
        return draw_jie_hao_yun_clean_cover(size, ticket, reference)
    if layout.kind == "paired-symbol-prize":
        return draw_clean_paired_symbol_cover(size, ticket, reference)
    if layout.kind == "wide-symbol-grid":
        return draw_clean_wide_symbol_cover(size, ticket, reference)
    return draw_generated_cover(size, None)


def draw_vertical_list_middle(
    draw: ImageDraw.ImageDraw,
    size: tuple[int, int],
    layout: ScratchLayout,
    entries: list[dict],
    win_numbers: list[str],
    dark: tuple[int, int, int],
    line: tuple[int, int, int],
    red: tuple[int, int, int],
) -> None:
    width, height = size
    margin = max(8, width // 18)
    header_h = max(82, int(height * 0.16))
    header_font = load_ticket_font(max(10, min(18, width // 10)), bold=True)
    number_font = load_ticket_font(max(15, min(29, width // 7)), bold=True, role="number")
    pinyin_font = load_ticket_font(max(5, min(9, width // 28)), role="pinyin")
    draw_text_center_at(draw, (width // 2, margin + 12), "中奖号码", header_font, dark)
    for index, number in enumerate(win_numbers):
        cx = margin + (index + 1) * (width - margin * 2) // (len(win_numbers) + 1)
        draw_text_center_at(draw, (cx, margin + 43), number, number_font, dark, 1, (248, 248, 244))
        draw_text_center_at(draw, (cx, margin + 64), number_pinyin_text(number), pinyin_font, dark)

    grid_x1 = margin
    grid_x2 = width - margin
    grid_y1 = header_h
    grid_y2 = height - margin
    row_h = max(1, (grid_y2 - grid_y1) // layout.rows)
    label_font = load_ticket_font(max(6, min(10, width // 24)), bold=True)
    draw_text_center_at(draw, (grid_x1 + (grid_x2 - grid_x1) // 4, grid_y1 - 8), "你的号码", label_font, dark)
    draw_text_center_at(draw, (grid_x1 + (grid_x2 - grid_x1) * 3 // 4, grid_y1 - 8), "奖金", label_font, dark)
    for row in range(layout.rows + 1):
        draw_dotted_line(draw, grid_x1, grid_y1 + row * row_h, grid_x2, line, dot=4, gap=6, width=2)
    for index, entry in enumerate(entries[: layout.rows]):
        y1 = grid_y1 + index * row_h + 1
        y2 = grid_y1 + (index + 1) * row_h - 1
        left_rect = (grid_x1, y1, grid_x1 + (grid_x2 - grid_x1) // 2, y2)
        right_rect = (grid_x1 + (grid_x2 - grid_x1) // 2, y1, grid_x2, y2)
        draw_number_only_cell(draw, left_rect, str(entry["number"]), dark, layout.outlined_text)
        draw_amount_only_cell(draw, right_rect, int(entry["amount"]), bool(entry.get("matched")), dark, red, layout.outlined_text)


def is_jie_hao_yun_ticket(ticket: dict) -> bool:
    return str(ticket.get("name") or "") == "接好运" and "全中" in ticket_rule(ticket)


def jie_hao_yun_play_count(ticket: dict) -> int:
    rule = ticket_rule(ticket)
    match = re.search(r"所示的\s*(\d+)\s*个奖金", rule)
    if match:
        return max(1, int(match.group(1)))
    chance = int(ticket.get("chance", 0) or 0)
    return max(12, chance - (5 if has_prize_amount_game(ticket) else 0))


def jie_hao_yun_all_symbol(ticket: dict) -> str:
    rule = ticket_rule(ticket)
    match = re.search(r"全中[^。；\n]*?出现\s*([^“”\"，。；\n]{1,3})标志", rule)
    if match:
        return normalize_symbol_label(match.group(1))
    quoted = re.findall(r"全中[^。；\n]*?[“\"]([^”\"]{1,3})[”\"]", rule)
    return normalize_symbol_label(quoted[-1]) if quoted else "运"


def draw_jie_hao_yun_middle(
    draw: ImageDraw.ImageDraw,
    size: tuple[int, int],
    ticket: dict,
    bonus_entries: list[dict],
    entries: list[dict],
    win_numbers: list[str],
    dark: tuple[int, int, int],
    line: tuple[int, int, int],
    red: tuple[int, int, int],
    reference: Image.Image | None = None,
) -> None:
    width, height = size
    edge = average_border_color(reference, (221, 137, 19))
    panel_fill = (224, 224, 222)
    border = tuple(max(80, min(236, channel + 52)) for channel in edge)
    draw.rectangle((0, 0, width, height), fill=edge)

    margin_x = max(10, width // 20)
    top_y = max(6, height // 80)
    has_bonus = bool(bonus_entries) and has_prize_amount_game(ticket)
    if has_bonus:
        bonus_h = max(38, min(58, int(height * 0.12)))
        bonus_panel = (margin_x, top_y, width - margin_x, top_y + bonus_h)
        draw.rounded_rectangle(bonus_panel, radius=max(5, width // 38), fill=panel_fill, outline=border, width=1)
        cols = min(5, max(1, len(bonus_entries)))
        cell_w = max(1, (bonus_panel[2] - bonus_panel[0] - 8) // cols)
        for index, entry in enumerate(bonus_entries[:cols]):
            rect = (
                bonus_panel[0] + 4 + index * cell_w,
                bonus_panel[1] + 5,
                bonus_panel[0] + 4 + (index + 1) * cell_w,
                bonus_panel[3] - 4,
            )
            draw_amount_only_cell(draw, rect, int(entry["amount"]), bool(entry.get("matched")), dark, red, False)
        main_y1 = bonus_panel[3] + max(16, height // 34)
    else:
        main_y1 = top_y

    main_y2 = height - max(6, height // 90)
    main_panel = (margin_x, main_y1, width - margin_x, main_y2)
    draw.rounded_rectangle(main_panel, radius=max(5, width // 34), fill=panel_fill, outline=border, width=1)

    inner_x1 = main_panel[0] + max(10, width // 28)
    inner_x2 = main_panel[2] - max(10, width // 28)
    inner_y1 = main_panel[1] + max(8, height // 70)
    inner_y2 = main_panel[3] - max(8, height // 75)
    header_h = max(50, min(76, int((inner_y2 - inner_y1) * 0.16)))
    all_w = max(56, int((inner_x2 - inner_x1) * 0.28))
    split_x = inner_x2 - all_w

    title_font = load_ticket_font(max(7, min(12, width // 26)), bold=True)
    number_font = load_ticket_font(max(12, min(21, width // 13)), bold=True, role="number")
    pinyin_font = load_ticket_font(max(5, min(8, width // 36)), role="pinyin")
    draw_text_center_at(draw, ((inner_x1 + split_x) // 2, inner_y1 + max(8, header_h // 5)), "中奖号码", title_font, dark)
    for index, number in enumerate(win_numbers[:3]):
        cx = inner_x1 + (index + 1) * (split_x - inner_x1) // 4
        draw_text_center_at(draw, (cx, inner_y1 + int(header_h * 0.58)), number, number_font, dark, 0, (248, 248, 244))
        draw_text_center_at(draw, (cx, inner_y1 + int(header_h * 0.82)), number_pinyin_text(number), pinyin_font, dark)

    draw.line((split_x, inner_y1 + 3, split_x, inner_y1 + header_h - 3), fill=dark, width=max(1, width // 160))
    all_symbol = jie_hao_yun_all_symbol(ticket)
    all_rect = (split_x + 2, inner_y1 + 3, inner_x2, inner_y1 + header_h - 12)
    draw_symbol_token(draw, all_rect, all_symbol, dark)
    draw_text_center_at(draw, ((split_x + inner_x2) // 2, inner_y1 + header_h - 7), "全中区", title_font, dark)

    rule_y = inner_y1 + header_h + max(2, height // 120)
    draw.line((inner_x1, rule_y, inner_x2, rule_y), fill=dark, width=max(1, width // 140))
    label_font = load_ticket_font(max(6, min(10, width // 28)), bold=True)
    draw_text_center_at(draw, (inner_x1 + (inner_x2 - inner_x1) // 4, rule_y + max(9, height // 45)), "你的号码", label_font, dark)

    grid_top = rule_y + max(17, height // 22)
    grid_bottom = inner_y2
    play_count = max(1, len(entries))
    cols = 6 if play_count <= 12 else 5
    rows = max(1, (play_count + cols - 1) // cols)
    cell_w = max(1, (inner_x2 - inner_x1) // cols)
    cell_h = max(1, (grid_bottom - grid_top) // rows)
    for row in range(1, rows):
        draw_dotted_line(draw, inner_x1, grid_top + row * cell_h, inner_x2, line, dot=3, gap=5, width=1)
    for index, entry in enumerate(entries[: cols * rows]):
        row = index // cols
        col = index % cols
        rect = (
            inner_x1 + col * cell_w,
            grid_top + row * cell_h + 1,
            inner_x1 + (col + 1) * cell_w,
            grid_top + (row + 1) * cell_h - 1,
        )
        draw_official_entry(draw, rect, entry, dark, red, False)


def draw_generated_middle(
    size: tuple[int, int],
    ticket: dict,
    prize: int,
    rng=None,
    accent: tuple[int, int, int] | None = None,
    reference: Image.Image | None = None,
    cover_reference: Image.Image | None = None,
) -> tuple[Image.Image, Image.Image, list[str], list[str]]:
    rng = rng or random
    width, height = size
    layout = official_scratch_layout(ticket, size)
    if layout.kind == "paired-symbol-prize":
        scenes = build_paired_symbol_prize_entries(ticket, prize, rng)
        image = Image.new("RGBA", size, (255, 255, 255, 0))
        cover = draw_generated_cover(size, cover_reference)
        draw = ImageDraw.Draw(image)
        dark = (22, 22, 22)
        line = (74, 74, 74)
        red = (214, 24, 30)
        draw_paired_symbol_prize_middle(draw, size, scenes, dark, line, red)
        flattened = [str(symbol) for scene in scenes for symbol in scene["symbols"]]
        return image, cover, flattened, []

    image = build_reference_middle_background(size, reference)
    cover = draw_generated_cover(size, cover_reference)
    draw = ImageDraw.Draw(image)
    dark = (22, 22, 22)
    line = (74, 74, 74)
    red = (214, 24, 30)

    if is_symbol_prize_ticket(ticket):
        symbol_entries = build_symbol_prize_entries(ticket, prize, rng, layout.play_count)
        draw_symbol_prize_grid_middle(draw, size, layout, symbol_entries, dark, line, red)
        return image, cover, [str(entry["symbol"]) for entry in symbol_entries], []

    if has_multi_same_game(ticket):
        scene_count = 8 if width < 360 else (12 if layout.play_count >= 12 else max(8, layout.play_count))
        scenes = build_multi_same_prize_entries(ticket, prize, rng, scene_count)
        draw_paired_symbol_prize_middle(draw, size, scenes, dark, line, red)
        flattened = [str(symbol) for scene in scenes for symbol in scene["symbols"]]
        return image, cover, flattened, []

    if has_prize_amount_game(ticket) and has_number_match_game(ticket):
        if is_jie_hao_yun_ticket(ticket):
            bonus_count = 5 if has_prize_amount_game(ticket) else 0
            bonus_entries = build_prize_amount_entries(ticket, prize, rng, bonus_count)
            match_count = jie_hao_yun_play_count(ticket)
            entries, win_numbers = build_middle_entries(ticket, prize, rng, match_count, 3)
            draw_jie_hao_yun_middle(draw, size, ticket, bonus_entries, entries, win_numbers, dark, line, red, reference)
            bonus_tokens = [f"奖金:{format_print_yuan(entry['amount'])}" for entry in bonus_entries]
            return image, cover, [entry["number"] for entry in entries] + bonus_tokens, win_numbers

        bonus_entries = build_prize_amount_entries(ticket, prize, rng, 4)
        match_count = layout.play_count if width < 360 and height > width * 1.15 else min(layout.play_count, 24 if width >= 640 else 15)
        entries, win_numbers = build_middle_entries(ticket, prize, rng, match_count, layout.win_count)
        symbol_specs = symbol_prize_specs(ticket) if has_symbol_prize_game(ticket) or "标志" in ticket_rule(ticket) else []
        draw_mixed_prize_match_middle(draw, size, layout, bonus_entries, entries, win_numbers, symbol_specs, dark, line, red)
        bonus_tokens = [f"奖金:{format_print_yuan(entry['amount'])}" for entry in bonus_entries]
        return image, cover, [entry["number"] for entry in entries] + bonus_tokens, win_numbers

    if has_prize_amount_game(ticket):
        play_count = max(6, min(layout.play_count, 12))
        bonus_entries = build_prize_amount_entries(ticket, prize, rng, play_count)
        title = "奖金区" if not has_collect_symbol_game(ticket) else "奖金区 / 收集区"
        draw_prize_amount_grid_middle(draw, size, bonus_entries, dark, line, red, title)
        return image, cover, [format_print_yuan(entry["amount"]) for entry in bonus_entries], []

    entries, win_numbers = build_middle_entries(ticket, prize, rng, layout.play_count, layout.win_count)

    if layout.kind == "wide-symbol-grid":
        draw_wide_official_middle(draw, size, entries, win_numbers, dark, line, red, layout.outlined_text)
    elif layout.kind == "wide-match":
        draw_wide_match_official_middle(draw, size, layout, entries, win_numbers, dark, line, red)
    elif layout.kind == "wide-bonus-strip":
        draw_wide_bonus_strip_middle(draw, size, layout, entries, win_numbers, dark, line, red)
    elif layout.kind == "tall-sheet":
        draw_tall_sheet_middle(draw, size, layout, entries, win_numbers, dark, line, red)
    elif layout.kind == "vertical-list":
        draw_vertical_list_middle(draw, size, layout, entries, win_numbers, dark, line, red)
    elif layout.kind == "vertical-grid":
        draw_vertical_official_middle(draw, size, entries, win_numbers, dark, line, red, layout.outlined_text)
    else:
        draw_compact_official_middle(draw, size, entries, dark, line, red, layout.outlined_text)

    return image, cover, [entry["number"] for entry in entries], win_numbers


def generate_official_ticket_visual(
    face_value: int | str,
    rng=None,
    ticket_id: int | None = None,
    theme_index: int = 0,
    base_output_path: str | Path | None = None,
    cover_output_path: str | Path | None = None,
    target_size: tuple[int, int] = (520, 780),
) -> GeneratedTicketVisual | None:
    rng = rng or random
    selected_ticket = find_official_ticket(ticket_id)
    tickets = official_tickets_for_face_value(face_value)
    if selected_ticket is not None and int(selected_ticket.get("money", 0)) == normalize_face_value(face_value):
        ticket = selected_ticket
    elif tickets:
        ticket = tickets[0]
    else:
        return None
    themes = list(ticket.get("themes", []))
    theme_index = max(0, min(int(theme_index), len(themes) - 1))
    theme = themes[theme_index]
    won = rng.random() < WIN_CHANCE
    prize = choose_official_prize(ticket, rng) if won else 0
    part_a = open_ticket_asset(theme["backgroundA"])
    part_c = open_ticket_asset(theme["backgroundC"])
    covered_reference = open_ticket_asset(theme["backgroundB"])
    revealed_reference = open_ticket_asset(theme["notAwardImg"])
    accent = ticket_accent_color(part_a, part_c)
    generated_middle, generated_cover, play_numbers, win_numbers = draw_generated_middle(
        covered_reference.size,
        ticket,
        prize,
        rng,
        accent,
        reference=revealed_reference,
        cover_reference=covered_reference,
    )
    scratch_area = detect_reveal_scratch_area(revealed_reference, covered_reference.size)
    layout = official_scratch_layout(ticket, covered_reference.size)
    generated_middle, generated_cover = compose_clean_middle_layers(
        ticket,
        layout,
        generated_middle,
        covered_reference,
        scratch_area,
    )
    generated_theme = {
        "backgroundA": theme["backgroundA"],
        "backgroundB": theme["backgroundB"],
        "backgroundC": theme["backgroundC"],
        "generatedMiddle": generated_middle,
        "generatedCover": generated_cover,
        "scratchArea": scratch_area,
    }
    base_image, cover_image, scratch_rect = compose_ticket_with_generated_middle(ticket, generated_theme, target_size)

    base_output = Path(base_output_path) if base_output_path is not None else default_ticket_base_file()
    cover_output = Path(cover_output_path) if cover_output_path is not None else default_ticket_cover_file()
    base_output.parent.mkdir(parents=True, exist_ok=True)
    cover_output.parent.mkdir(parents=True, exist_ok=True)
    base_image.save(base_output)
    cover_image.save(cover_output)

    return GeneratedTicketVisual(
        prize=prize,
        face_value=int(ticket.get("money", face_value)),
        product_name=str(ticket.get("name", get_ticket_type(face_value).name)),
        max_prize=int(ticket.get("maxAward", 0)),
        base_path=str(base_output),
        cover_path=str(cover_output),
        scratch_rect=scratch_rect,
        back_path=str(ticket_asset_path(str(ticket.get("backImg", "")))) if ticket.get("backImg") else str(default_ticket_back_file()),
        ticket_id=int(ticket.get("id", 0)),
        theme_index=theme_index,
        visual_style="official",
        rule_summary=str(ticket.get("introduce") or ticket.get("description") or ""),
        game_rule=str(ticket.get("gameRule") or ""),
        play_numbers=play_numbers,
        win_numbers=win_numbers,
    )


def draw_centered_text(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str, font, fill: str) -> tuple[int, int]:
    x, y = xy
    bbox = draw.textbbox((x, y), text, font=font)
    width = bbox[2] - bbox[0]
    height = bbox[3] - bbox[1]
    draw.text((x - width // 2, y), text, font=font, fill=fill)
    return width, height


def draw_wrapped_pil_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    xy: tuple[int, int],
    font,
    fill: str | tuple[int, int, int],
    max_width: int,
    line_spacing: int,
) -> int:
    x, y = xy
    current = ""
    for char in text:
        candidate = current + char
        bbox = draw.textbbox((0, 0), candidate, font=font)
        if current and bbox[2] - bbox[0] > max_width:
            draw.text((x, y), current, font=font, fill=fill)
            y += (bbox[3] - bbox[1]) + line_spacing
            current = char
        else:
            current = candidate
    if current:
        bbox = draw.textbbox((0, 0), current, font=font)
        draw.text((x, y), current, font=font, fill=fill)
        y += (bbox[3] - bbox[1]) + line_spacing
    return y


def build_legacy_back_image(size: tuple[int, int], ticket_type: TicketType) -> Image.Image:
    width, height = size
    scale = width / 520
    image = Image.new("RGBA", size, (255, 255, 255, 255))
    draw = ImageDraw.Draw(image)
    font_body = load_ticket_font(max(13, int(16 * scale)), bold=True)
    font_small = load_ticket_font(max(9, int(11 * scale)))
    font_title = load_ticket_font(max(24, int(32 * scale)), bold=True)
    font_stamp = load_ticket_font(max(17, int(24 * scale)), bold=True)
    font_number = load_ticket_font(max(11, int(13 * scale)), bold=True, role="number")

    margin = int(34 * scale)
    red = (210, 32, 24)
    dark = (34, 40, 48)
    gray = (96, 105, 118)
    line = (72, 78, 88)

    draw.text((margin, int(28 * scale)), "中国体育彩票", font=font_title, fill=dark)
    draw.text((margin, int(72 * scale)), f"{ticket_type.name}  本地模拟票背面", font=font_body, fill=gray)
    stamp_rect = (width - int(158 * scale), int(30 * scale), width - margin, int(104 * scale))
    draw.rounded_rectangle(stamp_rect, radius=int(10 * scale), outline=red, width=max(2, int(3 * scale)))
    draw.text((stamp_rect[0] + int(18 * scale), stamp_rect[1] + int(18 * scale)), "刮刮乐", font=font_stamp, fill=red)

    y = int(138 * scale)
    draw.line((margin, y, width - margin, y), fill=line, width=max(1, int(2 * scale)))
    y += int(20 * scale)
    draw.text((margin, y), "游戏规则", font=font_body, fill=dark)
    y += int(34 * scale)
    rules = [
        "刮开覆盖膜，如果你的号码中任意一个号码与中奖号码之一相同，即中得该号码下方所示奖金。",
        "中奖金额以票面显示为准，中奖后请在本程序内点击查看结果。",
        "本票为本地模拟演示票面，不作为实体彩票销售或兑奖凭证。",
    ]
    for index, rule in enumerate(rules, start=1):
        y = draw_wrapped_pil_text(
            draw,
            f"{index}. {rule}",
            (margin, y),
            font_small,
            dark,
            int(width * 0.58),
            int(7 * scale),
        ) + int(8 * scale)

    table_x = int(width * 0.64)
    table_y = int(174 * scale)
    table_w = width - table_x - margin
    row_h = int(30 * scale)
    draw.rectangle((table_x, table_y, table_x + table_w, table_y + row_h * 9), outline=line, width=max(1, int(2 * scale)))
    grade_x = table_x + int(10 * scale)
    prize_x = table_x + int(48 * scale)
    draw.text((grade_x, table_y + int(7 * scale)), "奖级", font=font_small, fill=dark)
    draw.text((prize_x, table_y + int(7 * scale)), "奖金", font=font_small, fill=dark)
    prize_rows = [ticket_type.max_prize, 10000, 1500, 1200, 1000, 600, 100, ticket_type.face_value]
    for row, amount in enumerate(prize_rows, start=1):
        top = table_y + row_h * row
        draw.line((table_x, top, table_x + table_w, top), fill=line, width=1)
        draw.text((grade_x + int(5 * scale), top + int(7 * scale)), str(row), font=font_number, fill=dark)
        amount_text = format_yuan(amount)
        amount_font = fit_ticket_font(
            draw,
            amount_text,
            max(1, table_x + table_w - prize_x - int(8 * scale)),
            max(9, int(13 * scale)),
            max(7, int(8 * scale)),
            bold=True,
            role="number",
        )
        draw.text((prize_x, top + int(7 * scale)), amount_text, font=amount_font, fill=dark)

    bottom_y = height - int(170 * scale)
    draw.line((margin, bottom_y, width - margin, bottom_y), fill=line, width=max(1, int(2 * scale)))
    draw.text((margin, bottom_y + int(20 * scale)), "销售机构盖章", font=font_body, fill=dark)
    draw.line((margin, bottom_y + int(68 * scale), int(width * 0.52), bottom_y + int(68 * scale)), fill=line, width=1)
    draw.text((margin, bottom_y + int(92 * scale)), "客服电话：95086", font=font_small, fill=gray)
    draw.text((margin, bottom_y + int(122 * scale)), "模拟编号：36-0881-00000001", font=font_small, fill=gray)

    barcode_x = int(width * 0.64)
    barcode_y = bottom_y + int(16 * scale)
    barcode_w = width - barcode_x - margin
    barcode_h = int(112 * scale)
    draw.rectangle((barcode_x - int(10 * scale), barcode_y - int(10 * scale), barcode_x + barcode_w + int(10 * scale), barcode_y + barcode_h + int(10 * scale)), fill=(248, 249, 251), outline=(210, 214, 220))
    rng = random.Random(20260601 + ticket_type.face_value)
    x = barcode_x
    while x < barcode_x + barcode_w:
        bar_w = rng.choice([2, 3, 4, 5]) * max(1, int(scale))
        if rng.random() > 0.34:
            draw.rectangle((x, barcode_y, min(x + bar_w, barcode_x + barcode_w), barcode_y + barcode_h), fill=(20, 20, 20))
        x += bar_w + max(1, int(scale))
    draw.text((barcode_x, barcode_y + barcode_h + int(12 * scale)), "693605252526", font=font_number, fill=dark)
    return image


def load_legacy_official_back_image(ticket_type: TicketType) -> Image.Image:
    path = default_ticket_back_file()
    try:
        return Image.open(path).convert("RGBA")
    except (OSError, FileNotFoundError):
        return build_legacy_back_image((520, 780), ticket_type)


def sharpen_ticket_back(image: Image.Image) -> Image.Image:
    if min(image.size) < 700:
        return image
    return image.filter(ImageFilter.UnsharpMask(radius=1.1, percent=115, threshold=2))


def normalize_money(amount: str) -> int:
    return int(amount.replace(",", ""))


def prize_pinyin(prize_text: str, prize_resource: dict | None = None) -> str:
    if prize_resource and prize_text in prize_resource:
        return str(prize_resource[prize_text])
    return PRIZE_PINYIN.get(prize_text, "JIANGJIN")


def format_yuan(amount: int | str) -> str:
    return f"¥{int(amount):,}"


def choose_prize_key(rng=None, face_value: int | str = TICKET_PRICE) -> str:
    rng = rng or random
    prize_weights = get_prize_weights(face_value)
    threshold = rng.random() * PRIZE_WEIGHT_TOTAL
    cumulative = 0

    for prize_key, weight in prize_weights:
        cumulative += weight
        if threshold < cumulative:
            return prize_key

    return prize_weights[-1][0]


def choose_ticket_numbers(valid_numbers: list[str], rng=None) -> tuple[list[str], list[str]]:
    rng = rng or random
    win_numbers = rng.sample(valid_numbers, 2)
    excluded = [number for number in valid_numbers if number not in win_numbers]

    if rng.random() < WIN_CHANCE:
        match_count = 2 if rng.random() < 0.25 else 1
        matching_numbers = rng.sample(win_numbers, match_count)
        play_numbers = rng.sample(excluded, 10 - match_count) + matching_numbers
    else:
        play_numbers = rng.sample(excluded, 10)

    rng.shuffle(play_numbers)
    return play_numbers, win_numbers


def build_win_marker_rects(ticket: TicketState) -> list[tuple[int, int, int, int]]:
    if ticket.prize <= 0 or not ticket.play_numbers or not ticket.win_numbers:
        return []

    winning_numbers = set(ticket.win_numbers)
    rects = []
    for index, number in enumerate(ticket.play_numbers):
        if number in winning_numbers:
            x, y = PLAY_COORDINATES[index]
            rects.append((x - 34, y - 6, 68, 54))
    return rects


def generate_scratch_card(
    output_path: str | Path | None = None,
    face_value: int | str = TICKET_PRICE,
    scale: float = 1.0,
):
    ticket_type = get_ticket_type(face_value)
    output = Path(output_path) if output_path is not None else default_ticket_output_file()
    output.parent.mkdir(parents=True, exist_ok=True)

    image_path = resource_path("Picture", "frontPicture", "i_love_china_mid_uncovered_clear.png")
    font_number_path = resource_path("Front", "Number.ttf")
    font_pinyin_path = resource_path("Front", "Pinyin.ttf")

    image = Image.open(image_path).convert("RGBA")
    scale = max(1.0, float(scale))
    if scale != 1.0:
        image = image.resize((int(image.width * scale), int(image.height * scale)), Image.Resampling.LANCZOS)
    draw = ImageDraw.Draw(image)

    font_number = ImageFont.truetype(str(font_number_path), max(1, int(21 * scale)))
    font_pinyin = ImageFont.truetype(str(font_pinyin_path), max(1, int(8 * scale)))
    font_money = ImageFont.truetype(str(font_pinyin_path), max(1, int(12 * scale)))

    number_pinyin_dict = load_json_resource("Datarecourses", "Number.txt")
    winning_dict = load_json_resource("Datarecourses", "Winning.txt")
    valid_numbers = [f"{i:02d}" for i in range(100)]

    play_numbers, win_numbers = choose_ticket_numbers(valid_numbers)
    total_money = 0

    for index, number in enumerate(play_numbers + win_numbers):
        base_x, base_y = (PLAY_COORDINATES + WIN_COORDINATES)[index]
        x, y = int(base_x * scale), int(base_y * scale)
        _, num_height = draw_centered_text(draw, (x, y), number, font_number, "black")

        pinyin_text = str(number_pinyin_dict[number]).upper()
        _, pinyin_height = draw_centered_text(draw, (x, y + num_height), pinyin_text, font_pinyin, "black")

        if index >= len(PLAY_COORDINATES):
            continue

        prize_text = choose_prize_key(face_value=ticket_type.face_value)
        amount_pinyin = prize_pinyin(prize_text, winning_dict)
        prize_value = normalize_money(prize_text)
        if number in win_numbers:
            total_money += prize_value

        money_text = f"¥{prize_value}"
        _, money_height = draw_centered_text(
            draw,
            (x, y + num_height + pinyin_height + int(6 * scale)),
            money_text,
            font_money,
            "black",
        )
        draw_centered_text(
            draw,
            (x, y + num_height + pinyin_height + money_height + int(9 * scale)),
            str(amount_pinyin).upper(),
            font_pinyin,
            "black",
        )

    image.save(output)
    return str(output), total_money, play_numbers, win_numbers


def generate_legacy_ticket_visual(
    face_value: int | str,
    base_output_path: str | Path | None = None,
    cover_output_path: str | Path | None = None,
    target_size: tuple[int, int] = (520, 780),
) -> GeneratedTicketVisual:
    ticket_type = get_ticket_type(face_value)
    render_scale = max(1.0, target_size[1] / 780)
    mid_path, prize, play_numbers, win_numbers = generate_scratch_card(face_value=ticket_type.face_value, scale=render_scale)
    up = Image.open(resource_path("Picture", "frontPicture", "i_love_china_up.png")).convert("RGBA")
    mid = Image.open(mid_path).convert("RGBA")
    down = Image.open(resource_path("Picture", "frontPicture", "i_love_china_down.png")).convert("RGBA")
    if render_scale != 1.0:
        up = up.resize((int(up.width * render_scale), int(up.height * render_scale)), Image.Resampling.LANCZOS)
        down = down.resize((int(down.width * render_scale), int(down.height * render_scale)), Image.Resampling.LANCZOS)
    covered = Image.open(resource_path("Picture", "frontPicture", "i_love_china_mid_covered.png")).convert("RGBA")
    covered = covered.resize(mid.size, Image.Resampling.LANCZOS)

    width = max(up.width, mid.width, down.width)
    height = up.height + mid.height + down.height
    base = Image.new("RGBA", (width, height), (255, 255, 255, 255))
    cover = Image.new("RGBA", (width, height), (255, 255, 255, 0))
    mid_x = (width - mid.width) // 2
    base.alpha_composite(up, ((width - up.width) // 2, 0))
    base.alpha_composite(mid, (mid_x, up.height))
    base.alpha_composite(down, ((width - down.width) // 2, up.height + mid.height))
    cover.alpha_composite(covered, (mid_x, up.height))
    scratch_rect = (mid_x, up.height, covered.width, covered.height)
    back = load_legacy_official_back_image(ticket_type)

    if base.size != target_size:
        base, scale, offset_x, offset_y = fit_ticket_image(base, target_size)
        cover = fit_cover_image(cover, target_size, scale, offset_x, offset_y)
        back, _back_scale, _back_offset_x, _back_offset_y = fit_ticket_image(back, target_size)
        scratch_rect = scale_rect(scratch_rect, scale, offset_x, offset_y)
    elif back.size != base.size:
        back, _back_scale, _back_offset_x, _back_offset_y = fit_ticket_image(back, base.size)
    back = sharpen_ticket_back(back)

    base_output = Path(base_output_path) if base_output_path is not None else default_ticket_base_file()
    cover_output = Path(cover_output_path) if cover_output_path is not None else default_ticket_cover_file()
    back_output = default_ticket_back_output_file()
    base_output.parent.mkdir(parents=True, exist_ok=True)
    cover_output.parent.mkdir(parents=True, exist_ok=True)
    back_output.parent.mkdir(parents=True, exist_ok=True)
    base.save(base_output)
    cover.save(cover_output)
    back.save(back_output)

    return GeneratedTicketVisual(
        prize=prize,
        face_value=ticket_type.face_value,
        product_name=ticket_type.name,
        max_prize=ticket_type.max_prize,
        base_path=str(base_output),
        cover_path=str(cover_output),
        scratch_rect=scratch_rect,
        back_path=str(back_output),
        visual_style="legacy",
        rule_summary="数字匹配",
        game_rule="刮开覆盖膜，如果你的号码中任意一个号码与中奖号码之一相同，即中得该号码下方所示奖金。",
        play_numbers=play_numbers,
        win_numbers=win_numbers,
    )


def generate_ticket_visual(
    face_value: int | str = TICKET_PRICE,
    rng=None,
    ticket_id: int | None = None,
    theme_index: int = 0,
    target_size: tuple[int, int] = (520, 780),
) -> GeneratedTicketVisual:
    return generate_legacy_ticket_visual(face_value, target_size=target_size)


def summarize_game_rule(rule: str, max_chars: int = 86) -> str:
    text = str(rule or "").replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\s+", "", text.replace("\n", "；"))
    replacements = (
        ("游戏规则：", ""),
        ("刮开覆盖膜，", ""),
        ("刮开覆盖膜如果", "如果"),
        ("中奖奖金兼中兼得。", ""),
        ("中奖奖金兼中兼得！", ""),
        ("中奖奖金兼中兼得", ""),
    )
    for old, new in replacements:
        text = text.replace(old, new)
    parts = [part for part in re.split(r"[。；]+", text) if part and "网络" not in part]
    summary = "；".join(parts[:2])
    if not summary:
        return ""
    if len(summary) > max_chars:
        return summary[: max(1, max_chars - 1)] + "…"
    return summary


def center_window(window: tk.Tk | tk.Toplevel, width: int, height: int) -> None:
    screen_width = window.winfo_screenwidth()
    screen_height = window.winfo_screenheight()
    x = (screen_width - width) // 2
    y = (screen_height - height) // 2
    window.geometry(f"{width}x{height}+{x}+{y}")


def draw_tk_round_rect(
    canvas: tk.Canvas,
    x1: int,
    y1: int,
    x2: int,
    y2: int,
    radius: int,
    fill: str,
    outline: str = "",
    width: int = 1,
    tags: str | tuple[str, ...] = (),
) -> None:
    radius = max(0, min(radius, (x2 - x1) // 2, (y2 - y1) // 2))
    item_options = {"fill": fill, "outline": ""}
    if tags:
        item_options["tags"] = tags

    canvas.create_rectangle(x1 + radius, y1, x2 - radius, y2, **item_options)
    canvas.create_rectangle(x1, y1 + radius, x2, y2 - radius, **item_options)
    canvas.create_oval(x1, y1, x1 + radius * 2, y1 + radius * 2, **item_options)
    canvas.create_oval(x2 - radius * 2, y1, x2, y1 + radius * 2, **item_options)
    canvas.create_oval(x1, y2 - radius * 2, x1 + radius * 2, y2, **item_options)
    canvas.create_oval(x2 - radius * 2, y2 - radius * 2, x2, y2, **item_options)

    if outline and width > 0:
        line_options = {"fill": outline, "width": width}
        if tags:
            line_options["tags"] = tags
        canvas.create_line(x1 + radius, y1, x2 - radius, y1, **line_options)
        canvas.create_line(x2, y1 + radius, x2, y2 - radius, **line_options)
        canvas.create_line(x2 - radius, y2, x1 + radius, y2, **line_options)
        canvas.create_line(x1, y2 - radius, x1, y1 + radius, **line_options)


def draw_tk_soft_background(canvas: tk.Canvas, width: int, height: int) -> None:
    top = hex_to_rgb(UI_HEX["window_bg_top"])
    bottom = hex_to_rgb(UI_HEX["window_bg_bottom"])
    for y in range(height):
        color = blend_color(top, bottom, y / max(1, height - 1))
        canvas.create_line(0, y, width, y, fill=f"#{color[0]:02x}{color[1]:02x}{color[2]:02x}")
    canvas.create_rectangle(0, 0, width, 7, fill=UI_HEX["primary"], outline="")
    canvas.create_rectangle(0, 7, width, 10, fill=UI_HEX["gold"], outline="")


def draw_tk_shadowed_card(
    canvas: tk.Canvas,
    x1: int,
    y1: int,
    x2: int,
    y2: int,
    radius: int = 8,
) -> None:
    draw_tk_round_rect(canvas, x1 + 14, y1 + 14, x2 + 14, y2 + 14, radius, "#dbe4ee")
    draw_tk_round_rect(canvas, x1 + 6, y1 + 7, x2 + 6, y2 + 7, radius, "#e5edf5")
    draw_tk_round_rect(canvas, x1, y1, x2, y2, radius, UI_HEX["card"], outline=UI_HEX["border"])


def bind_tk_button_hover(button: tk.Button, normal_bg: str, hover_bg: str) -> None:
    button.bind("<Enter>", lambda _event: button.configure(bg=hover_bg, activebackground=hover_bg))
    button.bind("<Leave>", lambda _event: button.configure(bg=normal_bg, activebackground=normal_bg))


class RoundedTkEntry(tk.Frame):
    def __init__(self, parent: tk.Widget, show: str | None = None) -> None:
        super().__init__(parent, background=UI_HEX["card"], height=46)
        self._fill = UI_HEX["card_soft"]
        self._outline = UI_HEX["border"]
        self._focused = False
        self._password_entry = bool(show)
        self._visible_var: tk.BooleanVar | None = None
        self._toggle_command = None
        self._eye_hover = False
        self.grid_propagate(False)
        self.canvas = tk.Canvas(self, background=UI_HEX["card"], borderwidth=0, highlightthickness=0)
        self.canvas.place(x=0, y=0, relwidth=1, relheight=1)
        self.entry = tk.Entry(
            self,
            font=("Microsoft YaHei UI", 11),
            bg=self._fill,
            fg=UI_HEX["text"],
            insertbackground=UI_HEX["primary"],
            highlightthickness=0,
            relief="flat",
            bd=0,
            show=show or "",
        )
        self._place_entry()
        self.bind("<Configure>", lambda _event: self._redraw())
        self.entry.bind("<FocusIn>", lambda _event: self._set_focus(True), add="+")
        self.entry.bind("<FocusOut>", lambda _event: self._set_focus(False), add="+")
        self.canvas.tag_bind("eye", "<Button-1>", lambda _event: self._toggle_password_visibility())
        self.canvas.tag_bind("eye", "<Enter>", lambda _event: self._set_eye_hover(True))
        self.canvas.tag_bind("eye", "<Leave>", lambda _event: self._set_eye_hover(False))

    def _place_entry(self) -> None:
        right_padding = 58 if self._password_entry else 32
        self.entry.place(x=16, y=8, relwidth=1, width=-right_padding, relheight=1, height=-16)

    def _set_focus(self, focused: bool) -> None:
        self._focused = focused
        self._redraw()

    def _set_eye_hover(self, hovered: bool) -> None:
        self._eye_hover = hovered
        self.canvas.configure(cursor="hand2" if hovered else "")
        self._redraw()

    def _password_visible(self) -> bool:
        if self._visible_var is not None:
            return bool(self._visible_var.get())
        return str(self.entry.cget("show")) == ""

    def _toggle_password_visibility(self) -> None:
        if not self._password_entry:
            return
        if self._visible_var is not None:
            self._visible_var.set(not self._visible_var.get())
        if self._toggle_command:
            self._toggle_command()
        else:
            self.entry.configure(show="" if str(self.entry.cget("show")) else "*")
        self._redraw()

    def set_visibility_control(self, variable: tk.BooleanVar, command=None) -> None:
        self._password_entry = True
        self._visible_var = variable
        self._toggle_command = command
        self._place_entry()
        self._redraw()

    def _redraw(self) -> None:
        width = max(1, self.winfo_width())
        height = max(1, self.winfo_height())
        self.canvas.delete("entry_shape")
        self.canvas.delete("eye")
        draw_tk_round_rect(
            self.canvas,
            0,
            0,
            width - 1,
            height - 1,
            min(15, height // 2),
            self._fill,
            outline=UI_HEX["primary"] if self._focused else self._outline,
            width=1,
            tags="entry_shape",
        )
        self.canvas.tag_lower("entry_shape")
        if self._password_entry and width > 60:
            center_x = width - 28
            center_y = height // 2
            color = UI_HEX["primary"] if self._password_visible() or self._eye_hover else UI_HEX["muted"]
            self.canvas.create_oval(center_x - 12, center_y - 7, center_x + 12, center_y + 7, outline=color, width=2, tags="eye")
            self.canvas.create_oval(center_x - 4, center_y - 4, center_x + 4, center_y + 4, fill=color, outline="", tags="eye")
            if not self._password_visible():
                self.canvas.create_line(center_x - 12, center_y + 9, center_x + 12, center_y - 9, fill=color, width=2, tags="eye")

    def configure(self, cnf=None, **kwargs):  # type: ignore[override]
        if cnf is not None and not kwargs:
            return self.entry.configure(cnf)
        entry_options = {}
        frame_options = {}
        for key, value in kwargs.items():
            if key in {"show", "fg", "foreground", "insertbackground", "font"}:
                if key == "show" and value:
                    self._password_entry = True
                entry_options[key] = value
            elif key in {"bg", "background"}:
                self._fill = str(value)
                entry_options["bg"] = value
            else:
                frame_options[key] = value
        if frame_options:
            super().configure(**frame_options)
        if entry_options:
            self.entry.configure(**entry_options)
        self._redraw()

    config = configure

    def bind(self, sequence=None, func=None, add=None):  # type: ignore[override]
        if sequence in ("<FocusIn>", "<FocusOut>"):
            return self.entry.bind(sequence, func, add="+")
        return super().bind(sequence, func, add)

    def get(self) -> str:
        return self.entry.get()

    def insert(self, index, string: str) -> None:
        self.entry.insert(index, string)

    def delete(self, first, last=None) -> None:
        self.entry.delete(first, last)

    def focus_set(self) -> None:
        self.entry.focus_set()


class ModernTkCheck(tk.Frame):
    def __init__(self, parent: tk.Widget, text: str, variable: tk.BooleanVar, command=None) -> None:
        super().__init__(parent, background=UI_HEX["card"], cursor="hand2")
        self.variable = variable
        self.command = command
        self.switch = tk.Canvas(self, width=38, height=22, background=UI_HEX["card"], borderwidth=0, highlightthickness=0)
        self.switch.pack(side="left")
        self.label = tk.Label(
            self,
            text=text,
            bg=UI_HEX["card"],
            fg=UI_HEX["muted"],
            cursor="hand2",
            font=("Microsoft YaHei UI", 10),
        )
        self.label.pack(side="left", padx=(8, 0))
        self._trace_id = self.variable.trace_add("write", lambda *_args: self._redraw())
        for widget in (self, self.switch, self.label):
            widget.bind("<Button-1>", self._toggle)
        self.bind("<Destroy>", self._remove_trace, add="+")
        self._redraw()

    def _remove_trace(self, event) -> None:
        if event.widget is not self:
            return
        if self._trace_id:
            try:
                self.variable.trace_remove("write", self._trace_id)
            except tk.TclError:
                pass
            self._trace_id = ""

    def _toggle(self, _event=None) -> None:
        self.variable.set(not self.variable.get())
        if self.command:
            self.command()

    def _redraw(self) -> None:
        if not self.winfo_exists():
            return
        self.switch.delete("all")
        enabled = bool(self.variable.get())
        track = UI_HEX["primary"] if enabled else "#dce5ef"
        knob = UI_HEX["white"]
        draw_tk_round_rect(self.switch, 0, 1, 37, 21, 10, track)
        knob_x = 25 if enabled else 13
        self.switch.create_oval(knob_x - 8, 4, knob_x + 8, 20, fill=knob, outline="")
        self.label.configure(fg=UI_HEX["primary"] if enabled else UI_HEX["muted"])


def set_tk_window_icon(window: tk.Tk | tk.Toplevel) -> None:
    icon_path = default_app_icon_png_file()
    if not icon_path.exists():
        return
    try:
        icon = tk.PhotoImage(file=str(icon_path))
        window.iconphoto(True, icon)
        window._app_icon = icon  # type: ignore[attr-defined]
    except tk.TclError:
        pass


def draw_loading_progress(progress_canvas: tk.Canvas, value: int) -> None:
    progress_canvas.delete("loading_dynamic")
    x1, y1, x2, y2 = progress_canvas.progress_bounds  # type: ignore[attr-defined]
    radius = (y2 - y1) // 2
    draw_tk_round_rect(progress_canvas, x1, y1, x2, y2, radius, "#dce5ef", tags="loading_dynamic")

    ratio = max(0.0, min(1.0, value / 100))
    fill_width = int((x2 - x1) * ratio)
    if fill_width > 0:
        fill_x2 = min(x2, x1 + max(fill_width, radius * 2))
        draw_tk_round_rect(progress_canvas, x1, y1, fill_x2, y2, radius, UI_HEX["gold"], tags="loading_dynamic")
        cap_width = min(fill_x2 - x1, 120)
        if cap_width > 0:
            draw_tk_round_rect(
                progress_canvas,
                x1,
                y1,
                x1 + cap_width,
                y2,
                radius,
                UI_HEX["primary"],
                tags="loading_dynamic",
            )

    progress_canvas.create_text(
        x2,
        y1 - 14,
        text=f"{value}%",
        anchor="e",
        fill=UI_HEX["muted"],
        font=("Microsoft YaHei UI", 9),
        tags="loading_dynamic",
    )


def choose_ticket_selection(username: str, initial_face_value: int | str = TICKET_PRICE) -> TicketSelection | None:
    balance = get_account_balance(username)
    try:
        selected_face_value = normalize_face_value(initial_face_value)
    except ValueError:
        selected_face_value = TICKET_PRICE
    if balance < selected_face_value:
        affordable = [price for price in LOTTERY_FACE_VALUES if price <= balance]
        selected_face_value = affordable[-1] if affordable else MIN_TICKET_PRICE

    result: dict[str, TicketSelection | None] = {"selection": None}
    selector = tk.Tk()
    selector.title("选择彩票面值")
    selector.resizable(False, False)
    selector.configure(background=UI_HEX["window_bg_bottom"])
    set_tk_window_icon(selector)
    window_width, window_height = 780, 700
    center_window(selector, window_width, window_height)

    style = ttk.Style(selector)
    style.theme_use("clam")
    style.configure("Select.TFrame", background=UI_HEX["card"])
    style.configure("SelectTitle.TLabel", background=UI_HEX["card"], foreground=UI_HEX["text"], font=("Microsoft YaHei UI", 22, "bold"))
    style.configure("SelectSub.TLabel", background=UI_HEX["card"], foreground=UI_HEX["muted"], font=("Microsoft YaHei UI", 10))
    style.configure("SelectBody.TLabel", background=UI_HEX["card"], foreground=UI_HEX["text"], font=("Microsoft YaHei UI", 11))
    style.configure("SelectKicker.TLabel", background=UI_HEX["card"], foreground=UI_HEX["primary"], font=("Microsoft YaHei UI", 9, "bold"))
    style.configure(
        "Select.TCombobox",
        fieldbackground=UI_HEX["card_soft"],
        background=UI_HEX["card_soft"],
        foreground=UI_HEX["text"],
        arrowcolor=UI_HEX["primary"],
        bordercolor=UI_HEX["border"],
        lightcolor=UI_HEX["border"],
        darkcolor=UI_HEX["border"],
        padding=(10, 8),
    )
    style.map("Select.TCombobox", bordercolor=[("focus", UI_HEX["primary"])])

    canvas = tk.Canvas(
        selector,
        width=window_width,
        height=window_height,
        background=UI_HEX["window_bg_bottom"],
        borderwidth=0,
        highlightthickness=0,
    )
    canvas.pack(fill="both", expand=True)
    draw_tk_soft_background(canvas, window_width, window_height)
    draw_tk_shadowed_card(canvas, 64, 58, 716, 646, 8)
    canvas.create_rectangle(64, 58, 716, 66, fill=UI_HEX["primary"], outline="")

    frame = ttk.Frame(canvas, style="Select.TFrame", padding=(40, 32, 40, 26))
    canvas.create_window(window_width // 2, window_height // 2 + 4, window=frame, width=584, height=546)

    selected_var = tk.IntVar(value=selected_face_value)
    detail_var = tk.StringVar()
    status_var = tk.StringVar()
    style_var = tk.StringVar()
    buttons: dict[int, tk.Button] = {}
    style_options: list[TicketSelection] = []
    style_combo = ttk.Combobox(
        frame,
        textvariable=style_var,
        state="readonly",
        height=18,
        width=58,
        font=("Microsoft YaHei UI", 10),
        style="Select.TCombobox",
    )

    ttk.Label(frame, text="账户票面", style="SelectKicker.TLabel").grid(row=0, column=0, columnspan=4, sticky="w")
    ttk.Label(frame, text="选择彩票面值", style="SelectTitle.TLabel").grid(row=1, column=0, columnspan=3, sticky="w", pady=(3, 0))
    ttk.Label(frame, text=f"余额 {format_yuan(balance)}", style="SelectSub.TLabel").grid(
        row=1,
        column=3,
        sticky="e",
        pady=(9, 0),
    )

    def refresh_selection() -> None:
        nonlocal style_options
        price = selected_var.get()
        ticket_type = get_ticket_type(price)
        style_options = ticket_style_options(price)
        style_labels = []
        for index, option in enumerate(style_options, start=1):
            label = f"{index:02d}. {option.product_name}"
            style_labels.append(label)
        style_combo.configure(values=style_labels)
        if style_labels:
            style_combo.current(0)
            style_var.set(style_labels[0])
        detail_var.set(
            f"{ticket_type.name}  面值 {format_yuan(price)}  最高奖金 {format_yuan(ticket_type.max_prize)}\n"
            f"仅保留本地模拟票面，连续刮同一种模拟样式\n{ticket_type.description}"
        )
        status_var.set("" if balance >= price else "余额不足，请选择更低面值。")
        for value, button in buttons.items():
            selected = value == price
            affordable = balance >= value
            if selected:
                bg = UI_HEX["primary"]
                hover_bg = UI_HEX["primary_hover"]
                fg = UI_HEX["white"]
            else:
                bg = UI_HEX["gold_soft"] if affordable else UI_HEX["card_soft"]
                hover_bg = "#fff8e7" if affordable else UI_HEX["card_soft"]
                fg = UI_HEX["text"] if affordable else UI_HEX["disabled"]
            button.configure(bg=bg, fg=fg, activebackground=bg, activeforeground=fg)
            bind_tk_button_hover(button, bg, hover_bg)

    def select_price(price: int) -> None:
        selected_var.set(price)
        refresh_selection()

    for index, price in enumerate(LOTTERY_FACE_VALUES):
        row = 2 + index // 4
        column = index % 4
        button = tk.Button(
            frame,
            text=f"{price}元",
            command=lambda value=price: select_price(value),
            relief="flat",
            bd=0,
            cursor="hand2",
            font=("Microsoft YaHei UI", 11, "bold"),
            width=9,
            height=2,
            highlightthickness=0,
        )
        button.grid(row=row, column=column, sticky="ew", padx=6, pady=(22 if index < 4 else 8, 0))
        buttons[price] = button
        frame.columnconfigure(column, weight=1)

    ttk.Label(frame, text="彩票样式", style="SelectSub.TLabel").grid(row=4, column=0, columnspan=4, sticky="w", pady=(18, 7))
    style_combo.grid(row=5, column=0, columnspan=4, sticky="ew", pady=(0, 0))

    ttk.Label(frame, textvariable=detail_var, style="SelectBody.TLabel", wraplength=430).grid(
        row=6,
        column=0,
        columnspan=4,
        sticky="w",
        pady=(14, 6),
    )
    ttk.Label(frame, textvariable=status_var, style="SelectSub.TLabel", wraplength=430).grid(
        row=7,
        column=0,
        columnspan=4,
        sticky="w",
    )

    def start_selected() -> None:
        price = selected_var.get()
        if balance < price:
            messagebox.showinfo("提示", "余额不足，请选择更低面值。")
            return
        selected_index = style_combo.current()
        if selected_index < 0:
            selected_index = 0
        result["selection"] = style_options[selected_index]
        selector.destroy()

    def cancel_selection() -> None:
        result["selection"] = None
        selector.destroy()

    action_frame = ttk.Frame(frame, style="Select.TFrame")
    action_frame.grid(row=8, column=0, columnspan=4, sticky="ew", pady=(18, 0))
    action_frame.columnconfigure(0, weight=1)
    action_frame.columnconfigure(1, weight=1)
    exit_button = tk.Button(
        action_frame,
        text="退出",
        command=cancel_selection,
        bg=UI_HEX["card_soft"],
        fg=UI_HEX["primary"],
        activebackground="#e8eef5",
        activeforeground=UI_HEX["primary"],
        relief="flat",
        bd=0,
        cursor="hand2",
        font=("Microsoft YaHei UI", 11, "bold"),
        height=2,
    )
    exit_button.grid(row=0, column=0, sticky="ew", padx=(0, 8))
    bind_tk_button_hover(exit_button, UI_HEX["card_soft"], "#edf2f7")
    start_button = tk.Button(
        action_frame,
        text="开始刮奖",
        command=start_selected,
        bg=UI_HEX["gold"],
        fg=UI_HEX["text"],
        activebackground=UI_HEX["gold_hover"],
        activeforeground=UI_HEX["text"],
        relief="flat",
        bd=0,
        cursor="hand2",
        font=("Microsoft YaHei UI", 11, "bold"),
        height=2,
    )
    start_button.grid(row=0, column=1, sticky="ew", padx=(8, 0))
    bind_tk_button_hover(start_button, UI_HEX["gold"], UI_HEX["gold_hover"])

    refresh_selection()
    selector.protocol("WM_DELETE_WINDOW", cancel_selection)
    selector.bind("<Return>", lambda _event: start_selected())
    selector.mainloop()
    return result["selection"]


def run_ticket_selection_flow(username: str, initial_face_value: int | str = TICKET_PRICE) -> None:
    next_face_value = normalize_face_value(initial_face_value)
    while True:
        selection = choose_ticket_selection(username, next_face_value)
        if selection is None:
            return

        result = main_game(
            username,
            face_value=selection.face_value,
            ticket_id=selection.ticket_id,
            theme_index=selection.theme_index,
        )
        if result != "reselect":
            return
        next_face_value = selection.face_value


def create_login_register_window() -> None:
    ensure_user_data_file()

    login_window = tk.Tk()
    login_window.title(APP_TITLE)
    login_window.resizable(False, False)
    login_window.configure(background=UI_HEX["window_bg_bottom"])
    set_tk_window_icon(login_window)
    window_width, window_height = 620, 660
    center_window(login_window, window_width, window_height)

    style = ttk.Style(login_window)
    style.theme_use("clam")
    style.configure("App.TFrame", background=UI_HEX["window_bg"])
    style.configure("Card.TFrame", background=UI_HEX["card"])
    style.configure("Title.TLabel", background=UI_HEX["card"], foreground=UI_HEX["text"], font=("Microsoft YaHei UI", 23, "bold"))
    style.configure("Sub.TLabel", background=UI_HEX["card"], foreground=UI_HEX["muted"], font=("Microsoft YaHei UI", 10))
    style.configure("Field.TLabel", background=UI_HEX["card"], foreground=UI_HEX["text"], font=("Microsoft YaHei UI", 10, "bold"))
    style.configure("Kicker.TLabel", background=UI_HEX["card"], foreground=UI_HEX["primary"], font=("Microsoft YaHei UI", 9, "bold"))
    style.configure(
        "Business.TEntry",
        fieldbackground=UI_HEX["card_soft"],
        foreground=UI_HEX["text"],
        bordercolor=UI_HEX["border"],
        lightcolor=UI_HEX["border"],
        darkcolor=UI_HEX["border"],
        insertcolor=UI_HEX["primary"],
        padding=(10, 8),
    )
    style.map("Business.TEntry", bordercolor=[("focus", UI_HEX["primary"])])
    style.configure(
        "Primary.TButton",
        background=UI_HEX["primary"],
        foreground=UI_HEX["white"],
        bordercolor=UI_HEX["primary"],
        focusthickness=0,
        focuscolor=UI_HEX["primary"],
        font=("Microsoft YaHei UI", 11, "bold"),
        padding=(14, 10),
        relief="flat",
    )
    style.map(
        "Primary.TButton",
        background=[("active", UI_HEX["primary_hover"]), ("pressed", UI_HEX["primary_hover"]), ("disabled", UI_HEX["disabled"])],
        foreground=[("disabled", UI_HEX["white"])],
    )
    style.configure(
        "Secondary.TButton",
        background=UI_HEX["gold"],
        foreground=UI_HEX["text"],
        bordercolor=UI_HEX["gold"],
        focusthickness=0,
        focuscolor=UI_HEX["gold"],
        font=("Microsoft YaHei UI", 11, "bold"),
        padding=(14, 10),
        relief="flat",
    )
    style.map(
        "Secondary.TButton",
        background=[("active", UI_HEX["gold_hover"]), ("pressed", UI_HEX["gold_hover"]), ("disabled", UI_HEX["disabled"])],
        foreground=[("disabled", UI_HEX["white"])],
    )

    canvas = tk.Canvas(
        login_window,
        width=window_width,
        height=window_height,
        background=UI_HEX["window_bg_bottom"],
        borderwidth=0,
        highlightthickness=0,
    )
    canvas.pack(fill="both", expand=True)

    draw_tk_soft_background(canvas, window_width, window_height)
    card_rect = (64, 54, 556, 614)
    draw_tk_shadowed_card(canvas, *card_rect, 8)
    canvas.create_rectangle(card_rect[0], card_rect[1], card_rect[2], card_rect[1] + 8, fill=UI_HEX["primary"], outline="")

    page_frame = ttk.Frame(canvas, style="Card.TFrame", padding=(40, 36, 40, 30))
    canvas.create_window(window_width // 2, window_height // 2 + 4, window=page_frame, width=416, height=502)

    status_var = tk.StringVar(value="")
    login_entries: dict[str, tk.Entry] = {}
    register_entries: dict[str, tk.Entry] = {}
    login_preferences = load_login_preferences()
    remember_password_var = tk.BooleanVar(value=bool(login_preferences.get("remember_password")))
    login_show_password_var = tk.BooleanVar(value=False)
    register_show_password_var = tk.BooleanVar(value=False)

    def clear_page() -> None:
        for child in page_frame.winfo_children():
            child.destroy()
        page_frame.columnconfigure(0, weight=0)
        page_frame.columnconfigure(1, weight=1)
        status_var.set("")

    def make_entry(parent: tk.Widget, show: str | None = None) -> RoundedTkEntry:
        return RoundedTkEntry(parent, show=show)

    def set_entry_placeholder(entry: tk.Entry, placeholder: str) -> None:
        entry.insert(0, placeholder)
        entry.configure(fg=UI_HEX["muted"])

        def on_focus_in(_event) -> None:
            if entry.get() == placeholder:
                entry.delete(0, tk.END)
                entry.configure(fg=UI_HEX["text"])

        def on_focus_out(_event) -> None:
            if not entry.get().strip():
                entry.insert(0, placeholder)
                entry.configure(fg=UI_HEX["muted"])

        entry.bind("<FocusIn>", on_focus_in)
        entry.bind("<FocusOut>", on_focus_out)

    def make_action_button(parent: tk.Widget, text: str, command, variant: str = "primary") -> tk.Button:
        if variant == "gold":
            background = UI_HEX["gold"]
            active_background = UI_HEX["gold_hover"]
            foreground = UI_HEX["text"]
        elif variant == "light":
            background = UI_HEX["card_soft"]
            active_background = "#e8eef5"
            foreground = UI_HEX["primary"]
        else:
            background = UI_HEX["primary"]
            active_background = UI_HEX["primary_hover"]
            foreground = UI_HEX["white"]

        button = tk.Button(
            parent,
            text=text,
            command=command,
            bg=background,
            fg=foreground,
            activebackground=active_background,
            activeforeground=foreground,
            relief="flat",
            bd=0,
            cursor="hand2",
            font=("Microsoft YaHei UI", 11, "bold"),
            height=2,
        )
        bind_tk_button_hover(button, background, active_background)
        return button

    def make_checkbutton(parent: tk.Widget, text: str, variable: tk.BooleanVar, command=None) -> ModernTkCheck:
        return ModernTkCheck(parent, text, variable, command)

    def update_login_password_visibility() -> None:
        entry = login_entries.get("password")
        if entry:
            entry.configure(show="" if login_show_password_var.get() else "*")

    def update_register_password_visibility() -> None:
        show = "" if register_show_password_var.get() else "*"
        for key in ("password", "confirm_password"):
            entry = register_entries.get(key)
            if entry:
                entry.configure(show=show)

    def add_status(row: int) -> None:
        ttk.Label(page_frame, textvariable=status_var, style="Sub.TLabel", wraplength=330).grid(
            row=row,
            column=0,
            columnspan=2,
            sticky="w",
            pady=(12, 0),
        )

    def read_login_form() -> tuple[str, str]:
        return login_entries["username"].get().strip(), login_entries["password"].get().strip()

    def read_register_form() -> tuple[str, str, str, str]:
        return (
            register_entries["username"].get().strip(),
            clean_placeholder_value(register_entries["email"].get(), "邮箱可不填"),
            register_entries["password"].get().strip(),
            register_entries["confirm_password"].get().strip(),
        )

    def show_login(prefill_username: str = "", message: str = "") -> None:
        clear_page()
        ttk.Label(page_frame, text="账户入口", style="Kicker.TLabel").grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(page_frame, text=APP_TITLE, style="Title.TLabel").grid(row=1, column=0, columnspan=2, sticky="w", pady=(3, 0))

        ttk.Label(page_frame, text="用户名", style="Field.TLabel").grid(row=2, column=0, sticky="w", pady=(34, 8))
        username_entry = make_entry(page_frame)
        username_entry.grid(row=2, column=1, sticky="ew", pady=(34, 8))
        username_entry.insert(0, prefill_username or str(login_preferences.get("username", "")))

        ttk.Label(page_frame, text="密码", style="Field.TLabel").grid(row=3, column=0, sticky="w", pady=8)
        password_entry = make_entry(page_frame, show="*")
        password_entry.grid(row=3, column=1, sticky="ew", pady=8)
        if remember_password_var.get():
            password_entry.insert(0, str(login_preferences.get("password", "")))

        login_entries.clear()
        login_entries.update({"username": username_entry, "password": password_entry})
        password_entry.set_visibility_control(login_show_password_var, update_login_password_visibility)
        update_login_password_visibility()
        status_var.set(message)
        options = ttk.Frame(page_frame, style="Card.TFrame")
        options.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        options.columnconfigure(0, weight=1)
        make_checkbutton(options, "记住账号", remember_password_var).grid(row=0, column=0, sticky="w")
        add_status(5)

        buttons = ttk.Frame(page_frame, style="Card.TFrame")
        buttons.grid(row=6, column=0, columnspan=2, sticky="ew", pady=(36, 0))
        buttons.columnconfigure(0, weight=1)
        buttons.columnconfigure(1, weight=1)
        make_action_button(buttons, "登录", on_login, "primary").grid(row=0, column=0, sticky="ew", padx=(0, 8))
        make_action_button(buttons, "注册", show_register, "gold").grid(row=0, column=1, sticky="ew", padx=(8, 0))

        login_window.bind("<Return>", lambda _event: on_login())
        username_entry.focus_set()

    def show_register() -> None:
        clear_page()
        ttk.Label(page_frame, text="账户入口", style="Kicker.TLabel").grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(page_frame, text="注册账号", style="Title.TLabel").grid(row=1, column=0, columnspan=2, sticky="w", pady=(3, 0))
        ttk.Label(page_frame, text="建立本地账户", style="Sub.TLabel").grid(
            row=2,
            column=0,
            columnspan=2,
            pady=(5, 18),
            sticky="w",
        )

        fields = [
            ("用户名", "username", None),
            ("邮箱", "email", None),
            ("密码", "password", "*"),
            ("确认密码", "confirm_password", "*"),
        ]
        register_entries.clear()
        for offset, (label, key, show) in enumerate(fields, start=3):
            ttk.Label(page_frame, text=label, style="Field.TLabel").grid(row=offset, column=0, sticky="w", pady=7)
            entry = make_entry(page_frame, show=show)
            entry.grid(row=offset, column=1, sticky="ew", pady=7)
            register_entries[key] = entry
            if key == "email":
                set_entry_placeholder(entry, "邮箱可不填")
        for key in ("password", "confirm_password"):
            register_entries[key].set_visibility_control(register_show_password_var, update_register_password_visibility)
        add_status(8)

        buttons = ttk.Frame(page_frame, style="Card.TFrame")
        buttons.grid(row=9, column=0, columnspan=2, sticky="ew", pady=(26, 0))
        buttons.columnconfigure(0, weight=1)
        buttons.columnconfigure(1, weight=1)
        make_action_button(buttons, "返回登录", lambda: show_login(), "light").grid(row=0, column=0, sticky="ew", padx=(0, 8))
        make_action_button(buttons, "完成注册", on_register_submit, "gold").grid(row=0, column=1, sticky="ew", padx=(8, 0))

        login_window.bind("<Return>", lambda _event: on_register_submit())
        register_entries["username"].focus_set()

    def on_register_submit() -> None:
        username, email, password, confirm_password = read_register_form()
        try:
            user = register_account(username, password, email=email, confirm_password=confirm_password)
        except AccountError as exc:
            status_var.set(str(exc))
            messagebox.showinfo("提示", str(exc))
            return
        messagebox.showinfo("注册成功", f"注册成功！初始余额 ¥{user['balance']}")
        show_login(username, "注册成功，请输入密码登录。")

    def on_login() -> None:
        username, password = read_login_form()
        try:
            user = authenticate_account(username, password)
            if int(user.get("balance", 0)) < MIN_TICKET_PRICE:
                raise InsufficientBalanceError(f"余额不足，至少需要 {format_yuan(MIN_TICKET_PRICE)} 才能开始。")
        except AccountError as exc:
            status_var.set(str(exc))
            messagebox.showinfo("提示", str(exc))
            return

        save_login_preferences(username, remember_password_var.get(), password)
        login_window.destroy()
        run_ticket_selection_flow(username)

    show_login()
    login_window.mainloop()


def update_progress(progress_canvas: tk.Canvas, animation_window: tk.Tk, value: int = 0) -> None:
    draw_loading_progress(progress_canvas, value)
    if value >= 100:
        animation_window.after(120, lambda: (animation_window.destroy(), create_login_register_window()))
        return
    animation_window.after(12, lambda: update_progress(progress_canvas, animation_window, min(value + 4, 100)))


def start_animation() -> None:
    start_image_path = resource_path("Picture", "StartPicture.jpg")
    if not start_image_path.exists():
        create_login_register_window()
        return

    animation_window = tk.Tk()
    animation_window.title(APP_TITLE)
    animation_window.overrideredirect(True)
    animation_window.configure(background=UI_HEX["window_bg"])
    set_tk_window_icon(animation_window)

    start_image = Image.open(start_image_path)
    window_width, window_height = start_image.size
    footer_height = 74
    center_window(animation_window, window_width, window_height + footer_height)

    start_image_tk = ImageTk.PhotoImage(start_image)
    tk.Label(animation_window, image=start_image_tk, borderwidth=0, background=UI_HEX["window_bg"]).pack()

    progress_canvas = tk.Canvas(
        animation_window,
        width=window_width,
        height=footer_height,
        background=UI_HEX["window_bg"],
        borderwidth=0,
        highlightthickness=0,
    )
    progress_canvas.pack(fill="x")
    progress_canvas.progress_bounds = (32, 42, window_width - 32, 54)  # type: ignore[attr-defined]
    progress_canvas.create_text(
        32,
        18,
        text="正在加载资源",
        anchor="w",
        fill=UI_HEX["muted"],
        font=("Microsoft YaHei UI", 10),
    )
    progress_canvas.image = start_image_tk  # keep a reference

    update_progress(progress_canvas, animation_window)
    animation_window.mainloop()


def run_smoke_test() -> int:
    ensure_user_data_file()
    output_path, _prize, _play_numbers, _win_numbers = generate_scratch_card()
    generated = Path(output_path)
    if not generated.exists() or generated.stat().st_size <= 0:
        raise RuntimeError("刮卡图片生成失败。")
    visual = generate_ticket_visual(50)
    if not Path(visual.base_path).exists() or not Path(visual.cover_path).exists() or not Path(visual.back_path).exists():
        raise RuntimeError("本地模拟票面生成失败。")
    return 0


def main_game(
    username: str,
    _balance: int | None = None,
    face_value: int | str = TICKET_PRICE,
    ticket_id: int | None = None,
    theme_index: int = 0,
) -> str | None:
    import pygame

    selected_face_value = normalize_face_value(face_value)
    selected_ticket_id = ticket_id
    selected_theme_index = int(theme_index)
    pygame.init()
    pygame.display.set_caption(APP_TITLE)
    try:
        pygame.mouse.set_cursor(pygame.SYSTEM_CURSOR_HAND)
    except pygame.error:
        pass
    icon_path = default_app_icon_png_file()
    if icon_path.exists():
        try:
            pygame.display.set_icon(pygame.image.load(str(icon_path)))
        except pygame.error:
            pass

    ticket_width, ticket_height = 930, 780
    side_width = 390
    screen = pygame.display.set_mode((ticket_width + side_width, ticket_height))

    colors = {
        "bg": (22, 24, 29),
        "side": hex_to_rgb(UI_HEX["window_bg"]),
        "panel": hex_to_rgb(UI_HEX["card"]),
        "panel_soft": hex_to_rgb(UI_HEX["card_soft"]),
        "text": hex_to_rgb(UI_HEX["text"]),
        "muted": hex_to_rgb(UI_HEX["muted"]),
        "red": hex_to_rgb(UI_HEX["red"]),
        "red_soft": hex_to_rgb(UI_HEX["red_soft"]),
        "green": hex_to_rgb(UI_HEX["green"]),
        "gold": hex_to_rgb(UI_HEX["gold"]),
        "gold_hover": hex_to_rgb(UI_HEX["gold_hover"]),
        "gold_soft": hex_to_rgb(UI_HEX["gold_soft"]),
        "gold_text": (124, 78, 18),
        "button": hex_to_rgb(UI_HEX["primary"]),
        "button_hover": hex_to_rgb(UI_HEX["primary_hover"]),
        "button_active": hex_to_rgb(UI_HEX["green"]),
        "button_disabled": hex_to_rgb(UI_HEX["disabled"]),
        "border": hex_to_rgb(UI_HEX["border"]),
        "white": hex_to_rgb(UI_HEX["white"]),
        "pending": (239, 246, 255),
    }

    def load_font(size: int, bold: bool = False):
        name = "MSYHBD.TTC" if bold else "MSYH.TTC"
        font_path = resource_path("Front", name)
        if not font_path.exists():
            font_path = resource_path("Front", "MSYHBD.TTC")
        return pygame.font.Font(str(font_path), size)

    def fit_pygame_font(text: str, max_width: int, start_size: int, min_size: int = 18, bold: bool = True):
        size = start_size
        while size > min_size:
            candidate = load_font(size, bold)
            if candidate.size(text)[0] <= max_width:
                return candidate
            size -= 1
        return load_font(min_size, bold)

    font_small = load_font(16)
    font_body = load_font(20)
    font_large = load_font(28, bold=True)
    font_balance = load_font(32, bold=True)
    font_button = load_font(20, bold=True)

    def fit_surface_to_canvas(source: "pygame.Surface", size: tuple[int, int]) -> "pygame.Surface":
        target_width, target_height = size
        fitted = pygame.Surface(size).convert()
        fitted.fill(colors["white"])
        source_width, source_height = source.get_size()
        scale = min(target_width / source_width, target_height / source_height)
        scaled_size = (max(1, int(source_width * scale)), max(1, int(source_height * scale)))
        scaled = pygame.transform.smoothscale(source, scaled_size)
        fitted.blit(scaled, ((target_width - scaled_size[0]) // 2, (target_height - scaled_size[1]) // 2))
        return fitted

    def crop_ticket_surfaces(
        base: "pygame.Surface",
        cover: "pygame.Surface",
        back: "pygame.Surface",
        rect: "pygame.Rect",
    ) -> tuple["pygame.Surface", "pygame.Surface", "pygame.Surface", "pygame.Rect"]:
        image_width, image_height = base.get_size()
        left = max(0, min(rect.left, image_width - 1))
        right = max(left + 1, min(rect.right, image_width))
        crop = pygame.Rect(left, 0, right - left, image_height)
        cropped_rect = pygame.Rect(rect.x - crop.x, rect.y - crop.y, rect.width, rect.height)
        return (
            base.subsurface(crop).copy(),
            cover.subsurface(crop).copy(),
            back.subsurface(crop).copy(),
            cropped_rect,
        )

    base_image = pygame.Surface((ticket_width, ticket_height)).convert()
    base_image.fill(colors["white"])
    cover_image = pygame.Surface((ticket_width, ticket_height), pygame.SRCALPHA)
    back_image = pygame.Surface((ticket_width, ticket_height)).convert()
    back_image.fill(colors["white"])
    scratch_rect = pygame.Rect(0, 0, ticket_width, ticket_height)
    erase_area = pygame.Surface((ticket_width, ticket_height), pygame.SRCALPHA)

    ticket: TicketState | None = None
    balance = get_account_balance(username)
    revealed = False
    scratch_ratio = 0.0
    dragging = False
    rotating_ticket = False
    ticket_angle = 0.0
    ticket_pitch = 0.0
    ticket_zoom = 1.0
    ticket_display_rect = pygame.Rect(0, 0, ticket_width, ticket_height)
    last_pos: tuple[int, int] | None = None
    last_rotate_pos: tuple[int, int] | None = None
    status_text = ""
    status_color = colors["muted"]
    change_text = ""
    change_until = 0
    celebration_started_at = -FIREWORK_DURATION_MS
    celebration_particles: list[CelebrationParticle] = []
    result_action: str | None = None
    clock = pygame.time.Clock()

    button_w = 230
    button_h = 46
    button_x = ticket_width + (side_width - button_w) // 2
    button_gap = 10
    button_y = ticket_height - (button_h * 3 + button_gap * 2 + 6)
    reselect_button = pygame.Rect(button_x, button_y, button_w, button_h)
    reveal_button = pygame.Rect(button_x, button_y + button_h + button_gap, button_w, button_h)
    next_button = pygame.Rect(button_x, button_y + (button_h + button_gap) * 2, button_w, button_h)
    selector_rect = pygame.Rect(ticket_width + 24, 236, side_width - 48, 236)
    info_scroll_offset = 0
    info_content_height = 0

    def draw_loading_screen(message: str = "正在生成票面...") -> None:
        screen.fill(colors["bg"], pygame.Rect(0, 0, ticket_width, ticket_height))
        draw_side_panel()
        message_surface = font_large.render(message, True, colors["white"])
        screen.blit(message_surface, message_surface.get_rect(center=(ticket_width // 2, ticket_height // 2)))
        hint_surface = font_body.render("本地模拟票面正在生成", True, (210, 218, 230))
        screen.blit(hint_surface, hint_surface.get_rect(center=(ticket_width // 2, ticket_height // 2 + 42)))
        pygame.display.flip()
        pygame.event.pump()

    def set_status(text: str, color_key: str = "muted") -> None:
        nonlocal status_text, status_color
        status_text = text
        status_color = colors[color_key]

    def reset_ticket_surfaces() -> None:
        erase_area.fill((255, 255, 255, 255))

    def calculate_scratch_ratio() -> float:
        if scratch_rect.width <= 0 or scratch_rect.height <= 0:
            return 0.0
        erased = 0
        for x in range(scratch_rect.left, scratch_rect.right):
            for y in range(scratch_rect.top, scratch_rect.bottom):
                if erase_area.get_at((x, y)).a == 0:
                    erased += 1
        return erased / (scratch_rect.width * scratch_rect.height)

    def start_new_ticket() -> bool:
        nonlocal balance, base_image, cover_image, back_image, scratch_rect, erase_area, ticket, revealed, scratch_ratio, change_text, change_until, celebration_started_at, celebration_particles, info_scroll_offset, ticket_angle, ticket_pitch, ticket_zoom
        ticket_type = get_ticket_type(selected_face_value)
        draw_loading_screen()
        visual = generate_ticket_visual(
            ticket_type.face_value,
            ticket_id=selected_ticket_id,
            theme_index=selected_theme_index,
            target_size=(ticket_width * TICKET_RENDER_SCALE, ticket_height * TICKET_RENDER_SCALE),
        )
        try:
            balance = charge_scratch_card(username, face_value=ticket_type.face_value)
        except AccountError as exc:
            set_status(str(exc), "red")
            return False

        base_image = pygame.image.load(visual.base_path).convert()
        cover_image = pygame.image.load(visual.cover_path).convert_alpha()
        back_image = fit_surface_to_canvas(pygame.image.load(visual.back_path).convert(), base_image.get_size())
        scratch_rect = pygame.Rect(*visual.scratch_rect)
        base_image, cover_image, back_image, scratch_rect = crop_ticket_surfaces(base_image, cover_image, back_image, scratch_rect)
        erase_area = pygame.Surface(cover_image.get_size(), pygame.SRCALPHA)
        ticket = TicketState(
            prize=visual.prize,
            face_value=visual.face_value,
            product_name=visual.product_name,
            max_prize=visual.max_prize,
            image_path=visual.base_path,
            cover_path=visual.cover_path,
            back_path=visual.back_path,
            scratch_rect=tuple(scratch_rect),
            ticket_id=visual.ticket_id,
            theme_index=visual.theme_index,
            visual_style=visual.visual_style,
            rule_summary=visual.rule_summary,
            game_rule=visual.game_rule,
            play_numbers=visual.play_numbers,
            win_numbers=visual.win_numbers,
        )
        reset_ticket_surfaces()
        revealed = False
        scratch_ratio = 0.0
        change_text = f"-¥{ticket_type.face_value}"
        change_until = pygame.time.get_ticks() + 1400
        celebration_started_at = -FIREWORK_DURATION_MS
        celebration_particles = []
        info_scroll_offset = 0
        ticket_angle = 0.0
        ticket_pitch = 0.0
        ticket_zoom = max(
            TICKET_ZOOM_MIN,
            min(
                TICKET_ZOOM_MAX,
                min((ticket_width * 0.78) / base_image.get_width(), (ticket_height * 0.94) / base_image.get_height()),
            ),
        )
        set_status(f"{visual.product_name} 已生成", "green")
        return True

    def finish_ticket() -> None:
        nonlocal balance, revealed, scratch_ratio, change_text, change_until, celebration_started_at, celebration_particles
        if not ticket or revealed:
            return

        pygame.draw.rect(erase_area, (255, 255, 255, 0), scratch_rect)
        scratch_ratio = 1.0
        balance = claim_ticket_prize(username, ticket)
        revealed = True
        if ticket.prize > 0:
            change_text = f"+{format_yuan(ticket.prize)}"
            change_until = pygame.time.get_ticks() + 1800
            celebration_started_at = pygame.time.get_ticks()
            celebration_particles = build_celebration_particles(ticket_width + side_width, ticket_height)
            set_status(f"中奖 {format_yuan(ticket.prize)}", "red")
        else:
            change_text = ""
            set_status("未中奖", "muted")

    def render_text(
        surface,
        text: str,
        font,
        color,
        pos: tuple[int, int],
        max_width: int | None = None,
        max_height: int | None = None,
    ) -> int:
        x, y = pos
        line_height = font.get_linesize()
        bottom = y + max_height if max_height is not None else None
        if max_width is None:
            if bottom is not None and y + line_height > bottom:
                return bottom
            surface.blit(font.render(text, True, color), (x, y))
            return y + line_height

        def draw_wrapped_line(line_text: str) -> bool:
            nonlocal y
            if bottom is not None and y + line_height > bottom:
                if y < bottom:
                    ellipsis = "..."
                    clipped = line_text
                    while clipped and font.size(clipped + ellipsis)[0] > max_width:
                        clipped = clipped[:-1]
                    final_text = clipped + ellipsis if clipped else ellipsis
                    if font.size(final_text)[0] <= max_width:
                        surface.blit(font.render(final_text, True, color), (x, y))
                y = bottom
                return False
            surface.blit(font.render(line_text, True, color), (x, y))
            y += line_height
            return True

        paragraphs = str(text).splitlines() or [""]
        for paragraph_index, paragraph in enumerate(paragraphs):
            line = ""
            for char in paragraph:
                candidate = line + char
                if font.size(candidate)[0] <= max_width:
                    line = candidate
                    continue
                if not draw_wrapped_line(line):
                    return y
                line = char
            if line:
                if not draw_wrapped_line(line):
                    return y
            elif paragraph_index < len(paragraphs) - 1:
                if not draw_wrapped_line(""):
                    return y
            if paragraph_index < len(paragraphs) - 1:
                y += max(2, line_height // 4)
                if bottom is not None and y >= bottom:
                    y = bottom
                    return y
        return y

    def draw_aa_round_rect(
        target: "pygame.Surface",
        rect: pygame.Rect,
        fill: tuple[int, int, int] | tuple[int, int, int, int],
        radius: int,
        border: tuple[int, int, int] | tuple[int, int, int, int] | None = None,
        border_width: int = 1,
    ) -> None:
        if rect.width <= 0 or rect.height <= 0:
            return
        scale = 3
        scaled_rect = pygame.Rect(0, 0, rect.width * scale, rect.height * scale)
        layer = pygame.Surface(scaled_rect.size, pygame.SRCALPHA)
        pygame.draw.rect(layer, fill, scaled_rect, border_radius=radius * scale)
        if border and border_width > 0:
            pygame.draw.rect(layer, border, scaled_rect, width=border_width * scale, border_radius=radius * scale)
        target.blit(pygame.transform.smoothscale(layer, rect.size), rect.topleft)

    def draw_soft_shadow(rect: pygame.Rect, radius: int = 14) -> None:
        for offset, alpha, grow in ((5, 22, 2), (10, 10, 5)):
            shadow_rect = rect.inflate(grow * 2, grow * 2)
            shadow_rect.move_ip(offset - grow, offset - grow)
            shadow = pygame.Surface(shadow_rect.size, pygame.SRCALPHA)
            draw_aa_round_rect(shadow, shadow.get_rect(), (22, 34, 51, alpha), radius + grow)
            screen.blit(shadow, shadow_rect.topleft)

    def draw_panel(rect: pygame.Rect, radius: int = 14, fill_key: str = "panel") -> None:
        draw_soft_shadow(rect, radius)
        draw_aa_round_rect(screen, rect, colors[fill_key], radius, colors["border"], 1)

    def draw_button(rect: pygame.Rect, label: str, enabled: bool = True, variant: str = "primary") -> None:
        mouse_pos = pygame.mouse.get_pos()
        hovered = enabled and rect.collidepoint(mouse_pos)
        if not enabled:
            fill = colors["button_disabled"]
            border = colors["button_disabled"]
        elif variant == "gold":
            fill = colors["gold_hover"] if hovered else colors["gold"]
            border = colors["gold_hover"]
        elif variant == "light":
            fill = (232, 238, 245) if hovered else colors["panel_soft"]
            border = colors["border"]
        else:
            fill = colors["button_hover"] if hovered else colors["button"]
            border = colors["button_hover"]

        if enabled:
            draw_soft_shadow(rect, 19)
        draw_aa_round_rect(screen, rect, fill, 19, border, 1)
        highlight = pygame.Rect(rect.x + 2, rect.y + 2, rect.width - 4, max(10, rect.height // 2))
        draw_aa_round_rect(screen, highlight, (*blend_color(fill, colors["white"], 0.12), 72), 17)
        text_color = colors["text"] if variant in ("gold", "light") and enabled else colors["white"]
        text_font = fit_pygame_font(label, rect.width - 26, 20, 15, True)
        text = text_font.render(label, True, text_color)
        screen.blit(text, text.get_rect(center=rect.center))

    def draw_side_panel() -> None:
        nonlocal info_scroll_offset, info_content_height
        now = pygame.time.get_ticks()
        side_rect = pygame.Rect(ticket_width, 0, side_width, ticket_height)
        screen.fill(colors["side"], side_rect)

        title = font_large.render(APP_TITLE, True, colors["text"])
        screen.blit(title, (ticket_width + 28, 26))

        account_rect = pygame.Rect(ticket_width + 24, 76, side_width - 48, 144)
        draw_panel(account_rect, 18)
        render_text(screen, f"用户：{username}", font_body, colors["text"], (account_rect.x + 18, account_rect.y + 18), account_rect.width - 36)
        render_text(screen, "当前余额", font_small, colors["muted"], (account_rect.x + 18, account_rect.y + 54), account_rect.width - 36)
        balance_rect = pygame.Rect(account_rect.x + 18, account_rect.y + 82, account_rect.width - 36, 46)
        draw_aa_round_rect(screen, balance_rect, colors["gold_soft"], 20, colors["gold"], 1)
        shine_rect = pygame.Rect(balance_rect.x + 2, balance_rect.y + 2, balance_rect.width - 4, balance_rect.height // 2)
        draw_aa_round_rect(screen, shine_rect, (255, 255, 255, 74), 18)
        balance_text = format_yuan(balance)
        change_surface = None
        change_gap = 0
        if change_text and now < change_until:
            change_color = colors["green"] if change_text.startswith("+") else colors["red"]
            change_surface = fit_pygame_font(change_text, 92, 19, 14, True).render(change_text, True, change_color)
            change_gap = change_surface.get_width() + 18
        balance_max_width = max(86, balance_rect.width - 28 - change_gap)
        balance_surface = fit_pygame_font(balance_text, balance_max_width, 31, 16, True).render(balance_text, True, colors["gold_text"])
        screen.blit(balance_surface, balance_surface.get_rect(midleft=(balance_rect.x + 14, balance_rect.centery)))
        if change_surface:
            screen.blit(change_surface, change_surface.get_rect(midright=(balance_rect.right - 14, balance_rect.centery)))

        draw_panel(selector_rect, 16)
        render_text(screen, "固定彩票风格", font_small, colors["muted"], (selector_rect.x + 18, selector_rect.y + 16))
        next_ticket_type = get_ticket_type(selected_face_value)
        selected_style_name = ticket.product_name if ticket else next_ticket_type.name
        info_y = selector_rect.y + 48
        active_name = ticket.product_name if ticket else next_ticket_type.name
        active_face = ticket.face_value if ticket else next_ticket_type.face_value
        active_rule = ticket.rule_summary if ticket and ticket.rule_summary else "随机生成票面"
        active_game_rule = ticket.game_rule if ticket else next_ticket_type.description
        active_game = active_game_rule.strip() or summarize_game_rule(active_game_rule)
        selector_text_bottom = selector_rect.bottom - 18
        next_source = "本地模拟票面"
        view_rect = pygame.Rect(selector_rect.x + 18, info_y, selector_rect.width - 36, max(1, selector_text_bottom - info_y))
        content = pygame.Surface((view_rect.width, 1600), pygame.SRCALPHA)
        content.fill((0, 0, 0, 0))
        content_y = 0
        content_y = render_text(content, f"本张：{active_name} / {active_face}元", font_body, colors["text"], (0, content_y), view_rect.width)
        content_y = render_text(content, f"类型：{active_rule}", font_small, colors["muted"], (0, content_y + 6), view_rect.width)
        if active_game:
            content_y = render_text(content, f"玩法：{active_game}", font_small, colors["muted"], (0, content_y + 6), view_rect.width)
        content_y = render_text(content, f"下张固定：{selected_style_name}，{next_source}", font_small, colors["muted"], (0, content_y + 6), view_rect.width)
        info_content_height = max(0, min(content.get_height(), content_y))
        max_scroll = max(0, info_content_height - view_rect.height)
        info_scroll_offset = max(0, min(info_scroll_offset, max_scroll))
        previous_clip = screen.get_clip()
        screen.set_clip(view_rect)
        screen.blit(content, (view_rect.x, view_rect.y - info_scroll_offset))
        screen.set_clip(previous_clip)
        if max_scroll > 0:
            bar_x = view_rect.right + 5
            track = pygame.Rect(bar_x, view_rect.y, 4, view_rect.height)
            pygame.draw.rect(screen, (214, 221, 230), track, border_radius=2)
            thumb_h = max(24, int(view_rect.height * view_rect.height / max(info_content_height, 1)))
            thumb_y = view_rect.y + int((view_rect.height - thumb_h) * info_scroll_offset / max_scroll)
            pygame.draw.rect(screen, colors["muted"], pygame.Rect(bar_x, thumb_y, 4, thumb_h), border_radius=2)

        result_rect = pygame.Rect(ticket_width + 24, 488, side_width - 48, 128)
        if revealed and ticket and ticket.prize > 0:
            result_fill = colors["red_soft"]
            result_border = colors["red"]
        elif revealed:
            result_fill = colors["panel_soft"]
            result_border = colors["border"]
        else:
            result_fill = colors["pending"]
            result_border = colors["gold"]
        draw_soft_shadow(result_rect, 16)
        pygame.draw.rect(screen, result_fill, result_rect, border_radius=16)
        pygame.draw.rect(screen, result_border, result_rect, 2, border_radius=16)
        render_text(screen, "本张结果", font_small, colors["muted"], (result_rect.x + 20, result_rect.y + 18))
        if revealed and ticket:
            if ticket.prize > 0:
                render_text(screen, "恭喜中奖", font_body, colors["red"], (result_rect.x + 20, result_rect.y + 48))
                prize_surface = font_balance.render(format_yuan(ticket.prize), True, colors["red"])
                screen.blit(prize_surface, (result_rect.x + 20, result_rect.y + 78))
            else:
                render_text(screen, "未中奖", font_large, colors["text"], (result_rect.x + 20, result_rect.y + 48))
                render_text(screen, "下次好运", font_body, colors["muted"], (result_rect.x + 20, result_rect.y + 88))
        else:
            render_text(screen, "待揭晓", font_large, colors["text"], (result_rect.x + 20, result_rect.y + 48))
            if status_text:
                render_text(screen, status_text, font_body, status_color, (result_rect.x + 20, result_rect.y + 88), result_rect.width - 40)

        draw_button(reselect_button, "重新选择", enabled=True, variant="light")
        draw_button(reveal_button, "查看结果", enabled=not revealed and ticket is not None)
        draw_button(next_button, f"再来一张 {selected_face_value}元", enabled=revealed and balance >= selected_face_value, variant="gold")

    def draw_win_markers(target: "pygame.Surface") -> None:
        if not revealed or not ticket or ticket.prize <= 0 or ticket.visual_style != "legacy":
            return

        for x, y, width, height in build_win_marker_rects(ticket):
            rect = pygame.Rect(scratch_rect.x + x, scratch_rect.y + y, width, height)
            pygame.draw.ellipse(target, colors["red"], rect, 4)

    def draw_celebration(now: int) -> None:
        if now - celebration_started_at > FIREWORK_DURATION_MS or not celebration_particles:
            return

        overlay = pygame.Surface((ticket_width + side_width, ticket_height), pygame.SRCALPHA)
        gravity = 420.0
        for particle in celebration_particles:
            age_ms = now - celebration_started_at - particle.birth_delay_ms
            if age_ms < 0 or age_ms > particle.life_ms:
                continue

            seconds = age_ms / 1000.0
            progress = age_ms / particle.life_ms
            alpha = max(0, min(255, int(255 * (1.0 - progress))))
            x = particle.x + particle.vx * seconds
            y = particle.y + particle.vy * seconds + 0.5 * gravity * seconds * seconds
            trail_x = x - particle.vx * 0.045
            trail_y = y - (particle.vy + gravity * seconds) * 0.045
            rgba = (*particle.color, alpha)
            pygame.draw.line(overlay, rgba, (trail_x, trail_y), (x, y), max(1, particle.size // 2))
            pygame.draw.circle(overlay, rgba, (int(x), int(y)), particle.size)

        pulse = max(0, min(255, int(210 * (1.0 - (now - celebration_started_at) / FIREWORK_DURATION_MS))))
        left_origin = (34, ticket_height - 120)
        right_origin = (ticket_width + side_width - 34, ticket_height - 120)
        pygame.draw.circle(overlay, (*colors["gold"], pulse), left_origin, 18)
        pygame.draw.circle(overlay, (*colors["gold"], pulse), right_origin, 18)
        pygame.draw.polygon(
            overlay,
            (*colors["red"], pulse),
            [(left_origin[0] + 4, left_origin[1] - 8), (left_origin[0] + 46, left_origin[1] - 28), (left_origin[0] + 8, left_origin[1] + 8)],
        )
        pygame.draw.polygon(
            overlay,
            (*colors["red"], pulse),
            [(right_origin[0] - 4, right_origin[1] - 8), (right_origin[0] - 46, right_origin[1] - 28), (right_origin[0] - 8, right_origin[1] + 8)],
        )
        screen.blit(overlay, (0, 0))

    def ticket_angle_normalized() -> float:
        return normalize_ticket_angle(ticket_angle)

    def ticket_front_scratchable() -> bool:
        return math.cos(ticket_angle_normalized()) >= TICKET_FRONT_SCRATCH_COS_MIN and abs(ticket_pitch) <= TICKET_PITCH_LIMIT

    def compose_front_surface() -> "pygame.Surface":
        front = base_image.copy()
        masked = cover_image.copy()
        masked.blit(erase_area, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        front.blit(masked, (0, 0))
        draw_win_markers(front)
        return front

    def draw_rotated_ticket(source: "pygame.Surface", angle: float, pitch: float) -> None:
        nonlocal ticket_display_rect
        source_width, source_height = source.get_size()
        center_x = ticket_width // 2
        center_y = ticket_height // 2
        _flat_left, _flat_top, width, height = flat_ticket_display_rect(
            (source_width, source_height),
            ticket_zoom,
            (ticket_width, ticket_height),
        )
        if ticket_uses_flat_render(angle, pitch):
            if (width, height) != (source_width, source_height):
                source = pygame.transform.smoothscale(source, (width, height))
            ticket_display_rect = pygame.Rect(_flat_left, _flat_top, width, height)
            shadow_width = max(80, int(ticket_display_rect.width * 0.94))
            shadow = pygame.Surface((shadow_width + 40, 44), pygame.SRCALPHA)
            pygame.draw.ellipse(shadow, (0, 0, 0, 76), shadow.get_rect())
            screen.blit(
                shadow,
                (ticket_display_rect.centerx - shadow.get_width() // 2, min(ticket_height - 54, ticket_display_rect.bottom - 18)),
            )
            screen.blit(source, ticket_display_rect)
            return

        half_width = width / 2
        half_height = height / 2
        camera_distance = TICKET_CAMERA_DISTANCE
        sin_yaw = math.sin(angle)
        cos_yaw = math.cos(angle)
        sin_pitch = math.sin(pitch)
        cos_pitch = math.cos(pitch)

        def project(display_x: float, display_y: float) -> tuple[float, float, float]:
            x = display_x - half_width
            y = display_y - half_height
            yaw_x = x * cos_yaw
            yaw_z = -x * sin_yaw
            pitch_y = y * cos_pitch - yaw_z * sin_pitch
            pitch_z = y * sin_pitch + yaw_z * cos_pitch
            scale = camera_distance / max(220.0, camera_distance + pitch_z)
            return center_x + yaw_x * scale, center_y + pitch_y * scale, scale

        corners = [project(0, 0), project(width, 0), project(0, height), project(width, height)]
        min_x = min(point[0] for point in corners)
        max_x = max(point[0] for point in corners)
        min_y = min(point[1] for point in corners)
        max_y = max(point[1] for point in corners)
        ticket_display_rect = pygame.Rect(
            int(min_x),
            int(min_y),
            max(1, int(max_x - min_x)),
            max(1, int(max_y - min_y)),
        )

        shadow_width = max(80, int(ticket_display_rect.width * 0.94))
        shadow_height = max(18, int(42 * (0.55 + 0.45 * abs(cos_yaw) * abs(cos_pitch))))
        shadow = pygame.Surface((shadow_width + 40, shadow_height + 20), pygame.SRCALPHA)
        pygame.draw.ellipse(shadow, (0, 0, 0, 82), shadow.get_rect())
        shadow_x = ticket_display_rect.centerx - shadow.get_width() // 2
        shadow_y = min(ticket_height - shadow.get_height() - 10, ticket_display_rect.bottom - 18)
        screen.blit(shadow, (shadow_x, shadow_y))

        strip_width = max(TICKET_3D_STRIP_WIDTH, int(TICKET_3D_STRIP_WIDTH / max(ticket_zoom, 0.2)))
        strip_starts = list(range(0, source_width, strip_width))
        if sin_yaw < 0:
            strip_starts.reverse()
        for source_x in strip_starts:
            actual_width = min(strip_width, source_width - source_x)
            display_x0 = source_x * ticket_zoom
            display_x1 = (source_x + actual_width) * ticket_zoom
            display_mid_x = (display_x0 + display_x1) / 2
            x0, _mid_y0, _scale0 = project(display_x0, half_height)
            x1, _mid_y1, _scale1 = project(display_x1, half_height)
            _top_x, top_y, _top_scale = project(display_mid_x, 0)
            _bottom_x, bottom_y, _bottom_scale = project(display_mid_x, height)
            dest_width = max(1, int(abs(x1 - x0)) + 1)
            dest_height = max(1, int(abs(bottom_y - top_y)) + 1)
            dest_x = int(min(x0, x1))
            dest_y = int(min(top_y, bottom_y))
            strip = source.subsurface((source_x, 0, actual_width, source_height))
            screen.blit(pygame.transform.smoothscale(strip, (dest_width, dest_height)), (dest_x, dest_y))

    def draw_ticket() -> None:
        screen.fill(colors["bg"], pygame.Rect(0, 0, ticket_width, ticket_height))
        normalized_angle = ticket_angle_normalized()
        front_visible, render_angle = visible_ticket_render_state(normalized_angle)
        if front_visible:
            surface = compose_front_surface()
        else:
            surface = back_image
        draw_rotated_ticket(surface, render_angle, ticket_pitch)

    def screen_to_ticket_point(pos: tuple[int, int]) -> tuple[int, int] | None:
        if not ticket_front_scratchable():
            return None
        front_visible, render_angle = visible_ticket_render_state(ticket_angle_normalized())
        if not front_visible:
            return None
        source_width, source_height = base_image.get_size()
        if ticket_uses_flat_render(render_angle, ticket_pitch):
            return screen_to_flat_ticket_source_point(
                pos,
                (source_width, source_height),
                ticket_zoom,
                (ticket_width, ticket_height),
            )
        return screen_to_ticket_source_point(
            pos,
            (source_width, source_height),
            ticket_zoom,
            render_angle,
            ticket_pitch,
            (ticket_width, ticket_height),
        )

    def handle_drag(pos: tuple[int, int]) -> None:
        nonlocal last_pos
        if not scratch_rect.collidepoint(pos) or revealed:
            last_pos = pos
            return

        brush_radius = max(12, int(22 / max(ticket_zoom, 0.1)))
        if last_pos and scratch_rect.collidepoint(last_pos):
            pygame.draw.line(erase_area, (255, 255, 255, 0), last_pos, pos, brush_radius * 2)
        pygame.draw.circle(erase_area, (255, 255, 255, 0), pos, brush_radius)
        last_pos = pos

    def adjust_ticket_zoom(direction: int) -> None:
        nonlocal ticket_zoom
        ticket_zoom = max(TICKET_ZOOM_MIN, min(TICKET_ZOOM_MAX, ticket_zoom + direction * TICKET_ZOOM_STEP))

    if not start_new_ticket():
        pygame.quit()
        messagebox.showinfo("提示", "余额不足，无法开始游戏。")
        return None

    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.MOUSEWHEEL:
                if selector_rect.collidepoint(pygame.mouse.get_pos()):
                    detail_height = max(1, selector_rect.bottom - 18 - (selector_rect.y + 48))
                    max_scroll = max(0, info_content_height - detail_height)
                    info_scroll_offset = max(0, min(max_scroll, info_scroll_offset - event.y * 34))
                elif pygame.mouse.get_pos()[0] < ticket_width:
                    adjust_ticket_zoom(1 if event.y > 0 else -1)
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if reselect_button.collidepoint(event.pos):
                    result_action = "reselect"
                    running = False
                elif reveal_button.collidepoint(event.pos) and not revealed:
                    finish_ticket()
                elif next_button.collidepoint(event.pos) and revealed:
                    start_new_ticket()
                else:
                    local_pos = screen_to_ticket_point(event.pos)
                    if local_pos and scratch_rect.collidepoint(local_pos) and not revealed:
                        dragging = True
                        last_pos = local_pos
                        handle_drag(local_pos)
                    elif event.pos[0] < ticket_width:
                        rotating_ticket = True
                        last_rotate_pos = event.pos
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button in (4, 5):
                if selector_rect.collidepoint(event.pos):
                    detail_height = max(1, selector_rect.bottom - 18 - (selector_rect.y + 48))
                    max_scroll = max(0, info_content_height - detail_height)
                    direction = -1 if event.button == 4 else 1
                    info_scroll_offset = max(0, min(max_scroll, info_scroll_offset + direction * 34))
                elif event.pos[0] < ticket_width:
                    adjust_ticket_zoom(1 if event.button == 4 else -1)
            elif event.type == pygame.MOUSEMOTION:
                if dragging:
                    local_pos = screen_to_ticket_point(event.pos)
                    if local_pos:
                        handle_drag(local_pos)
                    else:
                        last_pos = None
                elif rotating_ticket and last_rotate_pos is not None:
                    delta_x = event.pos[0] - last_rotate_pos[0]
                    delta_y = event.pos[1] - last_rotate_pos[1]
                    ticket_angle += delta_x * TICKET_ROTATION_SENSITIVITY
                    ticket_angle = normalize_ticket_angle(ticket_angle)
                    ticket_pitch = max(-TICKET_PITCH_LIMIT, min(TICKET_PITCH_LIMIT, ticket_pitch + delta_y * TICKET_PITCH_SENSITIVITY))
                    last_rotate_pos = event.pos
            elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                if dragging:
                    dragging = False
                    last_pos = None
                    if not revealed:
                        scratch_ratio = calculate_scratch_ratio()
                        if scratch_ratio >= AUTO_REVEAL_RATIO:
                            finish_ticket()
                if rotating_ticket:
                    rotating_ticket = False
                    last_rotate_pos = None

        draw_ticket()
        draw_side_panel()
        draw_celebration(pygame.time.get_ticks())
        pygame.display.flip()
        clock.tick(60)

    pygame.quit()
    return result_action


if __name__ == "__main__":
    if "--smoke-test" in sys.argv:
        raise SystemExit(run_smoke_test())
    start_animation()
