#!/usr/bin/env python3
"""
Lock System Manager
Handles /lock @username commands with auto-delete functionality

Author: Vzoel Fox's
Version: 2.0.0 Python (Database-backed)
"""

import logging
from collections import defaultdict
from typing import Dict, Optional

from telethon.errors import (
    UsernameInvalidError,
    UsernameNotOccupiedError,
)
from telethon.tl.types import (
    MessageEntityMention,
    MessageEntityMentionName,
)

logger = logging.getLogger(__name__)


class LockManager:
    """Manages user locking and auto-deletion (Database-backed)"""

    def __init__(self, database=None):
        self.database = database
        self.lock_reasons: Dict[int, Dict[int, str]] = defaultdict(dict)
        logger.info("LockManager initialized with Database backend")

    async def lock_user(self, chat_id: int, user_id: int, reason: str = "Locked by admin") -> bool:
        """Lock a user in a specific chat"""
        try:
            if not self.database:
                logger.error("Database not initialized")
                return False

            self.database.lock_user(chat_id, user_id)
            self.lock_reasons[chat_id][user_id] = reason
            logger.info(f"Locked user {user_id} in chat {chat_id}: {reason}")
            return True

        except Exception as e:
            logger.error(f"Error locking user {user_id} in chat {chat_id}: {e}")
            return False

    async def unlock_user(self, chat_id: int, user_id: int) -> bool:
        """Unlock a user in a specific chat"""
        try:
            if not self.database:
                logger.error("Database not initialized")
                return False

            self.database.unlock_user(chat_id, user_id)
            if chat_id in self.lock_reasons and user_id in self.lock_reasons[chat_id]:
                self.lock_reasons[chat_id].pop(user_id, None)
            logger.info(f"Unlocked user {user_id} in chat {chat_id}")
            return True

        except Exception as e:
            logger.error(f"Error unlocking user {user_id} in chat {chat_id}: {e}")
            return False

    def is_user_locked(self, chat_id: int, user_id: int) -> bool:
        """Check if a user is locked in a specific chat"""
        if not self.database:
            return False
        return self.database.is_locked(chat_id, user_id)

    async def process_message_for_locked_users(self, client, message) -> bool:
        """Check message and delete if from locked user"""
        try:
            chat_id = message.chat_id
            user_id = message.sender_id

            if self.is_user_locked(chat_id, user_id):
                # Delete the message
                await message.delete()

                # Log the deletion
                username = getattr(message.sender, 'username', 'Unknown')
                reason = self.lock_reasons.get(chat_id, {}).get(user_id, 'Locked by admin')

                logger.info(
                    f"Deleted message from locked user {user_id} (@{username}) in chat {chat_id}. Reason: {reason}"
                )
                return True

            return False

        except Exception as e:
            logger.error(f"Error processing message for locked users: {e}")
            return False

    async def parse_lock_command(self, client, message) -> Optional[int]:
        """Parse /lock command to extract user ID"""
        try:
            parts = message.text.split()
            if len(parts) < 2:
                return None

            target = parts[1]

            # Handle @username
            if target.startswith('@'):
                try:
                    entity = await client.get_entity(target)
                    return getattr(entity, 'id', None)
                except (ValueError, UsernameInvalidError, UsernameNotOccupiedError) as e:
                    logger.warning(f"Failed to resolve username {target}: {e}")
                    return None

            # Handle user ID directly
            if target.isdigit():
                return int(target)

            return None

        except Exception as e:
            logger.error(f"Error parsing lock command: {e}")
            return None

    async def extract_user_from_reply(self, message) -> Optional[int]:
        """Extract user ID from replied message"""
        try:
            if message.reply_to_msg_id:
                replied_message = await message.get_reply_message()
                if replied_message and replied_message.sender_id:
                    return replied_message.sender_id

            return None

        except Exception as e:
            logger.error(f"Error extracting user from reply: {e}")
            return None

    async def extract_user_from_mention(self, client, message) -> Optional[int]:
        """Extract user ID from mention in message"""
        try:
            if hasattr(message, 'entities') and message.entities:
                for entity in message.entities:
                    if isinstance(entity, MessageEntityMentionName):
                        return entity.user_id
                    if isinstance(entity, MessageEntityMention):
                        mention_text = message.text[entity.offset:entity.offset + entity.length]
                        try:
                            entity_user = await client.get_entity(mention_text)
                            return getattr(entity_user, 'id', None)
                        except (ValueError, UsernameInvalidError, UsernameNotOccupiedError) as e:
                            logger.warning(f"Failed to resolve mention {mention_text}: {e}")

            return None

        except Exception as e:
            logger.error(f"Error extracting user from mention: {e}")
            return None

    def get_locked_users(self, chat_id: int) -> Dict:
        """Get all locked users in a chat"""
        if not self.database:
            return {}

        locked_ids = self.database.get_locked_users(chat_id)
        return {user_id: {'reason': self.lock_reasons.get(chat_id, {}).get(user_id, 'Locked by admin')}
                for user_id in locked_ids}

    def get_lock_stats(self) -> Dict:
        """Get lock system statistics"""
        if not self.database:
            return {'total_locked_users': 0, 'chats_with_locks': 0}

        # Get stats from database
        stats = self.database.get_stats()
        return {
            'total_locked_users': stats.get('locked_users', 0),
            'chats_with_locks': len([k for k, v in self.database.data.get('locks', {}).items() if v])
        }
