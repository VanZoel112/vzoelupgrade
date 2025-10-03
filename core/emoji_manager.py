#!/usr/bin/env python3
"""Premium Emoji Manager utilities."""

from __future__ import annotations

import json
import logging
import random
import re
import time
from pathlib import Path
from threading import Lock
from typing import Dict, List, Optional

from telethon.tl.types import User

import config

logger = logging.getLogger(__name__)


class EmojiManager:
    """Manages premium emoji conversion, persistence, and fallback."""

    def __init__(self) -> None:
        self.mapping_file_path = Path(config.PREMIUM_EMOJI_MAPPING_FILE).expanduser()
        self.premium_emoji_map: Dict[str, List[str]] = {}
        self.premium_pool: List[str] = []
        self.user_premium_cache: Dict[int, bool] = {}
        self.cache_expiry = 3600  # 1 hour
        self.last_cache_update: Dict[int, float] = {}
        self._storage_lock = Lock()
        self._conversion_pattern: Optional[re.Pattern[str]] = None

        self._load_persistent_mappings()

    async def is_user_premium(self, client, user_id: int) -> bool:
        """Check if user has Telegram Premium."""
        try:
            current_time = time.time()

            if (
                user_id in self.user_premium_cache
                and user_id in self.last_cache_update
                and current_time - self.last_cache_update[user_id] < self.cache_expiry
            ):
                return self.user_premium_cache[user_id]

            user: User = await client.get_entity(user_id)
            is_premium = getattr(user, "premium", False)

            self.user_premium_cache[user_id] = is_premium
            self.last_cache_update[user_id] = current_time

            logger.debug("User %s premium status: %s", user_id, is_premium)
            return is_premium

        except Exception as exc:  # pragma: no cover - network errors
            logger.error("Error checking premium status for user %s: %s", user_id, exc)
            return False

    def convert_to_premium_emoji(self, text: str, use_premium: bool = True) -> str:
        """Convert standard emojis to premium emojis in text."""
        if not use_premium or not config.ENABLE_PREMIUM_EMOJI:
            return text

        if not self.premium_emoji_map or not text:
            return text

        if not self._conversion_pattern:
            self._rebuild_conversion_pattern()

        pattern = self._conversion_pattern
        if not pattern:
            return text

        def _replace(match: re.Match[str]) -> str:
            standard = match.group(0)
            options = self.premium_emoji_map.get(standard, [])
            if not options:
                return standard
            return random.choice(options)

        return pattern.sub(_replace, text)

    async def process_message_emojis(self, client, message_text: str, user_id: int) -> str:
        """Process message emojis based on user's premium status."""
        if not config.ENABLE_PREMIUM_EMOJI:
            return message_text

        try:
            is_premium = await self.is_user_premium(client, user_id)
            return self.convert_to_premium_emoji(message_text, is_premium)
        except Exception as exc:  # pragma: no cover - safety
            logger.error("Error processing emojis for user %s: %s", user_id, exc)
            return message_text

    def add_emoji_mapping(self, standard: str, premium: str, persist: bool = True) -> bool:
        """Add new emoji mapping."""
        if not standard or not premium:
            return False

        options = self.premium_emoji_map.setdefault(standard, [])
        if premium in options:
            return False

        options.append(premium)
        self._ensure_pool_contains(premium)
        self._rebuild_conversion_pattern()

        logger.info("Added emoji mapping: %s -> %s", standard, premium)

        if persist:
            self._save_persistent_mappings()

        return True

    def remove_emoji_mapping(self, standard: str) -> None:
        """Remove emoji mapping."""
        if standard in self.premium_emoji_map:
            del self.premium_emoji_map[standard]
            logger.info("Removed emoji mapping for: %s", standard)
            self._rebuild_conversion_pattern()
            self._save_persistent_mappings()

    def get_emoji_mappings(self) -> Dict[str, List[str]]:
        """Get all current emoji mappings."""
        return {key: value.copy() for key, value in self.premium_emoji_map.items()}

    def get_available_premium_emojis(self) -> List[str]:
        """Get list of available premium emojis."""
        if self.premium_pool:
            return list(self.premium_pool)

        unique: List[str] = []
        for options in self.premium_emoji_map.values():
            for emoji in options:
                if emoji not in unique:
                    unique.append(emoji)
        return unique

    def get_standard_emojis(self) -> List[str]:
        """Get list of standard emojis that can be converted."""
        return list(self.premium_emoji_map.keys())

    async def clear_premium_cache(self, user_id: Optional[int] = None) -> None:
        """Clear premium status cache."""
        if user_id:
            self.user_premium_cache.pop(user_id, None)
            self.last_cache_update.pop(user_id, None)
        else:
            self.user_premium_cache.clear()
            self.last_cache_update.clear()

        logger.info("Cleared premium cache for user %s", user_id if user_id else "all users")

    def create_emoji_showcase(self) -> str:
        """Create a showcase of available emoji conversions."""
        showcase = "🎨 **Premium Emoji Conversions:**\n\n"

        for standard, premium_list in self.premium_emoji_map.items():
            premium_preview = " / ".join(premium_list)
            showcase += f"{standard} → {premium_preview}\n"

        if self.premium_pool:
            showcase += "\n✨ *Premium pool:* " + " ".join(self.premium_pool)

        showcase += "\n💎 *Premium emojis are automatically used for Telegram Premium users*"
        return showcase

    def extract_emojis_from_text(self, text: str) -> List[str]:
        """Extract all emojis from text."""
        emoji_pattern = re.compile(
            "["
            "\U0001F600-\U0001F64F"  # emoticons
            "\U0001F300-\U0001F5FF"  # symbols & pictographs
            "\U0001F680-\U0001F6FF"  # transport & map symbols
            "\U0001F1E0-\U0001F1FF"  # flags (iOS)
            "\U00002702-\U000027B0"
            "\U000024C2-\U0001F251"
            "]+",
            flags=re.UNICODE,
        )

        return emoji_pattern.findall(text)

    async def suggest_premium_alternatives(self, emoji: str) -> Optional[List[str]]:
        """Suggest premium alternatives for a given emoji."""
        options = self.premium_emoji_map.get(emoji)
        return options.copy() if options else None

    def get_fallback_emoji(self, premium_emoji: str) -> Optional[str]:
        """Get standard fallback for a premium emoji."""
        for standard, premium_values in self.premium_emoji_map.items():
            if premium_emoji in premium_values:
                return standard
        return None

    async def test_emoji_conversion(self, test_text: str) -> Dict[str, object]:
        """Test emoji conversion for debugging."""
        result: Dict[str, object] = {
            "original": test_text,
            "premium_converted": self.convert_to_premium_emoji(test_text, True),
            "extracted_emojis": self.extract_emojis_from_text(test_text),
            "mappings_used": [],
        }

        for standard, premium_values in self.premium_emoji_map.items():
            if standard in test_text:
                result["mappings_used"].append(f"{standard} -> {' / '.join(premium_values)}")

        return result

    def update_premium_emoji_map(self, new_mappings: Dict[str, List[str]]) -> None:
        """Update premium emoji mappings."""
        updated = 0
        for standard, premium_values in new_mappings.items():
            values = [premium_values] if isinstance(premium_values, str) else list(premium_values)
            for premium in values:
                if self.add_emoji_mapping(standard, premium, persist=False):
                    updated += 1

        if updated:
            logger.info("Updated %s emoji mappings", updated)
            self._save_persistent_mappings()
        else:
            logger.debug("No emoji mappings were updated")

    def reset_to_default_mappings(self) -> None:
        """Reset to default emoji mappings."""
        defaults = config.PREMIUM_EMOJI_MAP
        self.premium_emoji_map = {
            key: [value] if isinstance(value, str) else list(value)
            for key, value in defaults.items()
        }
        self._rebuild_pool_from_map()
        self._rebuild_conversion_pattern()
        self._save_persistent_mappings()
        logger.info("Reset emoji mappings to default")

    def add_premium_pool_emoji(self, emoji: str, persist: bool = True) -> bool:
        """Add a premium emoji to the general pool."""
        if not emoji or emoji in self.premium_pool:
            return False

        self.premium_pool.append(emoji)
        if persist:
            self._save_persistent_mappings()

        logger.info("Added premium emoji %s to pool", emoji)
        return True

    def get_random_premium_emoji(self) -> Optional[str]:
        """Return a random premium emoji from the pool."""
        if not self.premium_pool:
            self._rebuild_pool_from_map()
        if not self.premium_pool:
            return None
        return random.choice(self.premium_pool)

    def record_mapping_from_metadata(self, metadata: Dict[str, object]) -> Dict[str, List[str]]:
        """Derive emoji mappings from showjson metadata."""
        if not metadata:
            return {}

        text = metadata.get("text") or ""
        custom_entries = metadata.get("custom_emojis") or []
        if not isinstance(custom_entries, list):
            return {}

        premium_emojis: List[str] = []
        offsets: List[tuple[int, int]] = []
        for entry in custom_entries:
            if not isinstance(entry, dict):
                continue
            emoji = entry.get("emoji")
            if isinstance(emoji, str) and emoji:
                premium_emojis.append(emoji)
            offset = entry.get("offset")
            length = entry.get("length")
            if isinstance(offset, int) and isinstance(length, int):
                offsets.append((offset, length))

        if not premium_emojis:
            return {}

        sanitized_chars = list(text)
        for offset, length in offsets:
            for idx in range(offset, min(offset + length, len(sanitized_chars))):
                sanitized_chars[idx] = " "
        sanitized_text = "".join(sanitized_chars)
        standard_emojis = self.extract_emojis_from_text(sanitized_text)

        new_mappings: Dict[str, List[str]] = {}

        for standard, premium in zip(standard_emojis, premium_emojis):
            if not standard or not premium or standard == premium:
                continue
            if self.add_emoji_mapping(standard, premium, persist=False):
                new_mappings.setdefault(standard, []).append(premium)

        if not new_mappings:
            for premium in premium_emojis:
                if self.add_premium_pool_emoji(premium, persist=False):
                    new_mappings.setdefault("__pool__", []).append(premium)

        if new_mappings:
            self._save_persistent_mappings()

        return new_mappings

    def _load_persistent_mappings(self) -> None:
        """Load emoji mappings from configuration and disk."""
        defaults = config.PREMIUM_EMOJI_MAP
        self.premium_emoji_map = {
            key: [value] if isinstance(value, str) else list(value)
            for key, value in defaults.items()
        }
        self._rebuild_pool_from_map()

        if not self.mapping_file_path.exists():
            self._rebuild_conversion_pattern()
            return

        try:
            data = json.loads(self.mapping_file_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.error(
                "Failed to load premium emoji mapping file %s: %s",
                self.mapping_file_path,
                exc,
            )
            self._rebuild_conversion_pattern()
            return

        mappings = data.get("mappings", {}) if isinstance(data, dict) else {}
        if isinstance(mappings, dict):
            for standard, values in mappings.items():
                values_list = [values] if isinstance(values, str) else list(values)
                for premium in values_list:
                    if isinstance(premium, str):
                        self.add_emoji_mapping(standard, premium, persist=False)

        pool = data.get("pool", []) if isinstance(data, dict) else []
        if isinstance(pool, list):
            for premium in pool:
                if isinstance(premium, str):
                    self.add_premium_pool_emoji(premium, persist=False)

        self._rebuild_conversion_pattern()
        self._save_persistent_mappings()

    def _save_persistent_mappings(self) -> None:
        """Persist emoji mappings to disk."""
        payload = {
            "mappings": {
                key: list(dict.fromkeys(values))
                for key, values in self.premium_emoji_map.items()
            },
            "pool": list(dict.fromkeys(self.premium_pool)),
        }

        self.mapping_file_path.parent.mkdir(parents=True, exist_ok=True)

        with self._storage_lock:
            try:
                self.mapping_file_path.write_text(
                    json.dumps(payload, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
            except OSError as exc:
                logger.error("Failed to persist premium emoji mappings: %s", exc)

    def _rebuild_conversion_pattern(self) -> None:
        """Recompile the regex pattern used for replacements."""
        if not self.premium_emoji_map:
            self._conversion_pattern = None
            return

        escaped = [re.escape(key) for key in sorted(self.premium_emoji_map.keys(), key=len, reverse=True)]
        if not escaped:
            self._conversion_pattern = None
            return

        self._conversion_pattern = re.compile("|".join(escaped))

    def _rebuild_pool_from_map(self) -> None:
        """Synchronise the premium pool with mapping values."""
        pool: List[str] = []
        for values in self.premium_emoji_map.values():
            for emoji in values:
                if emoji not in pool:
                    pool.append(emoji)
        self.premium_pool = pool

    def _ensure_pool_contains(self, emoji: str) -> None:
        if emoji and emoji not in self.premium_pool:
            self.premium_pool.append(emoji)
