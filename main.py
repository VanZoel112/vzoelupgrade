#!/usr/bin/env python3
"""
VBot Python - Main Application
Vzoel Robot Music Bot with comprehensive features

Author: VanZoel112 (Converted from Node.js)
Version: 2.0.0 Python
"""

import asyncio
import logging
import sys
from pathlib import Path

# Setup logging
log_dir = Path('logs')
log_dir.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_dir / 'vbot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Import configuration and validate
import config

# Import Telethon
from telethon import TelegramClient, events, Button, types
from telethon.tl.types import MessageEntityMentionName

# Import VBot modules
from core import AuthManager, EmojiManager, MusicManager
from modules import LockManager, TagManager, WelcomeManager, GitHubSync, PrivacyManager

class VBot:
    """Main VBot application class"""

    def __init__(self):
        self.client = None
        self.music_manager = None  # Will be initialized after client

        # Initialize managers (they will import config directly)
        self.auth_manager = AuthManager()
        self.emoji_manager = EmojiManager()
        self.lock_manager = LockManager()
        self.tag_manager = TagManager()
        self.welcome_manager = WelcomeManager()
        self.github_sync = GitHubSync()
        self.privacy_manager = PrivacyManager()

    async def initialize(self):
        """Initialize VBot"""
        try:
            # Validate configuration
            if not config.validate_config():
                return False

            # Initialize Telegram client
            self.client = TelegramClient(
                "vbot_session",
                config.API_ID,
                config.API_HASH
            )

            await self.client.start(bot_token=config.BOT_TOKEN)

            # Get bot info
            me = await self.client.get_me()
            logger.info(f"🎵 VBot started successfully!")
            logger.info(f"Bot: {me.first_name} (@{me.username})")

            # Initialize Music Manager with client (for PyTgCalls)
            from core.music_manager import MusicManager
            self.music_manager = MusicManager(self.client)
            await self.music_manager.start()
            logger.info("🎵 Music download system ready")

            # Setup event handlers
            self._setup_event_handlers()

            logger.info("✅ All systems initialized")
            return True

        except Exception as e:
            logger.error(f"❌ Failed to initialize VBot: {e}")
            return False

    def _setup_event_handlers(self):
        """Setup all event handlers"""

        # New message handler
        @self.client.on(events.NewMessage)
        async def handle_new_message(event):
            await self._handle_message(event)

        # New member handler
        @self.client.on(events.ChatAction)
        async def handle_chat_action(event):
            if event.user_joined or event.user_added:
                if config.ENABLE_WELCOME_SYSTEM:
                    await self.welcome_manager.handle_new_member(self.client, event)

        # Callback query handler
        @self.client.on(events.CallbackQuery)
        async def handle_callback(event):
            await self._handle_callback(event)

    async def _handle_message(self, event):
        """Handle incoming messages"""
        try:
            message = event.message

            # Skip if no text
            if not message.text:
                return

            # Check for locked users (auto-delete)
            if config.ENABLE_LOCK_SYSTEM:
                deleted = await self.lock_manager.process_message_for_locked_users(
                    self.client, message
                )
                if deleted:
                    return

            # Process emojis for premium users
            if config.ENABLE_PREMIUM_EMOJI and hasattr(message, 'sender_id'):
                processed_text = await self.emoji_manager.process_message_emojis(
                    self.client, message.text, message.sender_id
                )
                # Note: Would need to edit message if different, but that requires specific permissions

            # Handle commands
            if message.text.startswith(('.', '/', '#')):
                await self._handle_command(message)

        except Exception as e:
            logger.error(f"Error handling message: {e}")

    async def _handle_command(self, message):
        """Handle bot commands"""
        try:
            command_text = message.text.lower()
            command_parts = command_text.split()
            command = command_parts[0]

            # Check permissions
            has_permission = await self.auth_manager.check_permissions(
                self.client, message.sender_id, message.chat_id, command_text
            )

            if not has_permission:
                command_type = self.auth_manager.get_command_type(command_text)
                error_msg = self.auth_manager.get_permission_error_message(command_type)

                if config.ENABLE_PRIVACY_SYSTEM:
                    await self.privacy_manager.process_private_command(
                        self.client, message, error_msg
                    )
                else:
                    await message.reply(error_msg)
                return

            # Route commands
            await self._route_command(message, command, command_parts)

        except Exception as e:
            logger.error(f"Error handling command: {e}")

    async def _route_command(self, message, command, parts):
        """Route commands to appropriate handlers"""
        try:
            # Basic bot commands
            if command in ['/start', '/help']:
                await self._handle_start_command(message)
            elif command == '/about':
                await self._handle_about_command(message)

            # Music commands
            elif command in ['/play', '/p', '/music']:
                await self._handle_music_command(message, parts)
            elif command in ['/stop', '/end']:
                await self._handle_stop_command(message)
            elif command == '/pause':
                await self._handle_pause_command(message)
            elif command == '/resume':
                await self._handle_resume_command(message)
            elif command in ['/queue', '/q']:
                await self._handle_queue_command(message)

            # Lock commands
            elif command == '/lock':
                await self._handle_lock_command(message, parts)
            elif command == '/unlock':
                await self._handle_unlock_command(message, parts)
            elif command == '/locklist':
                await self._handle_locklist_command(message)

            # Tag commands
            elif command in ['/tag', '/tagall', '/tагall']:
                await self._handle_tag_command(message, parts)
            elif command in ['/ctag', '/canceltag']:
                await self._handle_cancel_tag_command(message)

            # Welcome commands
            elif command in ['.setwelcome', '.welcome', '/setwelcome', '/welcome']:
                await self._handle_welcome_command(message, parts)

            # Public commands
            elif command == '#help':
                await self._handle_help_command(message)
            elif command == '#rules':
                await self._handle_rules_command(message)
            elif command == '#session':
                await self._handle_session_command(message)

            # Admin commands
            elif command in ['.stats', '.status']:
                await self._handle_stats_command(message)

            else:
                # Unknown command
                await message.reply(f"❓ Unknown command: {command}\n\nType /start to see available commands.")

        except Exception as e:
            logger.error(f"Error routing command {command}: {e}")

    async def _handle_music_command(self, message, parts):
        """Handle music download commands"""
        if not config.MUSIC_ENABLED:
            await message.reply("🎵 Music system is disabled")
            return

        if not self.music_manager:
            await message.reply("❌ Music system not initialized")
            return

        try:
            if len(parts) < 2:
                await message.reply("🎵 **Usage:** /play <song name or URL>\n\n**Examples:**\n• /play shape of you\n• /play https://youtu.be/...")
                return

            query = ' '.join(parts[1:])

            # Show processing message
            status_msg = await message.reply("🔍 Searching and downloading audio...")

            # Play stream
            result = await self.music_manager.play_stream(
                message.chat_id,
                query,
                message.sender_id
            )

            if result['success']:
                song = result['song']

                if result.get('queued'):
                    # Song added to queue
                    await status_msg.edit(
                        f"📋 **Added to Queue (#{result['position']})**\n\n"
                        f"🎵 **{song['title']}**\n"
                        f"⏱️ Duration: {song.get('duration', 0) // 60}:{song.get('duration', 0) % 60:02d}"
                    )
                else:
                    # Update status to uploading
                    await status_msg.edit("⬆️ Uploading audio...")

                    # Send audio file
                    file_path = result.get('file_path')
                    if file_path:
                        await self.client.send_file(
                            message.chat_id,
                            file_path,
                            caption=f"🎵 **{song['title']}**\n⏱️ Duration: {song.get('duration', 0) // 60}:{song.get('duration', 0) % 60:02d}",
                            reply_to=message.id,
                            attributes=[
                                types.DocumentAttributeAudio(
                                    duration=song.get('duration', 0),
                                    title=song['title'],
                                    performer='VBot Music'
                                )
                            ]
                        )
                        # Delete status message after sending
                        await status_msg.delete()
                    else:
                        await status_msg.edit("❌ Failed to download audio file")
            else:
                await status_msg.edit(f"❌ Error: {result.get('error', 'Unknown error')}")

        except Exception as e:
            logger.error(f"Error in music command: {e}")
            await message.reply(f"❌ Error playing music: {str(e)}")

    async def _handle_stop_command(self, message):
        """Handle /stop command"""
        if not self.music_manager:
            return

        try:
            success = await self.music_manager.stop_stream(message.chat_id)
            if success:
                await message.reply("⏹️ Stopped music and cleared queue")
            else:
                await message.reply("❌ No active stream in this chat")
        except Exception as e:
            await message.reply(f"❌ Error stopping stream: {str(e)}")

    async def _handle_pause_command(self, message):
        """Handle /pause command"""
        await message.reply("❌ Pause not available in download mode")

    async def _handle_resume_command(self, message):
        """Handle /resume command"""
        await message.reply("❌ Resume not available in download mode")

    async def _handle_queue_command(self, message):
        """Handle /queue command"""
        if not self.music_manager:
            return

        try:
            current = self.music_manager.get_current_song(message.chat_id)
            queue = self.music_manager.get_queue(message.chat_id)

            if not current and not queue:
                await message.reply("📋 Queue is empty\n\nUse /play to add songs!")
                return

            response = "📋 **Music Queue**\n\n"

            if current:
                response += f"🎵 **Now Playing:**\n{current['title']}\n\n"

            if queue:
                response += "**Up Next:**\n"
                for i, song in enumerate(queue[:10], 1):
                    response += f"{i}. {song['title']}\n"

                if len(queue) > 10:
                    response += f"\n... and {len(queue) - 10} more"
            else:
                response += "No songs in queue"

            await message.reply(response)

        except Exception as e:
            await message.reply(f"❌ Error getting queue: {str(e)}")

    async def _handle_lock_command(self, message, parts):
        """Handle /lock command"""
        if not config.ENABLE_LOCK_SYSTEM:
            await message.reply("🔒 Lock system is disabled")
            return

        try:
            user_id = None
            reason = "Locked by admin"

            # Try to get user from reply
            if message.is_reply:
                user_id = await self.lock_manager.extract_user_from_reply(message)

            # Try to get user from mention
            if not user_id:
                user_id = await self.lock_manager.extract_user_from_mention(message)

            # Try to parse from command text
            if not user_id and len(parts) > 1:
                user_id = await self.lock_manager.parse_lock_command(message.text)

            if len(parts) > 2:
                reason = ' '.join(parts[2:])

            if user_id:
                success = await self.lock_manager.lock_user(
                    message.chat_id, user_id, reason
                )

                if success:
                    response = f"🔒 User {user_id} has been locked\nReason: {reason}"

                    # Sync to GitHub if enabled
                    if config.ENABLE_GITHUB_SYNC:
                        await self.github_sync.queue_sync('lock_data', {
                            'chat_id': message.chat_id,
                            'user_id': user_id,
                            'reason': reason
                        })
                else:
                    response = "❌ Failed to lock user"

                if config.ENABLE_PRIVACY_SYSTEM:
                    await self.privacy_manager.process_private_command(
                        self.client, message, response
                    )
                else:
                    await message.reply(response)
            else:
                await message.reply("❌ Please reply to a user or mention them to lock")

        except Exception as e:
            await message.reply(f"❌ Error locking user: {str(e)}")

    async def _handle_unlock_command(self, message, parts):
        """Handle /unlock command"""
        if not config.ENABLE_LOCK_SYSTEM:
            return

        try:
            if len(parts) < 2:
                await message.reply("Usage: /unlock <user_id>")
                return

            user_id = int(parts[1])
            success = await self.lock_manager.unlock_user(message.chat_id, user_id)

            response = f"🔓 User {user_id} unlocked" if success else "❌ User not found in lock list"

            if config.ENABLE_PRIVACY_SYSTEM:
                await self.privacy_manager.process_private_command(
                    self.client, message, response
                )
            else:
                await message.reply(response)

        except ValueError:
            await message.reply("❌ Invalid user ID")
        except Exception as e:
            await message.reply(f"❌ Error unlocking user: {str(e)}")

    async def _handle_tag_command(self, message, parts):
        """Handle /tag command"""
        if not config.ENABLE_TAG_SYSTEM:
            await message.reply("🏷️ Tag system is disabled")
            return

        try:
            if len(parts) < 2:
                await message.reply("Usage: /tag <message>")
                return

            tag_message = ' '.join(parts[1:])

            success = await self.tag_manager.start_tag_all(
                self.client, message.chat_id, tag_message, message.sender_id
            )

            if success:
                await message.reply("🏷️ Starting tag all process...")
            else:
                await message.reply("❌ Tag process already running or failed to start")

        except Exception as e:
            await message.reply(f"❌ Error starting tag: {str(e)}")

    async def _handle_start_command(self, message):
        """Handle /start command"""
        user = await message.get_sender()
        welcome_text = f"""
👋 **Welcome {user.first_name}!**

🎵 **VBot Python - Music & Management Bot**

I'm a feature-rich Telegram bot with:
• 🎵 Music player with yt-dlp integration
• 🔒 User lock system with auto-delete
• 🏷️ Progressive tag all members
• 👋 Welcome system for new members
• ⚙️ Multiple permission levels

**Quick Commands:**
• /play <song> - Play music from YouTube
• /tagall <text> - Mention all group members
• /lock @user - Lock user (auto-delete their messages)
• /welcome <text> - Set welcome message for new members

**More Commands:**
📁 /help - Show detailed command list
ℹ️ /about - Bot information
📊 .stats - Bot statistics (developers only)

**Permission Levels:**
/ - Admin commands (for group admins)
. - Developer commands (bot developers only)
# - Public commands (everyone can use)

**Support:** @VZLfxs
"""
        await message.reply(welcome_text)

    async def _handle_about_command(self, message):
        """Handle /about command"""
        about_text = """
ℹ️ **About VBot Python**

**Version:** 2.0.0 Python
**Developer:** Vzoel Fox
**Built with:** Python & Telethon

**Features:**
✅ Music System (YouTube)
✅ Lock/Unlock System
✅ Tag All Members
✅ Welcome System
✅ Premium Emoji Support
✅ Auto Backup System
✅ Privacy Mode
✅ Multi-level Permissions

**Tech Stack:**
• Python 3.12+
• Telethon
• yt-dlp
• AsyncIO

**Contact:** @VZLfxs

Made with ❤️ by Vzoel Fox
"""
        await message.reply(about_text)

    async def _handle_help_command(self, message):
        """Handle #help command"""
        help_text = """
📚 **VBot Python - Complete Command List**

**🎵 Music Commands:**
• /play <song> - Play music from YouTube
• /music <song> - Alias for /play

**🔒 Lock System (Admin):**
• /lock @user [reason] - Lock user (auto-delete their messages)
• /unlock <user_id> - Unlock user
• /locklist - Show all locked users

**🏷️ Tag System (Admin):**
• /tag <message> - Tag all group members
• /tagall <message> - Alias for /tag
• /ctag - Cancel ongoing tag process

**👋 Welcome System (Admin/Dev):**
• /welcome <message> - Set welcome message for new members
• /setwelcome <message> - Alias for /welcome

**📊 Developer Commands:**
• .stats - Show bot statistics
• .status - Alias for .stats

**🌐 Public Commands:**
• #help - Show this help
• #rules - Show group rules
• #session - Generate session string

**ℹ️ General:**
• /start - Welcome message
• /help - Same as /start
• /about - Bot information

**💡 Permission Levels:**
/ = Admin commands (group admins)
. = Developer commands (bot devs only)
# = Public commands (everyone)

**🔧 Support:** @VZLfxs
"""
        await message.reply(help_text)

    async def _handle_stats_command(self, message):
        """Handle .stats command"""
        try:
            stats = {
                'music': self.music_manager.get_download_stats() if config.MUSIC_ENABLED else {},
                'lock': self.lock_manager.get_lock_stats() if config.ENABLE_LOCK_SYSTEM else {},
                'tag': self.tag_manager.get_tag_stats() if config.ENABLE_TAG_SYSTEM else {},
                'welcome': self.welcome_manager.get_welcome_stats() if config.ENABLE_WELCOME_SYSTEM else {},
                'github': self.github_sync.get_sync_stats() if config.ENABLE_GITHUB_SYNC else {},
                'privacy': self.privacy_manager.get_privacy_stats() if config.ENABLE_PRIVACY_SYSTEM else {}
            }

            stats_text = "📊 **VBot Statistics:**\n\n"

            if stats['lock']:
                stats_text += f"🔒 **Lock System:**\n"
                stats_text += f"• Locked users: {stats['lock'].get('total_locked_users', 0)}\n"
                stats_text += f"• Chats with locks: {stats['lock'].get('chats_with_locks', 0)}\n\n"

            if stats['music']:
                stats_text += f"🎵 **Music System:**\n"
                stats_text += f"• Downloaded files: {stats['music'].get('total_files', 0)}\n"
                stats_text += f"• Storage used: {stats['music'].get('total_size_mb', 0)} MB\n\n"

            if stats['github']:
                stats_text += f"📁 **GitHub Sync:**\n"
                stats_text += f"• Configured: {'Yes' if stats['github'].get('github_configured') else 'No'}\n"
                stats_text += f"• Queue size: {stats['github'].get('queue_size', 0)}\n\n"

            if config.ENABLE_PRIVACY_SYSTEM:
                await self.privacy_manager.process_private_command(
                    self.client, message, stats_text
                )
            else:
                await message.reply(stats_text)

        except Exception as e:
            await message.reply(f"❌ Error getting stats: {str(e)}")

    async def _handle_callback(self, event):
        """Handle callback queries"""
        try:
            data = event.data.decode('utf-8')

            if data.startswith('music_'):
                await self.music_manager.handle_music_callback(self.client, event)
            elif data.startswith('welcome_'):
                await self.welcome_manager.handle_welcome_callback(self.client, event)
            else:
                await event.answer("Unknown callback")

        except Exception as e:
            logger.error(f"Error handling callback: {e}")

    async def run(self):
        """Run VBot"""
        logger.info("🎵 Starting VBot Python...")

        if await self.initialize():
            logger.info("🚀 VBot is running! Press Ctrl+C to stop.")
            await self.client.run_until_disconnected()
        else:
            logger.error("❌ Failed to start VBot")
            sys.exit(1)

    async def stop(self):
        """Stop VBot gracefully"""
        logger.info("🛑 Stopping VBot...")

        if self.tag_manager:
            await self.tag_manager.force_stop_all_tags()

        if self.client:
            await self.client.disconnect()

        logger.info("👋 VBot stopped")

async def main():
    """Main entry point"""
    vbot = VBot()

    try:
        await vbot.run()
    except KeyboardInterrupt:
        await vbot.stop()
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        await vbot.stop()
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())