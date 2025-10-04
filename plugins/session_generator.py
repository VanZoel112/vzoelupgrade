#!/usr/bin/env python3
"""
Session String Generator Plugin
Generate Telethon session string langsung dari bot

Commands:
    .gensession - Generate session string (private chat only)

Author: Vzoel Fox's
"""

import asyncio
import logging
from telethon import events, Button
from telethon.sessions import StringSession
from telethon import TelegramClient
from telethon.errors import PhoneCodeInvalidError, PhoneNumberInvalidError, SessionPasswordNeededError
import config

from core.branding import VBotBranding

logger = logging.getLogger(__name__)

# Store session generation state
generation_state = {}

class SessionGenerator:
    """Handle session string generation"""

    def __init__(self, bot_client):
        self.bot = bot_client

    async def start_generation(self, event):
        """Start session generation process"""
        # Only allow in private chat
        if event.is_group or event.is_channel:
            content = (
                "❌ **Session generator hanya bisa digunakan di Private Chat!**\n\n"
                "Click button di /start atau ketik /gensession di chat pribadi bot."
            )
            await event.reply(VBotBranding.wrap_message(content))
            return

        user_id = event.sender_id

        # Check if already in progress
        if user_id in generation_state:
            content = (
                "⚠️ **Kamu sudah memulai proses generate session!**\n\n"
                "Gunakan /cancel untuk membatalkan dan mulai ulang."
            )
            await event.reply(VBotBranding.wrap_message(content))
            return

        # Initialize state
        generation_state[user_id] = {
            'step': 'api_id',
            'data': {}
        }

        content = (
            "**Session String Generator**\n\n"
            "Generator ini akan membantu kamu membuat session string untuk Assistant Account.\n\n"
            "**CATATAN PENTING:**\n"
            "• Gunakan nomor HP yang BERBEDA dari owner\n"
            "• Account ini akan digunakan untuk join VC\n"
            "• Jangan share session string ke orang lain!\n\n"
            "**Step 1:** Masukkan **API ID** kamu\n"
            "(Dapatkan dari https://my.telegram.org)\n\n"
            "Ketik /cancel untuk membatalkan."
        )

        await event.reply(VBotBranding.wrap_message(content, include_footer=False))

    async def handle_message(self, event):
        """Handle user messages during generation"""
        user_id = event.sender_id

        # Check if user is in generation process
        if user_id not in generation_state:
            return

        state = generation_state[user_id]
        text = event.message.text.strip()

        # Handle cancel
        if text.lower() in ['/cancel', '.cancel']:
            del generation_state[user_id]
            await event.reply(
                VBotBranding.wrap_message("❌ **Proses dibatalkan.**")
            )
            return

        # Process based on current step
        if state['step'] == 'api_id':
            await self._handle_api_id(event, state, text)
        elif state['step'] == 'api_hash':
            await self._handle_api_hash(event, state, text)
        elif state['step'] == 'phone':
            await self._handle_phone(event, state, text)
        elif state['step'] == 'otp':
            await self._handle_otp(event, state, text)
        elif state['step'] == '2fa':
            await self._handle_2fa(event, state, text)

    async def _handle_api_id(self, event, state, text):
        """Handle API ID input"""
        try:
            api_id = int(text)
            state['data']['api_id'] = api_id
            state['step'] = 'api_hash'

            content = (
                "✅ **API ID tersimpan!**\n\n"
                "**Step 2:** Masukkan **API Hash** kamu"
            )

            await event.reply(
                VBotBranding.wrap_message(content, include_footer=False)
            )
        except ValueError:
            await event.reply(
                VBotBranding.wrap_message(
                    "❌ API ID harus berupa angka! Coba lagi:",
                    include_footer=False,
                )
            )

    async def _handle_api_hash(self, event, state, text):
        """Handle API Hash input"""
        state['data']['api_hash'] = text
        state['step'] = 'phone'

        content = (
            "✅ **API Hash tersimpan!**\n\n"
            "**Step 3:** Masukkan **nomor HP** untuk Assistant\n\n"
            "Format: +628123456789\n"
            "(Dengan kode negara, tanpa spasi)"
        )

        await event.reply(VBotBranding.wrap_message(content, include_footer=False))

    async def _handle_phone(self, event, state, text):
        """Handle phone number and send OTP"""
        phone = text.strip()
        state['data']['phone'] = phone

        # Create temporary client
        try:
            client = TelegramClient(
                StringSession(),
                state['data']['api_id'],
                state['data']['api_hash']
            )

            await client.connect()

            # Send code
            status_msg = await event.reply(
                VBotBranding.wrap_message(
                    "📱 **Mengirim kode OTP...**", include_footer=False
                )
            )

            result = await client.send_code_request(phone)
            state['data']['phone_code_hash'] = result.phone_code_hash
            state['data']['client'] = client
            state['step'] = 'otp'

            await status_msg.edit(
                VBotBranding.wrap_message(
                    "✅ **Kode OTP telah dikirim!**\n\n"
                    "**Step 4:** Masukkan **kode OTP** yang kamu terima dari Telegram\n\n"
                    "Format: 12345 (5 digit angka)",
                    include_footer=False,
                )
            )

        except PhoneNumberInvalidError:
            content = (
                "❌ **Nomor HP tidak valid!**\n\n"
                "Pastikan format: +628123456789"
            )
            await event.reply(VBotBranding.wrap_message(content))
        except Exception as e:
            logger.error(f"Error sending code: {e}")
            await event.reply(
                VBotBranding.wrap_message(f"❌ **Error:** {str(e)}")
            )
            if user_id in generation_state:
                del generation_state[event.sender_id]

    async def _handle_otp(self, event, state, text):
        """Handle OTP code"""
        code = text.strip().replace(" ", "")
        client = state['data']['client']

        try:
            status_msg = await event.reply(
                VBotBranding.wrap_message(
                    "🔐 **Verifikasi kode OTP...**", include_footer=False
                )
            )

            # Sign in with code
            await client.sign_in(
                state['data']['phone'],
                code,
                phone_code_hash=state['data']['phone_code_hash']
            )

            # Get session string
            session_string = client.session.save()

            # Get user info
            me = await client.get_me()

            # Success!
            await status_msg.delete()

            content = (
                "✅ **Session String berhasil dibuat!**\n\n"
                f"**Account Info:**\n"
                f"• Nama: {me.first_name}\n"
                f"• Username: @{me.username or 'no_username'}\n"
                f"• User ID: {me.id}\n"
                f"• Phone: {me.phone}\n\n"
                "**Session String akan dikirim di pesan berikutnya.**\n"
                "⚠️ **JANGAN BAGIKAN KE SIAPAPUN!**"
            )

            await event.reply(
                VBotBranding.wrap_message(content, include_footer=False)
            )

            # Send session string in separate message
            content = (
                "🔑 **Session String:**\n\n"
                f"`{session_string}`\n\n"
                "📋 **Copy dan simpan di config.py:**\n"
                "```python\n"
                f"STRING_SESSION = \"{session_string}\"\n"
                "```"
            )

            await event.reply(
                VBotBranding.wrap_message(content, include_footer=False)
            )

            # Cleanup
            await client.disconnect()
            del generation_state[event.sender_id]

        except PhoneCodeInvalidError:
            content = (
                "❌ **Kode OTP salah!**\n\n"
                "Coba lagi atau ketik /cancel untuk membatalkan."
            )
            await event.reply(VBotBranding.wrap_message(content))
        except SessionPasswordNeededError:
            state['step'] = '2fa'
            content = (
                "🔐 **Account dilindungi 2FA!**\n\n"
                "**Step 5:** Masukkan **password 2FA** kamu"
            )
            await event.reply(
                VBotBranding.wrap_message(content, include_footer=False)
            )
        except Exception as e:
            logger.error(f"Error signing in: {e}")
            await event.reply(
                VBotBranding.wrap_message(f"❌ **Error:** {str(e)}")
            )
            if event.sender_id in generation_state:
                await state['data']['client'].disconnect()
                del generation_state[event.sender_id]

    async def _handle_2fa(self, event, state, text):
        """Handle 2FA password"""
        password = text.strip()
        client = state['data']['client']

        try:
            status_msg = await event.reply(
                VBotBranding.wrap_message("🔐 **Verifikasi 2FA...**", include_footer=False)
            )

            # Sign in with password
            await client.sign_in(password=password)

            # Get session string
            session_string = client.session.save()

            # Get user info
            me = await client.get_me()

            # Success!
            await status_msg.delete()

            content = (
                "✅ **Session String berhasil dibuat!**\n\n"
                f"**Account Info:**\n"
                f"• Nama: {me.first_name}\n"
                f"• Username: @{me.username or 'no_username'}\n"
                f"• User ID: {me.id}\n"
                f"• Phone: {me.phone}\n\n"
                "**Session String akan dikirim di pesan berikutnya.**\n"
                "⚠️ **JANGAN BAGIKAN KE SIAPAPUN!**"
            )

            await event.reply(
                VBotBranding.wrap_message(content, include_footer=False)
            )

            # Send session string
            content = (
                "🔑 **Session String:**\n\n"
                f"`{session_string}`\n\n"
                "📋 **Copy dan simpan di config.py:**\n"
                "```python\n"
                f"STRING_SESSION = \"{session_string}\"\n"
                "```"
            )

            await event.reply(
                VBotBranding.wrap_message(content, include_footer=False)
            )

            # Cleanup
            await client.disconnect()
            del generation_state[event.sender_id]

        except Exception as e:
            logger.error(f"Error with 2FA: {e}")
            await event.reply(
                VBotBranding.wrap_message(
                    f"❌ **Password 2FA salah atau error:** {str(e)}"
                )
            )
            if event.sender_id in generation_state:
                await client.disconnect()
                del generation_state[event.sender_id]


def setup(bot):
    """Setup session generator handlers"""
    bot_client = getattr(bot, "client", bot)
    if bot_client is None:
        logger.warning("Session Generator plugin skipped: bot has no client instance")
        return

    generator = SessionGenerator(bot_client)

    @bot_client.on(events.NewMessage(pattern=r'^/gensession$'))
    async def handle_gensession(event):
        """Handle /gensession command"""
        await generator.start_generation(event)

    @bot_client.on(events.NewMessage(func=lambda e: e.sender_id in generation_state and e.is_private))
    async def handle_generation_message(event):
        """Handle messages during generation"""
        await generator.handle_message(event)

    # Export generator for callback use
    setattr(bot, "session_generator", generator)
    if bot_client is not bot:
        setattr(bot_client, "session_generator", generator)

    logger.info("✅ Session Generator plugin loaded")
