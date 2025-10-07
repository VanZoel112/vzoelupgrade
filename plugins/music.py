"""
Music Plugin - Voice Chat Music Player
Hanya untuk developer/owner dan admin grup, auto pakai assistant account untuk streaming

Commands:
    /play <query> - Play audio (developer/owner atau admin grup)
    /vplay <query> - Play video (developer/owner atau admin grup)
    /pause - Pause current song
    /resume - Resume paused song
    /skip - Skip to next song
    /stop - Stop and clear queue
    /queue - Show queue
    /shuffle - Shuffle queue
    /loop <off|current|all> - Set loop mode

Author: Vzoel Fox's
"""

import logging
from telethon import events, Button
import config

logger = logging.getLogger(__name__)

HANDLED_COMMANDS = {
    "/play", "/vplay", "/pause", "/resume", "/skip", "/stop", 
    "/queue", "/shuffle", "/loop"
}


class MusicPlayer:
    """Music player handler for voice chat"""

    def __init__(self, bot):
        self.bot = bot
        self.client = getattr(bot, "client", None)
        self.music_manager = getattr(bot, "music_manager", None)
        self.plugin_name = "Music Player"
        self.auth_manager = getattr(bot, "auth_manager", None)
        self._streaming_warning_chats = set()
        self._developer_ids = set(getattr(config, "DEVELOPER_IDS", []) or [])
        self._owner_id = getattr(config, "OWNER_ID", 0) or 0

        # Try to import branding
        try:
            from core.branding import VBotBranding
            self.branding = VBotBranding
        except ImportError:
            self.branding = None

    def format_message(
        self,
        content: str,
        *,
        include_footer: bool = True,
        include_header: bool = True,
    ) -> str:
        """Helper to apply VBot branding when available."""
        if self.branding:
            return self.branding.wrap_message(
                content,
                include_header=include_header,
                include_footer=include_footer,
                plugin_name=self.plugin_name,
            )
        return content

    def is_developer(self, user_id: int) -> bool:
        """Check if user is allowed to control music features."""
        if self.auth_manager:
            if self.auth_manager.is_developer(user_id) or self.auth_manager.is_owner(user_id):
                return True

        developer_ids = getattr(config, "DEVELOPER_IDS", []) or []
        if user_id in developer_ids:
            return True

        owner_id = getattr(config, "OWNER_ID", 0) or 0
        return bool(owner_id) and user_id == owner_id

    async def has_music_access(self, event) -> bool:
        """Return True if the event sender may control music in this chat."""
        user_id = event.sender_id

        client = getattr(event, "client", None) or self.client

        chat_id = getattr(event, "chat_id", None)
        if chat_id is None or client is None:
            return False

        if self.music_manager and hasattr(self.music_manager, "user_has_access"):
            try:
                return await self.music_manager.user_has_access(chat_id, user_id, client)
            except Exception:
                logger.warning(
                    "Music manager access check failed, falling back to plugin auth", exc_info=True
                )

        if not self.auth_manager:
            return self.is_developer(user_id)

        if self.is_developer(user_id):
            return True

        try:
            return await self.auth_manager.is_admin_in_chat(client, user_id, chat_id)
        except Exception:
            logger.warning("Failed to check admin privileges for music access", exc_info=True)
            return False
        if user_id in self._developer_ids:
            return True

        return bool(self._owner_id) and user_id == self._owner_id

    async def check_music_available(self, event):
        """Check if music manager is available"""
        if not self.music_manager:
            await event.reply(
                self.format_message(
                    "❌ **Music Manager tidak tersedia**\\n\\n"
                    "Pastikan assistant account sudah dikonfigurasi di .env"
                )
            )
            return False

        if not self.music_manager.streaming_available:
            chat_id = event.chat_id
            if chat_id not in self._streaming_warning_chats:
                self._streaming_warning_chats.add(chat_id)
                await event.reply(
                    self.format_message(
                        "ℹ️ **Streaming tidak tersedia**\\n\\n"
                        "Bot akan menggunakan mode unduhan sehingga musik masih bisa diputar."
                        "\\n\\nUntuk mengaktifkan streaming langsung, pastikan:"
                        "\\n• STRING_SESSION sudah diisi di .env"
                        "\\n• py-tgcalls sudah terinstall"
                        "\\n• Assistant account sudah login"
                    )
                )
            return True

        return True

    async def handle_play(self, event, audio_only=True):
        """Handle /play and /vplay commands"""
        user_id = event.sender_id

        # Check permission for controlling music
        if not await self.has_music_access(event):
            await event.reply(
                self.format_message(
                    "🎵 **VBot Music Player**\n\n"
                    "❌ Fitur musik hanya untuk developer/owner atau admin grup ini.\n\n"
                    "Silakan hubungi admin atau owner bot untuk akses."
                    "🎵 **VBot Music Player**\\n\\n"
                    "❌ Fitur musik hanya untuk developer atau owner.\\n\\n"
                    "Silakan hubungi owner bot untuk akses."
                )
            )
            return

        # Check if music manager available
        if not await self.check_music_available(event):
            return

        # Parse query
        text = event.message.text.strip()
        parts = text.split(maxsplit=1)
        
        if len(parts) < 2:
            media_type = "Audio" if audio_only else "Video"
            cmd = parts[0]
            await event.reply(
                self.format_message(
                    f"❌ **Format salah!**\\n\\n"
                    f"Penggunaan: {cmd} <judul lagu atau URL>\\n\\n"
                    f"Contoh:\\n"
                    f"• {cmd} Shape of You\\n"
                    f"• {cmd} https://youtube.com/watch?v=...",
                    include_footer=False
                )
            )
            return

        query = parts[1]
        chat_id = event.chat_id

        # Send loading message
        media_label = "audio" if audio_only else "video"
        loading_msg = await event.reply(
            self.format_message(
                f"⏳ **Mencari {media_label}...**\\n\\n"
                f"Query: {query[:50]}",
                include_footer=False
            )
        )

        try:
            # Play stream
            result = await self.music_manager.play_stream(
                chat_id, query, user_id, audio_only
            )

            await loading_msg.delete()

            if not result.get('success'):
                error_code = result.get('error_code')
                if error_code == 'not_authorized':
                    await event.reply(
                        self.format_message(
                            "🎵 **VBot Music Player**\\n\\n"
                            "❌ Fitur musik hanya untuk developer/owner atau admin grup ini.\\n\\n"
                            "Silakan hubungi admin atau owner bot untuk akses."
                        )
                    )
                    return

                error = result.get('error', 'Unknown error')
                await event.reply(
                    self.format_message(
                        f"❌ **Error**\\n\\n{error}"
                    )
                )
                return

            song = result.get('song', {})
            title = song.get('title', 'Unknown')
            duration = song.get('duration_string', 'Unknown')
            uploader = song.get('uploader', 'Unknown')
            thumbnail = song.get('thumbnail')

            if result.get('queued'):
                # Added to queue
                position = result.get('position', 0)
                message = (
                    f"📝 **Added to Queue** (#{position})\\n\\n"
                    f"**Title:** {title}\\n"
                    f"**Duration:** {duration}\\n"
                    f"**Uploader:** {uploader}"
                )
            else:
                # Now playing
                streaming = result.get('streaming', False)
                mode = "Streaming" if streaming else "Download"
                emoji = "🎵" if audio_only else "🎬"
                
                message = (
                    f"{emoji} **Now Playing** ({mode})\\n\\n"
                    f"**Title:** {title}\\n"
                    f"**Duration:** {duration}\\n"
                    f"**Uploader:** {uploader}"
                )

            # Control buttons
            buttons = [
                [
                    Button.inline("⏸️ Pause", b"music_pause"),
                    Button.inline("⏭️ Skip", b"music_skip"),
                    Button.inline("⏹️ Stop", b"music_stop")
                ],
                [
                    Button.inline("📝 Queue", b"music_queue"),
                    Button.inline("🔀 Shuffle", b"music_shuffle"),
                    Button.inline("🔁 Loop", b"music_loop")
                ]
            ]

            # Send with thumbnail if available
            if thumbnail and streaming:
                try:
                    await event.respond(
                        self.format_message(message, include_footer=False),
                        file=thumbnail,
                        buttons=buttons
                    )
                except:
                    await event.reply(
                        self.format_message(message, include_footer=False),
                        buttons=buttons
                    )
            else:
                await event.reply(
                    self.format_message(message, include_footer=False),
                    buttons=buttons
                )

        except Exception as e:
            logger.error(f"Error in handle_play: {e}", exc_info=True)
            await loading_msg.delete()
            await event.reply(
                self.format_message(f"❌ **Error:** {str(e)}")
            )

    async def handle_pause(self, event):
        """Handle /pause command"""
        if not await self.has_music_access(event):
            return

        if not await self.check_music_available(event):
            return

        result = await self.music_manager.pause(event.chat_id)
        await event.reply(self.format_message(result, include_footer=False))

    async def handle_resume(self, event):
        """Handle /resume command"""
        if not await self.has_music_access(event):
            return

        if not await self.check_music_available(event):
            return

        result = await self.music_manager.resume(event.chat_id)
        await event.reply(self.format_message(result, include_footer=False))

    async def handle_skip(self, event):
        """Handle /skip command"""
        if not await self.has_music_access(event):
            return

        if not await self.check_music_available(event):
            return

        result = await self.music_manager.skip(event.chat_id)
        await event.reply(self.format_message(result, include_footer=False))

    async def handle_stop(self, event):
        """Handle /stop command"""
        if not await self.has_music_access(event):
            return

        if not await self.check_music_available(event):
            return

        result = await self.music_manager.stop(event.chat_id)
        await event.reply(self.format_message(result, include_footer=False))

    async def handle_queue(self, event):
        """Handle /queue command"""
        if not await self.has_music_access(event):
            return

        if not await self.check_music_available(event):
            return

        result = await self.music_manager.show_queue(event.chat_id)
        await event.reply(self.format_message(result, include_footer=False))

    async def handle_shuffle(self, event):
        """Handle /shuffle command"""
        if not await self.has_music_access(event):
            return

        if not await self.check_music_available(event):
            return

        result = await self.music_manager.shuffle(event.chat_id)
        await event.reply(self.format_message(result, include_footer=False))

    async def handle_loop(self, event):
        """Handle /loop command"""
        if not await self.has_music_access(event):
            return

        if not await self.check_music_available(event):
            return

        # Parse mode
        text = event.message.text.strip()
        parts = text.split(maxsplit=1)
        mode = parts[1] if len(parts) > 1 else 'toggle'

        result = await self.music_manager.set_loop(event.chat_id, mode)
        await event.reply(self.format_message(result, include_footer=False))

    async def handle_callback(self, event):
        """Handle inline button callbacks"""
        data = event.data.decode()
        user_id = event.sender_id
        chat_id = event.chat_id

        # Check permission for inline controls
        if not await self.has_music_access(event):
            await event.answer(
                "❌ Hanya developer/owner atau admin grup yang bisa menggunakan kontrol musik",
        # Check developer
        if not self.is_developer(user_id):
            await event.answer(
                "❌ Hanya developer atau owner yang bisa menggunakan kontrol musik",
                alert=True
            )
            return

        if data == "music_pause":
            result = await self.music_manager.pause(chat_id)
            await event.answer(result)
        elif data == "music_skip":
            result = await self.music_manager.skip(chat_id)
            await event.answer("⏭️ Skipped")
        elif data == "music_stop":
            result = await self.music_manager.stop(chat_id)
            await event.answer("⏹️ Stopped")
            try:
                await event.edit(self.format_message("⏹️ Stopped", include_footer=False))
            except:
                pass
        elif data == "music_queue":
            result = await self.music_manager.show_queue(chat_id)
            await event.answer(result[:200], alert=True)
        elif data == "music_shuffle":
            result = await self.music_manager.shuffle(chat_id)
            await event.answer(result)
        elif data == "music_loop":
            result = await self.music_manager.set_loop(chat_id, 'toggle')
            await event.answer(result)


def setup(bot):
    """Setup music plugin"""
    bot_client = getattr(bot, "client", bot)
    if bot_client is None:
        logger.warning("Music plugin skipped: bot has no client instance")
        return

    handler = MusicPlayer(bot)

    # Check which commands are already handled
    play_enabled = not bot.plugin_loader.handles_command("/play")
    vplay_enabled = not bot.plugin_loader.handles_command("/vplay")
    pause_enabled = not bot.plugin_loader.handles_command("/pause")
    resume_enabled = not bot.plugin_loader.handles_command("/resume")
    skip_enabled = not bot.plugin_loader.handles_command("/skip")
    stop_enabled = not bot.plugin_loader.handles_command("/stop")
    queue_enabled = not bot.plugin_loader.handles_command("/queue")
    shuffle_enabled = not bot.plugin_loader.handles_command("/shuffle")
    loop_enabled = not bot.plugin_loader.handles_command("/loop")

    # Register handlers
    if play_enabled:
        @bot_client.on(events.NewMessage(pattern=r'^/play(@\\S+)?(\\s|$)'))
        async def handle_play_cmd(event):
            await handler.handle_play(event, audio_only=True)
    else:
        HANDLED_COMMANDS.discard("/play")
        logger.info("Skipping /play; already handled")

    if vplay_enabled:
        @bot_client.on(events.NewMessage(pattern=r'^/vplay(@\\S+)?(\\s|$)'))
        async def handle_vplay_cmd(event):
            await handler.handle_play(event, audio_only=False)
    else:
        HANDLED_COMMANDS.discard("/vplay")
        logger.info("Skipping /vplay; already handled")

    if pause_enabled:
        @bot_client.on(events.NewMessage(pattern=r'^/pause$'))
        async def handle_pause_cmd(event):
            await handler.handle_pause(event)
    else:
        HANDLED_COMMANDS.discard("/pause")

    if resume_enabled:
        @bot_client.on(events.NewMessage(pattern=r'^/resume$'))
        async def handle_resume_cmd(event):
            await handler.handle_resume(event)
    else:
        HANDLED_COMMANDS.discard("/resume")

    if skip_enabled:
        @bot_client.on(events.NewMessage(pattern=r'^/skip$'))
        async def handle_skip_cmd(event):
            await handler.handle_skip(event)
    else:
        HANDLED_COMMANDS.discard("/skip")

    if stop_enabled:
        @bot_client.on(events.NewMessage(pattern=r'^/stop$'))
        async def handle_stop_cmd(event):
            await handler.handle_stop(event)
    else:
        HANDLED_COMMANDS.discard("/stop")

    if queue_enabled:
        @bot_client.on(events.NewMessage(pattern=r'^/queue$'))
        async def handle_queue_cmd(event):
            await handler.handle_queue(event)
    else:
        HANDLED_COMMANDS.discard("/queue")

    if shuffle_enabled:
        @bot_client.on(events.NewMessage(pattern=r'^/shuffle$'))
        async def handle_shuffle_cmd(event):
            await handler.handle_shuffle(event)
    else:
        HANDLED_COMMANDS.discard("/shuffle")

    if loop_enabled:
        @bot_client.on(events.NewMessage(pattern=r'^/loop(@\\S+)?(\\s|$)'))
        async def handle_loop_cmd(event):
            await handler.handle_loop(event)
    else:
        HANDLED_COMMANDS.discard("/loop")

    # Callback handler for inline buttons
    @bot_client.on(events.CallbackQuery(pattern=b"^music_"))
    async def handle_music_callback(event):
        await handler.handle_callback(event)

    # Export handler
    setattr(bot, "music_player_handler", handler)
    if bot_client is not bot:
        setattr(bot_client, "music_player_handler", handler)

    logger.info("✅ Music plugin loaded (developer/owner + group admin access)")
