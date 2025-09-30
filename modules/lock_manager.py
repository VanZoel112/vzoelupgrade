#!/usr/bin/env python3
"""
Lock System Manager
Handles /lock @username commands with auto-delete functionality

Author: VanZoel112
Version: 2.0.0 Python
"""

import asyncio
import logging
import json
import time
from typing import Dict, Set, List, Optional
from pathlib import Path
from telethon.tl.types import MessageEntityMentionName

logger = logging.getLogger(__name__)

class LockManager:
    """Manages user locking and auto-deletion"""

    def __init__(self):
        
        self.data_path = Path("data/locked_users.json")
        self.locked_users: Dict[int, Set[int]] = {}  # chat_id -> set of locked user_ids
        self.lock_reasons: Dict[int, Dict[int, str]] = {}  # chat_id -> user_id -> reason
        self.lock_timestamps: Dict[int, Dict[int, float]] = {}  # chat_id -> user_id -> timestamp

        # Load existing locks
        asyncio.create_task(self.load_locked_users())

    async def load_locked_users(self):
        """Load locked users from file"""
        try:
            if self.data_path.exists():
                async with aiofiles.open(self.data_path, 'r') as f:
                    data = json.loads(await f.read())

                # Convert string keys back to integers
                for chat_id_str, user_data in data.get('locked_users', {}).items():
                    chat_id = int(chat_id_str)
                    self.locked_users[chat_id] = set(user_data.get('users', []))
                    self.lock_reasons[chat_id] = user_data.get('reasons', {})
                    self.lock_timestamps[chat_id] = user_data.get('timestamps', {})

                logger.info(f"Loaded {sum(len(users) for users in self.locked_users.values())} locked users")

        except Exception as e:
            logger.error(f"Error loading locked users: {e}")
            self.locked_users = {}
            self.lock_reasons = {}
            self.lock_timestamps = {}

    async def save_locked_users(self):
        """Save locked users to file"""
        try:
            # Ensure data directory exists
            self.data_path.parent.mkdir(exist_ok=True)

            # Convert sets to lists for JSON serialization
            data = {
                'locked_users': {},
                'last_updated': time.time()
            }

            for chat_id, user_set in self.locked_users.items():
                data['locked_users'][str(chat_id)] = {
                    'users': list(user_set),
                    'reasons': self.lock_reasons.get(chat_id, {}),
                    'timestamps': self.lock_timestamps.get(chat_id, {})
                }

            async with aiofiles.open(self.data_path, 'w') as f:
                await f.write(json.dumps(data, indent=2))

            logger.debug("Saved locked users to file")

        except Exception as e:
            logger.error(f"Error saving locked users: {e}")

    async def lock_user(self, chat_id: int, user_id: int, reason: str = "Locked by admin") -> bool:
        """Lock a user in a specific chat"""
        try:
            if chat_id not in self.locked_users:
                self.locked_users[chat_id] = set()
                self.lock_reasons[chat_id] = {}
                self.lock_timestamps[chat_id] = {}

            self.locked_users[chat_id].add(user_id)
            self.lock_reasons[chat_id][user_id] = reason
            self.lock_timestamps[chat_id][user_id] = time.time()

            await self.save_locked_users()

            logger.info(f"Locked user {user_id} in chat {chat_id}: {reason}")
            return True

        except Exception as e:
            logger.error(f"Error locking user {user_id} in chat {chat_id}: {e}")
            return False

    async def unlock_user(self, chat_id: int, user_id: int) -> bool:
        """Unlock a user in a specific chat"""
        try:
            if chat_id in self.locked_users and user_id in self.locked_users[chat_id]:
                self.locked_users[chat_id].discard(user_id)
                self.lock_reasons[chat_id].pop(user_id, None)
                self.lock_timestamps[chat_id].pop(user_id, None)

                await self.save_locked_users()

                logger.info(f"Unlocked user {user_id} in chat {chat_id}")
                return True

            return False

        except Exception as e:
            logger.error(f"Error unlocking user {user_id} in chat {chat_id}: {e}")
            return False

    def is_user_locked(self, chat_id: int, user_id: int) -> bool:
        """Check if a user is locked in a specific chat"""
        return chat_id in self.locked_users and user_id in self.locked_users[chat_id]

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
                reason = self.lock_reasons.get(chat_id, {}).get(user_id, 'Unknown')

                logger.info(f"Deleted message from locked user {user_id} (@{username}) in chat {chat_id}. Reason: {reason}")
                return True

            return False

        except Exception as e:
            logger.error(f"Error processing message for locked users: {e}")
            return False

    async def parse_lock_command(self, message_text: str) -> Optional[int]:
        """Parse /lock command to extract user ID"""
        try:
            parts = message_text.split()
            if len(parts) < 2:
                return None

            target = parts[1]

            # Handle @username
            if target.startswith('@'):
                username = target[1:]  # Remove @
                # Note: In real implementation, you'd need to resolve username to user_id
                # This would require a database or API call to get user_id from username
                return None  # Placeholder

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

    async def extract_user_from_mention(self, message) -> Optional[int]:
        """Extract user ID from mention in message"""
        try:
            if hasattr(message, 'entities') and message.entities:
                for entity in message.entities:
                    if isinstance(entity, MessageEntityMentionName):
                        return entity.user_id

            return None

        except Exception as e:
            logger.error(f"Error extracting user from mention: {e}")
            return None

    def get_locked_users_in_chat(self, chat_id: int) -> List[Dict]:
        """Get all locked users in a chat with details"""
        if chat_id not in self.locked_users:
            return []

        locked_list = []
        for user_id in self.locked_users[chat_id]:
            locked_list.append({
                'user_id': user_id,
                'reason': self.lock_reasons.get(chat_id, {}).get(user_id, 'Unknown'),
                'timestamp': self.lock_timestamps.get(chat_id, {}).get(user_id, 0),
                'locked_since': time.time() - self.lock_timestamps.get(chat_id, {}).get(user_id, time.time())
            })

        return sorted(locked_list, key=lambda x: x['timestamp'], reverse=True)

    def get_lock_stats(self) -> Dict:
        """Get lock system statistics"""
        total_locked = sum(len(users) for users in self.locked_users.values())
        chats_with_locks = len([chat for chat, users in self.locked_users.items() if users])

        return {
            'total_locked_users': total_locked,
            'chats_with_locks': chats_with_locks,
            'total_chats': len(self.locked_users)
        }

    def format_locked_users_list(self, chat_id: int) -> str:
        """Format locked users list for display"""
        locked_users = self.get_locked_users_in_chat(chat_id)

        if not locked_users:
            return "🔓 No locked users in this chat."

        response = f"🔒 **Locked Users ({len(locked_users)}):**\n\n"

        for i, user_info in enumerate(locked_users[:10], 1):  # Limit to 10 for readability
            user_id = user_info['user_id']
            reason = user_info['reason']
            days_ago = int(user_info['locked_since'] / 86400)

            response += f"{i}. User ID: `{user_id}`\n"
            response += f"   Reason: {reason}\n"
            response += f"   Locked: {days_ago} days ago\n\n"

        if len(locked_users) > 10:
            response += f"... and {len(locked_users) - 10} more users\n"

        response += f"\n💡 Use `/unlock <user_id>` to unlock users"

        return response

    async def clear_all_locks_in_chat(self, chat_id: int) -> int:
        """Clear all locks in a specific chat"""
        try:
            if chat_id in self.locked_users:
                count = len(self.locked_users[chat_id])
                self.locked_users[chat_id].clear()
                self.lock_reasons[chat_id].clear()
                self.lock_timestamps[chat_id].clear()

                await self.save_locked_users()

                logger.info(f"Cleared all {count} locks in chat {chat_id}")
                return count

            return 0

        except Exception as e:
            logger.error(f"Error clearing locks in chat {chat_id}: {e}")
            return 0

    async def cleanup_old_locks(self, max_age_days: int = 30):
        """Clean up locks older than specified days"""
        try:
            current_time = time.time()
            max_age_seconds = max_age_days * 24 * 3600
            cleaned_count = 0

            for chat_id in list(self.locked_users.keys()):
                users_to_remove = []

                for user_id in list(self.locked_users[chat_id]):
                    lock_time = self.lock_timestamps.get(chat_id, {}).get(user_id, current_time)
                    if current_time - lock_time > max_age_seconds:
                        users_to_remove.append(user_id)

                for user_id in users_to_remove:
                    self.locked_users[chat_id].discard(user_id)
                    self.lock_reasons[chat_id].pop(user_id, None)
                    self.lock_timestamps[chat_id].pop(user_id, None)
                    cleaned_count += 1

            if cleaned_count > 0:
                await self.save_locked_users()
                logger.info(f"Cleaned up {cleaned_count} old locks")

            return cleaned_count

        except Exception as e:
            logger.error(f"Error cleaning up old locks: {e}")
            return 0