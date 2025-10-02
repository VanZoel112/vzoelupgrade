#!/usr/bin/env python3
"""
Auth Manager
Handles permission checks for owner/admin/public commands.

Author: Vzoel Fox's
Version: 2.0.0 Python
"""

from __future__ import annotations

import logging
from typing import Optional

import config

logger = logging.getLogger(__name__)


class AuthManager:
    """Centralized authorization helper."""

    def __init__(self):
        self.owner_id: int = getattr(config, "OWNER_ID", 0)
        self.developer_ids = set(getattr(config, "DEVELOPER_IDS", []) or [])
        self.admin_chat_ids = set(getattr(config, "ADMIN_CHAT_IDS", []) or [])
        self.enable_public: bool = getattr(config, "ENABLE_PUBLIC_COMMANDS", True)

    # ------------------------------------------------------------------ #
    # Basic checks
    # ------------------------------------------------------------------ #

    def is_owner(self, user_id: int) -> bool:
        return user_id == self.owner_id if self.owner_id else False

    def is_developer(self, user_id: int) -> bool:
        return user_id in self.developer_ids

    async def is_admin_in_chat(self, client, user_id: int, chat_id: int) -> bool:
        """Check if user is admin in a chat."""
        try:
            # Fast path: configured admin chats allow all members
            if chat_id in self.admin_chat_ids:
                return True

            # Telethon permission check
            perms = await client.get_permissions(chat_id, user_id)
            return bool(getattr(perms, "is_admin", False) or getattr(perms, "is_creator", False))
        except Exception:
            return False

    # ------------------------------------------------------------------ #
    # High-level authorization rules
    # ------------------------------------------------------------------ #

    async def can_use_owner_command(self, user_id: int) -> bool:
        """Owner-level commands (prefix '+')"""
        return self.is_owner(user_id) or self.is_developer(user_id)

    async def can_use_admin_command(self, client, user_id: int, chat_id: int) -> bool:
        """Admin-level commands (prefix '/')"""
        if self.is_owner(user_id) or self.is_developer(user_id):
            return True
        return await self.is_admin_in_chat(client, user_id, chat_id)

    async def can_use_public_command(self, user_id: int) -> bool:
        """Public commands (prefix '.')"""
        return bool(self.enable_public)

    # ------------------------------------------------------------------ #
    # Command helpers
    # ------------------------------------------------------------------ #

    def get_command_type(self, message_text: str) -> Optional[str]:
        """Determine command type based on prefix."""
        if not message_text:
            return None
        if message_text.startswith('+'):
            return "owner"
        elif message_text.startswith('/'):
            return "admin"
        elif message_text.startswith('.'):
            return "public"
        return None

    async def check_permissions(self, client, user_id: int, chat_id: int, command_text: str) -> bool:
        """Main permission checker for commands."""
        cmd = command_text.split()[0].lower() if command_text else ""

        # Backward-compat: some slash-commands are public
        music_commands = ['/play', '/p', '/music', '/pause', '/resume', '/stop', '/end', '/queue', '/q']
        public_slash_commands = ['/ping']
        if cmd in music_commands or cmd in public_slash_commands:
            return True

        command_type = self.get_command_type(command_text)

        if command_type == "owner":
            return await self.can_use_owner_command(user_id)
        elif command_type == "admin":
            return await self.can_use_admin_command(client, user_id, chat_id)
        elif command_type == "public":
            return await self.can_use_public_command(user_id)

        return False

    async def log_command_usage(self, user_id: int, chat_id: int, command: str, success: bool):
        """Log command usage for monitoring."""
        status = "SUCCESS" if success else "DENIED"
        logger.info(f"Command {status}: user_id={user_id}, chat_id={chat_id}, command={command}")

    def get_permission_error_message(self, command_type: str) -> str:
        """Get appropriate error message for permission denial."""
        if command_type == "owner":
            return "Access denied. Owner-level authorization required."
        elif command_type == "admin":
            return "Access denied. Admin authorization required."
        elif command_type == "public":
            return "Access denied. Public commands are disabled."
        return "Access denied."
