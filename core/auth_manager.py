#!/usr/bin/env python3
"""
Authentication and Authorization Manager
Handles / commands for admins and . commands for developers

Author: VanZoel112
Version: 2.0.0 Python
"""

import asyncio
import logging
from typing import List, Dict, Set, Optional
from telethon.tl.types import User, Chat, Channel
from config import VBotConfig

logger = logging.getLogger(__name__)

class AuthManager:
    """Manages authentication and authorization for VBot"""

    def __init__(self, config: VBotConfig):
        self.config = config
        self.admin_cache: Dict[int, Set[int]] = {}  # chat_id -> set of admin user_ids
        self.cache_expiry = 300  # 5 minutes
        self.last_cache_update: Dict[int, float] = {}

    async def is_developer(self, user_id: int) -> bool:
        """Check if user is a developer (can use . commands)"""
        return user_id in self.config.auth.developer_ids or user_id == self.config.auth.owner_id

    async def is_owner(self, user_id: int) -> bool:
        """Check if user is the owner"""
        return user_id == self.config.auth.owner_id

    async def is_admin_in_chat(self, client, user_id: int, chat_id: int) -> bool:
        """Check if user is admin in specific chat (can use / commands)"""
        try:
            # Check cache first
            import time
            current_time = time.time()

            if (chat_id in self.admin_cache and
                chat_id in self.last_cache_update and
                current_time - self.last_cache_update[chat_id] < self.cache_expiry):
                return user_id in self.admin_cache[chat_id]

            # Refresh cache
            await self._refresh_admin_cache(client, chat_id)
            return user_id in self.admin_cache.get(chat_id, set())

        except Exception as e:
            logger.error(f"Error checking admin status: {e}")
            return False

    async def _refresh_admin_cache(self, client, chat_id: int):
        """Refresh admin cache for a specific chat"""
        try:
            admins = await client.get_participants(
                chat_id,
                filter=lambda x: x.participant
            )

            admin_ids = set()
            async for admin in admins:
                if hasattr(admin.participant, 'admin_rights') or hasattr(admin.participant, 'creator'):
                    admin_ids.add(admin.id)

            self.admin_cache[chat_id] = admin_ids
            import time
            self.last_cache_update[chat_id] = time.time()

            logger.debug(f"Refreshed admin cache for chat {chat_id}: {len(admin_ids)} admins")

        except Exception as e:
            logger.error(f"Failed to refresh admin cache for chat {chat_id}: {e}")
            self.admin_cache[chat_id] = set()

    async def can_use_admin_command(self, client, user_id: int, chat_id: int) -> bool:
        """Check if user can use admin commands (/ prefix)"""
        # Developers can always use admin commands
        if await self.is_developer(user_id):
            return True

        # Check if user is admin in the chat
        return await self.is_admin_in_chat(client, user_id, chat_id)

    async def can_use_dev_command(self, user_id: int) -> bool:
        """Check if user can use developer commands (. prefix)"""
        return await self.is_developer(user_id)

    async def can_use_public_command(self, user_id: int) -> bool:
        """Check if user can use public commands (# prefix)"""
        # Public commands can be used by anyone
        return True

    def get_command_type(self, message_text: str) -> Optional[str]:
        """Determine command type based on prefix"""
        if message_text.startswith(self.config.command_prefix_dev):
            return "developer"
        elif message_text.startswith(self.config.command_prefix_admin):
            return "admin"
        elif message_text.startswith(self.config.command_prefix_public):
            return "public"
        return None

    async def check_permissions(self, client, user_id: int, chat_id: int, command_text: str) -> bool:
        """Main permission checker for commands"""
        command_type = self.get_command_type(command_text)

        if command_type == "developer":
            return await self.can_use_dev_command(user_id)
        elif command_type == "admin":
            return await self.can_use_admin_command(client, user_id, chat_id)
        elif command_type == "public":
            return await self.can_use_public_command(user_id)

        return False

    async def log_command_usage(self, user_id: int, chat_id: int, command: str, success: bool):
        """Log command usage for monitoring"""
        status = "SUCCESS" if success else "DENIED"
        logger.info(f"Command {status}: user_id={user_id}, chat_id={chat_id}, command={command}")

    def get_permission_error_message(self, command_type: str) -> str:
        """Get appropriate error message for permission denial"""
        if command_type == "developer":
            return "⚠️ Developer command access denied. Only bot developers can use . commands."
        elif command_type == "admin":
            return "⚠️ Admin command access denied. Only group admins can use / commands."
        else:
            return "⚠️ Command access denied."

    async def clear_admin_cache(self, chat_id: Optional[int] = None):
        """Clear admin cache for specific chat or all chats"""
        if chat_id:
            self.admin_cache.pop(chat_id, None)
            self.last_cache_update.pop(chat_id, None)
        else:
            self.admin_cache.clear()
            self.last_cache_update.clear()

        logger.info(f"Cleared admin cache for chat {chat_id if chat_id else 'all chats'}")

# Decorator for permission checking
def require_permission(permission_type: str):
    """Decorator to require specific permission for command handlers"""
    def decorator(func):
        async def wrapper(client, message, auth_manager: AuthManager, *args, **kwargs):
            user_id = message.sender_id
            chat_id = message.chat_id
            command_text = message.text

            has_permission = False
            if permission_type == "developer":
                has_permission = await auth_manager.can_use_dev_command(user_id)
            elif permission_type == "admin":
                has_permission = await auth_manager.can_use_admin_command(client, user_id, chat_id)
            elif permission_type == "public":
                has_permission = await auth_manager.can_use_public_command(user_id)

            await auth_manager.log_command_usage(user_id, chat_id, command_text, has_permission)

            if has_permission:
                return await func(client, message, auth_manager, *args, **kwargs)
            else:
                error_msg = auth_manager.get_permission_error_message(permission_type)
                await message.reply(error_msg)

        return wrapper
    return decorator