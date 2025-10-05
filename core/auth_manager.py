#!/usr/bin/env python3
"""
Auth Manager
Handles permission checks for owner/admin/public commands.

Author: Vzoel Fox's
Version: 2.0.0 Python
"""

from __future__ import annotations

import logging
import time
from typing import Optional, Dict, Tuple

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
        # Kompatibilitas mundur: atribut lama yang mungkin masih digunakan modul lain
        self.admin_tag_commands = self._admin_tag_commands
        self.admin_tag_cancel_commands = self._admin_tag_cancel_commands
        self._admin_override_commands = (
            self._admin_tag_commands | self._admin_tag_cancel_commands
        )
        dev_prefix = getattr(config, "PREFIX_DEV", ".") or "."
        self.admin_dot_commands = {f"{dev_prefix}t".lower()}
        self._last_denied_reason: Optional[str] = None

        # Role detection cache: {(user_id, chat_id): (role, timestamp)}
        self._role_cache: Dict[Tuple[int, int], Tuple[str, float]] = {}
        self._role_cache_ttl = 300  # 5 minutes cache TTL

        # Admin status cache: {(user_id, chat_id): (is_admin, timestamp)}
        self._admin_cache: Dict[Tuple[int, int], Tuple[bool, float]] = {}
        self._admin_cache_ttl = 180  # 3 minutes cache TTL

    # ------------------------------------------------------------------ #
    # Basic checks
    # ------------------------------------------------------------------ #

    def is_owner(self, user_id: int) -> bool:
        return user_id == self.owner_id if self.owner_id else False

    def is_developer(self, user_id: int) -> bool:
        return user_id in self.developer_ids

    async def get_user_role(self, client, user_id: int, chat_id: int) -> str:
        """
        Auto-detect user role and return: 'founder' (developer), 'owner', or 'user'.
        Uses cache for performance.

        Note: Admin group members (non-developer) get 'user' role but have admin
        permissions in their group via is_admin_in_chat check.
        """
        # Check cache first
        cache_key = (user_id, chat_id)
        if cache_key in self._role_cache:
            role, timestamp = self._role_cache[cache_key]
            if time.time() - timestamp < self._role_cache_ttl:
                return role

        # Detect role hierarchy
        # Developer = Founder (full access everywhere)
        if self.is_developer(user_id):
            role = "founder"
        # Owner = Full access
        elif self.is_owner(user_id):
            role = "owner"
        # Everyone else is "user" (admin permissions checked separately)
        else:
            role = "user"

        # Cache the result
        self._role_cache[cache_key] = (role, time.time())

        # Clean old cache entries (keep last 1000)
        if len(self._role_cache) > 1000:
            current_time = time.time()
            self._role_cache = {
                k: v for k, v in self._role_cache.items()
                if current_time - v[1] < self._role_cache_ttl
            }

        logger.debug(f"Auto-detected role for user {user_id} in chat {chat_id}: {role}")
        return role

    async def is_admin_in_chat(self, client, user_id: int, chat_id: int) -> bool:
        """Check if user is admin in a chat with caching."""
        # Developer/Owner always have admin rights
        if self.is_developer(user_id) or self.is_owner(user_id):
            return True

        # Check cache first
        cache_key = (user_id, chat_id)
        if cache_key in self._admin_cache:
            is_admin, timestamp = self._admin_cache[cache_key]
            if time.time() - timestamp < self._admin_cache_ttl:
                return is_admin

        # Fetch permissions from Telegram
        perms = await self._get_chat_permissions(client, user_id, chat_id)
        is_admin = False

        if perms:
            is_admin = bool(getattr(perms, "is_admin", False) or getattr(perms, "is_creator", False))

        # Cache the result
        self._admin_cache[cache_key] = (is_admin, time.time())

        # Clean old cache entries (keep last 1000)
        if len(self._admin_cache) > 1000:
            current_time = time.time()
            self._admin_cache = {
                k: v for k, v in self._admin_cache.items()
                if current_time - v[1] < self._admin_cache_ttl
            }

        return is_admin

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

    def clear_role_cache(self, user_id: Optional[int] = None, chat_id: Optional[int] = None):
        """Clear role and admin cache. If user_id/chat_id provided, clear specific entry."""
        if user_id is not None and chat_id is not None:
            # Clear specific user in specific chat
            cache_key = (user_id, chat_id)
            self._role_cache.pop(cache_key, None)
            self._admin_cache.pop(cache_key, None)
            logger.info(f"Cleared role cache for user {user_id} in chat {chat_id}")
        elif user_id is not None:
            # Clear all entries for specific user
            self._role_cache = {k: v for k, v in self._role_cache.items() if k[0] != user_id}
            self._admin_cache = {k: v for k, v in self._admin_cache.items() if k[0] != user_id}
            logger.info(f"Cleared role cache for user {user_id}")
        elif chat_id is not None:
            # Clear all entries for specific chat
            self._role_cache = {k: v for k, v in self._role_cache.items() if k[1] != chat_id}
            self._admin_cache = {k: v for k, v in self._admin_cache.items() if k[1] != chat_id}
            logger.info(f"Cleared role cache for chat {chat_id}")
        else:
            # Clear all cache
            self._role_cache.clear()
            self._admin_cache.clear()
            logger.info("Cleared all role cache")

    def get_role_permissions(self, role: str) -> dict:
        """Get permissions available for a role."""
        permissions = {
            "founder": {
                "owner_commands": True,
                "admin_commands": True,
                "public_commands": True,
                "bypass_all": True,
                "description": "Founder dengan akses penuh ke semua fitur bot dimanapun"
            },
            "owner": {
                "owner_commands": True,
                "admin_commands": True,
                "public_commands": True,
                "bypass_all": True,
                "description": "Bot owner dengan hak akses penuh"
            },
            "user": {
                "owner_commands": False,
                "admin_commands": False,
                "public_commands": True,
                "bypass_all": False,
                "description": "User biasa (admin group dapat akses admin command di group mereka)"
            }
        }
        return permissions.get(role, permissions["user"])

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
        if command in self._admin_override_commands or command in self.admin_dot_commands:
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
            if cmd in self._admin_override_commands or cmd in self.admin_dot_commands:
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
        status = "BERHASIL" if success else "DITOLAK"
        logger.info(
            "Command %s: user_id=%s, chat_id=%s, command=%s",
            status,
            user_id,
            chat_id,
            command,
        )

    def get_permission_error_message(self, command_type: str) -> str:
        """Get appropriate error message for permission denial."""
        if self._last_denied_reason == "add_admins_required":
            return (
                "Akses ditolak. Perintah ini memerlukan izin Tambah Admin di grup ini."
            )
        if self._last_denied_reason == "not_chat_admin":
            return "Akses ditolak. Hanya admin grup yang dapat memakai perintah ini."
        if self._last_denied_reason == "permissions_unavailable":
            return (
                "Akses ditolak. Sistem tidak dapat memverifikasi izin admin Anda dalam percakapan ini."
            )
        if command_type == "owner":
            return "Akses ditolak. Diperlukan otorisasi level owner."
        elif command_type == "admin":
            return "Akses ditolak. Diperlukan otorisasi admin."
        elif command_type == "public":
            return "Akses ditolak. Perintah publik sedang dinonaktifkan."
        return "Akses ditolak."
