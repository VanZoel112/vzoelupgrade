"""Logo visibility helper and diagnostic plugin."""

from telethon import events, Button
from pathlib import Path
import config
from core.branding import VBotBranding
from core.branding_assets import VBotBrandingAssets


async def check_logo_status(bot_instance):
    """Check logo configuration status."""
    status = {
        "branding_image": False,
        "music_logo_id": False,
        "music_logo_path": False,
    }

    # Check branding image
    branding_path, _ = VBotBrandingAssets.get_primary_image()
    status["branding_image"] = branding_path is not None and branding_path.exists()

    # Check music logo configuration
    music_id = getattr(bot_instance, '_music_logo_file_id', None) or config.MUSIC_LOGO_FILE_ID
    music_path = getattr(bot_instance, '_music_logo_file_path', None) or config.MUSIC_LOGO_FILE_PATH

    status["music_logo_id"] = bool(music_id)
    status["music_logo_path"] = bool(music_path)

    return status, branding_path, music_id, music_path


@events.register(events.NewMessage(pattern=r'^[/\.\+](?:testlogo|logotest)$'))
async def test_logo_handler(event):
    """Test and display logo status - /testlogo"""

    if not event.out:
        return

    try:
        bot_instance = event.client._bot_instance
        status, branding_path, music_id, music_path = await check_logo_status(bot_instance)

        # Build status report
        status_lines = ["**Logo Configuration Status**\n"]

        status_lines.append(f"**Branding Image:** {'✅ Tersedia' if status['branding_image'] else '❌ Tidak ada'}")
        if branding_path:
            status_lines.append(f"  └ Path: `{branding_path}`")

        status_lines.append(f"\n**Music Logo ID:** {'✅ Configured' if status['music_logo_id'] else '❌ Not set'}")
        if music_id:
            status_lines.append(f"  └ ID: `{music_id[:30]}...`")

        status_lines.append(f"\n**Music Logo Path:** {'✅ Configured' if status['music_logo_path'] else '❌ Not set'}")
        if music_path:
            status_lines.append(f"  └ Path: `{music_path}`")

        # Instructions
        status_lines.append("\n\n**Cara Memperbaiki:**")
        status_lines.append("1. Upload foto logo ke chat ini")
        status_lines.append("2. Reply foto dengan `/getfileid`")
        status_lines.append("3. Copy file_id yang muncul")
        status_lines.append("4. Gunakan `/setlogo <file_id>`")
        status_lines.append("\n**Atau:** Reply foto langsung dengan `/setlogo`")

        buttons = [
            [Button.inline("📷 Test Branding Image", b"logo:test_branding")],
            [Button.inline("🎵 Test Music Logo", b"logo:test_music")],
        ]

        await event.reply(
            VBotBranding.wrap_message("\n".join(status_lines), plugin_name="Logo Helper"),
            buttons=buttons
        )

    except Exception as e:
        await event.reply(VBotBranding.format_error(f"Error checking logo: {e}"))


@events.register(events.NewMessage(pattern=r'^[/\.\+]showbranding$'))
async def show_branding_handler(event):
    """Display branding image - /showbranding"""

    if not event.out:
        return

    try:
        branding_path, caption = VBotBrandingAssets.get_primary_image()

        if branding_path and branding_path.exists():
            await event.reply(
                file=str(branding_path),
                caption=VBotBranding.wrap_message(
                    "**VBot Official Branding**\n\nGambar branding resmi VBot.",
                    plugin_name="Branding"
                )
            )
        else:
            await event.reply(
                VBotBranding.format_error(
                    "Branding image tidak ditemukan.\n\n"
                    f"Expected path: `{branding_path}`"
                )
            )

    except Exception as e:
        await event.reply(VBotBranding.format_error(f"Error: {e}"))


@events.register(events.NewMessage(pattern=r'^[/\.\+]fixlogo$'))
async def fix_logo_handler(event):
    """Show instructions to fix logo - /fixlogo"""

    if not event.out:
        return

    instructions = """
**Panduan Memperbaiki Logo Music**

Logo music menggunakan File ID dari Telegram. Jika logo tidak muncul, File ID mungkin expired.

**Langkah-langkah:**

1️⃣ **Upload Logo Baru**
   └ Kirim foto logo ke chat ini (private chat dengan bot)

2️⃣ **Dapatkan File ID**
   └ Reply foto dengan: `/getfileid`
   └ Copy file_id dari hasil

3️⃣ **Set Logo Baru**
   **Opsi A:** Reply foto dengan `/setlogo`
   **Opsi B:** Gunakan `/setlogo <file_id>`

4️⃣ **Reset Logo** (jika perlu)
   └ Gunakan: `/setlogo reset`

**Catatan Developer:**
- Branding image ada di: `assets/branding/vbot_branding.png`
- Music logo disimpan sebagai File ID di config
- File ID bisa expired jika foto asli dihapus

**Test Commands:**
- `/testlogo` - Cek status logo
- `/showbranding` - Tampilkan branding image
- `/getfileid` - Dapatkan file_id dari media (reply)
- `/setlogo` - Set music logo (reply to photo)
"""

    await event.reply(
        VBotBranding.wrap_message(instructions, plugin_name="Logo Helper")
    )


def setup(bot):
    """Setup logo helper plugin."""
    bot.client.add_event_handler(test_logo_handler)
    bot.client.add_event_handler(show_branding_handler)
    bot.client.add_event_handler(fix_logo_handler)
    print("✅ Logo Helper plugin loaded")
