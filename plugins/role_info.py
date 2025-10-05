"""Role Information and Management Plugin"""

from telethon import events
from core.branding import VBotBranding
import config


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

    if not event.out:
        return

    try:
        bot_instance = event.client._bot_instance
        auth_manager = bot_instance.auth_manager

        user_id = event.sender_id
        chat_id = event.chat_id

        # Get user role
        role = await auth_manager.get_user_role(event.client, user_id, chat_id)
        permissions = auth_manager.get_role_permissions(role)

        # Get user display name
        user_name = await get_user_display_name(event.client, user_id)

        # Role emoji mapping
        role_emoji = {
            "founder": "🔱",
            "owner": "👑",
            "user": "👤"
        }

        # Check if user is admin in this group (for display purposes)
        is_group_admin = await auth_manager.is_admin_in_chat(event.client, user_id, chat_id)
        admin_status = ""
        if role == "user" and is_group_admin:
            admin_status = "\n⚡ **Admin Group:** Ya (dapat akses admin command di group ini)"

        # Build role info
        role_text = f"""
**Role Information**

{role_emoji.get(role, '👤')} **Role:** {role.upper()}
👤 **User:** {user_name}
🆔 **User ID:** `{user_id}`
💬 **Chat ID:** `{chat_id}`{admin_status}

**Permissions:**
├ Owner Commands: {'✅' if permissions['owner_commands'] else '❌'}
├ Admin Commands: {'✅' if permissions['admin_commands'] or is_group_admin else '❌'}
├ Public Commands: {'✅' if permissions['public_commands'] else '❌'}
└ Bypass All Checks: {'✅' if permissions['bypass_all'] else '❌'}

**Description:**
{permissions['description']}

**Available Commands:**
"""

        if role in ['founder', 'owner']:
            role_text += "\n**Owner Commands:** (`+` prefix)\n"
            role_text += "├ +add - Add user permission\n"
            role_text += "├ +del - Remove user permission\n"
            role_text += "├ +setwelcome - Set welcome message\n"
            role_text += "├ +backup - Backup database\n"
            role_text += "├ +setlogo - Set music logo\n"
            role_text += "└ +getfileid - Get file ID\n"

        if role in ['founder', 'owner'] or is_group_admin:
            role_text += "\n**Admin Commands:** (`/` prefix)\n"
            role_text += "├ /pm - Promote to admin\n"
            role_text += "├ /dm - Demote from admin\n"
            role_text += "├ /lock - Lock user messages\n"
            role_text += "├ /unlock - Unlock user\n"
            role_text += "├ /t - Tag all members\n"
            role_text += "└ /c - Cancel tag\n"

        role_text += "\n**Public Commands:** (`.` prefix)\n"
        role_text += "├ .role - Show this info\n"
        role_text += "├ .ping - Check bot latency\n"
        role_text += "├ /play - Play music\n"
        role_text += "└ /vplay - Play video\n"

        await event.reply(
            VBotBranding.wrap_message(role_text, plugin_name="Role Info")
        )

    except Exception as e:
        await event.reply(VBotBranding.format_error(f"Error getting role: {e}"))


@events.register(events.NewMessage(pattern=r'^[/\.\+]refreshrole$'))
async def refresh_role_handler(event):
    """Refresh role cache - /refreshrole"""

    if not event.out:
        return

    try:
        bot_instance = event.client._bot_instance
        auth_manager = bot_instance.auth_manager

        user_id = event.sender_id
        chat_id = event.chat_id

        # Clear cache for current user in current chat
        auth_manager.clear_role_cache(user_id, chat_id)

        # Re-detect role
        new_role = await auth_manager.get_user_role(event.client, user_id, chat_id)

        await event.reply(
            VBotBranding.wrap_message(
                f"**Role Cache Refreshed**\n\n"
                f"✅ Cache cleared for user {user_id} in chat {chat_id}\n"
                f"🔄 New role detected: **{new_role.upper()}**\n\n"
                f"Your permissions have been updated based on current admin status.",
                plugin_name="Role Info"
            )
        )

    except Exception as e:
        await event.reply(VBotBranding.format_error(f"Error refreshing role: {e}"))


@events.register(events.NewMessage(pattern=r'^[/\.\+]listdevs?$'))
async def list_devs_handler(event):
    """List developers and owner - /listdevs or .listdevs"""

    if not event.out:
        return

    try:
        bot_instance = event.client._bot_instance
        auth_manager = bot_instance.auth_manager

        # Get owner
        owner_id = auth_manager.owner_id
        owner_name = await get_user_display_name(event.client, owner_id) if owner_id else "Not set"

        # Get founders (developers)
        founder_ids = list(auth_manager.developer_ids)
        founder_names = []
        for founder_id in founder_ids:
            founder_name = await get_user_display_name(event.client, founder_id)
            founder_names.append(f"• {founder_name} (`{founder_id}`)")

        founder_list = "\n".join(founder_names) if founder_names else "No founders configured"

        info_text = f"""
**Bot Administrators**

👑 **Owner:**
{owner_name} (`{owner_id}`)

🔱 **Founders:** ({len(founder_ids)} total)
{founder_list}

**Privileges:**
• Akses penuh ke semua command dimanapun
• Bypass semua permission checks
• Dapat manage konfigurasi bot
• Auto-granted admin rights di semua group
• Role "Founder" di group dan private chat
"""

        await event.reply(
            VBotBranding.wrap_message(info_text, plugin_name="Role Info")
        )

    except Exception as e:
        await event.reply(VBotBranding.format_error(f"Error listing developers: {e}"))


@events.register(events.NewMessage(pattern=r'^[/\+]clearcache(?:\s+(all|chat|user))?$'))
async def clear_cache_handler(event):
    """Clear role cache - /clearcache [all|chat|user] (Founder only)"""

    if not event.out:
        return

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
            message = "✅ Cleared all role cache (all users, all chats)"
        elif scope == "chat":
            auth_manager.clear_role_cache(chat_id=event.chat_id)
            message = f"✅ Cleared role cache for chat {event.chat_id}"
        elif scope == "user":
            auth_manager.clear_role_cache(user_id=event.sender_id)
            message = f"✅ Cleared role cache for user {event.sender_id}"
        else:
            await event.reply(VBotBranding.format_error("Invalid scope. Use: all, chat, or user"))
            return

        await event.reply(
            VBotBranding.wrap_message(
                f"**Cache Cleared**\n\n{message}\n\n"
                f"Role detection will be refreshed on next command.",
                plugin_name="Role Management"
            )
        )

    except Exception as e:
        await event.reply(VBotBranding.format_error(f"Error clearing cache: {e}"))


def setup(bot):
    """Setup role info plugin."""
    bot.client.add_event_handler(role_info_handler)
    bot.client.add_event_handler(refresh_role_handler)
    bot.client.add_event_handler(list_devs_handler)
    bot.client.add_event_handler(clear_cache_handler)
    print("✅ Role Info plugin loaded")
