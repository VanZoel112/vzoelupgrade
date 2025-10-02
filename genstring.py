#!/usr/bin/env python3
"""
String Session Generator for Assistant Account
Generate Pyrogram/Telethon session string untuk streaming di VC

Usage:
    python3 genstring.py

Author: Vzoel Fox's
"""

import asyncio
from telethon.sync import TelegramClient
from telethon.sessions import StringSession

print("""
╔══════════════════════════════════════════════╗
║   STRING SESSION GENERATOR                   ║
║   Untuk Assistant Account (VC Streaming)     ║
╚══════════════════════════════════════════════╝

CATATAN:
- Gunakan nomor HP yang BERBEDA dari owner
- Account ini akan join VC untuk streaming
- Bisa pakai nomor HP biasa atau nomor virtual
""")

# Input API credentials
print("\n📝 Masukkan API Credentials:")
print("(Dapatkan dari https://my.telegram.org)")
print()

api_id = input("API ID: ").strip()
api_hash = input("API HASH: ").strip()

if not api_id or not api_hash:
    print("\n❌ API ID dan API Hash harus diisi!")
    exit(1)

try:
    api_id = int(api_id)
except ValueError:
    print("\n❌ API ID harus berupa angka!")
    exit(1)

print("\n📱 Siapkan nomor HP untuk Assistant Account")
print("Format: +628123456789 (dengan kode negara)")
print()

async def main():
    client = TelegramClient(
        StringSession(),
        api_id,
        api_hash
    )

    await client.start()

    print("\n✅ Login berhasil!")

    # Get session string
    session_string = client.session.save()

    # Get user info
    me = await client.get_me()

    print("\n" + "="*50)
    print("📋 INFORMASI ACCOUNT ASSISTANT:")
    print("="*50)
    print(f"Nama: {me.first_name}")
    if me.last_name:
        print(f"Nama Lengkap: {me.first_name} {me.last_name}")
    if me.username:
        print(f"Username: @{me.username}")
    print(f"User ID: {me.id}")
    print(f"Phone: {me.phone}")
    print("="*50)

    print("\n🔑 STRING SESSION:")
    print("="*50)
    print(session_string)
    print("="*50)

    print("\n💾 Simpan string session di atas ke config.py:")
    print("STRING_SESSION = \"" + session_string + "\"")
    print()

    # Save to file
    with open("string_session.txt", "w") as f:
        f.write("# Assistant Account Session String\n")
        f.write(f"# Account: {me.first_name} (@{me.username or 'no_username'})\n")
        f.write(f"# User ID: {me.id}\n")
        f.write(f"# Phone: {me.phone}\n\n")
        f.write(f"STRING_SESSION = \"{session_string}\"\n")

    print("✅ Session string juga disimpan di: string_session.txt")
    print()

    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
