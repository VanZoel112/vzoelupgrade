"""
VBot Ping Plugin - Check bot responsiveness
Available to all users with / prefix

Author: Vzoel Fox's
"""

import logging
from datetime import datetime, timezone
from telethon import events

logger = logging.getLogger(__name__)


class PingHandler:
    """Handle ping command for all users"""

    def __init__(self, bot):
        self.bot = bot
        self.client = getattr(bot, "client", None)
        self.branding = None
        self.plugin_name = "Ping"

        # Try to import branding
        try:
            from core.branding import VBotBranding
            self.branding = VBotBranding
        except ImportError:
            logger.warning("VBotBranding not available, using simple format")

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

    async def handle_ping(self, event):
        """
        Handle /ping command
        Shows: latency, processing time, uptime
        Available to all users
        """
        try:
            # Get command context if available
            message_id = getattr(event.message, "id", None)
            command_status = None
            if hasattr(self.bot, "_command_context") and message_id is not None:
                command_status = self.bot._command_context.get(message_id)

            # Get status message if exists
            status_message = None
            if command_status:
                status_message = command_status.status_message

            # Calculate latency
            now = datetime.now(timezone.utc)
            message_time = event.message.date
            if isinstance(message_time, datetime) and message_time.tzinfo is None:
                message_time = message_time.replace(tzinfo=timezone.utc)

            latency_ms = (now - message_time).total_seconds() * 1000

            # Calculate processing time
            processing_ms = None
            if command_status and isinstance(command_status.start_time, datetime):
                processing_ms = (datetime.now() - command_status.start_time).total_seconds() * 1000

            # Calculate uptime
            uptime_text = "Unknown"
            if hasattr(self.bot, "start_time") and isinstance(self.bot.start_time, datetime):
                uptime_text = self._format_timedelta(now - self.bot.start_time)

            # Build response
            result_lines = [
                "🏓 **Pong!**",
                f"**Latency:** `{latency_ms:.2f} ms`",
            ]

            if processing_ms is not None:
                result_lines.append(f"**Processing:** `{processing_ms:.2f} ms`")

            result_lines.append(f"**Uptime:** `{uptime_text}`")

            # Format with branding if available
            if self.branding:
                result_text = self.branding.wrap_message(
                    "\n".join(result_lines),
                    include_footer=False,
                    plugin_name=self.plugin_name,
                )
            else:
                result_text = "\n".join(result_lines)
                result_text += "\n\n📱 VBot Python"

            # Update status message or reply
            if status_message:
                try:
                    await status_message.edit(result_text)
                    return
                except Exception as edit_error:
                    logger.debug(f"Failed to update ping status message: {edit_error}")

            await event.reply(result_text)

        except Exception as e:
            logger.error(f"Error in ping handler: {e}", exc_info=True)
            await event.reply(f"❌ **Ping failed:** {str(e)}")


def setup(bot):
    """Setup ping plugin"""
    bot_client = getattr(bot, "client", bot)
    if bot_client is None:
        logger.warning("Ping plugin skipped: bot has no client instance")
        return

    handler = PingHandler(bot)

    @bot_client.on(events.NewMessage(pattern=r'^/ping$'))
    async def handle_ping_command(event):
        """Handle /ping command - available to all users"""
        await handler.handle_ping(event)

    # Export handler for reference
    setattr(bot, "ping_handler", handler)
    if bot_client is not bot:
        setattr(bot_client, "ping_handler", handler)

    logger.info("✅ Ping plugin loaded")
