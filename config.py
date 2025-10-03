#VZOELFOX'S
"""VBot Python configuration helpers and defaults."""

from __future__ import annotations

import os
from pathlib import Path
from typing import List


# ==============================================
# ENVIRONMENT LOADING
# ==============================================


def _load_env_file(path: Path) -> None:
    """Populate ``os.environ`` with values from a .env file if present."""

    if not path.is_file():
        return

    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return

    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()

        if "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        if not key or key.startswith("#"):
            continue

        value = value.strip()
        if value and value[0] in {'"', "'"} and value[-1] == value[0]:
            value = value[1:-1]
            try:
                value = bytes(value, "utf-8").decode("unicode_escape")
            except UnicodeDecodeError:
                pass
        else:
            if "#" in value:
                value = value.split("#", 1)[0].rstrip()

        os.environ.setdefault(key, value)


_current_dir = Path(__file__).resolve().parent
_env_candidates = []

env_file_override = os.getenv("ENV_FILE")
if env_file_override:
    _env_candidates.append(Path(env_file_override).expanduser())

_env_candidates.extend(
    [
        Path(".env").resolve(),
        _current_dir / ".env",
    ]
)

_visited_env_paths = set()
for candidate in _env_candidates:
    try:
        resolved = candidate.resolve(strict=False)
    except OSError:
        continue

    if resolved in _visited_env_paths:
        continue

    _visited_env_paths.add(resolved)
    _load_env_file(resolved)


# ==============================================
# HELPER FUNCTIONS
# ==============================================

def _get_bool(name: str, default: bool) -> bool:
    """Return a boolean from environment variables."""
    value = os.getenv(name)
    if value is None:
        return default

    value = value.strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    return default


def _parse_int_list(value: str | None, *, separator: str = ",") -> List[int]:
    """Parse a comma-separated list of integers."""
    if not value:
        return []

    result: List[int] = []
    for raw in value.split(separator):
        raw = raw.strip()
        if not raw:
            continue
        try:
            result.append(int(raw))
        except ValueError:
            continue
    return result


# ==============================================
# TELEGRAM BOT CONFIGURATION
# ==============================================

# Get your bot token from @BotFather
BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")

# Telegram API credentials
API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "YOUR_API_HASH_HERE")


# ==============================================
# USER AUTHORIZATION
# ==============================================

# Your Telegram User ID (owner)
OWNER_ID = int(os.getenv("OWNER_ID", "0"))

# Developer IDs (can use . prefix commands)
_developer_ids_from_env = _parse_int_list(os.getenv("DEVELOPER_IDS"))
if OWNER_ID and OWNER_ID not in _developer_ids_from_env:
    _developer_ids_from_env.append(OWNER_ID)
DEVELOPER_IDS = _developer_ids_from_env

# Admin chat IDs (can use / prefix commands)
ADMIN_CHAT_IDS = _parse_int_list(os.getenv("ADMIN_CHAT_IDS"))

# Log group/chat ID (for bot logs and error tracking)
LOG_CHAT_ID = int(os.getenv("LOG_CHAT_ID", "0"))


# ==============================================
# MUSIC SYSTEM SETTINGS
# ==============================================

MUSIC_ENABLED = _get_bool("MUSIC_ENABLED", True)
DOWNLOAD_PATH = os.getenv("DOWNLOAD_PATH", "downloads/")
MAX_FILE_SIZE = int(os.getenv("MAX_FILE_SIZE", str(50 * 1024 * 1024)))  # 50MB
AUDIO_QUALITY = os.getenv("AUDIO_QUALITY", "bestaudio[ext=m4a]/bestaudio")
MUSIC_LOGO_FILE_ID = os.getenv("MUSIC_LOGO_FILE_ID", "6269447591602883849")

# ==============================================
# ASSISTANT ACCOUNT (Voice Chat Streaming)
# ==============================================
# Assistant account is a separate Telegram user account that will:
# - Join voice chats in groups
# - Stream audio/video when you use /play or /vplay commands
# - Handle all voice chat operations (bot can't join VC directly)
#
# How to get STRING_SESSION:
# 1. Use /gensession command in bot private chat
# 2. Or run: python genstring.py (if available)
# 3. Enter API_ID, API_HASH, phone number, and OTP
# 4. Copy the session string to .env file
#
# IMPORTANT:
# - Use a DIFFERENT phone number from the bot owner
# - This account will appear in voice chats
# - Keep this session string SECRET (full account access)
# - Leave empty ("") to disable voice chat streaming (download-only mode)
STRING_SESSION = os.getenv("STRING_SESSION", "")

# ==============================================
# YOUTUBE COOKIES (Bypass Age Restriction & Bot Detection)
# ==============================================
# YouTube may block requests from bots/servers. Cookies help bypass this.
#
# Option 1: Browser Cookies (Recommended for local development)
# - Automatically extract cookies from your browser
# - Supported: chrome, firefox, edge, opera, brave, etc.
# - Example: YOUTUBE_COOKIES_FROM_BROWSER="chrome"
YOUTUBE_COOKIES_FROM_BROWSER = os.getenv("YOUTUBE_COOKIES_FROM_BROWSER", "")

# Option 2: Cookies File (Recommended for production/server)
# - Export cookies from browser to file
# - Use browser extension: "Get cookies.txt" or "cookies.txt"
# - Save as youtube_cookies.txt in project root
# - Example: YOUTUBE_COOKIES_FILE="youtube_cookies.txt"
YOUTUBE_COOKIES_FILE = os.getenv("YOUTUBE_COOKIES_FILE", "youtube_cookies.txt")

# NOTE: If both are empty, yt-dlp will use default (may fail on restricted videos)

# Voice chat behaviour
VOICE_CHAT_AUTO_START = _get_bool("VOICE_CHAT_AUTO_START", True)  # Automatically start VC if none active
# Join as specific account/channel (username, id, or "me"). Leave None to use default.
VOICE_CHAT_JOIN_AS = os.getenv("VOICE_CHAT_JOIN_AS") or None


# ==============================================
# FEATURE TOGGLES
# ==============================================

ENABLE_LOCK_SYSTEM = _get_bool("ENABLE_LOCK_SYSTEM", True)
ENABLE_PREMIUM_EMOJI = _get_bool("ENABLE_PREMIUM_EMOJI", True)
ENABLE_TAG_SYSTEM = _get_bool("ENABLE_TAG_SYSTEM", True)
ENABLE_WELCOME_SYSTEM = _get_bool("ENABLE_WELCOME_SYSTEM", True)
ENABLE_GITHUB_SYNC = _get_bool("ENABLE_GITHUB_SYNC", False)  # Set to True if you want auto backup
ENABLE_PRIVACY_SYSTEM = _get_bool("ENABLE_PRIVACY_SYSTEM", True)
ENABLE_PUBLIC_COMMANDS = _get_bool("ENABLE_PUBLIC_COMMANDS", True)


# ==============================================
# COMMAND PREFIXES
# ==============================================

PREFIX_ADMIN = os.getenv("PREFIX_ADMIN", "/")     # For admin commands
PREFIX_DEV = os.getenv("PREFIX_DEV", ".")         # For developer commands
PREFIX_PUBLIC = os.getenv("PREFIX_PUBLIC", "#")   # For public commands


# ==============================================
# RATE LIMITING
# ==============================================

TAG_DELAY = float(os.getenv("TAG_DELAY", "2.0"))  # Seconds between tags
MUSIC_COOLDOWN = int(os.getenv("MUSIC_COOLDOWN", "5"))  # Seconds cooldown for music commands


# ==============================================
# GITHUB SYNC (Optional - for data backup)
# ==============================================

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")  # Your GitHub personal access token
GITHUB_REPOSITORY = os.getenv("GITHUB_REPOSITORY", "")  # Format: username/repo
GITHUB_BRANCH = os.getenv("GITHUB_BRANCH", "main")
GITHUB_AUTO_COMMIT = _get_bool("GITHUB_AUTO_COMMIT", True)
GITHUB_AUTO_PUSH = _get_bool("GITHUB_AUTO_PUSH", False)
GITHUB_AUTO_PUSH_INTERVAL = int(os.getenv("GITHUB_AUTO_PUSH_INTERVAL", "1200"))


# ==============================================
# PREMIUM EMOJI MAPPINGS
# ==============================================

PREMIUM_EMOJI_MAPPING_FILE = os.getenv(
    "PREMIUM_EMOJI_MAPPING_FILE",
    "database/premium_emoji_map.json",
)

PREMIUM_EMOJI_MAP = {
    "🎵": "🎵",
    "⏸️": "⏸️",
    "▶️": "▶️",
    "⏭️": "⏭️",
    "🔊": "🔊",
    "❤️": "❤️‍🔥",
    "🔥": "🔥",
    "⭐": "⭐",
    "🎉": "🎊",
    "👍": "👍",
    "😍": "🥰",
    "💯": "💯",
}


# ==============================================
# VALIDATION
# ==============================================

def validate_config() -> bool:
    """Validate configuration before starting bot."""
    errors = []

    if BOT_TOKEN == "YOUR_BOT_TOKEN_HERE" or not BOT_TOKEN.strip():
        errors.append("❌ BOT_TOKEN belum diisi! Dapatkan dari @BotFather")

    if API_ID <= 0 or API_HASH in {"", "YOUR_API_HASH_HERE"}:
        errors.append("❌ API_ID/API_HASH belum diisi! Ambil dari https://my.telegram.org")

    if OWNER_ID == 0:
        errors.append("❌ OWNER_ID belum diisi! Isi dengan Telegram User ID kamu")

    if not DEVELOPER_IDS:
        errors.append("⚠️  DEVELOPER_IDS belum diisi (optional)")

    if errors:
        print("\n🚨 CONFIGURATION ERRORS:\n")
        for error in errors:
            print(f"  {error}")
        print("\n📝 Edit environment variables atau config.py untuk mengisi konfigurasi!\n")
        return False

    print("✅ Configuration validated successfully!")
    return True


# ==============================================
# LOCAL CONFIGURATION OVERRIDE
# ==============================================

# Import local configuration if exists (gitignored, for sensitive data)
try:
    from config_local import *  # type: ignore
    print("✅ Loaded config_local.py (local overrides)")
except ImportError:
    pass  # config_local.py not found, use defaults
