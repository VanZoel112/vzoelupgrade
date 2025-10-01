#!/usr/bin/env python3
"""
Welcome System Manager
Auto welcome untuk member baru dengan toggle per grup

Author: VanZoel112
Version: 2.0.0 Python (Database-backed)
"""

import asyncio
import logging
from typing import Dict, Optional, List
from telethon import Button
import config

logger = logging.getLogger(__name__)

class WelcomeManager:
    """Manages welcome messages for new members (Database-backed)"""

    def __init__(self, database=None):
        self.database = database
        logger.info("WelcomeManager initialized with Database backend")

    async def set_welcome_message(self, chat_id: int, message: str, enabled: bool = True) -> bool:
        """Set welcome message for a chat"""
        try:
            if not self.database:
                logger.error("Database not initialized")
                return False

            self.database.set_welcome(chat_id, message, enabled)
            logger.info(f"Set welcome message for chat {chat_id}")
            return True

        except Exception as e:
            logger.error(f"Error setting welcome message: {e}")
            return False

    async def toggle_welcome(self, chat_id: int) -> Optional[bool]:
        """Toggle welcome on/off for a chat"""
        try:
            if not self.database:
                logger.error("Database not initialized")
                return None

            welcome_data = self.database.get_welcome(chat_id)

            if not welcome_data:
                # Set default
                self.database.set_welcome(chat_id, "👋 Welcome to the group!", True)
                return True
            else:
                current_state = welcome_data.get('enabled', False)
                self.database.toggle_welcome(chat_id, not current_state)
                return not current_state

        except Exception as e:
            logger.error(f"Error toggling welcome: {e}")
            return None

    async def handle_new_member(self, client, event):
        """Handle new member join"""
        try:
            chat_id = event.chat_id

            # Check if welcome is enabled for this chat
            if not self.is_welcome_enabled(chat_id):
                return

            # Get welcome message
            welcome_msg = self.get_welcome_message(chat_id)
            if not welcome_msg:
                return

            # Get new member info
            for user in event.users:
                if not user.bot:
                    # Format welcome message with user info
                    formatted_message = await self._format_welcome_message(
                        welcome_msg, user, event.chat
                    )

                    # Send welcome message
                    await client.send_message(chat_id, formatted_message)
                    logger.info(f"Sent welcome message to {user.id} in chat {chat_id}")

        except Exception as e:
            logger.error(f"Error handling new member: {e}")

    def is_welcome_enabled(self, chat_id: int) -> bool:
        """Check if welcome is enabled for a chat"""
        if not self.database:
            return False
        welcome_data = self.database.get_welcome(chat_id)
        return welcome_data.get('enabled', False) if welcome_data else False

    def get_welcome_message(self, chat_id: int) -> Optional[str]:
        """Get welcome message for a chat"""
        if not self.database:
            return None
        welcome_data = self.database.get_welcome(chat_id)
        return welcome_data.get('message') if welcome_data else None

    async def _format_welcome_message(self, message: str, user, chat) -> str:
        """Format welcome message with placeholders"""
        try:
            # Replace placeholders
            formatted = message.replace('{first_name}', user.first_name or 'User')
            formatted = formatted.replace('{last_name}', user.last_name or '')
            formatted = formatted.replace('{username}', f"@{user.username}" if user.username else 'No username')
            formatted = formatted.replace('{chat_title}', chat.title if hasattr(chat, 'title') else 'Group')
            formatted = formatted.replace('{user_id}', str(user.id))

            return formatted

        except Exception as e:
            logger.error(f"Error formatting welcome message: {e}")
            return message

    def create_welcome_toggle_keyboard(self, chat_id: int) -> List[List[Button]]:
        """Create inline keyboard for welcome toggle"""
        is_enabled = self.is_welcome_enabled(chat_id)

        keyboard = [
            [
                Button.inline(
                    f"{'🟢 Enabled' if is_enabled else '🔴 Disabled'}",
                    f"welcome_toggle_{chat_id}"
                )
            ],
            [
                Button.inline("📝 Edit Message", f"welcome_edit_{chat_id}"),
                Button.inline("📊 Status", f"welcome_status_{chat_id}")
            ]
        ]

        return keyboard

    async def handle_welcome_callback(self, client, event):
        """Handle welcome control callbacks"""
        try:
            data = event.data.decode('utf-8')
            parts = data.split('_')

            if len(parts) < 3:
                return

            action = parts[1]
            chat_id = int(parts[2])

            if action == "toggle":
                new_state = await self.toggle_welcome(chat_id)
                if new_state is not None:
                    status = "enabled" if new_state else "disabled"
                    keyboard = self.create_welcome_toggle_keyboard(chat_id)
                    await event.edit(
                        f"🔄 Welcome system {status} for this chat",
                        buttons=keyboard
                    )

            elif action == "status":
                status_text = self.get_welcome_status(chat_id)
                await event.edit(status_text)

            elif action == "edit":
                await event.edit(
                    "📝 To edit welcome message, use:\n"
                    "`.setwelcome Your new welcome message here`"
                )

        except Exception as e:
            logger.error(f"Error handling welcome callback: {e}")

    def get_welcome_status(self, chat_id: int) -> str:
        """Get welcome status for a chat"""
        if not self.database:
            return "❌ Database not configured"

        welcome_data = self.database.get_welcome(chat_id)

        if not welcome_data:
            return "❌ Welcome system not configured for this chat"

        enabled = welcome_data.get('enabled', False)
        message = welcome_data.get('message', 'Default message')

        status = f"📊 **Welcome System Status**\n\n"
        status += f"Status: {'🟢 Enabled' if enabled else '🔴 Disabled'}\n"
        status += f"Message: {message[:100]}{'...' if len(message) > 100 else ''}\n"

        return status

    async def remove_welcome(self, chat_id: int) -> bool:
        """Remove welcome configuration for a chat"""
        try:
            if not self.database:
                return False

            self.database.set_welcome(chat_id, "", False)
            logger.info(f"Removed welcome configuration for chat {chat_id}")
            return True

        except Exception as e:
            logger.error(f"Error removing welcome: {e}")
            return False

    def get_welcome_stats(self) -> Dict:
        """Get welcome system statistics"""
        if not self.database:
            return {'total_configured_chats': 0, 'enabled_chats': 0, 'disabled_chats': 0}

        stats = self.database.get_stats()
        return {
            'total_configured_chats': stats.get('welcome_chats', 0),
            'enabled_chats': stats.get('welcome_chats', 0),  # Simplified
            'disabled_chats': 0
        }