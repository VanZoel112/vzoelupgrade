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
from datetime import datetime

# Import advanced logging system
from core.logger import setup_logging, vbot_logger

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
            from telethon.tl.types import BotCommand, BotCommandScopeDefault

            # Define available commands
            commands = [
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
            ]

            # Set bot commands
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
        start_time = datetime.now()
        command_text = message.text.lower()

        try:
            command_parts = command_text.split()
            command = command_parts[0]

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

            # Music commands (slash prefix)
            elif command in ['/play', '/p']:
                await self._handle_music_command(message, parts, audio_only=True)
            elif command in ['/vplay', '/vp']:
                await self._handle_music_command(message, parts, audio_only=False)
            elif command == '/pause':
                await self._handle_pause_command(message)
            elif command == '/resume':
                await self._handle_resume_command(message)
            elif command in ['/skip', '/next']:
                await self._handle_skip_command(message)
            elif command == '/stop':
                await self._handle_stop_command(message)
            elif command in ['/queue', '/q']:
                await self._handle_queue_command(message)
            elif command == '/shuffle':
                await self._handle_shuffle_command(message)
            elif command == '/loop':
                await self._handle_loop_command(message, parts)
            elif command == '/seek':
                await self._handle_seek_command(message, parts)
            elif command == '/volume':
                await self._handle_volume_command(message, parts)
            elif command == '.join':
                await self._handle_join_vc_command(message)
            elif command == '.leave':
                await self._handle_leave_vc_command(message)

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

            # Show processing message
            media_type = "audio" if audio_only else "video"
            status_msg = await message.reply(f"**Processing {media_type} request...**")

            # Play stream
            result = await self.music_manager.play_stream(
                message.chat_id,
                query,
                message.sender_id,
                audio_only=audio_only
            )

            if result['success']:
                song = result['song']

                if result.get('queued'):
                    # Song added to queue
                    mode = "VC Queue" if result.get('streaming') else "Download Queue"

                    # Create inline buttons - VBot branding
                    buttons = [
                        [
                            Button.inline("Pause", data="music_pause"),
                            Button.inline("Skip", data="music_skip")
                        ],
                        [
                            Button.inline("Queue", data="music_queue"),
                            Button.inline("Shuffle", data="music_shuffle")
                        ],
                        [
                            Button.inline("Loop", data="music_loop"),
                            Button.inline("Stop", data="music_stop")
                        ],
                        [
                            Button.inline("VBot by Vzoel Fox's", data="vbot_info")
                        ]
                    ]

                    await status_msg.edit(
                        f"{mode} **#{result['position']}**\n\n"
                        f"**{song['title']}**\n"
                        f"Duration: {song.get('duration', 0) // 60}:{song.get('duration', 0) % 60:02d}",
                        buttons=buttons
                    )
                elif result.get('streaming'):
                    # Streaming in voice chat - add playback control buttons
                    buttons = [
                        [
                            Button.inline("Pause", data="music_pause"),
                            Button.inline("Resume", data="music_resume")
                        ],
                        [
                            Button.inline("Skip", data="music_skip"),
                            Button.inline("Stop", data="music_stop")
                        ],
                        [
                            Button.inline("Queue", data="music_queue"),
                            Button.inline("Shuffle", data="music_shuffle")
                        ],
                        [
                            Button.inline("Loop", data="music_loop"),
                            Button.inline("Volume", data="music_volume")
                        ],
                        [
                            Button.inline("VBot by Vzoel Fox's", data="vbot_info")
                        ]
                    ]

                    await status_msg.edit(
                        f"**Now Streaming in Voice Chat**\n\n"
                        f"**{song['title']}**\n"
                        f"Duration: {song.get('duration', 0) // 60}:{song.get('duration', 0) % 60:02d}\n\n"
                        f"Use the buttons below to control playback",
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
                await message.reply("**Queue Status**\n\nQueue is empty\n\nUse .play to add songs")
                return

            response = "**Music Queue**\n\n"

            if current:
                response += f"**Now Playing**\n{current['title']}\n\n"

            if queue:
                response += "**Up Next**\n"
                for i, song in enumerate(queue[:10], 1):
                    response += f"{i}. {song['title']}\n"

                if len(queue) > 10:
                    response += f"\n... and {len(queue) - 10} more"
            else:
                response += "No songs in queue"

            await message.reply(response)

        except Exception as e:
            await message.reply(f"Error getting queue: {str(e)}")

    async def _handle_join_vc_command(self, message):
        """Handle .join command - join voice chat"""
        try:
            if not self.music_manager:
                await message.reply("Music system not initialized")
                return

            if not self.music_manager.streaming_available:
                await message.reply("Voice chat streaming not available\nAssistant account not configured")
                return

            # Join voice chat
            status_msg = await message.reply("**Connecting to voice chat...**")

            success = await self.music_manager.join_voice_chat(message.chat_id)

            if success:
                await status_msg.edit("**Connected to voice chat**\n\nReady for streaming")
            else:
                await status_msg.edit("Failed to join voice chat\n\nCheck assistant permissions")

        except Exception as e:
            logger.error(f"Error joining VC: {e}")
            await message.reply(f"Error: {str(e)}")

    async def _handle_leave_vc_command(self, message):
        """Handle .leave command - leave voice chat"""
        try:
            if not self.music_manager:
                await message.reply("Music system not initialized")
                return

            if not self.music_manager.streaming_available:
                await message.reply("Not connected to voice chat")
                return

            # Leave voice chat
            status_msg = await message.reply("**Disconnecting from voice chat...**")

            success = await self.music_manager.leave_voice_chat(message.chat_id)

            if success:
                await status_msg.edit("**Disconnected from voice chat**")
            else:
                await status_msg.edit("Not in voice chat")

        except Exception as e:
            logger.error(f"Error leaving VC: {e}")
            await message.reply(f"Error: {str(e)}")

    async def _handle_skip_command(self, message):
        """Handle /skip command"""
        if not self.music_manager:
            await message.reply("Music system not initialized")
            return

        try:
            status_msg = await message.reply("**Skipping to next song...**")
            result = await self.music_manager.skip_song(message.chat_id)

            if result['success']:
                song = result['song']
                buttons = [
                    [
                        Button.inline("Pause", data="music_pause"),
                        Button.inline("Skip", data="music_skip")
                    ],
                    [
                        Button.inline("Queue", data="music_queue"),
                        Button.inline("Stop", data="music_stop")
                    ],
                    [
                        Button.inline("VBot by Vzoel Fox's", data="vbot_info")
                    ]
                ]

                await status_msg.edit(
                    f"**Now Playing**\n\n"
                    f"**{song['title']}**\n"
                    f"Duration: {song.get('duration', 0) // 60}:{song.get('duration', 0) % 60:02d}\n"
                    f"Remaining in queue: {result['remaining']}",
                    buttons=buttons
                )
            else:
                await status_msg.edit(f"**Error:** {result.get('error', 'Unable to skip')}")

        except Exception as e:
            await message.reply(f"Error: {str(e)}")

    async def _handle_shuffle_command(self, message):
        """Handle /shuffle command"""
        if not self.music_manager:
            await message.reply("Music system not initialized")
            return

        try:
            success = await self.music_manager.shuffle_queue(message.chat_id)

            if success:
                await message.reply("**Queue shuffled successfully**")
            else:
                await message.reply("**Error:** Queue is empty or shuffle failed")

        except Exception as e:
            await message.reply(f"Error: {str(e)}")

    async def _handle_loop_command(self, message, parts):
        """Handle /loop command"""
        if not self.music_manager:
            await message.reply("Music system not initialized")
            return

        try:
            if len(parts) < 2:
                current_mode = self.music_manager.get_loop_mode(message.chat_id)
                await message.reply(
                    f"**Current loop mode:** {current_mode}\n\n"
                    f"**Usage:** /loop <mode>\n"
                    f"**Modes:** off, current, all"
                )
                return

            mode = parts[1].lower()
            success = await self.music_manager.set_loop_mode(message.chat_id, mode)

            if success:
                await message.reply(f"**Loop mode set to:** {mode}")
            else:
                await message.reply("**Error:** Invalid mode. Use: off, current, all")

        except Exception as e:
            await message.reply(f"Error: {str(e)}")

    async def _handle_seek_command(self, message, parts):
        """Handle /seek command"""
        if not self.music_manager:
            await message.reply("Music system not initialized")
            return

        try:
            if len(parts) < 2:
                await message.reply(
                    f"**Usage:** /seek <timestamp>\n\n"
                    f"**Examples:**\n"
                    f"/seek 30 (30 seconds)\n"
                    f"/seek 1:30 (1 minute 30 seconds)"
                )
                return

            # Parse timestamp
            timestamp = parts[1]
            if ':' in timestamp:
                time_parts = timestamp.split(':')
                seconds = int(time_parts[0]) * 60 + int(time_parts[1])
            else:
                seconds = int(timestamp)

            success = await self.music_manager.seek_position(message.chat_id, seconds)

            if success:
                await message.reply(f"**Seeked to:** {seconds // 60}:{seconds % 60:02d}")
            else:
                await message.reply("**Error:** Seek not available (streaming mode only)")

        except ValueError:
            await message.reply("**Error:** Invalid timestamp format")
        except Exception as e:
            await message.reply(f"Error: {str(e)}")

    async def _handle_volume_command(self, message, parts):
        """Handle /volume command"""
        if not self.music_manager:
            await message.reply("Music system not initialized")
            return

        try:
            if len(parts) < 2:
                current_volume = self.music_manager.get_volume(message.chat_id)
                await message.reply(
                    f"**Current volume:** {current_volume}\n\n"
                    f"**Usage:** /volume <0-200>\n\n"
                    f"**Examples:**\n"
                    f"/volume 100 (default)\n"
                    f"/volume 150 (louder)"
                )
                return

            volume = int(parts[1])
            success = await self.music_manager.set_volume(message.chat_id, volume)

            if success:
                await message.reply(f"**Volume set to:** {volume}")
            else:
                await message.reply("**Error:** Volume must be 0-200")

        except ValueError:
            await message.reply("**Error:** Volume must be a number")
        except Exception as e:
            await message.reply(f"Error: {str(e)}")

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
**Welcome, {user.first_name}**

VBot - Advanced Telegram Management System
Powered by Vzoel Fox's

**Core Features**
• Music streaming and playback control
• Advanced user management system
• Smart tagging and moderation tools
• Customizable welcome automation
• Multi-level permission architecture

**Quick Start**
/help - View all available commands
/about - System information

**Permission Levels**
+ Owner commands (system management)
/ Admin commands (group moderation)
. Public commands (all users)

Contact: @VZLfxs
"""
        await message.reply(welcome_text)

    async def _handle_about_command(self, message):
        """Handle /about command"""
        about_text = """
**VBot System Information**

Version: 2.0.0 Python Edition
Developer: Vzoel Fox
Architecture: Python + Telethon

**System Modules**
Music streaming engine
User management system
Automated moderation tools
Welcome automation
Permission management
Database persistence

**Technology Stack**
Python 3.12+
Telethon MTProto
yt-dlp media engine
Async/await architecture

Developed by Vzoel Fox
Contact: @VZLfxs
"""
        await message.reply(about_text)

    async def _handle_help_command(self, message):
        """Handle #help command"""
        help_text = """
**VBot Command Reference**

**Owner Commands** (+ prefix)
+add <user> - Grant admin command access
+del <user> - Revoke admin command access
+setwelcome <text> - Configure welcome message
+backup - Create database backup

**Admin Commands** (/ prefix)
/pm <user> - Promote to admin list
/dm <user> - Demote from admin list
/tagall <text> - Tag all members
/cancel - Stop ongoing tag operation
/lock <user> - Enable auto-delete for user
/unlock <user> - Disable auto-delete
/locklist - View locked users

**Public Commands** (. prefix)
.play <query> - Stream or download music
.pause - Pause current playback
.resume - Resume playback
.stop - Stop and clear queue
.queue - View music queue

**Information**
/start - System overview
/about - Technical details
/help - This command reference

**Permission Structure**
+ Commands require owner authorization
/ Commands require admin or granted access
. Commands available to all users

System developed by Vzoel Fox
Contact: @VZLfxs
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
                'privacy': self.privacy_manager.get_privacy_stats() if config.ENABLE_PRIVACY_SYSTEM else {}
            }

            stats_text = "**System Statistics**\n\n"

            if stats['lock']:
                stats_text += f"**Lock System**\n"
                stats_text += f"Locked users: {stats['lock'].get('total_locked_users', 0)}\n"
                stats_text += f"Active chats: {stats['lock'].get('chats_with_locks', 0)}\n\n"

            if stats['music']:
                stats_text += f"**Music System**\n"
                stats_text += f"Cached files: {stats['music'].get('total_files', 0)}\n"
                stats_text += f"Storage usage: {stats['music'].get('total_size_mb', 0)} MB\n\n"

            db_stats = self.database.get_stats()
            stats_text += f"**Database**\n"
            stats_text += f"Authorized users: {db_stats.get('authorized_users', 0)}\n"
            stats_text += f"Database size: {db_stats.get('database_size', 0) / 1024:.2f} KB\n\n"

            stats_text += "Vzoel Fox's VBot System"

            if config.ENABLE_PRIVACY_SYSTEM:
                await self.privacy_manager.process_private_command(
                    self.client, message, stats_text
                )
            else:
                await message.reply(stats_text)

        except Exception as e:
            await message.reply(f"Error retrieving statistics: {str(e)}")

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
                f"**Access Granted**\n\n"
                f"User: {target_username or target_user_id}\n"
                f"ID: `{target_user_id}`\n\n"
                f"Admin command access enabled for this chat."
            )

            await message.reply(response)
            logger.info(f"Added permission for user {target_user_id} in chat {message.chat_id}")

        except Exception as e:
            logger.error(f"Error in +add command: {e}")
            await message.reply(f"Error: Unable to grant access - {str(e)}")

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
                    f"**Access Revoked**\n\n"
                    f"User: {target_username or target_user_id}\n"
                    f"ID: `{target_user_id}`\n\n"
                    f"Admin command access disabled for this chat."
                )
            else:
                response = f"User {target_user_id} not found in authorization list"

            await message.reply(response)
            logger.info(f"Removed permission for user {target_user_id} in chat {message.chat_id}")

        except Exception as e:
            logger.error(f"Error in +del command: {e}")
            await message.reply(f"Error: Unable to revoke access - {str(e)}")

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
                f"**Welcome Configuration Updated**\n\n"
                f"Preview:\n{welcome_text}\n\n"
                f"Available variables:\n"
                f"{{user}} - User first name\n"
                f"{{mention}} - User mention\n"
                f"{{chat}} - Chat name"
            )
            logger.info(f"Updated welcome message for chat {message.chat_id}")

        except Exception as e:
            logger.error(f"Error in +setwelcome command: {e}")
            await message.reply(f"Error: Unable to update welcome - {str(e)}")

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
                f"**User Promoted**\n\n"
                f"User: {target_username or target_user_id}\n"
                f"ID: `{target_user_id}`\n\n"
                f"Admin permissions granted via system management."
            )

        except Exception as e:
            logger.error(f"Error in /pm command: {e}")
            await message.reply(f"Error: Promotion failed - {str(e)}")

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
**Group Guidelines**

1. Maintain respectful communication
2. Avoid spam and excessive messaging
3. Keep content appropriate for all ages
4. Comply with Telegram Terms of Service
5. Use commands responsibly

Contact: @VZLfxs
"""
        await message.reply(rules_text)

    async def _handle_session_command(self, message):
        """Handle #session command"""
        session_text = """
**Session String Configuration**

Generate session string for assistant account:

**Terminal Method**
Execute: python3 genstring.py

**In-Bot Method**
Command: .gensession (private chat only)

**Technical Note**
Session can utilize any Telegram user account.
Requires valid API_ID and API_HASH credentials.

Contact: @VZLfxs
"""
        await message.reply(session_text)

    async def _handle_backup_command(self, message, parts):
        """Handle +backup command - manual database backup"""
        try:
            status_msg = await message.reply("**Processing backup...**")

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
                    f"**Backup Complete**\n\n"
                    f"Database synchronized to remote repository\n"
                    f"Last backup: {last_backup}\n"
                    f"Database size: {self.database.db_path.stat().st_size / 1024:.2f} KB\n\n"
                    f"Auto-backup: {'Enabled' if stats.get('auto_backup_enabled') else 'Disabled'}"
                )
            else:
                await status_msg.edit(
                    "**Backup Failed**\n\n"
                    "Verification checklist:\n"
                    "- Git configuration\n"
                    "- Remote repository access\n"
                    "- Push permissions\n\n"
                    "Review system logs for details."
                )

        except Exception as e:
            logger.error(f"Error in +backup command: {e}")
            await message.reply(f"Backup error: {str(e)}")

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
                        await event.answer("Paused")
                        # Update button to show resume
                        buttons = [
                            [
                                Button.inline("Resume", data="music_resume"),
                                Button.inline("Skip", data="music_skip")
                            ],
                            [
                                Button.inline("Queue", data="music_queue"),
                                Button.inline("Stop", data="music_stop")
                            ],
                            [
                                Button.inline("VBot by Vzoel Fox's", data="vbot_info")
                            ]
                        ]
                        await event.edit(buttons=buttons)
                    else:
                        await event.answer("Failed to pause", alert=True)

                elif action == 'resume':
                    success = await self.music_manager.resume_stream(chat_id)
                    if success:
                        await event.answer("Resumed")
                        # Update button to show pause
                        buttons = [
                            [
                                Button.inline("Pause", data="music_pause"),
                                Button.inline("Skip", data="music_skip")
                            ],
                            [
                                Button.inline("Queue", data="music_queue"),
                                Button.inline("Stop", data="music_stop")
                            ],
                            [
                                Button.inline("VBot by Vzoel Fox's", data="vbot_info")
                            ]
                        ]
                        await event.edit(buttons=buttons)
                    else:
                        await event.answer("Failed to resume", alert=True)

                elif action == 'stop':
                    success = await self.music_manager.stop_stream(chat_id)
                    if success:
                        await event.answer("Stopped")
                        await event.edit("**Stopped and cleared queue**")
                    else:
                        await event.answer("No active stream", alert=True)

                elif action == 'skip':
                    result = await self.music_manager.skip_song(chat_id)
                    if result['success']:
                        await event.answer("Skipped")
                        song = result['song']
                        buttons = [
                            [
                                Button.inline("Pause", data="music_pause"),
                                Button.inline("Skip", data="music_skip")
                            ],
                            [
                                Button.inline("Queue", data="music_queue"),
                                Button.inline("Stop", data="music_stop")
                            ],
                            [
                                Button.inline("VBot by Vzoel Fox's", data="vbot_info")
                            ]
                        ]
                        await event.edit(
                            f"**Now Playing**\n\n**{song['title']}**\n"
                            f"Remaining: {result['remaining']}",
                            buttons=buttons
                        )
                    else:
                        await event.answer(result.get('error', 'Unable to skip'), alert=True)

                elif action == 'shuffle':
                    success = await self.music_manager.shuffle_queue(chat_id)
                    if success:
                        await event.answer("Queue shuffled")
                    else:
                        await event.answer("Queue is empty", alert=True)

                elif action == 'loop':
                    # Cycle through loop modes: off -> current -> all -> off
                    current_mode = self.music_manager.get_loop_mode(chat_id)
                    modes = ['off', 'current', 'all']
                    next_mode = modes[(modes.index(current_mode) + 1) % len(modes)]
                    await self.music_manager.set_loop_mode(chat_id, next_mode)
                    await event.answer(f"Loop: {next_mode}")

                elif action == 'volume':
                    current_volume = self.music_manager.get_volume(chat_id)
                    await event.answer(
                        f"Current volume: {current_volume}\n\nUse /volume <0-200> to change",
                        alert=True
                    )

                elif action == 'queue':
                    # Show queue
                    current = self.music_manager.get_current_song(chat_id)
                    queue = self.music_manager.get_queue(chat_id)

                    if not current and not queue:
                        await event.answer("Queue is empty", alert=True)
                        return

                    response = "**Music Queue**\n\n"
                    if current:
                        response += f"**Now Playing:**\n{current['title']}\n\n"
                    if queue:
                        response += "**Up Next:**\n"
                        for i, song in enumerate(queue[:5], 1):
                            response += f"{i}. {song['title']}\n"
                        if len(queue) > 5:
                            response += f"\n... and {len(queue) - 5} more"

                    await event.answer(response, alert=True)

            elif data == 'vbot_info':
                await event.answer(
                    "VBot Music System\nDeveloped by Vzoel Fox's\n\nGithub: github.com/VanZoel112",
                    alert=True
                )

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

    async def stop(self, reason: str = "Manual shutdown"):
        """Stop VBot gracefully"""
        logger.info("🛑 Stopping VBot...")

        # Log shutdown to Telegram
        await vbot_logger.log_shutdown(reason)

        if self.tag_manager:
            await self.tag_manager.force_stop_all_tags()

        if self.music_manager:
            await self.music_manager.stop()

        if self.assistant_client:
            await self.assistant_client.disconnect()
            logger.info("✅ Assistant client disconnected")

        if self.client:
            await self.client.disconnect()

        # Stop logging system
        vbot_logger.stop()

        logger.info("👋 VBot stopped")

async def main():
    """Main entry point"""
    vbot = VBot()

    try:
        await vbot.run()
    except KeyboardInterrupt:
        await vbot.stop("Keyboard interrupt (Ctrl+C)")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        await vbot.stop(f"Fatal error: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())