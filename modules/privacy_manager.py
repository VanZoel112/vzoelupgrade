#!/usr/bin/env python3
"""
Privacy Manager
Silent command execution untuk private commands

Author: VanZoel112
Version: 2.0.0 Python
"""

import asyncio
import logging
from typing import Dict, Set, Optional
import config

logger = logging.getLogger(__name__)

class PrivacyManager:
    """Manages silent command execution and privacy settings"""

    def __init__(self):
        
        self.silent_chats: Set[int] = set()  # Chats where bot operates silently
        self.private_commands: Set[str] = {
            '.setwelcome', '.github', '.sync', '.privacy',
            '.lock', '.unlock', '.ctag', '.stats'
        }

    async def enable_silent_mode(self, chat_id: int):
        """Enable silent mode for a chat"""
        self.silent_chats.add(chat_id)
        logger.info(f"Enabled silent mode for chat {chat_id}")

    async def disable_silent_mode(self, chat_id: int):
        """Disable silent mode for a chat"""
        self.silent_chats.discard(chat_id)
        logger.info(f"Disabled silent mode for chat {chat_id}")

    def is_silent_mode(self, chat_id: int) -> bool:
        """Check if chat is in silent mode"""
        return chat_id in self.silent_chats

    async def should_execute_silently(self, message) -> bool:
        """Determine if command should be executed silently"""
        try:
            # Private messages are always executed silently
            if hasattr(message, 'is_private') and message.is_private:
                return True

            # Check if chat is in silent mode
            if self.is_silent_mode(message.chat_id):
                return True

            # Check if command is marked as private
            if hasattr(message, 'text') and message.text:
                command = message.text.split()[0].lower()
                if command in self.private_commands:
                    return True

            return False

        except Exception as e:
            logger.error(f"Error checking silent execution: {e}")
            return False

    async def process_private_command(self, client, message, response_text: str):
        """Process command with privacy consideration"""
        try:
            should_be_silent = await self.should_execute_silently(message)

            if should_be_silent:
                # Send response privately to user
                await client.send_message(message.sender_id, response_text)

                # Delete original command if in group
                if not (hasattr(message, 'is_private') and message.is_private):
                    try:
                        await message.delete()
                    except:
                        pass
            else:
                # Send normal response
                await message.reply(response_text)

        except Exception as e:
            logger.error(f"Error processing private command: {e}")

    def add_private_command(self, command: str):
        """Add command to private commands list"""
        self.private_commands.add(command.lower())
        logger.info(f"Added private command: {command}")

    def remove_private_command(self, command: str):
        """Remove command from private commands list"""
        self.private_commands.discard(command.lower())
        logger.info(f"Removed private command: {command}")

    def get_private_commands(self) -> Set[str]:
        """Get list of private commands"""
        return self.private_commands.copy()

    def get_silent_chats(self) -> Set[int]:
        """Get list of silent chats"""
        return self.silent_chats.copy()

    def get_privacy_stats(self) -> Dict:
        """Get privacy statistics"""
        return {
            'silent_chats': len(self.silent_chats),
            'private_commands': len(self.private_commands),
            'privacy_enabled': config.ENABLE_PRIVACY_SYSTEM
        }