#VZOELFOX'S
"""VBot Python configuration helpers and defaults."""

from __future__ import annotations

import os
from typing import List


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


# ==============================================
# MUSIC SYSTEM SETTINGS
# ==============================================

MUSIC_ENABLED = _get_bool("MUSIC_ENABLED", True)
DOWNLOAD_PATH = os.getenv("DOWNLOAD_PATH", "downloads/")
MAX_FILE_SIZE = int(os.getenv("MAX_FILE_SIZE", str(50 * 1024 * 1024)))  # 50MB
AUDIO_QUALITY = os.getenv("AUDIO_QUALITY", "bestaudio[ext=m4a]/bestaudio")

# YouTube Cookies (REQUIRED - helps bypass bot detection)
# Option 1: Use browser cookies (recommended for local)
YOUTUBE_COOKIES_FROM_BROWSER = os.getenv("YOUTUBE_COOKIES_FROM_BROWSER", "")
# Option 2: Use cookies file (recommended for server)
YOUTUBE_COOKIES_FILE = os.getenv("YOUTUBE_COOKIES_FILE", "youtube_cookies.txt")

# Assistant Account (for voice chat streaming)
# Generate using: .gensession command in bot PM or run genstring.py
# Leave empty ("") to disable streaming mode (download mode only)
STRING_SESSION = os.getenv("STRING_SESSION", "")

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


# ==============================================
# PREMIUM EMOJI MAPPINGS
# ==============================================

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
