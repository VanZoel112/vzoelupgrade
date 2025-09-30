#!/usr/bin/env python3
"""
Welcome System Manager
Auto welcome untuk member baru dengan toggle per grup

Author: VanZoel112
Version: 2.0.0 Python
"""

import asyncio
import logging
import json
import aiofiles
from typing import Dict, Optional, List
from pathlib import Path
from telethon import Button
import config

logger = logging.getLogger(__name__)

class WelcomeManager:
    """Manages welcome messages for new members"""

    def __init__(self):
        
        self.data_path = Path("data/welcome_settings.json")
        self.welcome_settings: Dict[int, Dict] = {}  # chat_id -> settings

        # Load existing settings
        asyncio.create_task(self.load_welcome_settings())

    async def load_welcome_settings(self):
        """Load welcome settings from file"""
        try:
            if self.data_path.exists():
                async with aiofiles.open(self.data_path, 'r') as f:
                    data = json.loads(await f.read())

                # Convert string keys back to integers
                for chat_id_str, settings in data.get('welcome_settings', {}).items():
                    self.welcome_settings[int(chat_id_str)] = settings

                logger.info(f"Loaded welcome settings for {len(self.welcome_settings)} chats")

        except Exception as e:
            logger.error(f"Error loading welcome settings: {e}")
            self.welcome_settings = {}

    async def save_welcome_settings(self):
        """Save welcome settings to file"""
        try:
            self.data_path.parent.mkdir(exist_ok=True)

            data = {
                'welcome_settings': {
                    str(chat_id): settings
                    for chat_id, settings in self.welcome_settings.items()
                },
                'last_updated': asyncio.get_event_loop().time()
            }

            async with aiofiles.open(self.data_path, 'w') as f:
                await f.write(json.dumps(data, indent=2))

        except Exception as e:
            logger.error(f"Error saving welcome settings: {e}")

    async def set_welcome_message(self, chat_id: int, message: str, enabled: bool = True) -> bool:
        """Set welcome message for a chat"""
        try:
            if chat_id not in self.welcome_settings:
                self.welcome_settings[chat_id] = {}

            self.welcome_settings[chat_id].update({
                'message': message,
                'enabled': enabled,
                'set_by': 'admin',
                'timestamp': asyncio.get_event_loop().time()
            })

            await self.save_welcome_settings()
            logger.info(f"Set welcome message for chat {chat_id}")
            return True

        except Exception as e:
            logger.error(f"Error setting welcome message: {e}")
            return False

    async def toggle_welcome(self, chat_id: int) -> Optional[bool]:
        """Toggle welcome on/off for a chat"""
        try:
            if chat_id not in self.welcome_settings:
                self.welcome_settings[chat_id] = {
                    'message': "👋 Welcome to the group!",
                    'enabled': True
                }
            else:
                current_state = self.welcome_settings[chat_id].get('enabled', False)
                self.welcome_settings[chat_id]['enabled'] = not current_state

            await self.save_welcome_settings()
            new_state = self.welcome_settings[chat_id]['enabled']
            logger.info(f"Toggled welcome for chat {chat_id}: {new_state}")
            return new_state

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
        settings = self.welcome_settings.get(chat_id, {})
        return settings.get('enabled', False)

    def get_welcome_message(self, chat_id: int) -> Optional[str]:
        """Get welcome message for a chat"""
        settings = self.welcome_settings.get(chat_id, {})
        return settings.get('message')

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
        settings = self.welcome_settings.get(chat_id, {})

        if not settings:
            return "❌ Welcome system not configured for this chat"

        enabled = settings.get('enabled', False)
        message = settings.get('message', 'Default message')

        status = f"📊 **Welcome System Status**\n\n"
        status += f"Status: {'🟢 Enabled' if enabled else '🔴 Disabled'}\n"
        status += f"Message: {message[:100]}{'...' if len(message) > 100 else ''}\n"

        return status

    def get_all_welcome_chats(self) -> Dict[int, Dict]:
        """Get all chats with welcome configured"""
        return self.welcome_settings.copy()

    async def remove_welcome(self, chat_id: int) -> bool:
        """Remove welcome configuration for a chat"""
        try:
            if chat_id in self.welcome_settings:
                del self.welcome_settings[chat_id]
                await self.save_welcome_settings()
                logger.info(f"Removed welcome configuration for chat {chat_id}")
                return True
            return False

        except Exception as e:
            logger.error(f"Error removing welcome: {e}")
            return False

    def get_welcome_stats(self) -> Dict:
        """Get welcome system statistics"""
        total_chats = len(self.welcome_settings)
        enabled_chats = sum(
            1 for settings in self.welcome_settings.values()
            if settings.get('enabled', False)
        )

        return {
            'total_configured_chats': total_chats,
            'enabled_chats': enabled_chats,
            'disabled_chats': total_chats - enabled_chats
        }