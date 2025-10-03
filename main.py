#!/usr/bin/env python3
"""
VBot Python - Main Application
Vzoel Robot Music Bot with comprehensive features

Author: Vzoel Fox's
Version: 2.0.0 Python
"""

import asyncio
import logging
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

# Import advanced logging system
from core.logger import setup_logging, vbot_logger

logger = logging.getLogger(__name__)

# Import configuration and validate
import config

# Import Telethon
from telethon import TelegramClient, events, Button, types
from telethon.sessions import StringSession
from telethon.tl.types import MessageEntityMentionName
from telethon.tl.functions.bots import SetBotCommandsRequest
from telethon.tl.types import BotCommand, BotCommandScopeDefault

# Import VBot modules
from core.auth_manager import AuthManager
from core.emoji_manager import EmojiManager
from core.music_manager import MusicManager
from core.database import Database
from core.branding import VBotBranding
from core.plugin_loader import PluginLoader
from modules.lock_manager import LockManager
from modules.tag_manager import TagManager
from modules.welcome_manager import WelcomeManager
from modules.github_sync import GitHubSync
from modules.privacy_manager import PrivacyManager


@dataclass
class CommandStatus:
    """Context information for an in-flight command."""

    start_time: datetime
    status_message: Optional[object] = None


class VBot:
    """Main VBot application class"""

    def __init__(self):
        self.client = None
        self.assistant_client = None  # Assistant for voice chat streaming
        self.music_manager = None  # Will be initialized after client

        # Initialize database (core persistence layer)
        self.database = Database()

        # Track startup time for diagnostics
        self.start_time = None

        # Initialize managers with database
        self.auth_manager = AuthManager()
        self.emoji_manager = EmojiManager()
        self.lock_manager = LockManager(self.database)
        self.tag_manager = TagManager()
        self.welcome_manager = WelcomeManager(self.database)
        self.github_sync = GitHubSync()
        self.privacy_manager = PrivacyManager()
        self._command_context: Dict[int, CommandStatus] = {}
        self.plugin_loader = PluginLoader(
            enabled_plugins=getattr(config, "ENABLED_PLUGINS", None),
            disabled_plugins=getattr(config, "DISABLED_PLUGINS", None),
        )

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

            # Record bot start time (UTC)
            self.start_time = datetime.now(timezone.utc)

            # Setup advanced logging system with Telegram & SQL integration
            await setup_logging(self.client)

            # Log startup with bot info
            bot_info = {
                'first_name': me.first_name,
                'username': me.username,
                'user_id': me.id
            }
            await vbot_logger.log_startup(bot_info)

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
                except Exception as exc:
                    logger.error(f"Failed to initialize assistant client: {exc}")
                    self.assistant_client = None

            # Initialize Music Manager
            self.music_manager = MusicManager(self.client, self.assistant_client)

            # Register handlers
            self.client.add_event_handler(self._handle_message, events.NewMessage)

            # Setup bot commands
            await self._setup_bot_commands()

            # Load plugins dynamically
            loaded_plugins = await self.plugin_loader.load_plugins(self)
            if loaded_plugins:
                logger.info("Loaded plugins: %s", ", ".join(loaded_plugins))
            else:
                logger.info("No plugins loaded")

            logger.info("VBot initialization complete")
            return True

        except Exception as e:
            logger.error(f"Initialization error: {e}", exc_info=True)
            return False

    async def _setup_bot_commands(self):
        """Configure command suggestions for the bot"""
        try:
            commands = [
                # Core
                BotCommand(command="start", description="System overview and welcome"),
                BotCommand(command="help", description="Complete command reference"),
                BotCommand(command="about", description="System information"),

                # Music commands
                BotCommand(command="play", description="Play Mp3/audio from YouTube/Spotify/link"),
                BotCommand(command="vplay", description="Play mp4/webm video"),
                BotCommand(command="pause", description="Pause musik"),
                BotCommand(command="resume", description="Resume musik"),
                BotCommand(command="skip", description="Skip ke lagu berikutnya"),
                BotCommand(command="stop", description="Stop & clear queue"),
                BotCommand(command="queue", description="Lihat antrian"),
                BotCommand(command="shuffle", description="Acak queue"),
                BotCommand(command="loop", description="Loop mode (off/current/all)"),
                BotCommand(command="seek", description="Jump ke waktu tertentu"),
                BotCommand(command="volume", description="Adjust volume (0-200)"),

                # Admin commands
                BotCommand(command="pm", description="Promote user to admin"),
                BotCommand(command="dm", description="Demote user from admin"),
                BotCommand(command="tagall", description="Tag all members"),
                BotCommand(command="cancel", description="Cancel tag operation"),
                BotCommand(command="lock", description="Lock user (auto-delete)"),
                BotCommand(command="unlock", description="Unlock user"),
                BotCommand(command="locklist", description="Show locked users"),
                BotCommand(command="ping", description="Check bot responsiveness"),
            ]

            await self.client(SetBotCommandsRequest(
                scope=BotCommandScopeDefault(),
                lang_code='en',
                commands=commands
            ))

            logger.info("Bot command suggestions configured")

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
                _ = await self.emoji_manager.process_message_emojis(
                    self.client, message.text, message.sender_id
                )

            # Handle commands
            if message.text.startswith(('.', '/', '+', '#')):
                await self._handle_command(message)

        except Exception as e:
            logger.error(f"Error handling message: {e}")

    async def _handle_command(self, message):
        """Handle bot commands"""
        start_time = datetime.now()
        message_id = getattr(message, "id", None)
        if message_id is not None:
            self._command_context[message_id] = CommandStatus(start_time=start_time)
        command_text = message.text.lower()

        try:
            command_parts = command_text.split()
            command = command_parts[0]

            # Strip @botname from command (e.g., /start@vmusic_vbot -> /start)
            if '@' in command:
                command = command.split('@')[0]
                command_parts[0] = command

            # Check permissions
            has_permission = await self.auth_manager.check_permissions(
                self.client, message.sender_id, message.chat_id, command_text
            )

            if not has_permission:
                command_type = self.auth_manager.get_command_type(command_text)
                error_msg = self.auth_manager.get_permission_error_message(command_type)

                # Log failed permission check
                execution_time = (datetime.now() - start_time).total_seconds()
                await vbot_logger.log_command(
                    message.sender_id,
                    command_text,
                    success=False,
                    execution_time=execution_time,
                    error="Permission denied"
                )

                if config.ENABLE_PRIVACY_SYSTEM:
                    await self.privacy_manager.process_private_command(
                        self.client, message, error_msg
                    )
                else:
                    await message.reply(error_msg)
                return

            # Pre-run visual phases
            status_message = None
            if message_id is not None:
                status_message = await self._run_command_edit_phases(message, command)
                command_status = self._command_context.get(message_id)
                if command_status:
                    command_status.status_message = status_message

            # Route commands
            await self._route_command(message, command, command_parts)

            # Log successful command execution
            execution_time = (datetime.now() - start_time).total_seconds()
            await vbot_logger.log_command(
                message.sender_id,
                command_text,
                success=True,
                execution_time=execution_time
            )

        except Exception as e:
            # Log error with full context
            execution_time = (datetime.now() - start_time).total_seconds()
            await vbot_logger.log_error(
                e,
                context=f"Command execution: {command_text}",
                user_id=message.sender_id,
                send_to_telegram=True
            )

            await vbot_logger.log_command(
                message.sender_id,
                command_text,
                success=False,
                execution_time=execution_time,
                error=str(e)
            )

            command_status = self._command_context.get(message_id) if message_id is not None else None
            status_message = command_status.status_message if command_status else None
            if status_message:
                try:
                    await status_message.edit(
                        VBotBranding.format_error(f"{command_text} failed: {str(e)}")
                    )
                except Exception as edit_error:
                    logger.debug(f"Failed to update status message: {edit_error}")

        finally:
            self._finalize_command_status(message_id)

    def _finalize_command_status(self, message_id: Optional[int]):
        """Remove command context for a completed message."""

        if message_id is None:
            return

        self._command_context.pop(message_id, None)

    async def _route_command(self, message, command, parts):
        """Route commands to appropriate handlers"""
        try:
            # Basic bot commands
            if command in ['/start', '/help']:
                await self._handle_start_command(message)
            elif command == '/about':
                await self._handle_about_command(message)
            elif command == '/ping':
                await self._handle_ping_command(message)

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
            elif command in ['/adminlist', '/admins']:
                await self._handle_adminlist_command(message)

            # Music commands (slash prefix)
            elif command in ['/play', '/p']:
                await self._handle_music_command(message, parts, audio_only=True)
            elif command in ['/vplay', '/vp']:
                await self._handle_music_command(message, parts, audio_only=False)
            elif command == '/pause':
                await self._handle_pause_command(message)
            elif command == '/resume':
                await self._handle_resume_command(message)
            elif command == '/skip':
                await self._handle_skip_command(message)
            elif command == '/stop':
                await self._handle_stop_command(message)
            elif command == '/queue':
                await self._handle_queue_command(message)
            elif command == '/shuffle':
                await self._handle_shuffle_command(message)
            elif command == '/loop':
                await self._handle_loop_command(message, parts)
            elif command == '/seek':
                await self._handle_seek_command(message, parts)
            elif command == '/volume':
                await self._handle_volume_command(message, parts)

            # Lock system
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
            await message.reply(VBotBranding.format_error(f"Command error: {str(e)}"))

    async def _run_command_edit_phases(self, message, command):
        """Display a 12-phase status update for any command"""
        command_name = command.lstrip('/+.#') or command
        phases = [
            f"⚙️ {command_name.title()} • Phase 1/12 – Initializing",
            f"⚙️ {command_name.title()} • Phase 2/12 – Authorizing",
            f"⚙️ {command_name.title()} • Phase 3/12 – Preparing context",
            f"⚙️ {command_name.title()} • Phase 4/12 – Syncing data",
            f"⚙️ {command_name.title()} • Phase 5/12 – Gathering resources",
            f"⚙️ {command_name.title()} • Phase 6/12 – Processing",
            f"⚙️ {command_name.title()} • Phase 7/12 – Validating",
            f"⚙️ {command_name.title()} • Phase 8/12 – Optimizing",
            f"⚙️ {command_name.title()} • Phase 9/12 – Final checks",
            f"⚙️ {command_name.title()} • Phase 10/12 – Formatting output",
            f"⚙️ {command_name.title()} • Phase 11/12 – Polishing response",
            f"✅ {command_name.title()} • Phase 12/12 – Ready",
        ]

        try:
            status_message = await message.reply(phases[0])
        except Exception as reply_error:
            logger.debug(f"Unable to send status message: {reply_error}")
            return None

        for phase_text in phases[1:]:
            await asyncio.sleep(0.15)
            try:
                await status_message.edit(phase_text)
            except Exception as edit_error:
                logger.debug(f"Failed to edit status message: {edit_error}")
                break

        return status_message

    @staticmethod
    def _format_timedelta(delta):
        """Format timedelta for human-readable output"""
        total_seconds = int(delta.total_seconds())
        days, remainder = divmod(total_seconds, 86400)
        hours, remainder = divmod(remainder, 3600)
        minutes, seconds = divmod(remainder, 60)

        parts = []
        if days:
            parts.append(f"{days}d")
        if hours or parts:
            parts.append(f"{hours}h")
        if minutes or parts:
            parts.append(f"{minutes}m")
        parts.append(f"{seconds}s")

        return " ".join(parts)

    async def _handle_ping_command(self, message):
        """Handle /ping command accessible to all roles"""
        message_id = getattr(message, "id", None)
        command_status = self._command_context.get(message_id) if message_id is not None else None
        status_message = command_status.status_message if command_status else None

        now = datetime.now(timezone.utc)
        message_time = message.date
        if isinstance(message_time, datetime) and message_time.tzinfo is None:
            message_time = message_time.replace(tzinfo=timezone.utc)

        latency_ms = (now - message_time).total_seconds() * 1000

        processing_ms = None
        if command_status and isinstance(command_status.start_time, datetime):
            processing_ms = (datetime.now() - command_status.start_time).total_seconds() * 1000

        uptime_text = "Unknown"
        if isinstance(self.start_time, datetime):
            uptime_text = self._format_timedelta(now - self.start_time)

        result_lines = [
            "🏓 **Pong!**",
            f"**Latency:** `{latency_ms:.2f} ms`",
        ]

        if processing_ms is not None:
            result_lines.append(f"**Processing:** `{processing_ms:.2f} ms`")

        result_lines.append(f"**Uptime:** `{uptime_text}`")

        result_text = VBotBranding.wrap_message("\n".join(result_lines), include_footer=False)

        if status_message:
            try:
                await status_message.edit(result_text)
                return
            except Exception as edit_error:
                logger.debug(f"Failed to update ping status message: {edit_error}")

        await message.reply(result_text)

    async def _handle_start_command(self, message):
        """Handle /start and /help commands"""
        try:
            # Get bot info
            me = await self.client.get_me()
            bot_username = me.username or "VBot"

            # Build welcome message
            welcome_text = f"""
👋 **Welcome to {me.first_name}!**

🎵 **VBot Music Bot** - Full-featured Telegram music bot

**Quick Start:**
• `/play <query>` - Play audio from YouTube/Spotify
• `/vplay <query>` - Play video
• `/queue` - Show current queue
• `/help` - Show all commands

**Features:**
✅ YouTube & Spotify support
✅ Voice chat streaming
✅ Queue management
✅ Admin controls
✅ Session generator

**Get Started:**
Type `/help` for complete command list or just send a song name!

📱 **VBot Python v2.0.0**
By Vzoel Fox's
"""

            # Add inline buttons
            buttons = [
                [
                    Button.inline("📚 Help", b"help_main"),
                    Button.inline("ℹ️ About", b"about")
                ],
                [
                    Button.inline("🔐 Gen Session", b"start_gensession")
                ]
            ]

            await message.reply(
                VBotBranding.wrap_message(welcome_text, include_footer=False),
                buttons=buttons
            )

        except Exception as e:
            logger.error(f"Error in start command: {e}")
            await message.reply("👋 Welcome to VBot!\n\nType /help for commands.")

    async def _handle_help_command(self, message):
        """Handle /help command - show all commands"""
        try:
            help_text = """
📚 **VBot Command Reference**

**🎵 Music Commands:**
• `/play <query>` - Play audio (YouTube/Spotify)
• `/vplay <query>` - Play video
• `/pause` - Pause playback
• `/resume` - Resume playback
• `/skip` - Skip current song
• `/stop` - Stop and clear queue
• `/queue` - Show queue
• `/shuffle` - Shuffle queue
• `/loop <off/current/all>` - Loop mode
• `/seek <seconds>` - Jump to position
• `/volume <0-200>` - Adjust volume

**👥 Group Management:**
• `/pm @user <title>` - Promote to admin
• `/dm @user` - Demote from admin
• `/tagall <text>` - Tag all members
• `/cancel` - Cancel tag operation
• `/lock @user` - Lock user (auto-delete)
• `/unlock @user` - Unlock user
• `/locklist` - Show locked users

**🔧 Bot Commands:**
• `/start` - Start bot & main menu
• `/help` - This help message
• `/about` - Bot information
• `/ping` - Check bot status
• `/gensession` - Generate session string

**ℹ️ Prefix Info:**
• `/` - Public commands (available to all)
• `+` - Owner/Developer commands
• `.` - Admin commands

Type any command for usage help!
"""

            await message.reply(
                VBotBranding.wrap_message(help_text, include_footer=False)
            )

        except Exception as e:
            logger.error(f"Error in help command: {e}")
            await message.reply("📚 Help system error. Please contact support.")

    async def _handle_about_command(self, message):
        """Handle /about command - show bot info"""
        try:
            # Calculate uptime
            uptime_text = "Unknown"
            if self.start_time:
                now = datetime.now(timezone.utc)
                uptime_text = self._format_timedelta(now - self.start_time)

            # Get bot info
            me = await self.client.get_me()

            about_text = f"""
ℹ️ **About VBot**

**Bot Information:**
• Name: {me.first_name}
• Username: @{me.username}
• Version: 2.0.0 Python
• Uptime: {uptime_text}

**Features:**
✅ Music streaming (YouTube/Spotify)
✅ Voice chat support
✅ Group management tools
✅ Session string generator
✅ Premium emoji system
✅ Advanced logging

**Technology:**
• Python 3.11+
• Telethon (MTProto)
• yt-dlp for downloads
• PyTgCalls for streaming

**Developer:**
👨‍💻 Vzoel Fox's
📧 @VZLfxs

**Links:**
• GitHub: [VanZoel112](https://github.com/VanZoel112)
• Support: Contact @VZLfxs

**License:**
© 2025 Vzoel Fox's Lutpan
"""

            buttons = [
                [
                    Button.url("📱 Developer", "https://t.me/VZLfxs"),
                    Button.url("💻 GitHub", "https://github.com/VanZoel112")
                ]
            ]

            await message.reply(
                VBotBranding.wrap_message(about_text, include_footer=False),
                buttons=buttons
            )

        except Exception as e:
            logger.error(f"Error in about command: {e}")
            await message.reply("ℹ️ VBot v2.0.0 by Vzoel Fox's")

    async def _handle_music_command(self, message, parts, audio_only=True):
        """Handle music download/stream commands"""
        if not config.MUSIC_ENABLED:
            await message.reply("Music system is disabled")
            return

        if not self.music_manager:
            await message.reply("Music system not initialized")
            return

        try:
            if len(parts) < 2:
                media_type = "audio" if audio_only else "video"
                await message.reply(
                    f"**Usage:** {parts[0]} <query or URL>\n\n"
                    f"**Examples:**\n"
                    f"{parts[0]} shape of you\n"
                    f"{parts[0]} https://youtu.be/..."
                )
                return

            query = ' '.join(parts[1:])

            # Show animated processing message
            media_type = "audio" if audio_only else "video"
            # (implementation continues…)
        except Exception as e:
            await message.reply(VBotBranding.format_error(f"Music error: {e}"))


async def main():
    bot = VBot()
    ok = await bot.initialize()
    if not ok:
        sys.exit(1)
    logger.info("VBot is up and running.")
    await asyncio.Future()  # run forever


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass

