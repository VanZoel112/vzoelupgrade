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
from config import load_config, validate_config

# Import Telethon
from telethon import TelegramClient, events, Button
from telethon.tl.types import MessageEntityMentionName

# Import VBot modules
from core import AuthManager, EmojiManager, MusicManager
from modules import LockManager, TagManager, WelcomeManager, GitHubSync, PrivacyManager

class VBot:
    """Main VBot application class"""

    def __init__(self):
        self.config = load_config()
        self.client = None

        # Initialize managers
        self.auth_manager = AuthManager(self.config)
        self.emoji_manager = EmojiManager(self.config)
        self.music_manager = MusicManager(self.config)
        self.lock_manager = LockManager(self.config)
        self.tag_manager = TagManager(self.config)
        self.welcome_manager = WelcomeManager(self.config)
        self.github_sync = GitHubSync(self.config)
        self.privacy_manager = PrivacyManager(self.config)

    async def initialize(self):
        """Initialize VBot"""
        try:
            # Validate configuration
            config_errors = validate_config(self.config)
            if config_errors:
                logger.error("Configuration errors:")
                for error in config_errors:
                    logger.error(f"  - {error}")
                return False

            # Initialize Telegram client
            self.client = TelegramClient(
                self.config.telegram.session_name,
                self.config.telegram.api_id,
                self.config.telegram.api_hash
            )

            await self.client.start(bot_token=self.config.telegram.bot_token)

            # Get bot info
            me = await self.client.get_me()
            logger.info(f"🎵 VBot started successfully!")
            logger.info(f"Bot: {me.first_name} (@{me.username})")

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
                if self.config.enable_welcome_system:
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
            if self.config.enable_lock_system:
                deleted = await self.lock_manager.process_message_for_locked_users(
                    self.client, message
                )
                if deleted:
                    return

            # Process emojis for premium users
            if self.config.enable_premium_emoji and hasattr(message, 'sender_id'):
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

                if self.config.enable_privacy_system:
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
            # Music commands
            if command in ['/play', '/p']:
                await self._handle_music_command(message, parts)

            # Lock commands
            elif command == '/lock':
                await self._handle_lock_command(message, parts)
            elif command == '/unlock':
                await self._handle_unlock_command(message, parts)
            elif command == '/locklist':
                await self._handle_locklist_command(message)

            # Tag commands
            elif command == '/tag':
                await self._handle_tag_command(message, parts)
            elif command == '/ctag':
                await self._handle_cancel_tag_command(message)

            # Welcome commands
            elif command in ['.setwelcome', '.welcome']:
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
                await message.reply(f"❓ Unknown command: {command}")

        except Exception as e:
            logger.error(f"Error routing command {command}: {e}")

    async def _handle_music_command(self, message, parts):
        """Handle music commands"""
        if not self.config.enable_music:
            await message.reply("🎵 Music system is disabled")
            return

        try:
            if len(parts) < 2:
                await message.reply("🎵 Usage: /play <song name or URL>")
                return

            query = ' '.join(parts[1:])

            # Search for music
            results = await self.music_manager.search_music(query, max_results=1)
            if not results:
                await message.reply("❌ No music found for your query")
                return

            # Download audio
            song_info = results[0]
            download_result = await self.music_manager.download_audio(
                song_info['url'], message.sender_id
            )

            if download_result:
                # Create music keyboard
                keyboard = self.music_manager.create_music_keyboard(
                    message.chat_id, song_info['id']
                )

                # Format info
                info_text = self.music_manager.format_music_info(song_info)

                # Send with controls
                await message.reply(
                    f"🎵 **Now Playing:**\n\n{info_text}",
                    buttons=keyboard
                )

                # Send audio file
                await self.client.send_file(
                    message.chat_id,
                    download_result['file_path'],
                    caption=f"🎵 {song_info['title']}"
                )

        except Exception as e:
            await message.reply(f"❌ Error playing music: {str(e)}")

    async def _handle_lock_command(self, message, parts):
        """Handle /lock command"""
        if not self.config.enable_lock_system:
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
                    if self.config.enable_github_sync:
                        await self.github_sync.queue_sync('lock_data', {
                            'chat_id': message.chat_id,
                            'user_id': user_id,
                            'reason': reason
                        })
                else:
                    response = "❌ Failed to lock user"

                if self.config.enable_privacy_system:
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
        if not self.config.enable_lock_system:
            return

        try:
            if len(parts) < 2:
                await message.reply("Usage: /unlock <user_id>")
                return

            user_id = int(parts[1])
            success = await self.lock_manager.unlock_user(message.chat_id, user_id)

            response = f"🔓 User {user_id} unlocked" if success else "❌ User not found in lock list"

            if self.config.enable_privacy_system:
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
        if not self.config.enable_tag_system:
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

    async def _handle_help_command(self, message):
        """Handle #help command"""
        help_text = """
🎵 **VBot Python - Help**

**Music Commands:**
/play <song> - Play music from YouTube

**Admin Commands:**
/lock <user> - Lock user (auto-delete messages)
/unlock <user_id> - Unlock user
/tag <message> - Tag all members

**Developer Commands:**
.stats - Bot statistics
.setwelcome <message> - Set welcome message

**Public Commands:**
#help - Show this help
#rules - Show group rules
#session - Generate session string

💡 **Prefixes:**
/ - Admin commands
. - Developer commands
# - Public commands
"""
        await message.reply(help_text)

    async def _handle_stats_command(self, message):
        """Handle .stats command"""
        try:
            stats = {
                'music': self.music_manager.get_download_stats() if self.config.enable_music else {},
                'lock': self.lock_manager.get_lock_stats() if self.config.enable_lock_system else {},
                'tag': self.tag_manager.get_tag_stats() if self.config.enable_tag_system else {},
                'welcome': self.welcome_manager.get_welcome_stats() if self.config.enable_welcome_system else {},
                'github': self.github_sync.get_sync_stats() if self.config.enable_github_sync else {},
                'privacy': self.privacy_manager.get_privacy_stats() if self.config.enable_privacy_system else {}
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

            if self.config.enable_privacy_system:
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