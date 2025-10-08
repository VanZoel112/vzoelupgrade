"""Media tools plugin for handling file IDs and logo management."""

from telethon import events
import config
from core.branding import VBotBranding
from pathlib import Path


@events.register(events.NewMessage(pattern=r'^[/\.\+]getfileid$'))
async def get_file_id_handler(event):
    """Get file_id from replied media - /getfileid"""

    if not event.out:
        return

    # Check if replying to a message
    if not event.reply_to_msg_id:
        await event.reply(
            VBotBranding.format_error(
                "❌ **Reply ke media** untuk mendapatkan file_id!\n\n"
                "**Usage:** Reply ke foto/video/file dengan `/getfileid`"
            )
        )
        return

    try:
        replied_msg = await event.get_reply_message()

        if not replied_msg.media:
            await event.reply(
                VBotBranding.format_error(
                    "❌ Pesan yang di-reply tidak mengandung media!"
                )
            )
            return

        # Get file information
        media = replied_msg.media
        file_info = []
        file_id_full = None

        # Get file_id based on media type
        if hasattr(media, 'photo'):
            photo = media.photo
            media_type = "Photo"

            # Get full file identifier
            file_id_full = {
                "id": str(photo.id),
                "access_hash": str(photo.access_hash),
                "file_reference": photo.file_reference.hex() if photo.file_reference else "",
                "chat_id": str(replied_msg.chat_id)
            }

            file_info.append(f"**Type:** {media_type}")
            file_info.append(f"**Photo ID:** `{photo.id}`")
            file_info.append(f"**Access Hash:** `{photo.access_hash}`")
            file_info.append(f"**Chat ID:** `{replied_msg.chat_id}`")
            file_info.append(f"**File Reference:** `{file_id_full['file_reference'][:40]}...`")
            file_info.append(f"**Sizes:** {len(photo.sizes)} available")

        elif hasattr(media, 'document'):
            doc = media.document
            media_type = getattr(doc, 'mime_type', 'Unknown')
            file_size = doc.size

            # Get full file identifier
            file_id_full = {
                "id": str(doc.id),
                "access_hash": str(doc.access_hash),
                "file_reference": doc.file_reference.hex() if doc.file_reference else "",
                "chat_id": str(replied_msg.chat_id)
            }

            file_info.append(f"**Type:** Document ({media_type})")
            file_info.append(f"**Document ID:** `{doc.id}`")
            file_info.append(f"**Access Hash:** `{doc.access_hash}`")
            file_info.append(f"**Chat ID:** `{replied_msg.chat_id}`")
            file_info.append(f"**File Reference:** `{file_id_full['file_reference'][:40]}...`")
            file_info.append(f"**Size:** {file_size / (1024*1024):.2f} MB")

            # Get filename if available
            for attr in doc.attributes:
                if hasattr(attr, 'file_name'):
                    file_info.append(f"**Filename:** {attr.file_name}")

        else:
            # For other media types
            file_info.append(f"**Type:** {type(media).__name__}")
            file_info.append("**Note:** File ID extraction may vary for this media type")

        # Construct response with file_id info
        if file_id_full:
            # Create compact file_id string (untuk setlogo)
            compact_id = f"{file_id_full['id']}:{file_id_full['access_hash']}:{file_id_full['chat_id']}"

            response = f"""
**📎 Media File Information**

{chr(10).join(file_info)}

**📋 File ID (untuk setlogo):**
`{compact_id}`

**💡 Cara Menggunakan:**
1. `/setlogo {compact_id}`
2. Atau reply foto ini: `/setlogo`

**🔍 Full JSON Format:**
```json
{{
  "id": "{file_id_full['id']}",
  "access_hash": "{file_id_full['access_hash']}",
  "file_reference": "{file_id_full['file_reference']}",
  "chat_id": "{file_id_full['chat_id']}"
}}
```
"""
        else:
            response = f"""
**📎 Media File Information**

{chr(10).join(file_info)}

**⚠️ Note:** Untuk music logo, sebaiknya gunakan foto/image
"""

        await event.reply(
            VBotBranding.wrap_message(response, plugin_name="Media Tools")
        )

    except Exception as e:
        await event.reply(
            VBotBranding.format_error(f"Error getting file info: {str(e)}")
        )


@events.register(events.NewMessage(pattern=r'^[/\.\+]setlogo(?:\s+(.+))?$'))
async def set_logo_handler(event):
    """Set music logo - /setlogo [file_id] or reply to photo"""

    if not event.out:
        return

    try:
        bot_instance = event.client._bot_instance
        match = event.pattern_match
        file_id_arg = match.group(1).strip() if match.group(1) else None

        # Handle reset
        if file_id_arg and file_id_arg.lower() == "reset":
            bot_instance._music_logo_file_id = None
            bot_instance._music_logo_file_path = None

            await event.reply(
                VBotBranding.wrap_message(
                    "✅ **Music logo direset!**\n\n"
                    "Logo akan menggunakan default dari config.",
                    plugin_name="Logo Manager"
                )
            )
            return

        # Get file_id from argument or replied message
        new_file_id = None
        new_file_reference = None
        new_chat_id = None

        if file_id_arg:
            # File ID provided as argument (format: id:access_hash:chat_id)
            new_file_id = file_id_arg

        elif event.reply_to_msg_id:
            # File ID from replied photo/media
            replied_msg = await event.get_reply_message()

            if not replied_msg.media:
                await event.reply(
                    VBotBranding.format_error(
                        "❌ **Reply ke foto/media** atau berikan file_id!\n\n"
                        "**Usage:**\n"
                        "• Reply foto: `/setlogo`\n"
                        "• Dengan ID: `/setlogo <file_id>`"
                    )
                )
                return

            # Get file info from media
            media = replied_msg.media
            new_chat_id = str(replied_msg.chat_id)

            if hasattr(media, 'photo'):
                photo = media.photo
                new_file_id = f"{photo.id}:{photo.access_hash}:{new_chat_id}"
                new_file_reference = photo.file_reference.hex() if photo.file_reference else ""

            elif hasattr(media, 'document'):
                doc = media.document
                new_file_id = f"{doc.id}:{doc.access_hash}:{new_chat_id}"
                new_file_reference = doc.file_reference.hex() if doc.file_reference else ""

            else:
                await event.reply(
                    VBotBranding.format_error(
                        "❌ Media type tidak didukung!\n\n"
                        "Gunakan foto atau dokumen."
                    )
                )
                return

        else:
            await event.reply(
                VBotBranding.format_error(
                    "❌ **Berikan file_id atau reply ke foto!**\n\n"
                    "**Usage:**\n"
                    "• Reply foto: `/setlogo`\n"
                    "• Dengan ID: `/setlogo <file_id>`\n"
                    "• Reset: `/setlogo reset`\n\n"
                    "**Cara Mendapatkan File ID:**\n"
                    "1. Upload foto logo\n"
                    "2. Reply foto dengan `/getfileid`\n"
                    "3. Copy file_id yang muncul\n"
                    "4. Gunakan `/setlogo <file_id>`"
                )
            )
            return

        # Update bot instance with new file_id
        bot_instance._music_logo_file_id = new_file_id
        if new_file_reference:
            bot_instance._music_logo_file_reference = new_file_reference
        if new_chat_id:
            bot_instance._music_logo_chat_id = new_chat_id

        # Also update .env file for persistence
        env_path = Path(__file__).parent.parent / ".env"

        if env_path.exists():
            content = env_path.read_text(encoding='utf-8')
            lines = content.splitlines()

            # Find and update MUSIC_LOGO_FILE_ID line
            updated = False
            for i, line in enumerate(lines):
                if line.startswith("MUSIC_LOGO_FILE_ID="):
                    lines[i] = f"MUSIC_LOGO_FILE_ID={new_file_id}"
                    updated = True
                    break

            # If not found, append it
            if not updated:
                lines.append(f"MUSIC_LOGO_FILE_ID={new_file_id}")

            # Write back
            env_path.write_text('\n'.join(lines) + '\n', encoding='utf-8')

            file_id_display = new_file_id if len(new_file_id) <= 60 else f"{new_file_id[:60]}..."

            await event.reply(
                VBotBranding.wrap_message(
                    f"✅ **Music logo berhasil diupdate!**\n\n"
                    f"**New File ID:**\n`{file_id_display}`\n\n"
                    f"✅ File `.env` sudah diupdate\n"
                    f"✅ Bot instance sudah diupdate\n\n"
                    f"**Test dengan:** `/testlogo`",
                    plugin_name="Logo Manager"
                )
            )
        else:
            # Just update bot instance if .env not found
            file_id_display = new_file_id if len(new_file_id) <= 60 else f"{new_file_id[:60]}..."

            await event.reply(
                VBotBranding.wrap_message(
                    f"✅ **Music logo diupdate di bot instance!**\n\n"
                    f"**New File ID:**\n`{file_id_display}`\n\n"
                    f"⚠️ File `.env` tidak ditemukan, update hanya temporary.\n"
                    f"**Untuk permanent:** Edit `.env` secara manual.",
                    plugin_name="Logo Manager"
                )
            )

    except Exception as e:
        await event.reply(
            VBotBranding.format_error(f"Error setting logo: {str(e)}")
        )


def setup(bot):
    """Setup media tools plugin."""
    bot.client.add_event_handler(get_file_id_handler)
    bot.client.add_event_handler(set_logo_handler)

    # Initialize music logo attributes if not present
    if not hasattr(bot, '_music_logo_file_id'):
        bot._music_logo_file_id = config.MUSIC_LOGO_FILE_ID
    if not hasattr(bot, '_music_logo_file_path'):
        bot._music_logo_file_path = config.MUSIC_LOGO_FILE_PATH
    if not hasattr(bot, '_music_logo_file_reference'):
        bot._music_logo_file_reference = getattr(config, 'MUSIC_LOGO_FILE_REFERENCE', '')
    if not hasattr(bot, '_music_logo_chat_id'):
        bot._music_logo_chat_id = getattr(config, 'MUSIC_LOGO_CHAT_ID', '')

    print("✅ Media Tools plugin loaded (getfileid, setlogo)")
