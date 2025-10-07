"""
Reload Plugin - Hot reload plugins without restarting bot
Developer only command

Commands:
    /reload - Reload all plugins (developer only)

Author: Vzoel Fox's
"""

import logging
from telethon import events
import config

logger = logging.getLogger(__name__)

HANDLED_COMMANDS = {"/reload"}


class ReloadHandler:
    """Handler for plugin reloading"""

    def __init__(self, bot):
        self.bot = bot
        self.client = getattr(bot, "client", None)
        self.plugin_loader = getattr(bot, "plugin_loader", None)
        self.plugin_name = "Reload"

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
        """Check if user is developer"""
        return user_id in config.DEVELOPER_IDS

    async def handle_reload(self, event):
        """Handle /reload command"""
        user_id = event.sender_id

        # Check developer only
        if not self.is_developer(user_id):
            await event.reply(
                self.format_message(
                    "❌ **Access Denied**\\n\\n"
                    "Reload command hanya untuk developer."
                )
            )
            return

        # Check if plugin loader exists
        if not self.plugin_loader:
            await event.reply(
                self.format_message(
                    "❌ **Plugin loader tidak tersedia**\\n\\n"
                    "Bot harus di-restart manual."
                )
            )
            return

        loading_msg = await event.reply(
            self.format_message(
                "⏳ **Reloading plugins...**",
                include_footer=False
            )
        )

        try:
            # Reload plugins
            reload_method = getattr(self.plugin_loader, 'reload_all_plugins', None)
            if not reload_method:
                # Try alternative method names
                reload_method = getattr(self.plugin_loader, 'reload_plugins', None)
            
            if not reload_method:
                # Fallback: try to reload manually
                await loading_msg.edit(
                    self.format_message(
                        "⚠️ **Reload method tidak ditemukan**\\n\\n"
                        "Silakan restart bot secara manual.",
                        include_footer=False
                    )
                )
                return

            # Call reload
            result = await reload_method()

            # Parse result
            if isinstance(result, dict):
                loaded = result.get('loaded', [])
                failed = result.get('failed', [])
                
                message = "✅ **Plugins Reloaded**\\n\\n"
                
                if loaded:
                    message += f"**Loaded ({len(loaded)}):**\\n"
                    for plugin in loaded[:10]:  # Show max 10
                        message += f"• {plugin}\\n"
                    if len(loaded) > 10:
                        message += f"... and {len(loaded) - 10} more\\n"
                
                if failed:
                    message += f"\\n**Failed ({len(failed)}):**\\n"
                    for plugin, error in failed[:5]:
                        message += f"• {plugin}: {str(error)[:50]}\\n"
                    if len(failed) > 5:
                        message += f"... and {len(failed) - 5} more\\n"
            else:
                message = "✅ **Plugins reloaded successfully!**"

            await loading_msg.edit(
                self.format_message(message, include_footer=False)
            )

            logger.info(f"Plugins reloaded by user {user_id}")

        except Exception as e:
            logger.error(f"Error reloading plugins: {e}", exc_info=True)
            await loading_msg.edit(
                self.format_message(
                    f"❌ **Error reloading plugins**\\n\\n{str(e)}",
                    include_footer=False
                )
            )


def setup(bot):
    """Setup reload plugin"""
    bot_client = getattr(bot, "client", bot)
    if bot_client is None:
        logger.warning("Reload plugin skipped: bot has no client instance")
        return

    handler = ReloadHandler(bot)

    # Check if command already handled
    if bot.plugin_loader.handles_command("/reload"):
        logger.info("Skipping /reload; already handled")
        HANDLED_COMMANDS.discard("/reload")
        return

    # Register handler
    @bot_client.on(events.NewMessage(pattern=r'^/reload$'))
    async def handle_reload_cmd(event):
        await handler.handle_reload(event)

    # Export handler
    setattr(bot, "reload_handler", handler)
    if bot_client is not bot:
        setattr(bot_client, "reload_handler", handler)

    logger.info("✅ Reload plugin loaded (developer only)")
