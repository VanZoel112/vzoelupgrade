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


class _ConfiguredAdminPermissions:
    """Synthetic permissions object for ADMIN_CHAT_IDS override."""

    is_admin = True
    is_creator = False
    add_admins = True


class AuthManager:
    """Centralized authorization helper."""

    def __init__(self):
        self.owner_id: int = getattr(config, "OWNER_ID", 0)
        self.developer_ids = set(getattr(config, "DEVELOPER_IDS", []) or [])
        self.admin_chat_ids = set(getattr(config, "ADMIN_CHAT_IDS", []) or [])
        self.enable_public: bool = getattr(config, "ENABLE_PUBLIC_COMMANDS", True)
        self._tag_command_prefixes = (".", "/", "+")
        self._admin_tag_commands = {f"{prefix}t" for prefix in self._tag_command_prefixes}
        self._admin_tag_cancel_commands = {f"{prefix}c" for prefix in self._tag_command_prefixes}
        self._admin_override_commands = (
            self._admin_tag_commands | self._admin_tag_cancel_commands
        )
        dev_prefix = getattr(config, "PREFIX_DEV", ".") or "."
        self.admin_dot_commands = {f"{dev_prefix}t".lower()}
        self._last_denied_reason: Optional[str] = None

    # ------------------------------------------------------------------ #
    # Basic checks
    # ------------------------------------------------------------------ #

    def is_owner(self, user_id: int) -> bool:
        return user_id == self.owner_id if self.owner_id else False

    def is_developer(self, user_id: int) -> bool:
        return user_id in self.developer_ids

    async def is_admin_in_chat(self, client, user_id: int, chat_id: int) -> bool:
        """Check if user is admin in a chat."""
        perms = await self._get_chat_permissions(client, user_id, chat_id)
        if not perms:
            return False

        return bool(getattr(perms, "is_admin", False) or getattr(perms, "is_creator", False))

    async def _get_chat_permissions(self, client, user_id: int, chat_id: int):
        """Retrieve permissions for the user in the given chat."""
        if not chat_id:
            return None

        # Fast path: configured admin chats allow all members
        if chat_id in self.admin_chat_ids:
            return _ConfiguredAdminPermissions()

        try:
            return await client.get_permissions(chat_id, user_id)
        except Exception:
            logger.debug("Failed to fetch chat permissions", exc_info=True)
            return None

    def _reset_denied_reason(self):
        self._last_denied_reason = None

    def _set_denied_reason(self, reason: str):
        self._last_denied_reason = reason

    # ------------------------------------------------------------------ #
    # High-level authorization rules
    # ------------------------------------------------------------------ #

    async def can_use_owner_command(self, user_id: int) -> bool:
        """Owner-level commands (prefix '+')"""
        return self.is_owner(user_id) or self.is_developer(user_id)

    async def can_use_admin_command(
        self,
        client,
        user_id: int | None,
        chat_id: int,
        *,
        require_manage_admins: bool = False,
    ) -> bool:
        """Admin-level commands (prefix '/')"""
        if user_id is None:
            # Anonymous or channel-linked admins don't provide sender IDs but are
            # inherently administrators of the chat they speak as.
            return True

        perms = await self._get_chat_permissions(client, user_id, chat_id)

        if perms is None:
            self._set_denied_reason("permissions_unavailable")
            return False

        is_creator = bool(getattr(perms, "is_creator", False))
        is_admin = bool(getattr(perms, "is_admin", False) or is_creator)

        if not is_admin:
            # Owners/developers may bypass chat admin check when configured
            if self.is_owner(user_id) or self.is_developer(user_id):
                return True

            self._set_denied_reason("not_chat_admin")
            return False

        if require_manage_admins and not (is_creator or getattr(perms, "add_admins", False)):
            self._set_denied_reason("add_admins_required")
            return False

        return True

    async def can_use_public_command(self, user_id: int) -> bool:
        """Public commands (prefix '.')"""
        return bool(self.enable_public)

    # ------------------------------------------------------------------ #
    # Command helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _normalize_command(message_text: str) -> str:
        if not message_text:
            return ""
        base = message_text.split()[0]
        if '@' in base:
            base = base.split('@', 1)[0]
        return base.lower()

    def get_command_type(self, message_text: str) -> Optional[str]:
        """Determine command type based on prefix."""
        command = self._normalize_command(message_text)
        if not command:
            return None
        if command in self._admin_override_commands:
        if command in self.admin_dot_commands:
            return "admin"
        if command.startswith('+'):
            return "owner"
        if command.startswith('/'):
            return "admin"
        if command.startswith('.'):
            return "public"
        return None

    async def check_permissions(
        self,
        client,
        user_id: int | None,
        chat_id: int,
        command_text: str,
    ) -> bool:
        """Main permission checker for commands."""
        cmd = self._normalize_command(command_text)

        # Backward-compat: some slash-commands are public
        music_commands = ['/play', '/p', '/music', '/pause', '/resume', '/stop', '/end', '/queue', '/q']
        public_slash_commands = ['/ping', '/start']
        if cmd in music_commands or cmd in public_slash_commands:
            return True

        require_manage_admins = cmd in {'/pm', '/dm'}

        self._reset_denied_reason()
        command_type = self.get_command_type(command_text)

        if command_type == "owner":
            return await self.can_use_owner_command(user_id)
        elif command_type == "admin":
            if cmd in self._admin_override_commands:
            if cmd in self.admin_dot_commands:
                return await self.can_use_admin_command(
                    client,
                    user_id,
                    chat_id,
                )
            allowed = await self.can_use_admin_command(
                client,
                user_id,
                chat_id,
                require_manage_admins=require_manage_admins,
            )
            if not allowed and require_manage_admins and self._last_denied_reason is None:
                self._set_denied_reason("add_admins_required")
            return allowed
        elif command_type == "public":
            return await self.can_use_public_command(user_id)

        return False

    async def log_command_usage(self, user_id: int, chat_id: int, command: str, success: bool):
        """Log command usage for monitoring."""
        status = "SUCCESS" if success else "DENIED"
        logger.info(f"Command {status}: user_id={user_id}, chat_id={chat_id}, command={command}")

    def get_permission_error_message(self, command_type: str) -> str:
        """Get appropriate error message for permission denial."""
        if self._last_denied_reason == "add_admins_required":
            return "Access denied. This command requires Add Admins permission in this group."
        if self._last_denied_reason == "not_chat_admin":
            return "Access denied. Only group administrators can use this command."
        if self._last_denied_reason == "permissions_unavailable":
            return "Access denied. Unable to verify your admin permissions in this chat."
        if command_type == "owner":
            return "Access denied. Owner-level authorization required."
        elif command_type == "admin":
            return "Access denied. Admin authorization required."
        elif command_type == "public":
            return "Access denied. Public commands are disabled."
        return "Access denied."
