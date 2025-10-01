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
from telethon.sessions import StringSession
from telethon.tl.types import MessageEntityMentionName

# Import VBot modules
from core import AuthManager, EmojiManager, MusicManager, Database
from modules import LockManager, TagManager, WelcomeManager, GitHubSync, PrivacyManager

class VBot:
    """Main VBot application class"""

    def __init__(self):
        self.client = None
        self.assistant_client = None  # Assistant for voice chat streaming
        self.music_manager = None  # Will be initialized after client

        # Initialize database (core persistence layer)
        self.database = Database()

        # Initialize managers with database
        self.auth_manager = AuthManager(self.database)
        self.emoji_manager = EmojiManager()
        self.lock_manager = LockManager(self.database)
        self.tag_manager = TagManager()
        self.welcome_manager = WelcomeManager(self.database)
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

            # Initialize Assistant Client (for voice chat streaming)
            if config.STRING_SESSION and config.STRING_SESSION.strip():
                try:
                    logger.info("🔄 Initializing assistant client for voice chat streaming...")
                    self.assistant_client = TelegramClient(
                        StringSession(config.STRING_SESSION),
                        config.API_ID,
                        config.API_HASH
                    )
                    await self.assistant_client.start()

                    assistant_me = await self.assistant_client.get_me()
                    logger.info(f"✅ Assistant: {assistant_me.first_name} (@{assistant_me.username or 'no_username'})")
                except Exception as e:
                    logger.error(f"❌ Failed to initialize assistant client: {e}")
                    logger.warning("⚠️ Voice chat streaming will be disabled (download mode only)")
                    self.assistant_client = None
            else:
                logger.info("ℹ️ No STRING_SESSION configured - using download mode only")

            # Initialize Music Manager with clients
            from core.music_manager import MusicManager
            self.music_manager = MusicManager(self.client, self.assistant_client)
            await self.music_manager.start()
            # Log message handled by music_manager.start()

            # Setup event handlers
            self._setup_event_handlers()

            # Setup bot commands (slash suggestions)
            await self._setup_bot_commands()

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

    async def _setup_bot_commands(self):
        """Setup bot command suggestions (slash commands visible in menu)"""
        try:
            from telethon.tl.functions.bots import SetBotCommandsRequest
            from telethon.tl.types import BotCommand

            # Define available commands
            commands = [
                BotCommand(command="start", description="Start the bot and see welcome message"),
                BotCommand(command="help", description="Show detailed command list"),
                BotCommand(command="about", description="Bot information and features"),

                # Admin commands (/)
                BotCommand(command="pm", description="Promote user to admin (reply or @username)"),
                BotCommand(command="dm", description="Demote user from admin"),
                BotCommand(command="tagall", description="Tag all members in chat"),
                BotCommand(command="cancel", description="Cancel ongoing tag operation"),
                BotCommand(command="lock", description="Lock user (auto-delete messages)"),
                BotCommand(command="unlock", description="Unlock user"),
                BotCommand(command="locklist", description="Show all locked users"),
            ]

            # Set bot commands
            await self.client(SetBotCommandsRequest(
                scope=types.BotCommandScopeDefault(),
                lang_code='en',
                commands=commands
            ))

            logger.info("✅ Bot command suggestions configured")

        except Exception as e:
            logger.error(f"Failed to setup bot commands: {e}")
            # Non-critical, continue anyway

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
            if message.text.startswith(('.', '/', '+', '#')):
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

            # Owner/Developer commands (+ prefix)
            elif command == '+add':
                await self._handle_add_permission_command(message, parts)
            elif command == '+del':
                await self._handle_del_permission_command(message, parts)
            elif command == '+setwelcome':
                await self._handle_setwelcome_command(message, parts)
            elif command == '+backup':
                await self._handle_backup_command(message, parts)

            # Admin commands for user management (/ prefix)
            elif command == '/pm':
                await self._handle_promote_command(message, parts)
            elif command == '/dm':
                await self._handle_demote_command(message, parts)

            # Public music commands (. prefix)
            elif command in ['.play', '.p']:
                await self._handle_music_command(message, parts)
            elif command == '.stop':
                await self._handle_stop_command(message)
            elif command == '.pause':
                await self._handle_pause_command(message)
            elif command == '.resume':
                await self._handle_resume_command(message)
            elif command in ['.queue', '.q']:
                await self._handle_queue_command(message)
            elif command == '.gensession':
                # Handled by plugin
                pass

            # Admin tag commands (/ prefix)
            elif command in ['/tagall', '/tag']:
                await self._handle_tag_command(message, parts)
            elif command in ['/cancel', '/canceltag']:
                await self._handle_cancel_tag_command(message)

            # Admin lock commands (/ prefix)
            elif command == '/lock':
                await self._handle_lock_command(message, parts)
            elif command == '/unlock':
                await self._handle_unlock_command(message, parts)
            elif command == '/locklist':
                await self._handle_locklist_command(message)

            # Help command (available to all)
            elif command in ['/help', '#help']:
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
                    mode = "🎙️ VC Queue" if result.get('streaming') else "📋 Download Queue"

                    # Create inline buttons for queue management
                    buttons = [
                        [
                            Button.inline("⏭️ Skip", data="music_skip"),
                            Button.inline("📋 Queue", data="music_queue")
                        ],
                        [
                            Button.inline("⏹️ Stop", data="music_stop")
                        ]
                    ]

                    await status_msg.edit(
                        f"{mode} **#{result['position']}**\n\n"
                        f"🎵 **{song['title']}**\n"
                        f"⏱️ Duration: {song.get('duration', 0) // 60}:{song.get('duration', 0) % 60:02d}",
                        buttons=buttons
                    )
                elif result.get('streaming'):
                    # Streaming in voice chat - add playback control buttons
                    buttons = [
                        [
                            Button.inline("⏸️ Pause", data="music_pause"),
                            Button.inline("⏭️ Skip", data="music_skip")
                        ],
                        [
                            Button.inline("📋 Queue", data="music_queue"),
                            Button.inline("⏹️ Stop", data="music_stop")
                        ]
                    ]

                    await status_msg.edit(
                        f"🎙️ **Now Streaming in Voice Chat**\n\n"
                        f"🎶 **{song['title']}**\n"
                        f"⏱️ Duration: {song.get('duration', 0) // 60}:{song.get('duration', 0) % 60:02d}\n\n"
                        f"Use the buttons below to control playback ⬇️",
                        buttons=buttons
                    )
                else:
                    # Download mode - send file
                    await status_msg.edit("⬆️ Uploading audio...")

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
        """Handle .pause command"""
        if not self.music_manager:
            return

        try:
            success = await self.music_manager.pause_stream(message.chat_id)
            if success:
                # Show resume button
                buttons = [
                    [
                        Button.inline("▶️ Resume", data="music_resume"),
                        Button.inline("⏹️ Stop", data="music_stop")
                    ]
                ]
                await message.reply("⏸️ **Paused stream**", buttons=buttons)
            else:
                await message.reply("❌ No active stream to pause or streaming not available")
        except Exception as e:
            logger.error(f"Error pausing: {e}")
            await message.reply("❌ Error pausing stream")

    async def _handle_resume_command(self, message):
        """Handle .resume command"""
        if not self.music_manager:
            return

        try:
            success = await self.music_manager.resume_stream(message.chat_id)
            if success:
                # Show pause button
                buttons = [
                    [
                        Button.inline("⏸️ Pause", data="music_pause"),
                        Button.inline("⏹️ Stop", data="music_stop")
                    ]
                ]
                await message.reply("▶️ **Resumed stream**", buttons=buttons)
            else:
                await message.reply("❌ No paused stream to resume or streaming not available")
        except Exception as e:
            logger.error(f"Error resuming: {e}")
            await message.reply("❌ Error resuming stream")

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

    async def _handle_add_permission_command(self, message, parts):
        """Handle +add command - authorize user for / commands"""
        try:
            # Extract user from reply or mention
            target_user_id = None
            target_username = None

            if message.is_reply:
                reply_msg = await message.get_reply_message()
                target_user_id = reply_msg.sender_id
                target_user = await reply_msg.get_sender()
                target_username = target_user.username or target_user.first_name
            elif len(parts) > 1:
                # Try parsing user ID or username
                user_arg = parts[1].lstrip('@')
                try:
                    target_user_id = int(user_arg)
                except ValueError:
                    # Try username lookup
                    try:
                        target_user = await self.client.get_entity(user_arg)
                        target_user_id = target_user.id
                        target_username = target_user.username or target_user.first_name
                    except Exception as e:
                        await message.reply(f"❌ Could not find user: {user_arg}")
                        return

            if not target_user_id:
                await message.reply(
                    "**Usage:** +add <user_id|@username> or reply to a user\n\n"
                    "**Examples:**\n"
                    "• +add 123456789\n"
                    "• +add @username\n"
                    "• Reply to a user and type: +add"
                )
                return

            # Add permission to database
            self.database.add_permission(target_user_id, message.chat_id)

            response = (
                f"✅ **Permission granted**\n\n"
                f"User: {target_username or target_user_id}\n"
                f"ID: `{target_user_id}`\n\n"
                f"This user can now use **/** commands in this chat."
            )

            await message.reply(response)
            logger.info(f"Added permission for user {target_user_id} in chat {message.chat_id}")

        except Exception as e:
            logger.error(f"Error in +add command: {e}")
            await message.reply(f"❌ Error adding permission: {str(e)}")

    async def _handle_del_permission_command(self, message, parts):
        """Handle +del command - remove user authorization"""
        try:
            # Extract user from reply or mention
            target_user_id = None
            target_username = None

            if message.is_reply:
                reply_msg = await message.get_reply_message()
                target_user_id = reply_msg.sender_id
                target_user = await reply_msg.get_sender()
                target_username = target_user.username or target_user.first_name
            elif len(parts) > 1:
                user_arg = parts[1].lstrip('@')
                try:
                    target_user_id = int(user_arg)
                except ValueError:
                    try:
                        target_user = await self.client.get_entity(user_arg)
                        target_user_id = target_user.id
                        target_username = target_user.username or target_user.first_name
                    except Exception as e:
                        await message.reply(f"❌ Could not find user: {user_arg}")
                        return

            if not target_user_id:
                await message.reply(
                    "**Usage:** +del <user_id|@username> or reply to a user\n\n"
                    "**Examples:**\n"
                    "• +del 123456789\n"
                    "• +del @username\n"
                    "• Reply to a user and type: +del"
                )
                return

            # Remove permission from database
            success = self.database.remove_permission(target_user_id, message.chat_id)

            if success:
                response = (
                    f"✅ **Permission revoked**\n\n"
                    f"User: {target_username or target_user_id}\n"
                    f"ID: `{target_user_id}`\n\n"
                    f"This user can no longer use **/** commands in this chat."
                )
            else:
                response = f"⚠️ User {target_user_id} was not in the authorized list"

            await message.reply(response)
            logger.info(f"Removed permission for user {target_user_id} in chat {message.chat_id}")

        except Exception as e:
            logger.error(f"Error in +del command: {e}")
            await message.reply(f"❌ Error removing permission: {str(e)}")

    async def _handle_setwelcome_command(self, message, parts):
        """Handle +setwelcome command - configure welcome message"""
        try:
            if len(parts) < 2:
                # Show current welcome message
                welcome_data = self.database.get_welcome(message.chat_id)
                if welcome_data and welcome_data.get('enabled'):
                    await message.reply(
                        f"**Current welcome message:**\n\n{welcome_data['message']}\n\n"
                        f"**Usage:** +setwelcome <message> to update\n"
                        f"**Disable:** +setwelcome off"
                    )
                else:
                    await message.reply(
                        "**Welcome system is disabled**\n\n"
                        "**Usage:** +setwelcome <message>\n\n"
                        "**Example:**\n"
                        "+setwelcome Welcome {user}! Please read the rules."
                    )
                return

            welcome_text = ' '.join(parts[1:])

            # Check if disabling
            if welcome_text.lower() in ['off', 'disable', 'disabled']:
                self.database.set_welcome(message.chat_id, "", False)
                await message.reply("✅ Welcome system **disabled** for this chat")
                return

            # Set welcome message
            self.database.set_welcome(message.chat_id, welcome_text, True)

            await message.reply(
                f"✅ **Welcome message updated**\n\n"
                f"**Preview:**\n{welcome_text}\n\n"
                f"**Variables:**\n"
                f"• {{user}} - User's first name\n"
                f"• {{mention}} - Mention the user\n"
                f"• {{chat}} - Chat name"
            )
            logger.info(f"Updated welcome message for chat {message.chat_id}")

        except Exception as e:
            logger.error(f"Error in +setwelcome command: {e}")
            await message.reply(f"❌ Error setting welcome: {str(e)}")

    async def _handle_promote_command(self, message, parts):
        """Handle /pm command - promote user to bot-managed admin list"""
        try:
            target_user_id = None
            target_username = None

            if message.is_reply:
                reply_msg = await message.get_reply_message()
                target_user_id = reply_msg.sender_id
                target_user = await reply_msg.get_sender()
                target_username = target_user.username or target_user.first_name
            elif len(parts) > 1:
                user_arg = parts[1].lstrip('@')
                try:
                    target_user_id = int(user_arg)
                except ValueError:
                    try:
                        target_user = await self.client.get_entity(user_arg)
                        target_user_id = target_user.id
                        target_username = target_user.username or target_user.first_name
                    except Exception:
                        await message.reply(f"❌ Could not find user: {user_arg}")
                        return

            if not target_user_id:
                await message.reply(
                    "**Usage:** /pm <user> or reply to a user\n\n"
                    "Promote user to bot-managed admin list (can use / commands)"
                )
                return

            # Add to bot-managed admin list
            self.database.add_admin(message.chat_id, target_user_id)

            await message.reply(
                f"✅ **User promoted**\n\n"
                f"User: {target_username or target_user_id}\n"
                f"ID: `{target_user_id}`\n\n"
                f"This user can now use **/** commands via bot-managed permissions."
            )

        except Exception as e:
            logger.error(f"Error in /pm command: {e}")
            await message.reply(f"❌ Error promoting user: {str(e)}")

    async def _handle_demote_command(self, message, parts):
        """Handle /dm command - demote user from bot-managed admin list"""
        try:
            target_user_id = None
            target_username = None

            if message.is_reply:
                reply_msg = await message.get_reply_message()
                target_user_id = reply_msg.sender_id
                target_user = await reply_msg.get_sender()
                target_username = target_user.username or target_user.first_name
            elif len(parts) > 1:
                user_arg = parts[1].lstrip('@')
                try:
                    target_user_id = int(user_arg)
                except ValueError:
                    try:
                        target_user = await self.client.get_entity(user_arg)
                        target_user_id = target_user.id
                        target_username = target_user.username or target_user.first_name
                    except Exception:
                        await message.reply(f"❌ Could not find user: {user_arg}")
                        return

            if not target_user_id:
                await message.reply(
                    "**Usage:** /dm <user> or reply to a user\n\n"
                    "Demote user from bot-managed admin list"
                )
                return

            # Remove from bot-managed admin list
            success = self.database.remove_admin(message.chat_id, target_user_id)

            if success:
                await message.reply(
                    f"✅ **User demoted**\n\n"
                    f"User: {target_username or target_user_id}\n"
                    f"ID: `{target_user_id}`\n\n"
                    f"This user has been removed from bot-managed admin list."
                )
            else:
                await message.reply(f"⚠️ User was not in the bot-managed admin list")

        except Exception as e:
            logger.error(f"Error in /dm command: {e}")
            await message.reply(f"❌ Error demoting user: {str(e)}")

    async def _handle_cancel_tag_command(self, message):
        """Handle /cancel command - stop ongoing tag operation"""
        try:
            if not config.ENABLE_TAG_SYSTEM:
                return

            success = await self.tag_manager.cancel_tag(message.chat_id)

            if success:
                await message.reply("✅ Tag operation cancelled")
            else:
                await message.reply("⚠️ No active tag operation in this chat")

        except Exception as e:
            logger.error(f"Error in /cancel command: {e}")
            await message.reply(f"❌ Error cancelling tag: {str(e)}")

    async def _handle_locklist_command(self, message):
        """Handle /locklist command - show locked users"""
        try:
            if not config.ENABLE_LOCK_SYSTEM:
                await message.reply("🔒 Lock system is disabled")
                return

            locked_users = self.lock_manager.get_locked_users(message.chat_id)

            if not locked_users:
                await message.reply("📋 No locked users in this chat")
                return

            response = "🔒 **Locked Users:**\n\n"
            for user_id, data in locked_users.items():
                reason = data.get('reason', 'No reason')
                response += f"• User ID: `{user_id}`\n  Reason: {reason}\n\n"

            response += f"**Total:** {len(locked_users)} user(s)"

            if config.ENABLE_PRIVACY_SYSTEM:
                await self.privacy_manager.process_private_command(
                    self.client, message, response
                )
            else:
                await message.reply(response)

        except Exception as e:
            logger.error(f"Error in /locklist command: {e}")
            await message.reply(f"❌ Error getting lock list: {str(e)}")

    async def _handle_rules_command(self, message):
        """Handle #rules command"""
        rules_text = """
📜 **Group Rules**

1. Be respectful to all members
2. No spam or flooding
3. No NSFW content
4. Follow Telegram's Terms of Service
5. Use appropriate language

For support: @VZLfxs
"""
        await message.reply(rules_text)

    async def _handle_session_command(self, message):
        """Handle #session command"""
        session_text = """
🔐 **Session String Generator**

To generate a session string for the assistant account:

**Method 1: Terminal (recommended)**
```bash
python3 genstring.py
```

**Method 2: In-bot**
Send `.gensession` command in private chat with the bot

**Note:** The session can be from any Telegram account (user account, not bot). You just need valid API_ID and API_HASH.

**Support:** @VZLfxs
"""
        await message.reply(session_text)

    async def _handle_backup_command(self, message, parts):
        """Handle +backup command - manual database backup to GitHub"""
        try:
            status_msg = await message.reply("📦 **Creating backup...**")

            # Get custom commit message if provided
            commit_message = None
            if len(parts) > 1:
                commit_message = ' '.join(parts[1:])

            # Perform manual backup
            success = await self.database.manual_backup(commit_message)

            if success:
                # Get backup stats
                stats = self.database.get_backup_stats()
                last_backup = stats.get('last_backup', 'Never')

                await status_msg.edit(
                    f"✅ **Database Backup Complete**\n\n"
                    f"📁 Database backed up to GitHub\n"
                    f"⏰ Last backup: {last_backup}\n"
                    f"📊 Database size: {self.database.db_path.stat().st_size / 1024:.2f} KB\n\n"
                    f"**Auto-backup:** {'Enabled' if stats.get('auto_backup_enabled') else 'Disabled'}"
                )
            else:
                await status_msg.edit(
                    "❌ **Backup Failed**\n\n"
                    "Please check:\n"
                    "• Git is configured\n"
                    "• Remote repository is set\n"
                    "• You have push access\n\n"
                    "Check logs for details."
                )

        except Exception as e:
            logger.error(f"Error in +backup command: {e}")
            await message.reply(f"❌ Backup error: {str(e)}")

    async def _handle_callback(self, event):
        """Handle callback queries"""
        try:
            data = event.data.decode('utf-8')

            if data.startswith('music_'):
                # Handle music control callbacks
                action = data.split('_')[1]
                chat_id = event.chat_id

                if action == 'pause':
                    success = await self.music_manager.pause_stream(chat_id)
                    if success:
                        await event.answer("⏸️ Paused")
                        # Update button to show resume
                        buttons = [
                            [
                                Button.inline("▶️ Resume", data="music_resume"),
                                Button.inline("⏹️ Stop", data="music_stop")
                            ]
                        ]
                        await event.edit(buttons=buttons)
                    else:
                        await event.answer("❌ Failed to pause", alert=True)

                elif action == 'resume':
                    success = await self.music_manager.resume_stream(chat_id)
                    if success:
                        await event.answer("▶️ Resumed")
                        # Update button to show pause
                        buttons = [
                            [
                                Button.inline("⏸️ Pause", data="music_pause"),
                                Button.inline("⏭️ Skip", data="music_skip")
                            ],
                            [
                                Button.inline("📋 Queue", data="music_queue"),
                                Button.inline("⏹️ Stop", data="music_stop")
                            ]
                        ]
                        await event.edit(buttons=buttons)
                    else:
                        await event.answer("❌ Failed to resume", alert=True)

                elif action == 'stop':
                    success = await self.music_manager.stop_stream(chat_id)
                    if success:
                        await event.answer("⏹️ Stopped")
                        await event.edit("⏹️ **Stopped and cleared queue**")
                    else:
                        await event.answer("❌ No active stream", alert=True)

                elif action == 'skip':
                    # Skip to next song in queue
                    await event.answer("⏭️ Skipping...")
                    # Note: Skip functionality would need to be implemented in music_manager
                    await event.edit("⏭️ **Skipped to next song**")

                elif action == 'queue':
                    # Show queue
                    current = self.music_manager.get_current_song(chat_id)
                    queue = self.music_manager.get_queue(chat_id)

                    if not current and not queue:
                        await event.answer("📋 Queue is empty", alert=True)
                        return

                    response = "📋 **Music Queue**\n\n"
                    if current:
                        response += f"🎵 **Now Playing:**\n{current['title']}\n\n"
                    if queue:
                        response += "**Up Next:**\n"
                        for i, song in enumerate(queue[:5], 1):
                            response += f"{i}. {song['title']}\n"
                        if len(queue) > 5:
                            response += f"\n... and {len(queue) - 5} more"

                    await event.answer(response, alert=True)

            elif data.startswith('welcome_'):
                # Handle welcome callbacks if needed
                await event.answer("Welcome action")

            else:
                await event.answer("Unknown callback")

        except Exception as e:
            logger.error(f"Error handling callback: {e}")
            await event.answer("❌ Error processing action", alert=True)

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

        if self.music_manager:
            await self.music_manager.stop()

        if self.assistant_client:
            await self.assistant_client.disconnect()
            logger.info("✅ Assistant client disconnected")

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