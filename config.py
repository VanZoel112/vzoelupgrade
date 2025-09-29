#!/usr/bin/env python3
"""
VBot Python Configuration
Centralized configuration management for all vbot features

Author: VanZoel112 (Converted from Node.js)
Version: 2.0.0 Python
"""

import os
from typing import Dict, List, Optional
from dataclasses import dataclass
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

@dataclass
class TelegramConfig:
    """Telegram API Configuration"""
    api_id: int
    api_hash: str
    bot_token: str
    session_name: str = "vbot_session"

@dataclass
class AuthConfig:
    """Authorization Configuration"""
    developer_ids: List[int]
    admin_chat_ids: List[int]
    owner_id: int

@dataclass
class MusicConfig:
    """Music System Configuration"""
    download_path: str = "downloads/"
    max_file_size: int = 50 * 1024 * 1024  # 50MB
    audio_quality: str = "best[height<=480]"
    enable_ytdlp: bool = True

@dataclass
class GitHubConfig:
    """GitHub Integration Configuration"""
    token: str
    repository: str
    branch: str = "main"
    auto_commit: bool = True

@dataclass
class VBotConfig:
    """Main VBot Configuration Container"""
    telegram: TelegramConfig
    auth: AuthConfig
    music: MusicConfig
    github: Optional[GitHubConfig] = None

    # Feature toggles
    enable_music: bool = True
    enable_lock_system: bool = True
    enable_premium_emoji: bool = True
    enable_tag_system: bool = True
    enable_welcome_system: bool = True
    enable_github_sync: bool = True
    enable_privacy_system: bool = True
    enable_public_commands: bool = True

    # System settings
    command_prefix_admin: str = "/"
    command_prefix_dev: str = "."
    command_prefix_public: str = "#"

    # Rate limiting
    tag_delay: float = 2.0  # seconds between tags
    music_cooldown: int = 5  # seconds

    # Emoji mappings (standard -> premium)
    premium_emoji_map: Dict[str, str] = None

    def __post_init__(self):
        """Initialize default emoji mappings"""
        if self.premium_emoji_map is None:
            self.premium_emoji_map = {
                "🎵": "🎵",  # Music note
                "⏸️": "⏸️",  # Pause
                "▶️": "▶️",  # Play
                "⏭️": "⏭️",  # Next
                "🔊": "🔊",  # Volume
                "❤️": "❤️‍🔥",  # Premium heart
                "🔥": "🔥",  # Fire
                "⭐": "⭐",  # Star
                "🎉": "🎊",  # Party
                "👍": "👍",  # Thumbs up
                "😍": "🥰",  # Love eyes
                "💯": "💯",  # Hundred points
            }

def load_config() -> VBotConfig:
    """Load configuration from environment variables"""

    # Telegram configuration
    telegram_config = TelegramConfig(
        api_id=int(os.getenv("TELEGRAM_API_ID", "0")),
        api_hash=os.getenv("TELEGRAM_API_HASH", ""),
        bot_token=os.getenv("TELEGRAM_BOT_TOKEN", ""),
        session_name=os.getenv("SESSION_NAME", "vbot_session")
    )

    # Auth configuration
    developer_ids = []
    dev_ids_str = os.getenv("DEVELOPER_IDS", "")
    if dev_ids_str:
        developer_ids = [int(x.strip()) for x in dev_ids_str.split(",")]

    admin_chat_ids = []
    admin_ids_str = os.getenv("ADMIN_CHAT_IDS", "")
    if admin_ids_str:
        admin_chat_ids = [int(x.strip()) for x in admin_ids_str.split(",")]

    auth_config = AuthConfig(
        developer_ids=developer_ids,
        admin_chat_ids=admin_chat_ids,
        owner_id=int(os.getenv("OWNER_ID", "0"))
    )

    # Music configuration
    music_config = MusicConfig(
        download_path=os.getenv("DOWNLOAD_PATH", "downloads/"),
        max_file_size=int(os.getenv("MAX_FILE_SIZE", str(50 * 1024 * 1024))),
        audio_quality=os.getenv("AUDIO_QUALITY", "best[height<=480]"),
        enable_ytdlp=os.getenv("ENABLE_YTDLP", "true").lower() == "true"
    )

    # GitHub configuration (optional)
    github_config = None
    github_token = os.getenv("GITHUB_TOKEN")
    github_repo = os.getenv("GITHUB_REPOSITORY")

    if github_token and github_repo:
        github_config = GitHubConfig(
            token=github_token,
            repository=github_repo,
            branch=os.getenv("GITHUB_BRANCH", "main"),
            auto_commit=os.getenv("GITHUB_AUTO_COMMIT", "true").lower() == "true"
        )

    return VBotConfig(
        telegram=telegram_config,
        auth=auth_config,
        music=music_config,
        github=github_config,

        # Feature toggles from environment
        enable_music=os.getenv("ENABLE_MUSIC", "true").lower() == "true",
        enable_lock_system=os.getenv("ENABLE_LOCK_SYSTEM", "true").lower() == "true",
        enable_premium_emoji=os.getenv("ENABLE_PREMIUM_EMOJI", "true").lower() == "true",
        enable_tag_system=os.getenv("ENABLE_TAG_SYSTEM", "true").lower() == "true",
        enable_welcome_system=os.getenv("ENABLE_WELCOME_SYSTEM", "true").lower() == "true",
        enable_github_sync=os.getenv("ENABLE_GITHUB_SYNC", "true").lower() == "true",
        enable_privacy_system=os.getenv("ENABLE_PRIVACY_SYSTEM", "true").lower() == "true",
        enable_public_commands=os.getenv("ENABLE_PUBLIC_COMMANDS", "true").lower() == "true",

        # Rate limiting
        tag_delay=float(os.getenv("TAG_DELAY", "2.0")),
        music_cooldown=int(os.getenv("MUSIC_COOLDOWN", "5"))
    )

# Global config instance
config = load_config()

# Validation
def validate_config(config: VBotConfig) -> List[str]:
    """Validate configuration and return list of errors"""
    errors = []

    if not config.telegram.api_id:
        errors.append("TELEGRAM_API_ID is required")

    if not config.telegram.api_hash:
        errors.append("TELEGRAM_API_HASH is required")

    if not config.telegram.bot_token:
        errors.append("TELEGRAM_BOT_TOKEN is required")

    if not config.auth.developer_ids:
        errors.append("At least one DEVELOPER_ID is required")

    if not config.auth.owner_id:
        errors.append("OWNER_ID is required")

    return errors