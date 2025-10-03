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
            await self.music_manager.start()

            # Register handlers
            self.client.add_event_handler(self._handle_message, events.NewMessage)
            self.client.add_event_handler(self._handle_callback, events.CallbackQuery)

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

    async def _handle_callback(self, event):
        """Handle inline button callbacks"""
        try:
            data = event.data.decode('utf-8')

            # Help main callback
            if data == "help_main":
                help_text = """
**VBot Command Reference**

**Music Commands:**
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

**Group Management:**
• `/pm @user <title>` - Promote to admin
• `/dm @user` - Demote from admin
• `/tagall <text>` - Tag all members
• `/cancel` - Cancel tag operation
• `/lock @user` - Lock user (auto-delete)
• `/unlock @user` - Unlock user
• `/locklist` - Show locked users

**Bot Commands:**
• `/start` - Start bot & main menu
• `/help` - This help message
• `/about` - Bot information
• `/ping` - Check bot status
• `/gensession` - Generate session string

**Prefix Info:**
• `/` - Public commands (available to all)
• `+` - Owner commands (developer only)
• `.` - Admin commands

**VBot Python v2.0.0**
By Vzoel Fox's
"""
                await event.edit(VBotBranding.wrap_message(help_text, include_footer=False))

            # About callback
            elif data == "about":
                await event.answer("Loading about info...")
                me = await self.client.get_me()
                about_text = f"""
**About VBot Music Bot**

**Bot Info:**
• Name: {me.first_name}
• Username: @{me.username}
• Version: 2.0.0 Python

**Features:**
• Multi-platform music (YouTube/Spotify)
• Video streaming support
• Smart queue management
• Admin & group controls
• Session generator
• Lock & privacy system

**Technology:**
• Python 3.x
• Telethon (MTProto)
• Pytgcalls (Voice Chat)
• yt-dlp (Download)

**Developer:**
• Vzoel Fox's
• Contact: @VzoelFoxs

**VBot Python v2.0.0**
"""
                await event.edit(VBotBranding.wrap_message(about_text, include_footer=False))

            # Session generator callback
            elif data == "start_gensession":
                # Check if in private chat
                if not event.is_private:
                    await event.answer("Session generator hanya bisa di private chat!", alert=True)
                    return

                # Redirect to /gensession command
                me = await self.client.get_me()
                await event.answer("Starting session generator...")
                redirect_text = (
                    "**Session String Generator**\n\n"
                    "Untuk memulai, silakan ketik:\n"
                    "`/gensession`\n\n"
                    "atau klik tombol di bawah untuk memulai."
                )
                buttons = [[Button.inline("Start Generator", b"run_gensession")]]
                await event.edit(redirect_text, buttons=buttons)

            # Run session generator
            elif data == "run_gensession":
                if hasattr(self, 'session_generator'):
                    # Create a mock event for the generator
                    await event.answer("Memulai generator...")
                    # Trigger the generator
                    await event.respond("/gensession")
                else:
                    await event.answer("Session generator plugin tidak aktif!", alert=True)

            else:
                await event.answer("Unknown callback")

        except Exception as e:
            logger.error(f"Error handling callback: {e}")
            await event.answer("Error processing request", alert=True)

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

            # Tag system
            elif command == '/tagall':
                await self._handle_tagall_command(message, parts)
            elif command == '/cancel':
                await self._handle_cancel_command(message)

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
                await message.reply(f"Unknown command: {command}\n\nType /start to see available commands.")

        except Exception as e:
            logger.error(f"Error routing command {command}: {e}")
            await message.reply(VBotBranding.format_error(f"Command error: {str(e)}"))

    async def _run_command_edit_phases(self, message, command):
        """Display a simple 4-phase status update for any command"""
        phases = [
            "wait..",
            "processing..",
            "initializing..",
            "ok...",
        ]

        try:
            status_message = await message.reply(phases[0])
        except Exception as reply_error:
            logger.debug(f"Unable to send status message: {reply_error}")
            return None

        for phase_text in phases[1:]:
            await asyncio.sleep(0.5)
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
            "**Pong!**",
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
**Welcome to {me.first_name}!**

**VBot Music Bot** - Full-featured Telegram music bot

**Quick Start:**
• `/play <query>` - Play audio from YouTube/Spotify
• `/vplay <query>` - Play video
• `/queue` - Show current queue
• `/help` - Show all commands

**Features:**
• YouTube & Spotify support
• Voice chat streaming
• Queue management
• Admin controls
• Session generator

**Get Started:**
Type `/help` for complete command list or just send a song name!

**VBot Python v2.0.0**
By Vzoel Fox's
"""

            # Different buttons for private vs group
            if message.is_private:
                # Private chat buttons: Generate String, Add to Group, Help
                buttons = [
                    [
                        Button.inline("Generate String", b"start_gensession"),
                    ],
                    [
                        Button.url("Add to Group", f"https://t.me/{bot_username}?startgroup=true"),
                        Button.inline("Help", b"help_main")
                    ]
                ]
            else:
                # Group chat buttons: VBot by Vzoel Fox's, Help
                buttons = [
                    [
                        Button.url("VBot by Vzoel Fox's", "https://t.me/VzoelFoxs"),
                        Button.inline("Help", b"help_main")
                    ]
                ]

            await message.reply(
                VBotBranding.wrap_message(welcome_text, include_footer=False),
                buttons=buttons
            )

        except Exception as e:
            logger.error(f"Error in start command: {e}")
            await message.reply("Welcome to VBot!\n\nType /help for commands.")

    async def _handle_help_command(self, message):
        """Handle /help command - show all commands"""
        try:
            help_text = """
**VBot Command Reference**

**Music Commands:**
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

**Group Management:**
• `/pm @user <title>` - Promote to admin
• `/dm @user` - Demote from admin
• `/tagall <text>` - Tag all members
• `/cancel` - Cancel tag operation
• `/lock @user` - Lock user (auto-delete)
• `/unlock @user` - Unlock user
• `/locklist` - Show locked users

**Bot Commands:**
• `/start` - Start bot & main menu
• `/help` - This help message
• `/about` - Bot information
• `/ping` - Check bot status
• `/gensession` - Generate session string

**Prefix Info:**
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
            await message.reply("Help system error. Please contact support.")

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
**About VBot**

**Bot Information:**
• Name: {me.first_name}
• Username: @{me.username}
• Version: 2.0.0 Python
• Uptime: {uptime_text}

**Features:**
• Music streaming (YouTube/Spotify)
• Voice chat support
• Group management tools
• Session string generator
• Premium emoji system
• Advanced logging

**Technology:**
• Python 3.11+
• Telethon (MTProto)
• yt-dlp for downloads
• PyTgCalls for streaming

**Developer:**
• Vzoel Fox's
• @VZLfxs

**Support:**
Contact @VZLfxs for support & inquiries

**License:**
© 2025 Vzoel Fox's Lutpan
"""

            buttons = [
                [
                    Button.url("Developer", "https://t.me/VZLfxs")
                ]
            ]

            await message.reply(
                VBotBranding.wrap_message(about_text, include_footer=False),
                buttons=buttons
            )

        except Exception as e:
            logger.error(f"Error in about command: {e}")
            await message.reply("VBot v2.0.0 by Vzoel Fox's")

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
            status_msg = await message.reply(f"Searching for {media_type}...")

            # Delegate to music manager
            result = await self.music_manager.play_stream(
                message.chat_id,
                query,
                message.sender_id,
                audio_only=audio_only
            )

            # Format result message
            if result.get('success'):
                song_info = result.get('song', {})
                if result.get('queued'):
                    response = f"**Added to queue (Position {result['position']})**\n\n"
                    response += f"**Title:** {song_info.get('title', 'Unknown')}\n"
                    response += f"**Duration:** {song_info.get('duration_string', 'Unknown')}"
                else:
                    response = f"**Now Playing**\n\n"
                    response += f"**Title:** {song_info.get('title', 'Unknown')}\n"
                    response += f"**Duration:** {song_info.get('duration_string', 'Unknown')}"

                if result.get('streaming'):
                    response += f"\n**Mode:** Streaming"
                    await status_msg.edit(response)
                else:
                    response += f"\n**Mode:** Download"
                    await status_msg.edit(response)

                    file_path = result.get('file_path')
                    if file_path:
                        caption_lines = [
                            f"**Title:** {song_info.get('title', 'Unknown')}",
                            f"**Duration:** {song_info.get('duration_string', 'Unknown')}"
                        ]
                        uploader = song_info.get('uploader')
                        if uploader:
                            caption_lines.append(f"**Uploader:** {uploader}")
                        caption = "\n".join(caption_lines)

                        try:
                            await self.client.send_file(
                                message.chat_id,
                                file_path,
                                caption=VBotBranding.wrap_message(caption, include_footer=False),
                                force_document=False,
                                supports_streaming=True
                            )
                        except Exception as send_error:
                            logger.error(f"Failed to send media file: {send_error}")
                            await self.client.send_message(
                                message.chat_id,
                                VBotBranding.format_error(f"Gagal mengirim file: {send_error}")
                            )
            else:
                error_msg = result.get('error', 'Unknown error')
                await status_msg.edit(f"**Error:** {error_msg}")

        except Exception as e:
            logger.error(f"Music command error: {e}", exc_info=True)
            await message.reply(VBotBranding.format_error(f"Music error: {e}"))

    async def _handle_pause_command(self, message):
        """Handle /pause command"""
        if not self.music_manager:
            await message.reply("❌ Music system not initialized")
            return

        try:
            result = await self.music_manager.pause(message.chat_id)
            await message.reply(result)
        except Exception as e:
            logger.error(f"Pause error: {e}")
            await message.reply(f"❌ Pause failed: {str(e)}")

    async def _handle_resume_command(self, message):
        """Handle /resume command"""
        if not self.music_manager:
            await message.reply("❌ Music system not initialized")
            return

        try:
            result = await self.music_manager.resume(message.chat_id)
            await message.reply(result)
        except Exception as e:
            logger.error(f"Resume error: {e}")
            await message.reply(f"❌ Resume failed: {str(e)}")

    async def _handle_skip_command(self, message):
        """Handle /skip command"""
        if not self.music_manager:
            await message.reply("❌ Music system not initialized")
            return

        try:
            result = await self.music_manager.skip(message.chat_id)
            await message.reply(result)
        except Exception as e:
            logger.error(f"Skip error: {e}")
            await message.reply(f"❌ Skip failed: {str(e)}")

    async def _handle_stop_command(self, message):
        """Handle /stop command"""
        if not self.music_manager:
            await message.reply("❌ Music system not initialized")
            return

        try:
            result = await self.music_manager.stop(message.chat_id)
            await message.reply(result)
        except Exception as e:
            logger.error(f"Stop error: {e}")
            await message.reply(f"❌ Stop failed: {str(e)}")

    async def _handle_queue_command(self, message):
        """Handle /queue command"""
        if not self.music_manager:
            await message.reply("❌ Music system not initialized")
            return

        try:
            result = await self.music_manager.show_queue(message.chat_id)
            await message.reply(result)
        except Exception as e:
            logger.error(f"Queue error: {e}")
            await message.reply(f"❌ Queue error: {str(e)}")

    async def _handle_shuffle_command(self, message):
        """Handle /shuffle command"""
        if not self.music_manager:
            await message.reply("❌ Music system not initialized")
            return

        try:
            result = await self.music_manager.shuffle(message.chat_id)
            await message.reply(result)
        except Exception as e:
            logger.error(f"Shuffle error: {e}")
            await message.reply(f"❌ Shuffle failed: {str(e)}")

    async def _handle_loop_command(self, message, parts):
        """Handle /loop command"""
        if not self.music_manager:
            await message.reply("❌ Music system not initialized")
            return

        try:
            mode = parts[1].lower() if len(parts) > 1 else "toggle"
            result = await self.music_manager.set_loop(message.chat_id, mode)
            await message.reply(result)
        except Exception as e:
            logger.error(f"Loop error: {e}")
            await message.reply(f"❌ Loop error: {str(e)}")

    async def _handle_seek_command(self, message, parts):
        """Handle /seek command"""
        if not self.music_manager:
            await message.reply("❌ Music system not initialized")
            return

        try:
            if len(parts) < 2:
                await message.reply("**Usage:** `/seek <seconds>`\n\n**Example:** `/seek 60`")
                return

            seconds = int(parts[1])
            result = await self.music_manager.seek(message.chat_id, seconds)
            await message.reply(result)
        except ValueError:
            await message.reply("❌ Invalid number! Use: `/seek <seconds>`")
        except Exception as e:
            logger.error(f"Seek error: {e}")
            await message.reply(f"❌ Seek failed: {str(e)}")

    async def _handle_volume_command(self, message, parts):
        """Handle /volume command"""
        if not self.music_manager:
            await message.reply("❌ Music system not initialized")
            return

        try:
            if len(parts) < 2:
                await message.reply("**Usage:** `/volume <0-200>`\n\n**Example:** `/volume 100`")
                return

            volume = int(parts[1])
            if not 0 <= volume <= 200:
                await message.reply("❌ Volume must be between 0-200!")
                return

            result = await self.music_manager.set_volume(message.chat_id, volume)
            await message.reply(result)
        except ValueError:
            await message.reply("Invalid number! Use: `/volume <0-200>`")
        except Exception as e:
            logger.error(f"Volume error: {e}")
            await message.reply(f"Volume error: {str(e)}")

    async def _handle_promote_command(self, message, parts):
        """Handle /pm (promote) command - promote user to admin"""
        if not message.is_group and not message.is_channel:
            await message.reply("**Promote command only works in groups!**")
            return

        try:
            # Get target user
            target_user_id = None
            title = "Admin"

            # Method 1: Reply to message
            if message.reply_to_msg_id:
                replied_msg = await message.get_reply_message()
                if replied_msg:
                    target_user_id = replied_msg.sender_id
                    # Get title from parts if provided
                    if len(parts) > 1:
                        title = ' '.join(parts[1:])

            # Method 2: From @username or ID
            elif len(parts) >= 2:
                target = parts[1]

                # Handle @username
                if target.startswith('@'):
                    try:
                        entity = await self.client.get_entity(target)
                        target_user_id = entity.id
                    except Exception as e:
                        await message.reply(f"**Error:** Could not find user {target}")
                        return

                # Handle user ID
                elif target.isdigit():
                    target_user_id = int(target)

                # Get title if provided
                if len(parts) > 2:
                    title = ' '.join(parts[2:])

            if not target_user_id:
                await message.reply(
                    "**Usage:** `/pm @username [title]` or `/pm <user_id> [title]` or reply to message\n\n"
                    "**Examples:**\n"
                    "• `/pm @user Admin`\n"
                    "• `/pm @user`\n"
                    "• Reply to user message with `/pm Moderator`"
                )
                return

            # Promote user
            from telethon.tl.functions.channels import EditAdminRequest
            from telethon.tl.types import ChatAdminRights

            rights = ChatAdminRights(
                change_info=True,
                post_messages=True,
                edit_messages=True,
                delete_messages=True,
                ban_users=True,
                invite_users=True,
                pin_messages=True,
                add_admins=False,
                manage_call=True
            )

            await self.client(EditAdminRequest(
                channel=message.chat_id,
                user_id=target_user_id,
                admin_rights=rights,
                rank=title[:16]  # Max 16 characters for title
            ))

            try:
                user_entity = await self.client.get_entity(target_user_id)
                username = f"@{user_entity.username}" if user_entity.username else f"User {target_user_id}"
                name = user_entity.first_name or "User"
            except:
                username = f"User {target_user_id}"
                name = "User"

            await message.reply(
                f"**User Promoted**\n\n"
                f"**User:** {name} ({username})\n"
                f"**Title:** {title}\n\n"
                f"User is now an admin with full permissions."
            )

        except Exception as e:
            logger.error(f"Error in promote command: {e}", exc_info=True)
            await message.reply(f"**Error:** {str(e)}\n\nMake sure bot has admin rights to promote users.")

    async def _handle_demote_command(self, message, parts):
        """Handle /dm (demote) command - demote user from admin"""
        if not message.is_group and not message.is_channel:
            await message.reply("**Demote command only works in groups!**")
            return

        try:
            # Get target user
            target_user_id = None

            # Method 1: Reply to message
            if message.reply_to_msg_id:
                replied_msg = await message.get_reply_message()
                if replied_msg:
                    target_user_id = replied_msg.sender_id

            # Method 2: From @username or ID
            elif len(parts) >= 2:
                target = parts[1]

                # Handle @username
                if target.startswith('@'):
                    try:
                        entity = await self.client.get_entity(target)
                        target_user_id = entity.id
                    except Exception as e:
                        await message.reply(f"**Error:** Could not find user {target}")
                        return

                # Handle user ID
                elif target.isdigit():
                    target_user_id = int(target)

            if not target_user_id:
                await message.reply(
                    "**Usage:** `/dm @username` or `/dm <user_id>` or reply to message\n\n"
                    "**Examples:**\n"
                    "• `/dm @user`\n"
                    "• `/dm 123456789`\n"
                    "• Reply to admin message with `/dm`"
                )
                return

            # Demote user (remove admin rights)
            from telethon.tl.functions.channels import EditAdminRequest
            from telethon.tl.types import ChatAdminRights

            # Empty rights = demote
            rights = ChatAdminRights(
                change_info=False,
                post_messages=False,
                edit_messages=False,
                delete_messages=False,
                ban_users=False,
                invite_users=False,
                pin_messages=False,
                add_admins=False,
                manage_call=False
            )

            await self.client(EditAdminRequest(
                channel=message.chat_id,
                user_id=target_user_id,
                admin_rights=rights,
                rank=""
            ))

            try:
                user_entity = await self.client.get_entity(target_user_id)
                username = f"@{user_entity.username}" if user_entity.username else f"User {target_user_id}"
                name = user_entity.first_name or "User"
            except:
                username = f"User {target_user_id}"
                name = "User"

            await message.reply(
                f"**User Demoted**\n\n"
                f"**User:** {name} ({username})\n\n"
                f"User is no longer an admin."
            )

        except Exception as e:
            logger.error(f"Error in demote command: {e}", exc_info=True)
            await message.reply(f"**Error:** {str(e)}\n\nMake sure bot has admin rights to demote users.")

    async def _handle_adminlist_command(self, message):
        """Handle /adminlist command - stub"""
        await message.reply("🚧 **Admin list under development**\n\nComing soon!")

    async def _handle_add_permission_command(self, message, parts):
        """Handle +add command - stub"""
        await message.reply("🚧 **Add permission under development**\n\nComing soon!")

    async def _handle_del_permission_command(self, message, parts):
        """Handle +del command - stub"""
        await message.reply("🚧 **Del permission under development**\n\nComing soon!")

    async def _handle_setwelcome_command(self, message, parts):
        """Handle +setwelcome command - stub"""
        await message.reply("🚧 **Set welcome under development**\n\nComing soon!")

    async def _handle_backup_command(self, message, parts):
        """Handle +backup command - stub"""
        await message.reply("🚧 **Backup command under development**\n\nComing soon!")

    async def _handle_lock_command(self, message, parts):
        """Handle /lock command - lock user with auto-delete"""
        if not message.is_group and not message.is_channel:
            await message.reply("**Lock command only works in groups!**")
            return

        try:
            # Try to get user ID from different sources
            target_user_id = None

            # Method 1: Reply to message
            target_user_id = await self.lock_manager.extract_user_from_reply(message)

            # Method 2: From mention in message
            if not target_user_id:
                target_user_id = await self.lock_manager.extract_user_from_mention(self.client, message)

            # Method 3: From command argument (@username or ID)
            if not target_user_id:
                target_user_id = await self.lock_manager.parse_lock_command(self.client, message)

            if not target_user_id:
                await message.reply(
                    "**Usage:** `/lock @username` or `/lock <user_id>` or reply to user's message\n\n"
                    "**Examples:**\n"
                    "• `/lock @spammer`\n"
                    "• `/lock 123456789`\n"
                    "• Reply to user message with `/lock`"
                )
                return

            # Get reason if provided
            reason = "Locked by admin"
            if len(parts) > 2:
                reason = ' '.join(parts[2:])
            elif len(parts) == 2 and not parts[1].startswith('@') and not parts[1].isdigit():
                reason = parts[1]

            # Lock the user
            success = await self.lock_manager.lock_user(message.chat_id, target_user_id, reason)

            if success:
                try:
                    user_entity = await self.client.get_entity(target_user_id)
                    username = f"@{user_entity.username}" if user_entity.username else f"User {target_user_id}"
                except:
                    username = f"User {target_user_id}"

                await message.reply(
                    f"**User Locked**\n\n"
                    f"**User:** {username}\n"
                    f"**Reason:** {reason}\n\n"
                    f"All messages from this user will be auto-deleted."
                )
            else:
                await message.reply("**Error:** Failed to lock user. Database error.")

        except Exception as e:
            logger.error(f"Error in lock command: {e}", exc_info=True)
            await message.reply(f"**Error:** {str(e)}")

    async def _handle_unlock_command(self, message, parts):
        """Handle /unlock command - unlock user"""
        if not message.is_group and not message.is_channel:
            await message.reply("**Unlock command only works in groups!**")
            return

        try:
            # Try to get user ID from different sources
            target_user_id = None

            # Method 1: Reply to message
            target_user_id = await self.lock_manager.extract_user_from_reply(message)

            # Method 2: From mention in message
            if not target_user_id:
                target_user_id = await self.lock_manager.extract_user_from_mention(self.client, message)

            # Method 3: From command argument (@username or ID)
            if not target_user_id:
                target_user_id = await self.lock_manager.parse_lock_command(self.client, message)

            if not target_user_id:
                await message.reply(
                    "**Usage:** `/unlock @username` or `/unlock <user_id>` or reply to user's message\n\n"
                    "**Examples:**\n"
                    "• `/unlock @user`\n"
                    "• `/unlock 123456789`\n"
                    "• Reply to user message with `/unlock`"
                )
                return

            # Unlock the user
            success = await self.lock_manager.unlock_user(message.chat_id, target_user_id)

            if success:
                try:
                    user_entity = await self.client.get_entity(target_user_id)
                    username = f"@{user_entity.username}" if user_entity.username else f"User {target_user_id}"
                except:
                    username = f"User {target_user_id}"

                await message.reply(
                    f"**User Unlocked**\n\n"
                    f"**User:** {username}\n\n"
                    f"User can now send messages normally."
                )
            else:
                await message.reply("**Error:** Failed to unlock user or user is not locked.")

        except Exception as e:
            logger.error(f"Error in unlock command: {e}", exc_info=True)
            await message.reply(f"**Error:** {str(e)}")

    async def _handle_locklist_command(self, message):
        """Handle /locklist command - show locked users"""
        if not message.is_group and not message.is_channel:
            await message.reply("**Lock list only works in groups!**")
            return

        try:
            locked_users = self.lock_manager.get_locked_users(message.chat_id)

            if not locked_users:
                await message.reply("**No locked users in this chat.**")
                return

            response = "**Locked Users in This Chat**\n\n"

            for user_id, data in locked_users.items():
                try:
                    user_entity = await self.client.get_entity(user_id)
                    username = f"@{user_entity.username}" if user_entity.username else f"User {user_id}"
                    name = user_entity.first_name or "Unknown"
                except:
                    username = f"User {user_id}"
                    name = "Unknown"

                reason = data.get('reason', 'No reason')
                response += f"• **{name}** ({username})\n  Reason: {reason}\n\n"

            response += f"**Total:** {len(locked_users)} user(s) locked"

            await message.reply(response)

        except Exception as e:
            logger.error(f"Error in locklist command: {e}", exc_info=True)
            await message.reply(f"**Error:** {str(e)}")

    async def _handle_tagall_command(self, message, parts):
        """Handle /tagall command - tag all members"""
        if not message.is_group and not message.is_channel:
            await message.reply("**Tag all only works in groups!**")
            return

        try:
            # Get custom message if provided
            custom_message = "Tagging all members..."
            if len(parts) > 1:
                custom_message = ' '.join(parts[1:])

            # Start tag all process
            success = await self.tag_manager.start_tag_all(
                self.client,
                message.chat_id,
                custom_message,
                message.sender_id
            )

            if success:
                await message.reply(
                    f"**Tag All Started**\n\n"
                    f"**Message:** {custom_message}\n\n"
                    f"Tagging all members... Use `/cancel` to stop."
                )
            else:
                # Check if already tagging
                if message.chat_id in self.tag_manager.active_tags:
                    await message.reply(
                        "**Tag all already in progress!**\n\n"
                        "Wait for current process to finish or use `/cancel` to stop it."
                    )
                else:
                    await message.reply("**Error:** Could not start tag all. No members found or insufficient permissions.")

        except Exception as e:
            logger.error(f"Error in tagall command: {e}", exc_info=True)
            await message.reply(f"**Error:** {str(e)}")

    async def _handle_cancel_command(self, message):
        """Handle /cancel command - cancel ongoing tag all"""
        if not message.is_group and not message.is_channel:
            await message.reply("**Cancel only works in groups!**")
            return

        try:
            success = await self.tag_manager.cancel_tag_all(message.chat_id)

            if success:
                await message.reply(
                    "**Tag All Cancelled**\n\n"
                    "The tagging process has been stopped."
                )
            else:
                await message.reply("**No active tag all process in this chat.**")

        except Exception as e:
            logger.error(f"Error in cancel command: {e}", exc_info=True)
            await message.reply(f"**Error:** {str(e)}")


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

