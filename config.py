#!/usr/bin/env python3
"""
VBot Python Configuration
Simple and straightforward - just edit the values below!

Author: VanZoel112
Version: 2.0.0 Python
"""

# ==============================================
# TELEGRAM BOT CONFIGURATION
# ==============================================

# Get your bot token from @BotFather
BOT_TOKEN = "8417614653:AAH2qRNOv2v2cAYrxbiVvI6woaf9WZxVEBE"

# Your Telegram API credentials (from vzl2 - no need to change)
API_ID = 29919905
API_HASH = "717957f0e3ae20a7db004d08b66bfd30"

# ==============================================
# USER AUTHORIZATION
# ==============================================

# Your Telegram User ID (owner)
OWNER_ID = 8024282347  # VanZoel112

# Developer IDs (can use . prefix commands)
DEVELOPER_IDS = [
    8024282347,  # VanZoel112
]

# Admin chat IDs (can use / prefix commands)
ADMIN_CHAT_IDS = [
    # Add your group/channel IDs here
]

# ==============================================
# MUSIC SYSTEM SETTINGS
# ==============================================

MUSIC_ENABLED = True
DOWNLOAD_PATH = "downloads/"
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
AUDIO_QUALITY = "bestaudio[ext=m4a]/bestaudio"

# YouTube Cookies (optional - helps bypass bot detection)
# You can use cookies file path or browser name (chrome, firefox, edge, etc)
YOUTUBE_COOKIES_FROM_BROWSER = ""  # e.g., "chrome" or "firefox"
YOUTUBE_COOKIES_FILE = ""  # e.g., "cookies.txt" (path to cookies file)

# ==============================================
# FEATURE TOGGLES
# ==============================================

ENABLE_LOCK_SYSTEM = True
ENABLE_PREMIUM_EMOJI = True
ENABLE_TAG_SYSTEM = True
ENABLE_WELCOME_SYSTEM = True
ENABLE_GITHUB_SYNC = False  # Set to True if you want auto backup
ENABLE_PRIVACY_SYSTEM = True
ENABLE_PUBLIC_COMMANDS = True

# ==============================================
# COMMAND PREFIXES
# ==============================================

PREFIX_ADMIN = "/"    # For admin commands
PREFIX_DEV = "."      # For developer commands
PREFIX_PUBLIC = "#"   # For public commands

# ==============================================
# RATE LIMITING
# ==============================================

TAG_DELAY = 2.0  # Seconds between tags
MUSIC_COOLDOWN = 5  # Seconds cooldown for music commands

# ==============================================
# GITHUB SYNC (Optional - for data backup)
# ==============================================

GITHUB_TOKEN = ""  # Your GitHub personal access token
GITHUB_REPOSITORY = ""  # Format: username/repo
GITHUB_BRANCH = "main"
GITHUB_AUTO_COMMIT = True

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

def validate_config():
    """Validate configuration before starting bot"""
    errors = []

    if BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        errors.append("❌ BOT_TOKEN belum diisi! Dapatkan dari @BotFather")

    if OWNER_ID == 0:
        errors.append("❌ OWNER_ID belum diisi! Isi dengan Telegram User ID kamu")

    if not DEVELOPER_IDS or DEVELOPER_IDS == [0]:
        errors.append("⚠️  DEVELOPER_IDS belum diisi (optional)")

    if errors:
        print("\n🚨 CONFIGURATION ERRORS:\n")
        for error in errors:
            print(f"  {error}")
        print("\n📝 Edit file config.py untuk mengisi konfigurasi!\n")
        return False

    print("✅ Configuration validated successfully!")
    return True