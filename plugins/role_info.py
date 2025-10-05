"""Role Information and Management Plugin"""

from __future__ import annotations

import logging
from typing import List, Optional, Tuple

from telethon import Button, events
from telethon.errors import MessageNotModifiedError

from core.branding import VBotBranding


logger = logging.getLogger(__name__)


class RolePanel:
    """Helper to build inline role panels with toggle support."""

    def __init__(self, bot_instance):
        self.bot = bot_instance
        self.auth_manager = bot_instance.auth_manager
        self._cached_bot_username: Optional[str] = None

    async def send_panel(self, event, *, view: str = "info") -> None:
        """Reply with the requested role panel view."""

        user_id = event.sender_id
        chat_id = event.chat_id
        if user_id is None or chat_id is None:
            return

        panel_text, buttons, _ = await self.build_panel(
            event.client, user_id, chat_id, view=view
        )

        await event.reply(
            VBotBranding.wrap_message(panel_text, plugin_name="Role Info"),
            buttons=buttons,
        )

    async def build_panel(
        self,
        client,
        user_id: int,
        chat_id: int,
        *,
        view: str = "info",
    ) -> Tuple[str, List[List[Button]], str]:
        """Build the requested panel view, returning text, buttons and active view."""

        context = await self._gather_context(client, user_id, chat_id)
        normalized_view = view if view in {"info", "commands", "links"} else "info"

        if normalized_view == "commands":
            panel_text = self._format_commands_view(context)
        elif normalized_view == "links":
            panel_text = self._format_links_view(context)
        else:
            panel_text = self._format_info_view(context)
            normalized_view = "info"

        buttons = self._build_keyboard(
            user_id,
            chat_id,
            normalized_view,
            context.get("bot_username", ""),
        )

        return panel_text, buttons, normalized_view

    async def handle_callback(self, event, data: str) -> bool:
        """Process inline callback interactions for the role panel."""

        try:
            parts = data.split(":")
            if len(parts) < 2 or parts[0] != "role":
                return False

            action = parts[1]

            if action == "view" and len(parts) >= 5:
                view = parts[2]
                try:
                    target_user = int(parts[3])
                    target_chat = int(parts[4])
                except ValueError:
                    return False

                if event.sender_id != target_user:
                    await event.answer(
                        "Panel ini hanya bisa digunakan oleh pengguna yang membukanya.",
                        alert=True,
                    )
                    return True

                if event.chat_id != target_chat:
                    await event.answer(
                        "Panel role ini tidak berlaku di chat berbeda.",
                        alert=True,
                    )
                    return True

                panel_text, buttons, active_view = await self.build_panel(
                    event.client, target_user, target_chat, view=view
                )

                await self._edit_panel(event, panel_text, buttons)
                if active_view != view:
                    await event.answer("Berpindah ke tampilan role info.")
                return True

            if action == "refresh" and len(parts) >= 4:
                try:
                    target_user = int(parts[2])
                    target_chat = int(parts[3])
                except ValueError:
                    return False

                if event.sender_id != target_user:
                    await event.answer(
                        "Hanya pengguna pemilik panel yang dapat me-refresh role.",
                        alert=True,
                    )
                    return True

                if event.chat_id != target_chat:
                    await event.answer(
                        "Panel role ini tidak berlaku di chat berbeda.",
                        alert=True,
                    )
                    return True

                self.auth_manager.clear_role_cache(target_user, target_chat)
                panel_text, buttons, _ = await self.build_panel(
                    event.client, target_user, target_chat, view="info"
                )

                await self._edit_panel(event, panel_text, buttons)
                await event.answer("Role diperbarui dari cache.")
                return True

        except MessageNotModifiedError:
            return True
        except Exception as error:
            logger.error("Error handling role panel callback: %s", error, exc_info=True)
            await event.answer("Gagal memproses aksi role.", alert=True)
            return True

        return False

    async def _gather_context(self, client, user_id: int, chat_id: int) -> dict:
        role = await self.auth_manager.get_user_role(client, user_id, chat_id)
        permissions = self.auth_manager.get_role_permissions(role)
        is_group_admin = await self.auth_manager.is_admin_in_chat(
            client, user_id, chat_id
        )
        user_name = await get_user_display_name(client, user_id)
        bot_username = await self._ensure_bot_username(client)

        return {
            "user_id": user_id,
            "chat_id": chat_id,
            "role": role,
            "permissions": permissions,
            "is_group_admin": is_group_admin,
            "user_name": user_name,
            "bot_username": bot_username,
        }

    async def _ensure_bot_username(self, client) -> str:
        if self._cached_bot_username is not None:
            return self._cached_bot_username

        try:
            me = await client.get_me()
            self._cached_bot_username = me.username or ""
        except Exception as error:
            logger.debug("Failed to fetch bot username: %s", error)
            self._cached_bot_username = ""

        return self._cached_bot_username

    def _format_info_view(self, context: dict) -> str:
        role = context["role"]
        permissions = context["permissions"]
        user_name = context["user_name"]
        user_id = context["user_id"]
        chat_id = context["chat_id"]
        is_group_admin = context["is_group_admin"]

        role_emoji = {
            "founder": "🔱",
            "orang_dalam": "👑",
            "user": "💎",
        }

        admin_status = ""
        if role == "user" and is_group_admin:
            admin_status = (
                "\nAdmin Group: Ya (dapat akses admin command di group ini)"
            )

        role_marker = role_emoji.get(role, "")
        role_line = f"{role_marker} **Role:** {role.upper()}" if role_marker else f"**Role:** {role.upper()}"

        info_lines = [
            "**Role Information**",
            "",
            role_line,
            f"User: {user_name}",
            f"User ID: `{user_id}`",
            f"Chat ID: `{chat_id}`{admin_status}",
            "",
            "**Permissions:**",
            f"├ Owner Commands: {'Yes' if permissions['owner_commands'] else 'No'}",
            "├ Admin Commands: "
            f"{'Yes' if permissions['admin_commands'] or is_group_admin else 'No'}",
            f"├ Public Commands: {'Yes' if permissions['public_commands'] else 'No'}",
            f"└ Bypass All Checks: {'Yes' if permissions['bypass_all'] else 'No'}",
            "",
            "**Description:**",
            permissions.get("description", "Tidak ada deskripsi."),
            "",
            "Gunakan tombol di bawah untuk melihat daftar command atau link panel.",
        ]

        return "\n".join(info_lines)

    def _format_commands_view(self, context: dict) -> str:
        role = context["role"]
        is_group_admin = context["is_group_admin"]

        lines = [
            "**Role Command Reference**",
            "",
            f"Aktif sebagai: **{role.upper()}**",
            "",
        ]

        if role in ["founder", "orang_dalam"]:
            lines.extend(
                [
                    "**Owner Commands** (`+` prefix)",
                    "├ +add - Add user permission",
                    "├ +del - Remove user permission",
                    "├ +setwelcome - Set welcome message",
                    "├ +backup - Backup database",
                    "├ +setlogo - Set music logo",
                    "└ +getfileid - Get file ID",
                    "",
                ]
            )

        if role in ["founder", "orang_dalam"] or is_group_admin:
            lines.extend(
                [
                    "**Admin Commands** (`/` prefix)",
                    "├ /pm - Promote to admin",
                    "├ /dm - Demote from admin",
                    "├ /lock - Lock user messages",
                    "├ /unlock - Unlock user",
                    "├ /t - Tag all members",
                    "└ /c - Cancel tag",
                    "",
                ]
            )

        lines.extend(
            [
                "**Public Commands** (`.` prefix)",
                "├ .role - Show this info",
                "├ .ping - Check bot latency",
                "├ /play - Play music",
                "└ /vplay - Play video",
            ]
        )

        return "\n".join(lines)

    def _format_links_view(self, context: dict) -> str:
        bot_username = context.get("bot_username", "")

        if bot_username:
            panel_link = f"https://t.me/{bot_username}?start=rolepanel"
            link_line = (
                f"Panel Private: [t.me/{bot_username}?start=rolepanel]({panel_link})"
            )
        else:
            link_line = (
                "Panel Private: Bot tidak memiliki username publik untuk link."
            )

        lines = [
            "**Role Quick Access**",
            "",
            "Gunakan opsi berikut untuk membuka panel role atau men-trigger plugin:",
            "",
            link_line,
            "",
            "Command Trigger:",
            "• `.role` - Tampilkan info role di chat ini",
            "• `/refreshrole` - Paksa deteksi ulang role",
            "• `/listdevs` - Daftar developer & owner",
            "",
            "Tips: gunakan tombol `Refresh Role` untuk membersihkan cache secara instan.",
        ]

        return "\n".join(lines)

    def _build_keyboard(
        self,
        user_id: int,
        chat_id: int,
        active_view: str,
        bot_username: str,
    ) -> List[List[Button]]:
        def view_label(base: str, view_name: str) -> str:
            return f"{base} (aktif)" if active_view == view_name else base

        buttons: List[List[Button]] = [
            [
                Button.inline(
                    view_label("Info", "info"),
                    f"role:view:info:{user_id}:{chat_id}".encode(),
                ),
                Button.inline(
                    view_label("Commands", "commands"),
                    f"role:view:commands:{user_id}:{chat_id}".encode(),
                ),
                Button.inline(
                    view_label("Links", "links"),
                    f"role:view:links:{user_id}:{chat_id}".encode(),
                ),
            ]
        ]

        buttons.append(
            [
                Button.inline(
                    "Refresh Role",
                    f"role:refresh:{user_id}:{chat_id}".encode(),
                )
            ]
        )

        if active_view == "links" and bot_username:
            panel_link = f"https://t.me/{bot_username}?start=rolepanel"
            buttons.append([Button.url("Buka Panel Role", panel_link)])

        return buttons

    async def _edit_panel(
        self,
        event,
        panel_text: str,
        buttons: List[List[Button]],
    ) -> None:
        wrapped = VBotBranding.wrap_message(panel_text, plugin_name="Role Info")
        try:
            await event.edit(wrapped, buttons=buttons)
        except MessageNotModifiedError:
            raise


async def get_user_display_name(client, user_id: int) -> str:
    """Get user display name."""
    try:
        user = await client.get_entity(user_id)
        if user.username:
            return f"@{user.username}"
        return user.first_name or f"User {user_id}"
    except Exception:
        return f"User {user_id}"


@events.register(events.NewMessage(pattern=r'^[/\.\+](?:role|myrole|whoami)$'))
async def role_info_handler(event):
    """Show current user's role and permissions - /role or .role"""

    try:
        bot_instance = event.client._bot_instance
        role_panel: Optional[RolePanel] = getattr(bot_instance, "role_panel", None)

        if role_panel:
            await role_panel.send_panel(event, view="info")
            return

        # Fallback to basic information if panel manager is not available
        auth_manager = bot_instance.auth_manager

        user_id = event.sender_id
        chat_id = event.chat_id

        role = await auth_manager.get_user_role(event.client, user_id, chat_id)
        permissions = auth_manager.get_role_permissions(role)
        user_name = await get_user_display_name(event.client, user_id)
        is_group_admin = await auth_manager.is_admin_in_chat(event.client, user_id, chat_id)

        role_emoji = {
            "founder": "🔱",
            "orang_dalam": "👑",
            "user": "💎",
        }
        role_marker = role_emoji.get(role, "")
        role_line = f"{role_marker} **Role:** {role.upper()}" if role_marker else f"**Role:** {role.upper()}"

        fallback_text = [
            "**Role Information**",
            "",
            role_line,
            f"User: {user_name}",
            f"User ID: `{user_id}`",
            f"Chat ID: `{chat_id}`",
            "",
            "**Permissions:**",
            f"├ Owner Commands: {'Yes' if permissions['owner_commands'] else 'No'}",
            "├ Admin Commands: "
            f"{'Yes' if permissions['admin_commands'] or is_group_admin else 'No'}",
            f"├ Public Commands: {'Yes' if permissions['public_commands'] else 'No'}",
            f"└ Bypass All Checks: {'Yes' if permissions['bypass_all'] else 'No'}",
        ]

        await event.reply(
            VBotBranding.wrap_message("\n".join(fallback_text), plugin_name="Role Info")
        )

    except Exception as e:
        await event.reply(VBotBranding.format_error(f"Error getting role: {e}"))


@events.register(events.NewMessage(pattern=r'^[/\.\+]refreshrole$'))
async def refresh_role_handler(event):
    """Refresh role cache - /refreshrole"""

    try:
        bot_instance = event.client._bot_instance
        auth_manager = bot_instance.auth_manager

        user_id = event.sender_id
        chat_id = event.chat_id

        # Clear cache for current user in current chat
        auth_manager.clear_role_cache(user_id, chat_id)

        # Re-detect role
        new_role = await auth_manager.get_user_role(event.client, user_id, chat_id)

        role_panel: Optional[RolePanel] = getattr(bot_instance, "role_panel", None)

        refresh_text = (
            f"**Role Cache Refreshed**\n\n"
            f"Cache cleared for user {user_id} in chat {chat_id}\n"
            f"New role detected: **{new_role.upper()}**\n"
        )

        if role_panel:
            panel_text, buttons, _ = await role_panel.build_panel(
                event.client, user_id, chat_id, view="info"
            )
            combined = refresh_text + "\n" + panel_text
            await event.reply(
                VBotBranding.wrap_message(combined, plugin_name="Role Info"),
                buttons=buttons,
            )
        else:
            await event.reply(
                VBotBranding.wrap_message(
                    refresh_text
                    + "\nGunakan `.role` untuk melihat informasi lengkap.",
                    plugin_name="Role Info",
                )
            )

    except Exception as e:
        await event.reply(VBotBranding.format_error(f"Error refreshing role: {e}"))


@events.register(events.NewMessage(pattern=r'^[/\.\+]listdevs?$'))
async def list_devs_handler(event):
    """List developers and owner - /listdevs or .listdevs"""

    try:
        bot_instance = event.client._bot_instance
        auth_manager = bot_instance.auth_manager

        # Get Orang Dalam (owner)
        orang_dalam_id = auth_manager.owner_id
        orang_dalam_name = (
            await get_user_display_name(event.client, orang_dalam_id)
            if orang_dalam_id
            else "Not set"
        )

        # Get founders (developers)
        founder_ids = list(auth_manager.developer_ids)
        founder_names = []
        for founder_id in founder_ids:
            founder_name = await get_user_display_name(event.client, founder_id)
            founder_names.append(f"• {founder_name} (`{founder_id}`)")

        founder_list = "\n".join(founder_names) if founder_names else "No founders configured"

        info_text = f"""
**Bot Administrators**

👑 **Owner (Orang Dalam):**
{orang_dalam_name} (`{orang_dalam_id}`)

🔱 **Founders:** ({len(founder_ids)} total)
{founder_list}

**Privileges:**
• Akses penuh ke semua command dimanapun
• Bypass semua permission checks
• Dapat manage konfigurasi bot
• Auto-granted admin rights di semua group
• Role "Founder" & "Orang Dalam" di group dan private chat
"""

        await event.reply(
            VBotBranding.wrap_message(info_text, plugin_name="Role Info")
        )

    except Exception as e:
        await event.reply(VBotBranding.format_error(f"Error listing developers: {e}"))


@events.register(events.NewMessage(pattern=r'^[/\+]clearcache(?:\s+(all|chat|user))?$'))
async def clear_cache_handler(event):
    """Clear role cache - /clearcache [all|chat|user] (Founder only)"""

    try:
        bot_instance = event.client._bot_instance
        auth_manager = bot_instance.auth_manager

        # Founder only
        if not auth_manager.is_developer(event.sender_id):
            await event.reply(VBotBranding.format_error("Command ini hanya untuk Founder."))
            return

        # Parse argument
        match = event.pattern_match.group(1)
        scope = match.lower() if match else "chat"

        if scope == "all":
            auth_manager.clear_role_cache()
            message = "Cleared all role cache (all users, all chats)"
        elif scope == "chat":
            auth_manager.clear_role_cache(chat_id=event.chat_id)
            message = f"Cleared role cache for chat {event.chat_id}"
        elif scope == "user":
            auth_manager.clear_role_cache(user_id=event.sender_id)
            message = f"Cleared role cache for user {event.sender_id}"
        else:
            await event.reply(VBotBranding.format_error("Invalid scope. Use: all, chat, or user"))
            return

        await event.reply(
            VBotBranding.wrap_message(
                f"**Cache Cleared**\n\n{message}\n\n",
                f"Role detection will be refreshed on next command.",
                plugin_name="Role Management",
            )
        )

    except Exception as e:
        await event.reply(VBotBranding.format_error(f"Error clearing cache: {e}"))


def setup(bot):
    """Setup role info plugin."""
    bot.client._bot_instance = bot
    bot.role_panel = RolePanel(bot)

    bot.client.add_event_handler(role_info_handler)
    bot.client.add_event_handler(refresh_role_handler)
    bot.client.add_event_handler(list_devs_handler)
    bot.client.add_event_handler(clear_cache_handler)
    print("Role Info plugin loaded")
