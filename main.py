#!/usr/bin/env python3
"""
VBot Python - Main Application
Vzoel Robot Music Bot with comprehensive features

Author: Vzoel Fox's
Version: 2.0.0 Python
"""

import asyncio
import io
import json
import logging
import re
import sys
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
from typing import Any, Deque, Dict, Optional, List, Set, Tuple
from typing import Any, Dict, Optional, List, Tuple

try:
    import uvloop
except ImportError:  # pragma: no cover - optional dependency
    uvloop = None

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
from telethon.utils import pack_bot_file_id

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
        self._tag_prefixes = (".", "/", "+")
        self._tag_start_commands = {f"{prefix}t" for prefix in self._tag_prefixes}
        self._tag_stop_commands = {f"{prefix}c" for prefix in self._tag_prefixes}
        self._help_pages = self._build_help_pages()
        self._music_logo_file_id = getattr(config, "MUSIC_LOGO_FILE_ID", "")
        self._admin_sync_cache: Dict[int, float] = {}
        self._admin_sync_interval = getattr(config, "GROUP_ADMIN_SYNC_INTERVAL", 600)
        self._premium_wrapper_ids: Set[int] = set()
        self._premium_wrapper_id_queue: Deque[int] = deque()
        self._premium_wrapper_id_limit = 4096

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

            # Start background GitHub auto push if enabled
            self.github_sync.start_auto_push_loop()

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
                BotCommand(command="t", description="Tag semua anggota secara bertahap"),
                BotCommand(command="c", description="Hentikan proses tag massal"),
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

            # Enable premium emoji responses for this user
            self._prepare_premium_wrappers(message, getattr(message, "sender_id", None))

            # Handle commands
            if message.text.startswith(('.', '/', '+', '#')):
                await self._handle_command(message)

        except Exception as e:
            logger.error(f"Error handling message: {e}")

    async def _prepare_premium_arguments(
        self,
        args: Tuple[Any, ...],
        kwargs: Dict[str, Any],
        user_id: Optional[int],
    ) -> Tuple[Tuple[Any, ...], Dict[str, Any]]:
        """Convert textual arguments for premium users when needed."""

        new_args = args
        new_kwargs = dict(kwargs)
        text_arg, location = self._extract_text_argument(new_args, new_kwargs)

        if isinstance(text_arg, str):
            converted = await self._convert_for_user(text_arg, user_id)
            if isinstance(converted, str) and converted != text_arg and location:
                new_args, new_kwargs = self._apply_text_argument(
                    new_args, new_kwargs, location, converted
                )

        return new_args, new_kwargs

    def _register_wrapped_message(self, message_obj) -> bool:
        """Record that a message has premium wrappers to avoid double wrapping."""

        try:
            setattr(message_obj, "_premium_hooks_applied", True)
            return True
        except AttributeError:
            message_id = id(message_obj)
            if message_id in self._premium_wrapper_ids:
                return False
            self._premium_wrapper_ids.add(message_id)
            self._premium_wrapper_id_queue.append(message_id)
            while len(self._premium_wrapper_id_queue) > self._premium_wrapper_id_limit:
                old_id = self._premium_wrapper_id_queue.popleft()
                self._premium_wrapper_ids.discard(old_id)
            return True

    def _prepare_premium_wrappers(self, message_obj, user_id: Optional[int]) -> None:
        """Wrap reply/edit helpers so bot responses honour premium emojis."""

        if (
            not config.ENABLE_PREMIUM_EMOJI
            or not isinstance(user_id, int)
            or user_id <= 0
            or message_obj is None
        ):
            return

        if getattr(message_obj, "_premium_hooks_applied", False):
            return

        if id(message_obj) in self._premium_wrapper_ids:
            return

        if not self._register_wrapped_message(message_obj):
            return

        original_reply = getattr(message_obj, "reply", None)
        if callable(original_reply):

            @wraps(original_reply)
            async def reply_with_premium(*args, **kwargs):
                patched_args, patched_kwargs = await self._prepare_premium_arguments(
                    args, kwargs, user_id
                )
                result = await original_reply(*patched_args, **patched_kwargs)
                self._propagate_premium_wrappers(result, user_id)
                return result

            message_obj.reply = reply_with_premium  # type: ignore[assignment]

        original_edit = getattr(message_obj, "edit", None)
        if callable(original_edit):

            @wraps(original_edit)
            async def edit_with_premium(*args, **kwargs):
                patched_args, patched_kwargs = await self._prepare_premium_arguments(
                    args, kwargs, user_id
                )
                result = await original_edit(*patched_args, **patched_kwargs)
                self._propagate_premium_wrappers(result, user_id)
                return result

            message_obj.edit = edit_with_premium  # type: ignore[assignment]

    def _propagate_premium_wrappers(self, result, user_id: Optional[int]) -> None:
        """Apply premium wrappers to any messages returned by helper calls."""

        if not result:
            return

        if isinstance(result, list):
            for item in result:
                self._prepare_premium_wrappers(item, user_id)
        else:
            self._prepare_premium_wrappers(result, user_id)

    @staticmethod
    def _extract_text_argument(
        args: Tuple[Any, ...], kwargs: Dict[str, Any]
    ) -> Tuple[Optional[str], Optional[Tuple[str, Any]]]:
        """Locate textual arguments passed to Telethon helpers."""

        if args:
            value = args[0]
            return (value if isinstance(value, str) else None), ("args", 0)

        for key in ("message", "text"):
            if key in kwargs:
                value = kwargs[key]
                return (value if isinstance(value, str) else None), ("kwargs", key)

        return None, None

    @staticmethod
    def _apply_text_argument(
        args: Tuple[Any, ...],
        kwargs: Dict[str, Any],
        location: Optional[Tuple[str, Any]],
        new_text: str,
    ) -> Tuple[Tuple[Any, ...], Dict[str, Any]]:
        """Replace text in args/kwargs based on the provided location descriptor."""

        if not location:
            return args, kwargs

        target_type, target_key = location
        if target_type == "args":
            items = list(args)
            items[int(target_key)] = new_text
            return tuple(items), kwargs

        kwargs[str(target_key)] = new_text
        return args, kwargs

    async def _convert_for_user(
        self, text: Optional[str], user_id: Optional[int]
    ) -> Optional[str]:
        """Convert plain emoji text to premium equivalents for specific users."""

        if (
            not isinstance(text, str)
            or not isinstance(user_id, int)
            or user_id <= 0
            or not config.ENABLE_PREMIUM_EMOJI
        ):
            return text

        return await self.emoji_manager.process_message_emojis(
            self.client, text, user_id
        )

    async def _send_premium_message(
        self,
        chat_id: int,
        text: str,
        *,
        reply_to: Optional[int] = None,
        user_id: Optional[int] = None,
        **kwargs: Any,
    ):
        """Send a message while honouring premium emoji mappings."""

        prepared = await self._convert_for_user(text, user_id)
        result = await self.client.send_message(
            chat_id,
            prepared if isinstance(prepared, str) else text,
            reply_to=reply_to,
            **kwargs,
        )
        self._propagate_premium_wrappers(result, user_id)
        return result

    async def _handle_callback(self, event):
        """Handle inline button callbacks"""
        try:
            data = event.data.decode('utf-8')

            # Help main callback
            if data.startswith("help:page:"):
                await self._handle_help_navigation(event, data)

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

            # Branding info callback
            elif data == "branding:info":
                await event.answer(
                    "DEVELOPED by. Vzoel Fox's (Lutpan) ID : @VZLfxs / @itspizolpoks",
                    alert=True
                )

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

            # Music playback callbacks
            elif data.startswith("music:"):
                await self._handle_music_callback(event, data)

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

            command_type = self.auth_manager.get_command_type(command_text)

            # Keep admin snapshots fresh so each group maintains its own list
            if (
                command_type == "admin"
                and (message.is_group or message.is_channel)
                and message.chat_id is not None
            ):
                await self._ensure_group_admin_sync(message.chat_id)

            # Check permissions
            has_permission = await self.auth_manager.check_permissions(
                self.client, message.sender_id, message.chat_id, command_text
            )

            if not has_permission:
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

            # Persist confirmed admins after successful permission check
            if (
                command_type == "admin"
                and (message.is_group or message.is_channel)
                and message.chat_id is not None
            ):
                try:
                    if await self.auth_manager.is_admin_in_chat(
                        self.client, message.sender_id, message.chat_id
                    ):
                        self.database.add_group_admin(message.chat_id, message.sender_id)
                except Exception as perm_error:
                    logger.debug(
                        "Failed to refresh admin cache for chat %s: %s",
                        message.chat_id,
                        perm_error,
                    )

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
            elif command in self._tag_start_commands:
                await self._handle_tag_command(message)
            elif command in self._tag_stop_commands:
                await self._handle_tag_cancel_command(message)
            elif command == '/cancel' and not (message.is_group or message.is_channel):
                # Biarkan generator session dan alur lainnya menangani /cancel di private chat
                return

            # Help command (available to all)
            elif command in ['/help', '#help']:
                await self._handle_help_command(message)
            elif command == '#rules':
                await self._handle_rules_command(message)
            elif command == '#session':
                await self._handle_session_command(message)

            # JSON/metadata helper
            elif command in ['/showjson', '.showjson', '+showjson']:
                await self._handle_showjson_command(message)

            # Music branding configuration
            elif command in ['/setlogo', '+setlogo']:
                await self._handle_setlogo_command(message)

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
                        Button.inline("Help", f"help:page:0".encode())
                    ]
                ]
            else:
                # Group chat buttons: VBOT info toggle, Help
                buttons = [
                    [
                        Button.inline("VBOT", b"branding:info"),
                        Button.inline("Help", f"help:page:0".encode())
                    ]
                ]

            await message.reply(
                VBotBranding.wrap_message(welcome_text, include_footer=False),
                buttons=buttons
            )

        except Exception as e:
            logger.error(f"Error in start command: {e}")
            await message.reply("Welcome to VBot!\n\nType /help for commands.")

    def _build_help_pages(self) -> List[Dict[str, object]]:
        """Define help sections for slash commands."""

        tag_start_display = " / ".join(f"`{prefix}t`" for prefix in self._tag_prefixes)
        tag_stop_display = " / ".join(f"`{prefix}c`" for prefix in self._tag_prefixes)

        return [
            {
                "label": "Music",
                "title": "Music Playback",
                "commands": [
                    ("`/play <query>`", "Putar audio dari pencarian (alias: `/p`)"),
                    ("`/vplay <query>`", "Putar video atau streaming visual (alias: `/vp`)"),
                    ("`/pause`", "Jeda lagu yang sedang diputar"),
                    ("`/resume`", "Lanjutkan pemutaran yang dijeda"),
                    ("`/skip`", "Lewati ke lagu berikutnya"),
                    ("`/stop`", "Hentikan musik dan hapus antrean"),
                    ("`/queue`", "Tampilkan antrean yang sedang aktif"),
                    ("`/shuffle`", "Acak urutan antrean"),
                    ("`/loop <off/current/all>`", "Atur mode pengulangan"),
                    ("`/seek <detik>`", "Loncat ke posisi tertentu"),
                    ("`/volume <0-200>`", "Atur volume streaming"),
                ],
            },
            {
                "label": "Admin",
                "title": "Administrasi & Moderasi",
                "commands": [
                    ("`/pm @user <title>`", "Promosikan anggota menjadi admin"),
                    ("`/dm @user`", "Turunkan admin menjadi member"),
                    ("`/adminlist`", "Lihat daftar admin (alias: `/admins`)"),
                    ("`/lock @user`", "Kunci pengguna agar pesannya dihapus otomatis"),
                    ("`/unlock @user`", "Buka kunci pengguna"),
                    ("`/locklist`", "Daftar pengguna yang terkunci"),
                    (f"{tag_start_display} [batch] <text>", "Mention semua anggota via edit batch"),
                    (f"{tag_stop_display}", "Batalkan penandaan massal"),
                ],
            },
            {
                "label": "Bot",
                "title": "Informasi Bot & Utilitas",
                "commands": [
                    ("`/start`", "Tampilkan menu utama bot"),
                    ("`/help`", "Buka panduan interaktif ini"),
                    ("`/about`", "Informasi detail mengenai bot"),
                    ("`/ping`", "Cek latensi & uptime"),
                    ("`/gensession`", "Mulai generator string session"),
                ],
            },
        ]

    def _render_help_page(self, page_index: int) -> Tuple[str, List[List[Button]]]:
        """Render help page text and inline keyboard for navigation."""

        if not self._help_pages:
            fallback = VBotBranding.wrap_message("Tidak ada data bantuan.", include_footer=False)
            return fallback, []

        total_pages = len(self._help_pages)
        current_index = page_index % total_pages
        page = self._help_pages[current_index]

        lines = [f"**{page['title']}**", ""]
        for command, description in page.get("commands", []):
            lines.append(f"• {command} - {description}")

        lines.append("")
        lines.append(f"_Halaman {current_index + 1}/{total_pages}_")

        text = VBotBranding.wrap_message("\n".join(lines), include_footer=False)

        toggle_row: List[Button] = []
        for idx, section in enumerate(self._help_pages):
            label_prefix = "Aktif | " if idx == current_index else ""
            toggle_row.append(
                Button.inline(
                    f"{label_prefix}{section['label']}",
                    f"help:page:{idx}".encode()
                )
            )

        navigation_row = [
            Button.inline("Sebelumnya", f"help:page:{(current_index - 1) % total_pages}".encode()),
            Button.url("FOUNDER", "https://t.me/VZLfxs"),
            Button.inline("Berikutnya", f"help:page:{(current_index + 1) % total_pages}".encode()),
        ]

        return text, [toggle_row, navigation_row]

    async def _send_help_page(self, message, page_index: int):
        """Send the interactive help page to a chat."""

        text, buttons = self._render_help_page(page_index)
        await message.reply(text, buttons=buttons if buttons else None)

    async def _handle_help_navigation(self, event, data: str):
        """Handle inline navigation between help pages."""

        try:
            _, _, page_str = data.partition("help:page:")
            page_index = int(page_str) if page_str.isdigit() else 0
        except ValueError:
            page_index = 0

        text, buttons = self._render_help_page(page_index)

        try:
            await event.edit(text, buttons=buttons if buttons else None)
        except Exception as edit_error:
            logger.debug(f"Failed to edit help message: {edit_error}")
        finally:
            try:
                await event.answer()
            except Exception:
                pass

    async def _handle_help_command(self, message):
        """Handle /help command - show all commands"""
        try:
            await self._send_help_page(message, 0)

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

    async def _handle_showjson_command(self, message):
        """Return structured metadata for the replied message."""

        try:
            if not self.auth_manager.is_developer(getattr(message, "sender_id", 0)):
                await message.reply(VBotBranding.format_error("Perintah ini hanya untuk developer."))
                return

            sender_id = getattr(message, "sender_id", 0)
            if not await self.emoji_manager.is_user_premium(self.client, sender_id):
                await message.reply(
                    VBotBranding.format_error(
                        "Fitur mapping premium membutuhkan akun Telegram Premium."
                    )
                )
                return

            reply = await message.get_reply_message()
            if not reply:
                await message.reply("Balas ke pesan atau media yang ingin dianalisis dengan perintah ini.")
                return

            metadata = await self._extract_message_metadata(reply)
            new_mappings = self.emoji_manager.record_mapping_from_metadata(metadata)

            response_lines = []
            if new_mappings:
                response_lines.append("Mapping emoji premium berhasil diperbarui otomatis!")
                for standard, values in new_mappings.items():
                    if standard == "__pool__":
                        for emoji in values:
                            response_lines.append(f"• Ditambahkan ke pool: {emoji}")
                    else:
                        preview = " / ".join(values)
                        response_lines.append(f"• {standard} → {preview}")
            else:
                response_lines.append("Tidak ada emoji premium baru yang dapat dipetakan dari pesan ini.")

            random_premium = self.emoji_manager.get_random_premium_emoji()
            if random_premium:
                response_lines.append("")
                response_lines.append(f"Emoji premium acak: {random_premium}")

            await message.reply(VBotBranding.format_success("\n".join(response_lines)))

        except Exception as exc:
            logger.error(f"showjson command failed: {exc}", exc_info=True)
            await message.reply(VBotBranding.format_error(f"Gagal mengambil metadata: {exc}"))

    async def _handle_setlogo_command(self, message):
        """Persist the replied media file_id as the default music artwork."""

        try:
            sender_id = getattr(message, "sender_id", 0)
            if not self.auth_manager.is_developer(sender_id):
                await message.reply(VBotBranding.format_error("Perintah ini hanya dapat digunakan oleh developer."))
                return

            if not message.is_private:
                await message.reply(VBotBranding.format_error("/setlogo hanya tersedia di private chat dengan bot."))
                return

            reply = await message.get_reply_message()
            if not reply:
                await message.reply("Balas ke foto/stiker/logo yang ingin dijadikan cover musik.")
                return

            metadata = await self._extract_message_metadata(reply)
            file_id = metadata.get("file_id")
            if not file_id:
                await message.reply(VBotBranding.format_error("Tidak dapat menemukan file_id dari media yang dibalas."))
                return

            await self._update_music_logo_file_id(file_id)

            success_text = (
                "Logo musik berhasil diperbarui dan disimpan."
                "\nFile ID sudah ditulis ke .env dan config.py."
            )
            await message.reply(VBotBranding.format_success(success_text))
            await self._deliver_json_metadata(
                message.chat_id,
                message.id,
                metadata,
                requester_id=sender_id,
            )

        except Exception as exc:
            logger.error(f"setlogo command failed: {exc}", exc_info=True)
            await message.reply(VBotBranding.format_error(f"Gagal menyimpan logo: {exc}"))

    async def _deliver_json_metadata(
        self,
        chat_id: int,
        reply_to_id: Optional[int],
        metadata: Dict[str, Any],
        requester_id: Optional[int] = None,
    ) -> None:
        """Send metadata as formatted JSON or attachment when too large."""

        formatted = self._format_json_metadata(metadata)
        payload = f"```json\n{formatted}\n```"

        if len(payload) <= 3500:
            await self._send_premium_message(
                chat_id,
                payload,
                reply_to=reply_to_id,
                user_id=requester_id,
            )
            return

        buffer = io.BytesIO(formatted.encode("utf-8"))
        buffer.name = "showjson.json"
        caption_text = await self._convert_for_user("ShowJSON result", requester_id)
        await self.client.send_file(
            chat_id,
            buffer,
            caption=caption_text if isinstance(caption_text, str) else "ShowJSON result",
            reply_to=reply_to_id,
        )

    async def _extract_message_metadata(self, target) -> Dict[str, Any]:
        """Collect metadata about the provided message/media."""

        metadata: Dict[str, Any] = {
            "chat_id": getattr(target, "chat_id", None),
            "message_id": getattr(target, "id", None),
            "sender_id": getattr(target, "sender_id", None),
            "date": target.date.isoformat() if getattr(target, "date", None) else None,
            "text": getattr(target, "raw_text", None),
            "media_type": None,
        }

        media = getattr(target, "media", None)
        metadata["media_type"] = media.__class__.__name__ if media else "text"

        file_id: Optional[str] = None
        if media:
            try:
                file_id = pack_bot_file_id(media)
            except Exception as exc:
                logger.debug(f"Unable to pack file id: {exc}")

        metadata["file_id"] = file_id

        file_info: Dict[str, Any] = {}
        file_attr = getattr(target, "file", None)
        if file_attr:
            file_info = {
                "name": getattr(file_attr, "name", None),
                "size": getattr(file_attr, "size", None),
                "mime_type": getattr(file_attr, "mime_type", None),
                "id": getattr(file_attr, "id", None),
                "access_hash": getattr(file_attr, "access_hash", None),
                "dc_id": getattr(file_attr, "dc_id", None),
            }
        metadata["file"] = file_info or None

        custom_emojis = []
        entities = getattr(target, "entities", None) or []
        text_value = getattr(target, "raw_text", "") or ""
        for entity in entities:
            if isinstance(entity, types.MessageEntityCustomEmoji):
                emoji_text = text_value[entity.offset: entity.offset + entity.length]
                custom_emojis.append(
                    {
                        "emoji": emoji_text,
                        "document_id": getattr(entity, "document_id", None),
                        "offset": getattr(entity, "offset", None),
                        "length": getattr(entity, "length", None),
                    }
                )
        metadata["custom_emojis"] = custom_emojis or None

        document = getattr(media, "document", None) if media else None
        if document and getattr(document, "attributes", None):
            attributes: List[Any] = []
            for attr in document.attributes:
                if hasattr(attr, "to_dict"):
                    attributes.append(attr.to_dict())
                else:
                    attributes.append(str(attr))
            metadata["document_attributes"] = attributes

        photo = getattr(media, "photo", None) if media else getattr(target, "photo", None)
        if photo and hasattr(photo, "sizes"):
            sizes = []
            for size in photo.sizes:
                if hasattr(size, "to_dict"):
                    sizes.append(size.to_dict())
                else:
                    sizes.append(str(size))
            metadata["photo_sizes"] = sizes

        try:
            metadata["raw"] = target.to_dict()
        except Exception:
            metadata["raw"] = None

        return metadata

    def _format_json_metadata(self, metadata: Dict[str, Any]) -> str:
        """Convert metadata dictionary into pretty JSON string."""

        def _default(obj: Any):
            if isinstance(obj, datetime):
                return obj.isoformat()
            if hasattr(obj, "isoformat"):
                try:
                    return obj.isoformat()
                except Exception:
                    pass
            if isinstance(obj, bytes):
                return obj.hex()
            if isinstance(obj, Path):
                return str(obj)
            return str(obj)

        return json.dumps(metadata, indent=2, ensure_ascii=False, default=_default)

    async def _update_music_logo_file_id(self, file_id: str) -> None:
        """Persist the logo file id to runtime, config.py, and .env."""

        self._music_logo_file_id = file_id
        config.MUSIC_LOGO_FILE_ID = file_id

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._write_music_logo_configuration, file_id)

    def _write_music_logo_configuration(self, file_id: str) -> None:
        """Write the logo file id to .env and config.py."""

        env_path = Path(".env").resolve()
        self._update_env_file_value(env_path, "MUSIC_LOGO_FILE_ID", file_id)

        config_path = Path(config.__file__).resolve()
        try:
            content = config_path.read_text(encoding="utf-8")
        except OSError as exc:
            logger.error(f"Failed to read config.py for logo update: {exc}")
            return

        pattern = re.compile(
            r'MUSIC_LOGO_FILE_ID = os\.getenv\("MUSIC_LOGO_FILE_ID", ".*?"\)'
        )
        replacement = f'MUSIC_LOGO_FILE_ID = os.getenv("MUSIC_LOGO_FILE_ID", "{file_id}")'
        if pattern.search(content):
            new_content = pattern.sub(replacement, content, count=1)
        else:
            new_content = content.replace(
                'MUSIC_LOGO_FILE_ID = os.getenv("MUSIC_LOGO_FILE_ID", "")',
                replacement,
                1,
            )

        if new_content != content:
            try:
                config_path.write_text(new_content, encoding="utf-8")
            except OSError as exc:
                logger.error(f"Failed to write config.py for logo update: {exc}")

    def _update_env_file_value(self, path: Path, key: str, value: str) -> None:
        """Insert or replace a key=value pair in an env file."""

        new_line = f'{key}="{value}"'

        lines: List[str] = []
        try:
            if path.exists():
                lines = path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            logger.error(f"Failed to read {path} for env update: {exc}")
            return

        updated = False
        for idx, raw_line in enumerate(lines):
            stripped = raw_line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if stripped.split("=", 1)[0].strip() == key:
                lines[idx] = new_line
                updated = True
                break

        if not updated:
            lines.append(new_line)

        try:
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        except OSError as exc:
            logger.error(f"Failed to write {path} for env update: {exc}")

    def _build_music_status_message(self, chat_id: int) -> str:
        """Return formatted status for current playback."""
        if not self.music_manager:
            return "❌ Music system not initialized"

        manager = self.music_manager
        current = manager.current_song.get(chat_id)
        queue = manager.queues.get(chat_id, [])
        paused = manager.paused.get(chat_id, False)
        stream_mode = manager.stream_mode.get(chat_id, 'audio')
        loop_mode = manager.loop_mode.get(chat_id, 'off')

        lines: List[str] = []

        if current:
            lines.append("**Now Playing**")
            lines.append(f"**Title:** {current.get('title', 'Unknown')}")
            lines.append(f"**Duration:** {current.get('duration_string', 'Unknown')}")
            uploader = current.get('uploader')
            if uploader:
                lines.append(f"**Uploader:** {uploader}")

            status_label = "⏸️ Paused" if paused else "▶️ Playing"
            mode_label = "Audio" if stream_mode == 'audio' else "Video"
            lines.append(f"**Status:** {status_label}")
            lines.append(f"**Mode:** Streaming ({mode_label})")
        else:
            lines.append("📭 **No active playback**")

        if loop_mode != 'off':
            loop_label = {
                'current': 'Current track',
                'all': 'Entire queue'
            }.get(loop_mode, loop_mode.title())
            lines.append(f"**Loop:** {loop_label}")

        if queue:
            lines.append("")
            lines.append("**Up Next:**")
            for index, item in enumerate(queue[:5], start=1):
                title = item.get('title', 'Unknown')
                duration = item.get('duration_string', 'Unknown')
                lines.append(f"{index}. {title} ({duration})")
            if len(queue) > 5:
                remaining = len(queue) - 5
                lines.append(f"...and {remaining} more")

        return "\n".join(lines)

    def _build_music_control_buttons(self, chat_id: int) -> Optional[List[List[Button]]]:
        """Create inline buttons for controlling playback."""
        if not self.music_manager:
            return None

        manager = self.music_manager
        if not getattr(manager, 'streaming_available', False):
            return None

        active_calls = getattr(manager, 'active_calls', {})
        if chat_id not in active_calls:
            return None

        paused = manager.paused.get(chat_id, False)
        loop_mode = manager.loop_mode.get(chat_id, 'off')
        loop_label = {
            'off': 'Off',
            'current': 'Current',
            'all': 'All'
        }.get(loop_mode, loop_mode.title())

        return [
            [
                Button.inline(
                    "⏸ Pause" if not paused else "▶️ Resume",
                    f"music:toggle_pause:{chat_id}".encode()
                ),
                Button.inline("⏭ Skip", f"music:skip:{chat_id}".encode()),
                Button.inline("⏹ Stop", f"music:stop:{chat_id}".encode()),
            ],
            [
                Button.inline(
                    f"🔁 Loop: {loop_label}",
                    f"music:loop:{chat_id}".encode()
                ),
                Button.inline("🔀 Shuffle", f"music:shuffle:{chat_id}".encode()),
                Button.inline("📜 Queue", f"music:queue:{chat_id}".encode()),
            ],
        ]

    def _format_music_queue_response(self, chat_id: int, result: Dict) -> str:
        """Format response when a track is added to the queue."""
        song_info = result.get('song', {})
        position = result.get('position')

        lines = [
            f"**Added to queue (Position {position})**" if position else "**Added to queue**",
            "",
            f"**Title:** {song_info.get('title', 'Unknown')}",
            f"**Duration:** {song_info.get('duration_string', 'Unknown')}"
        ]

        queue_status = self._build_music_status_message(chat_id)
        if queue_status:
            lines.extend(["", queue_status])

        return "\n".join(lines)

    def _format_music_download_response(self, result: Dict) -> str:
        """Format response when media is downloaded instead of streamed."""
        song_info = result.get('song', {})

        lines = [
            "**Now Playing (Download Mode)**",
            "",
            f"**Title:** {song_info.get('title', 'Unknown')}",
            f"**Duration:** {song_info.get('duration_string', 'Unknown')}",
            "**Mode:** Download"
        ]

        uploader = song_info.get('uploader')
        if uploader:
            lines.insert(3, f"**Uploader:** {uploader}")

        return "\n".join(lines)

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

            if not result.get('success'):
                error_msg = result.get('error', 'Unknown error')
                await status_msg.edit(f"**Error:** {error_msg}")
                return

            logo_id = self._music_logo_file_id or getattr(config, "MUSIC_LOGO_FILE_ID", "")

            if result.get('streaming'):
                if result.get('queued'):
                    response = self._format_music_queue_response(message.chat_id, result)
                else:
                    response = self._build_music_status_message(message.chat_id)

                caption = VBotBranding.wrap_message(response, include_footer=False)
                buttons = self._build_music_control_buttons(message.chat_id)
                buttons_param = buttons if buttons else None

                if logo_id:
                    try:
                        await self.client.send_file(
                            message.chat_id,
                            logo_id,
                            caption=caption,
                            buttons=buttons_param,
                            force_document=False,
                        )
                        try:
                            await status_msg.delete()
                        except Exception:
                            pass
                    except Exception as send_error:
                        logger.error(f"Failed to send logo artwork: {send_error}")
                        await status_msg.edit(caption, buttons=buttons_param)
                else:
                    await status_msg.edit(caption, buttons=buttons_param)

                return

            response = self._format_music_download_response(result)
            caption = VBotBranding.wrap_message(response, include_footer=False)
            await status_msg.edit(caption)

            file_path = result.get('file_path')
            if not file_path:
                return

            song_info = result.get('song', {})
            caption_lines = [
                f"**Title:** {song_info.get('title', 'Unknown')}",
                f"**Duration:** {song_info.get('duration_string', 'Unknown')}"
            ]
            uploader = song_info.get('uploader')
            if uploader:
                caption_lines.append(f"**Uploader:** {uploader}")
            file_caption = VBotBranding.wrap_message("\n".join(caption_lines), include_footer=False)
            converted_caption = await self._convert_for_user(
                file_caption,
                getattr(message, "sender_id", None),
            )
            if isinstance(converted_caption, str):
                file_caption = converted_caption

            try:
                await self.client.send_file(
                    message.chat_id,
                    file_path,
                    caption=file_caption,
                    force_document=False,
                    supports_streaming=True
                )
            except Exception as send_error:
                logger.error(f"Failed to send media file: {send_error}")
                await self._send_premium_message(
                    message.chat_id,
                    VBotBranding.format_error(f"Gagal mengirim file: {send_error}"),
                    user_id=getattr(message, "sender_id", None),
                )
            return

        except Exception as e:
            logger.error(f"Music command error: {e}", exc_info=True)
            await message.reply(VBotBranding.format_error(f"Music error: {e}"))

    async def _handle_music_callback(self, event, data: str):
        """Process inline button callbacks for music controls."""
        if not self.music_manager:
            await event.answer("❌ Music system not initialized", alert=True)
            return

        try:
            _, action, chat_id_raw = data.split(":", 2)
            chat_id = int(chat_id_raw)
        except ValueError:
            await event.answer("❌ Invalid music action", alert=True)
            return

        manager = self.music_manager
        response_text: Optional[str] = None

        try:
            if action == "toggle_pause":
                paused = manager.paused.get(chat_id, False)
                if paused:
                    response_text = await manager.resume(chat_id)
                else:
                    response_text = await manager.pause(chat_id)
            elif action == "skip":
                response_text = await manager.skip(chat_id)
            elif action == "stop":
                response_text = await manager.stop(chat_id)
            elif action == "loop":
                response_text = await manager.set_loop(chat_id, "toggle")
            elif action == "shuffle":
                response_text = await manager.shuffle(chat_id)
            elif action == "queue":
                queue_text = await manager.show_queue(chat_id)
                await self.client.send_message(chat_id, queue_text)
                response_text = "📨 Queue dikirim ke chat"
            else:
                await event.answer("❌ Unknown action", alert=True)
                return
        except Exception as exc:
            logger.error(f"Music callback error: {exc}", exc_info=True)
            await event.answer("❌ Gagal memproses tombol", alert=True)
            return

        try:
            status_text = self._build_music_status_message(chat_id)
            buttons = self._build_music_control_buttons(chat_id)
            await event.edit(status_text, buttons=buttons)
        except Exception as edit_error:
            logger.debug(f"Failed to update music status message: {edit_error}")

        if response_text:
            show_alert = response_text.startswith("❌")
            await event.answer(response_text, alert=show_alert)
        else:
            await event.answer("Selesai", alert=False)

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

            await self._ensure_group_admin_sync(message.chat_id, force=True)

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

            await self._ensure_group_admin_sync(message.chat_id, force=True)

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

    async def _ensure_group_admin_sync(self, chat_id: int, *, force: bool = False) -> None:
        """Refresh stored admin list for a chat when the cache expires."""

        if not chat_id:
            return

        now = time.monotonic()
        last_sync = self._admin_sync_cache.get(chat_id)
        if not force and last_sync is not None and (now - last_sync) < self._admin_sync_interval:
            return

        admin_entities: List[Any] = []
        try:
            async for participant in self.client.iter_participants(
                chat_id,
                filter=types.ChannelParticipantsAdmins(),
            ):
                if participant:
                    admin_entities.append(participant)
        except Exception as iter_error:
            logger.debug(
                "iter_participants admin sync failed for chat %s: %s",
                chat_id,
                iter_error,
            )
            try:
                fetched = await self.client.get_participants(
                    chat_id, filter=types.ChannelParticipantsAdmins()
                )
                admin_entities.extend(fetched)
            except Exception as fetch_error:
                logger.warning(
                    "Unable to fetch admin list for chat %s: %s",
                    chat_id,
                    fetch_error,
                )
                return

        admin_ids = {
            getattr(entity, "id", None)
            for entity in admin_entities
            if getattr(entity, "id", None)
        }

        if not admin_ids:
            logger.debug(
                "Admin sync yielded empty list for chat %s; keeping previous data",
                chat_id,
            )
            self._admin_sync_cache[chat_id] = now
            return

        existing = set(self.database.get_group_admins(chat_id))

        for user_id in admin_ids - existing:
            self.database.add_group_admin(chat_id, user_id)

        for user_id in existing - admin_ids:
            self.database.remove_group_admin(chat_id, user_id)

        self._admin_sync_cache[chat_id] = now

    @staticmethod
    def _format_admin_entry(entity: Any) -> str:
        """Return a readable label for an admin entity."""

        user_id = getattr(entity, "id", None)
        username = getattr(entity, "username", None)
        first_name = getattr(entity, "first_name", "") or ""
        last_name = getattr(entity, "last_name", "") or ""
        full_name = " ".join(part for part in [first_name, last_name] if part).strip()

        if username and full_name:
            return f"{full_name} (@{username})"
        if username:
            return f"@{username}"
        if full_name:
            return f"{full_name} (`{user_id}`)"
        return f"`User {user_id}`"

    async def _handle_adminlist_command(self, message):
        """Handle /adminlist command - show tracked admins for this group."""

        if not message.is_group and not message.is_channel:
            await message.reply("**Perintah ini hanya tersedia di grup.**")
            return

        chat_id = message.chat_id
        if chat_id is None:
            await message.reply("Tidak dapat menentukan grup saat ini.")
            return

        await self._ensure_group_admin_sync(chat_id, force=True)

        admin_ids = self.database.get_group_admins(chat_id)
        if not admin_ids:
            await message.reply(
                "⚠️ **Belum ada admin yang tercatat untuk grup ini.**\n"
                "Gunakan perintah admin sekali agar bot dapat menyinkronkan daftar."
            )
            return

        admin_lines: List[str] = []
        for index, user_id in enumerate(admin_ids, start=1):
            try:
                entity = await self.client.get_entity(user_id)
                admin_lines.append(f"{index}. {self._format_admin_entry(entity)}")
            except Exception as fetch_error:
                logger.debug(
                    "Unable to resolve admin %s in chat %s: %s",
                    user_id,
                    chat_id,
                    fetch_error,
                )
                admin_lines.append(f"{index}. `User {user_id}`")

        header = "**Daftar Admin Grup**"
        await message.reply(f"{header}\n\n" + "\n".join(admin_lines))

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

            # Prevent locking bot developers/owners
            if self.auth_manager.is_developer(target_user_id) or self.auth_manager.is_owner(target_user_id):
                issuer_id = getattr(message, 'sender_id', None)
                if not issuer_id:
                    await message.reply("**Error:** You cannot lock bot developers or owners.")
                    return

                protected_role = "developer" if self.auth_manager.is_developer(target_user_id) else "owner"
                punishment_reason = (
                    f"Attempted to lock a protected {protected_role}. "
                    "Only bot developers can unlock this restriction."
                )
                metadata = {
                    'requires_developer': True,
                    'reason': punishment_reason,
                    'locked_for': 'protected_account_attempt',
                    'protected_role': protected_role,
                    'protected_user_id': target_user_id,
                }

                logger.warning(
                    "User %s attempted to lock protected %s %s", issuer_id, protected_role, target_user_id
                )

                success = await self.lock_manager.lock_user(
                    message.chat_id,
                    issuer_id,
                    punishment_reason,
                    metadata=metadata,
                )

                if success:
                    try:
                        issuer_entity = await self.client.get_entity(issuer_id)
                        if getattr(issuer_entity, 'username', None):
                            issuer_label = f"@{issuer_entity.username}"
                        else:
                            issuer_label = f"[User {issuer_id}](tg://user?id={issuer_id})"
                    except Exception:
                        issuer_label = f"User {issuer_id}"

                    await message.reply(
                        "**Protected Account Attempt**\n\n"
                        f"{issuer_label} tried to lock a protected {protected_role} and has been locked instead.\n"
                        "Only bot developers can unlock this restriction."
                    )
                else:
                    await message.reply(
                        "**Error:** Protected account detected but failed to apply the automatic lock."
                    )
                await message.reply("**Error:** You cannot lock bot developers or owners.")
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
            metadata = self.lock_manager.get_lock_metadata(message.chat_id, target_user_id)
            if metadata.get('requires_developer'):
                issuer_id = getattr(message, 'sender_id', None)
                if not issuer_id or not self.auth_manager.is_developer(issuer_id):
                    await message.reply(
                        "**Error:** Only bot developers can unlock this user after they attempted to lock a protected account."
                    )
                    return

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

    async def _handle_tag_command(self, message):
        """Handle perintah tag massal dengan dukungan batch dinamis."""
        if not config.ENABLE_TAG_SYSTEM:
            await message.reply(
                VBotBranding.format_error("Sistem tag sedang dinonaktifkan oleh Vzoel Fox's (Lutpan).")
            )
            return

        if not message.is_group and not message.is_channel:
            await message.reply(
                VBotBranding.format_error("Perintah tag massal hanya tersedia di grup atau kanal.")
            )
            return

        try:
            reply_message = None
            if getattr(message, "is_reply", False):
                try:
                    reply_message = await message.get_reply_message()
                except Exception as fetch_error:
                    logger.debug("Failed to fetch replied message: %s", fetch_error)

            raw_text = message.raw_text or message.text or ""
            remainder = ""
            if raw_text:
                parts = raw_text.split(maxsplit=1)
                if len(parts) > 1:
                    remainder = parts[1].strip()

            provided_batch: Optional[int] = None
            custom_message = remainder

            if remainder:
                first_split = remainder.split(maxsplit=1)
                candidate = first_split[0]
                rest_text = first_split[1] if len(first_split) > 1 else ""
                if candidate.isdigit():
                    provided_batch = int(candidate)
                    custom_message = rest_text.strip()
                else:
                    custom_message = remainder

            if not custom_message and reply_message:
                reply_text = getattr(reply_message, "raw_text", None) or getattr(reply_message, "message", "")
                custom_message = reply_text.strip()

            if not custom_message:
                custom_message = "Sedang menandai seluruh anggota..."

            custom_message = (
                f"{custom_message}\n\n_Disajikan oleh Vzoel Fox's (Lutpan)_"
            )

            reply_to_msg_id = getattr(message, "reply_to_msg_id", None)

            success = await self.tag_manager.start_tag_all(
                self.client,
                message.chat_id,
                custom_message,
                message.sender_id,
                batch_size=provided_batch,
                reply_to_msg_id=reply_to_msg_id,
            )

            if success:
                confirm_text = (
                    "**Tag Massal Dimulai**\n\n"
                    f"**Pesan:** {custom_message}\n\n"
                    "Bot akan menandai seluruh anggota secara bertahap. Gunakan `.c`/`/c`/`+c` untuk menghentikan."
                )
                await message.reply(
                    VBotBranding.wrap_message(confirm_text, include_footer=False)
                )
                return

            if not success:
                if message.chat_id in self.tag_manager.active_tags:
                    await message.reply(
                        VBotBranding.format_error(
                            "Proses tag massal sedang berlangsung. Tunggu hingga selesai atau gunakan `.c`/`/c`/`+c`."
                        )
                    )
                else:
                    await message.reply(
                        VBotBranding.format_error(
                            "Tag massal gagal dimulai. Periksa anggota dan izin bot."
                        )
                    )

        except Exception as e:
            logger.error(f"Error in tag command: {e}", exc_info=True)
            await message.reply(
                VBotBranding.format_error(f"Galat sistem: {str(e)}")
            )

    async def _handle_tag_cancel_command(self, message):
        """Handle perintah pembatalan tag massal."""
        if not message.is_group and not message.is_channel:
            await message.reply(
                VBotBranding.format_error("Perintah pembatalan hanya tersedia di grup atau kanal.")
            )
            return

        try:
            success = await self.tag_manager.cancel_tag_all(message.chat_id)

            if success:
                cancel_text = (
                    "**Tag Massal Dibatalkan**\n\n"
                    "Proses penandaan telah dihentikan sesuai permintaan admin."
                )
                await message.reply(
                    VBotBranding.wrap_message(cancel_text, include_footer=False)
                )
            else:
                await message.reply(
                    VBotBranding.format_error("Tidak ada proses tag massal yang aktif di percakapan ini.")
                )

        except Exception as e:
            logger.error(f"Error in cancel command: {e}", exc_info=True)
            await message.reply(
                VBotBranding.format_error(f"Galat sistem: {str(e)}")
            )


async def main():
    bot = VBot()
    ok = await bot.initialize()
    if not ok:
        sys.exit(1)
    logger.info("VBot is up and running.")
    await asyncio.Future()  # run forever


if __name__ == "__main__":
    try:
        if uvloop is not None:
            asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
        asyncio.run(main())
    except KeyboardInterrupt:
        pass

