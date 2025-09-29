#!/usr/bin/env python3
"""
Premium Emoji Manager
Converts standard emojis to premium emojis if user has Telegram Premium

Author: VanZoel112
Version: 2.0.0 Python
"""

import asyncio
import logging
import re
from typing import Dict, Optional, List
from telethon.tl.types import User
from config import VBotConfig

logger = logging.getLogger(__name__)

class EmojiManager:
    """Manages premium emoji conversion and fallback"""

    def __init__(self, config: VBotConfig):
        self.config = config
        self.premium_emoji_map = config.premium_emoji_map.copy()
        self.user_premium_cache: Dict[int, bool] = {}
        self.cache_expiry = 3600  # 1 hour
        self.last_cache_update: Dict[int, float] = {}

    async def is_user_premium(self, client, user_id: int) -> bool:
        """Check if user has Telegram Premium"""
        try:
            # Check cache first
            import time
            current_time = time.time()

            if (user_id in self.user_premium_cache and
                user_id in self.last_cache_update and
                current_time - self.last_cache_update[user_id] < self.cache_expiry):
                return self.user_premium_cache[user_id]

            # Get user info
            user = await client.get_entity(user_id)
            is_premium = getattr(user, 'premium', False)

            # Update cache
            self.user_premium_cache[user_id] = is_premium
            self.last_cache_update[user_id] = current_time

            logger.debug(f"User {user_id} premium status: {is_premium}")
            return is_premium

        except Exception as e:
            logger.error(f"Error checking premium status for user {user_id}: {e}")
            return False

    def convert_to_premium_emoji(self, text: str, use_premium: bool = True) -> str:
        """Convert standard emojis to premium emojis in text"""
        if not use_premium or not self.config.enable_premium_emoji:
            return text

        converted_text = text
        for standard, premium in self.premium_emoji_map.items():
            converted_text = converted_text.replace(standard, premium)

        return converted_text

    async def process_message_emojis(self, client, message_text: str, user_id: int) -> str:
        """Process message emojis based on user's premium status"""
        if not self.config.enable_premium_emoji:
            return message_text

        try:
            is_premium = await self.is_user_premium(client, user_id)
            return self.convert_to_premium_emoji(message_text, is_premium)
        except Exception as e:
            logger.error(f"Error processing emojis for user {user_id}: {e}")
            return message_text

    def add_emoji_mapping(self, standard: str, premium: str):
        """Add new emoji mapping"""
        self.premium_emoji_map[standard] = premium
        logger.info(f"Added emoji mapping: {standard} -> {premium}")

    def remove_emoji_mapping(self, standard: str):
        """Remove emoji mapping"""
        if standard in self.premium_emoji_map:
            del self.premium_emoji_map[standard]
            logger.info(f"Removed emoji mapping for: {standard}")

    def get_emoji_mappings(self) -> Dict[str, str]:
        """Get all current emoji mappings"""
        return self.premium_emoji_map.copy()

    def get_available_premium_emojis(self) -> List[str]:
        """Get list of available premium emojis"""
        return list(self.premium_emoji_map.values())

    def get_standard_emojis(self) -> List[str]:
        """Get list of standard emojis that can be converted"""
        return list(self.premium_emoji_map.keys())

    async def clear_premium_cache(self, user_id: Optional[int] = None):
        """Clear premium status cache"""
        if user_id:
            self.user_premium_cache.pop(user_id, None)
            self.last_cache_update.pop(user_id, None)
        else:
            self.user_premium_cache.clear()
            self.last_cache_update.clear()

        logger.info(f"Cleared premium cache for user {user_id if user_id else 'all users'}")

    def create_emoji_showcase(self) -> str:
        """Create a showcase of available emoji conversions"""
        showcase = "🎨 **Premium Emoji Conversions:**\n\n"

        for standard, premium in self.premium_emoji_map.items():
            showcase += f"{standard} → {premium}\n"

        showcase += "\n💎 *Premium emojis are automatically used for Telegram Premium users*"
        return showcase

    def extract_emojis_from_text(self, text: str) -> List[str]:
        """Extract all emojis from text"""
        # Basic emoji regex pattern
        emoji_pattern = re.compile(
            "["
            "\U0001F600-\U0001F64F"  # emoticons
            "\U0001F300-\U0001F5FF"  # symbols & pictographs
            "\U0001F680-\U0001F6FF"  # transport & map symbols
            "\U0001F1E0-\U0001F1FF"  # flags (iOS)
            "\U00002702-\U000027B0"
            "\U000024C2-\U0001F251"
            "]+",
            flags=re.UNICODE
        )

        return emoji_pattern.findall(text)

    async def suggest_premium_alternatives(self, emoji: str) -> Optional[str]:
        """Suggest premium alternative for a given emoji"""
        return self.premium_emoji_map.get(emoji)

    def get_fallback_emoji(self, premium_emoji: str) -> Optional[str]:
        """Get standard fallback for a premium emoji"""
        for standard, premium in self.premium_emoji_map.items():
            if premium == premium_emoji:
                return standard
        return None

    async def test_emoji_conversion(self, test_text: str) -> Dict[str, str]:
        """Test emoji conversion for debugging"""
        result = {
            "original": test_text,
            "premium_converted": self.convert_to_premium_emoji(test_text, True),
            "extracted_emojis": self.extract_emojis_from_text(test_text),
            "mappings_used": []
        }

        for standard in self.premium_emoji_map:
            if standard in test_text:
                result["mappings_used"].append(f"{standard} -> {self.premium_emoji_map[standard]}")

        return result

    def update_premium_emoji_map(self, new_mappings: Dict[str, str]):
        """Update premium emoji mappings"""
        self.premium_emoji_map.update(new_mappings)
        logger.info(f"Updated {len(new_mappings)} emoji mappings")

    def reset_to_default_mappings(self):
        """Reset to default emoji mappings"""
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
        logger.info("Reset emoji mappings to default")