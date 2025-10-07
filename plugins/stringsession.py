"""
String Session Generator Plugin (Improved)
Generate Telethon session string with inline buttons interface

Features:
- Private chat only (blocked in groups)
- Inline button interface for better UX
- Toggle system to enable/disable in groups
- Step-by-step guided process
- Secure session handling

Commands:
    /gensession - Generate session string (private only)
    /sessiontoggle - Enable/disable session gen in group (admin only)

Author: Vzoel Fox's
"""

import asyncio
import logging
from telethon import events, Button
from telethon.sessions import StringSession
from telethon import TelegramClient
from telethon.errors import (
    PhoneCodeInvalidError,
    PhoneNumberInvalidError,
    SessionPasswordNeededError,
    FloodWaitError
)
import config

logger = logging.getLogger(__name__)

# Store session generation state per user
generation_sessions = {}

# Store group settings (chat_id: enabled)
group_settings = {}


HANDLED_COMMANDS = {"/gensession", "/sessiontoggle"}


class StringSessionHandler:
    """Handle string session generation with inline interface"""

    def __init__(self, bot):
        self.bot = bot
        self.client = getattr(bot, "client", None)
        self.plugin_name = "String Session"

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

    async def check_group_allowed(self, event):
        """Check if session generation is allowed in this group"""
        chat_id = event.chat_id
        return group_settings.get(chat_id, False)  # Default: blocked

    async def handle_gensession_command(self, event):
        """
        Handle /gensession command
        Developer only - Blocks in groups unless explicitly enabled
        """
        # Check if user is developer
        user_id = event.sender_id
        if user_id not in config.DEVELOPER_IDS:
            await event.reply(
                self.format_message(
                    "❌ **Access Denied**\n\n"
                    "Session generator hanya untuk developer."
                )
            )
            return

        # Check if in group/channel
        if event.is_group or event.is_channel:
            allowed = await self.check_group_allowed(event)
            if not allowed:
                buttons = [
                    [Button.url("💬 Chat Pribadi Bot", f"t.me/{self.client.me.username}?start=gensession")]
                ]

                message = self.format_message(
                    (
                        "🔒 **Session Generator - Private Only**\n\n"
                        "❌ Session generator **TIDAK BISA** digunakan di grup!\n\n"
                        "**Alasan Keamanan:**\n"
                        "• Session string = akses penuh ke akun\n"
                        "• Data sensitif (API ID, Phone, OTP)\n"
                        "• Risk kebocoran data\n\n"
                        "**Cara pakai:**\n"
                        "Klik tombol di bawah untuk chat pribadi dengan bot.\n\n"
                        "**Admin:** Ketik `/sessiontoggle` untuk enable di grup ini (NOT RECOMMENDED!)"
                    ),
                    include_footer=False,
                )

                await event.reply(message, buttons=buttons)
                return

        # Check if already in progress
        if user_id in generation_sessions:
            await event.reply(
                self.format_message(
                    (
                        "⚠️ **Kamu sudah memulai proses generate session!**\n\n"
                        "Klik **Cancel** pada pesan sebelumnya atau tunggu 5 menit."
                    )
                )
            )
            return

        # Start session generation
        await self.start_session_wizard(event)

    async def start_session_wizard(self, event):
        """Start the session generation wizard with inline buttons"""
        user_id = event.sender_id

        # Initialize session state
        generation_sessions[user_id] = {
            'step': 'start',
            'data': {},
            'client': None,
            'start_time': asyncio.get_event_loop().time()
        }

        welcome_message = self.format_message(
            (
                "🔐 **String Session Generator**\n\n"
                "Generator ini akan membuat **Session String** untuk Assistant Account.\n\n"
                "**⚠️ PENTING:**\n"
                "• Gunakan nomor HP **BERBEDA** dari owner\n"
                "• Account untuk join Voice Chat\n"
                "• **JANGAN SHARE** session string!\n"
                "• Session = Full access ke akun kamu\n\n"
                "**Yang kamu butuhkan:**\n"
                "📱 API ID & API Hash (dari my.telegram.org)\n"
                "📞 Nomor HP (untuk assistant)\n"
                "🔢 OTP Code (akan dikirim ke Telegram)\n\n"
                "**Ready?** Klik tombol di bawah untuk mulai!"
            ),
            include_footer=False,
        )

        buttons = [
            [Button.inline("✅ Start Generation", b"session_start")],
            [Button.inline("❌ Cancel", b"session_cancel")]
        ]

        await event.reply(welcome_message, buttons=buttons)

    async def handle_callback(self, event):
        """Handle inline button callbacks"""
        data = event.data.decode()
        user_id = event.sender_id

        # Session generation callbacks
        if data == "session_start":
            await self.ask_api_id(event)
        elif data == "session_cancel":
            await self.cancel_session(event, user_id)
        elif data.startswith("session_"):
            await event.answer("⚠️ Invalid action", alert=True)

    async def ask_api_id(self, event):
        """Ask user for API ID"""
        user_id = event.sender_id

        if user_id not in generation_sessions:
            await event.answer("❌ Session expired. Start again with /gensession", alert=True)
            return

        generation_sessions[user_id]['step'] = 'api_id'

        message = self.format_message(
            (
                "**Step 1/4:** API ID\n\n"
                "Masukkan **API ID** kamu dari https://my.telegram.org\n\n"
                "Contoh: `12345678`\n\n"
                "Ketik /cancel untuk batalkan."
            ),
            include_footer=False,
        )

        try:
            await event.edit(message)
        except:
            await event.respond(message)

    async def cancel_session(self, event, user_id):
        """Cancel session generation"""
        if user_id in generation_sessions:
            # Disconnect client if exists
            session = generation_sessions[user_id]
            if session.get('client'):
                try:
                    await session['client'].disconnect()
                except:
                    pass

            del generation_sessions[user_id]

        try:
            await event.edit("❌ **Session generation cancelled.**")
        except:
            await event.answer("❌ Cancelled", alert=True)

    async def handle_text_input(self, event):
        """Handle text input during session generation"""
        user_id = event.sender_id

        if user_id not in generation_sessions:
            return

        session = generation_sessions[user_id]
        text = event.message.text.strip()

        # Handle cancel command
        if text.lower() in ['/cancel', '.cancel']:
            await self.cancel_session(event, user_id)
            return

        step = session['step']

        try:
            if step == 'api_id':
                await self.process_api_id(event, session, text)
            elif step == 'api_hash':
                await self.process_api_hash(event, session, text)
            elif step == 'phone':
                await self.process_phone(event, session, text)
            elif step == 'otp':
                await self.process_otp(event, session, text)
            elif step == '2fa':
                await self.process_2fa(event, session, text)
        except Exception as e:
            logger.error(f"Error processing step {step}: {e}", exc_info=True)
            await event.reply(
                self.format_message(
                    f"❌ **Error:** {str(e)}\n\nKetik /cancel untuk batalkan dan mulai ulang."
                )
            )

    async def process_api_id(self, event, session, text):
        """Process API ID input"""
        try:
            api_id = int(text)
            session['data']['api_id'] = api_id
            session['step'] = 'api_hash'

            message = self.format_message(
                (
                    "**Step 2/4:** API Hash\n\n"
                    "Masukkan **API Hash** kamu dari https://my.telegram.org\n\n"
                    "Contoh: `abcdef1234567890abcdef1234567890`\n\n"
                    "Ketik /cancel untuk batalkan."
                ),
                include_footer=False,
            )

            await event.reply(message)
        except ValueError:
            await event.reply(
                self.format_message(
                    "❌ **Invalid API ID!** Harus berupa angka.\n\nCoba lagi:",
                    include_footer=False,
                )
            )

    async def process_api_hash(self, event, session, text):
        """Process API Hash input"""
        if len(text) != 32:
            await event.reply(
                self.format_message(
                    "❌ **Invalid API Hash!** Harus 32 karakter.\n\nCoba lagi:",
                    include_footer=False,
                )
            )
            return

        session['data']['api_hash'] = text
        session['step'] = 'phone'

        message = self.format_message(
            (
                "**Step 3/4:** Phone Number\n\n"
                "Masukkan **nomor HP** untuk assistant account.\n\n"
                "**Format:** `+6281234567890` (dengan kode negara)\n\n"
                "⚠️ Gunakan nomor **BERBEDA** dari owner!\n\n"
                "Ketik /cancel untuk batalkan."
            ),
            include_footer=False,
        )

        await event.reply(message)

    async def process_phone(self, event, session, text):
        """Process phone number and send OTP"""
        if not text.startswith('+'):
            await event.reply(
                self.format_message(
                    "❌ **Format salah!** Harus dimulai dengan + dan kode negara.\n\nContoh: `+6281234567890`",
                    include_footer=False,
                )
            )
            return

        phone = text
        session['data']['phone'] = phone

        # Create Telethon client
        try:
            loading_msg = await event.reply(
                self.format_message(
                    "⏳ **Menghubungi Telegram...**",
                    include_footer=False,
                )
            )

            client = TelegramClient(
                StringSession(),
                session['data']['api_id'],
                session['data']['api_hash']
            )

            await client.connect()
            session['client'] = client

            # Send OTP
            sent = await client.send_code_request(phone)
            session['data']['phone_code_hash'] = sent.phone_code_hash
            session['step'] = 'otp'

            await loading_msg.delete()

            message = self.format_message(
                (
                    "**Step 4/4:** OTP Code\n\n"
                    "📨 **Kode OTP** sudah dikirim ke Telegram kamu!\n\n"
                    "Masukkan kode OTP (5 digit):\n\n"
                    "Contoh: `12345`\n\n"
                    "Ketik /cancel untuk batalkan."
                ),
                include_footer=False,
            )

            await event.reply(message)

        except PhoneNumberInvalidError:
            await event.reply(
                self.format_message(
                    "❌ **Nomor HP invalid!**\n\nCoba lagi dengan format yang benar.",
                )
            )
            session['step'] = 'phone'
        except FloodWaitError as e:
            await event.reply(
                self.format_message(
                    f"❌ **Flood Wait!** Tunggu {e.seconds} detik.\n\nTry again later."
                )
            )
            if session.get('client'):
                await session['client'].disconnect()
            del generation_sessions[event.sender_id]
        except Exception as e:
            logger.error(f"Error sending OTP: {e}")
            await event.reply(
                self.format_message(
                    f"❌ **Error:** {str(e)}\n\nCoba lagi atau ketik /cancel"
                )
            )
            session['step'] = 'phone'

    async def process_otp(self, event, session, text):
        """Process OTP code"""
        client = session.get('client')
        if not client:
            await event.reply(
                self.format_message("❌ **Session expired!** Start again with /gensession")
            )
            del generation_sessions[event.sender_id]
            return

        try:
            loading_msg = await event.reply(
                self.format_message(
                    "⏳ **Verifying OTP...**",
                    include_footer=False,
                )
            )

            await client.sign_in(
                session['data']['phone'],
                text,
                phone_code_hash=session['data']['phone_code_hash']
            )

            # Success! Generate session string
            session_string = client.session.save()
            await loading_msg.delete()

            success_message = self.format_message(
                (
                    "✅ **Session String Generated!**\n\n"
                    "🔐 **SIMPAN SESSION INI:**\n\n"
                    f"`{session_string}`\n\n"
                    "**Cara pakai:**\n"
                    "1. Copy session string di atas\n"
                    "2. Paste ke `.env` file:\n"
                    "   `STRING_SESSION=session_string_kamu`\n"
                    "3. Restart bot\n\n"
                    "⚠️ **JANGAN SHARE KE SIAPAPUN!**\n"
                    "Session = full access ke akun kamu!"
                ),
                include_footer=False,
            )

            await event.reply(success_message)

            # Cleanup
            await client.disconnect()
            del generation_sessions[event.sender_id]

        except PhoneCodeInvalidError:
            await event.reply(
                self.format_message("❌ **OTP Code salah!**\n\nCoba lagi:")
            )
        except SessionPasswordNeededError:
            session['step'] = '2fa'
            message = self.format_message(
                (
                    "🔒 **2FA Detected**\n\n"
                    "Account kamu menggunakan 2FA (Two-Factor Authentication).\n\n"
                    "Masukkan **password 2FA** kamu:\n\n"
                    "Ketik /cancel untuk batalkan."
                ),
                include_footer=False,
            )

            await event.reply(message)
        except Exception as e:
            logger.error(f"Error verifying OTP: {e}")
            await event.reply(
                self.format_message(
                    f"❌ **Error:** {str(e)}\n\nCoba lagi atau ketik /cancel"
                )
            )

    async def process_2fa(self, event, session, text):
        """Process 2FA password"""
        client = session.get('client')
        if not client:
            await event.reply(
                self.format_message("❌ **Session expired!** Start again with /gensession")
            )
            del generation_sessions[event.sender_id]
            return

        try:
            loading_msg = await event.reply(
                self.format_message(
                    "⏳ **Verifying 2FA password...**",
                    include_footer=False,
                )
            )

            await client.sign_in(password=text)

            # Success! Generate session string
            session_string = client.session.save()
            await loading_msg.delete()

            success_message = self.format_message(
                (
                    "✅ **Session String Generated!**\n\n"
                    "🔐 **SIMPAN SESSION INI:**\n\n"
                    f"`{session_string}`\n\n"
                    "**Cara pakai:**\n"
                    "1. Copy session string di atas\n"
                    "2. Paste ke `.env` file:\n"
                    "   `STRING_SESSION=session_string_kamu`\n"
                    "3. Restart bot\n\n"
                    "⚠️ **JANGAN SHARE KE SIAPAPUN!**"
                ),
                include_footer=False,
            )

            await event.reply(success_message)

            # Cleanup
            await client.disconnect()
            del generation_sessions[event.sender_id]

        except Exception as e:
            logger.error(f"Error with 2FA: {e}")
            await event.reply(
                self.format_message(f"❌ **Password 2FA salah!**\n\nCoba lagi:")
            )

    async def handle_session_toggle(self, event):
        """Toggle session generation in groups (admin only)"""
        if not (event.is_group or event.is_channel):
            await event.reply(
                self.format_message("❌ Command ini hanya untuk grup/channel!")
            )
            return

        # Check if user is admin
        try:
            perms = await self.client.get_permissions(event.chat_id, event.sender_id)
            if not perms.is_admin:
                await event.reply(
                    self.format_message("❌ Hanya admin yang bisa mengubah setting ini!")
                )
                return
        except:
            await event.reply(self.format_message("❌ Gagal cek permission!"))
            return

        chat_id = event.chat_id
        current = group_settings.get(chat_id, False)
        new_status = not current
        group_settings[chat_id] = new_status

        status_emoji = "✅" if new_status else "❌"
        status_text = "**ENABLED**" if new_status else "**DISABLED**"

        message = (
            f"{status_emoji} **Session Generator - {status_text}**\n\n"
            f"Status di grup ini: {status_text}\n\n"
        )

        if new_status:
            message += (
                "⚠️ **WARNING:**\n"
                "• Session generator sekarang BISA digunakan di grup ini\n"
                "• Data sensitif (API ID, OTP) akan terlihat\n"
                "• **SANGAT TIDAK DISARANKAN!**\n\n"
                "Ketik `/sessiontoggle` lagi untuk disable."
            )
        else:
            message += (
                "✅ Session generator di-block di grup ini.\n"
                "User harus chat pribadi dengan bot.\n\n"
                "Ketik `/sessiontoggle` lagi untuk enable (not recommended)."
            )

        message = self.format_message(message, include_footer=False)

        await event.reply(message)


def setup(bot):
    """Setup string session plugin"""
    bot_client = getattr(bot, "client", bot)
    if bot_client is None:
        logger.warning("StringSession plugin skipped: bot has no client instance")
        return

    handler = StringSessionHandler(bot)

    gensession_enabled = True
    if bot.plugin_loader.handles_command("/gensession"):
        gensession_enabled = False
        HANDLED_COMMANDS.discard("/gensession")
        logger.info("Skipping /gensession in StringSession plugin; already handled")

    sessiontoggle_enabled = True
    if bot.plugin_loader.handles_command("/sessiontoggle"):
        sessiontoggle_enabled = False
        HANDLED_COMMANDS.discard("/sessiontoggle")
        logger.info("Skipping /sessiontoggle in StringSession plugin; already handled")

    if gensession_enabled:
        @bot_client.on(events.NewMessage(pattern=r'^/gensession$'))
        async def handle_gensession(event):
            """Handle /gensession command"""
            await handler.handle_gensession_command(event)

    # Text input handler for session generation
    @bot_client.on(events.NewMessage(func=lambda e: e.sender_id in generation_sessions and e.is_private))
    async def handle_session_input(event):
        """Handle text input during session generation"""
        await handler.handle_text_input(event)

    # Callback handler for inline buttons
    @bot_client.on(events.CallbackQuery(pattern=b"^session_"))
    async def handle_session_callback(event):
        """Handle inline button callbacks"""
        await handler.handle_callback(event)

    if sessiontoggle_enabled:
        @bot_client.on(events.NewMessage(pattern=r'^/sessiontoggle$'))
        async def handle_toggle(event):
            """Handle /sessiontoggle command"""
            await handler.handle_session_toggle(event)

    # Export handler
    setattr(bot, "stringsession_handler", handler)
    if bot_client is not bot:
        setattr(bot_client, "stringsession_handler", handler)

    logger.info("✅ StringSession plugin loaded (with inline buttons & group block)")
