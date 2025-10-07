#!/usr/bin/env python3
"""
VBot Assistant Account String Session Generator
Generate session string for assistant account and auto-save to .env

Author: Vzoel Fox's
"""

import asyncio
import sys
from pathlib import Path
from telethon import TelegramClient
from telethon.sessions import StringSession


def print_header():
    """Print welcome header"""
    print("\n" + "="*60)
    print("  VBot Music & Clear Chat Management")
    print("  Generator String Session - Akun Assistant")
    print("="*60)
    print("\nScript ini akan generate session string untuk akun assistant.")
    print("Akun assistant akan digunakan untuk:")
    print("  - Join voice chat di grup")
    print("  - Stream audio/video saat user pakai /play atau /vplay")
    print("  - Handle semua operasi voice chat")
    print("\nPENTING:")
    print("  - Gunakan nomor HP BERBEDA dari owner bot")
    print("  - Akun ini akan muncul di voice chat")
    print("  - Session string = akses penuh akun (rahasiakan!)")
    print("="*60 + "\n")


def get_env_path():
    """Get .env file path"""
    env_path = Path(__file__).parent / ".env"
    return env_path


def read_env_file(env_path):
    """Read .env file and return lines"""
    if not env_path.exists():
        return []
    
    try:
        with open(env_path, 'r', encoding='utf-8') as f:
            return f.readlines()
    except Exception as e:
        print(f"⚠ Warning: Tidak bisa baca file .env: {e}")
        return []


def write_env_file(env_path, session_string):
    """Write or update STRING_SESSION in .env file"""
    try:
        lines = read_env_file(env_path)
        
        # Check if STRING_SESSION already exists
        session_found = False
        new_lines = []
        
        for line in lines:
            if line.strip().startswith('STRING_SESSION='):
                # Replace existing STRING_SESSION
                new_lines.append(f'STRING_SESSION="{session_string}"\n')
                session_found = True
            else:
                new_lines.append(line)
        
        # If STRING_SESSION not found, append it
        if not session_found:
            if new_lines and not new_lines[-1].endswith('\n'):
                new_lines.append('\n')
            new_lines.append('\n# Assistant Account Session String (Auto-generated)\n')
            new_lines.append(f'STRING_SESSION="{session_string}"\n')
        
        # Write back to file
        with open(env_path, 'w', encoding='utf-8') as f:
            f.writelines(new_lines)
        
        return True
    except Exception as e:
        print(f"❌ Error menulis file .env: {e}")
        return False


def get_api_id():
    """Get API ID with retry loop"""
    while True:
        try:
            api_id_input = input("Masukkan API ID: ").strip()
            api_id = int(api_id_input)
            if api_id <= 0:
                print("\n❌ API ID harus berupa angka positif! Coba lagi:\n")
                continue
            return api_id
        except ValueError:
            print("\n❌ API ID harus berupa angka! Coba lagi:\n")
        except KeyboardInterrupt:
            print("\n\n❌ Dibatalkan oleh user")
            sys.exit(0)


def get_api_hash():
    """Get API Hash with validation"""
    while True:
        try:
            api_hash = input("Masukkan API Hash: ").strip()
            if not api_hash:
                print("\n❌ API Hash tidak boleh kosong! Coba lagi:\n")
                continue
            if len(api_hash) < 30:
                print("\n❌ API Hash terlalu pendek! Pastikan sudah benar. Coba lagi:\n")
                continue
            return api_hash
        except KeyboardInterrupt:
            print("\n\n❌ Dibatalkan oleh user")
            sys.exit(0)


def get_phone_number():
    """Get phone number with validation"""
    while True:
        try:
            phone = input("Masukkan nomor HP (format: +628xxx): ").strip()
            if not phone:
                print("\n❌ Nomor HP tidak boleh kosong! Coba lagi:\n")
                continue
            if not phone.startswith('+'):
                print("\n❌ Nomor HP harus diawali dengan + dan kode negara! Coba lagi:\n")
                continue
            if len(phone) < 10:
                print("\n❌ Nomor HP terlalu pendek! Coba lagi:\n")
                continue
            return phone
        except KeyboardInterrupt:
            print("\n\n❌ Dibatalkan oleh user")
            sys.exit(0)


async def generate_session():
    """Generate session string"""
    print_header()
    
    # Get API credentials
    print("Langkah 1/5: Kredensial API")
    print("-" * 60)
    print("Dapatkan dari: https://my.telegram.org")
    print()
    
    api_id = get_api_id()
    print("✓ API ID diterima\n")
    
    api_hash = get_api_hash()
    print("✓ API Hash diterima")
    
    # Get phone number
    print("\nLangkah 2/5: Nomor Telepon")
    print("-" * 60)
    
    phone = get_phone_number()
    print("✓ Nomor telepon diterima")
    
    # Create client and start
    print("\nLangkah 3/5: Login ke Telegram")
    print("-" * 60)
    
    client = None
    try:
        client = TelegramClient(StringSession(), api_id, api_hash)
        
        print("Menghubungkan ke Telegram...")
        await client.connect()
        
        print("✓ Terhubung!\n")
        print(f"Mengirim kode OTP ke {phone}...\n")
        
        # Start will handle OTP and 2FA automatically  
        await client.start(phone=phone)
        
        print("\n✓ Login berhasil!")
        
    except Exception as e:
        print(f"\n❌ Error saat login: {e}")
        if client:
            try:
                await client.disconnect()
            except:
                pass
        return None
    
    # Get session string
    print("\nLangkah 4/5: Generate Session String")
    print("-" * 60)
    
    try:
        session_string = client.session.save()
        
        # Get user info
        me = await client.get_me()
        
        print("\n" + "="*60)
        print("  ✓ SESSION STRING BERHASIL DIBUAT!")
        print("="*60)
        print(f"\nInfo Akun:")
        print(f"  Nama: {me.first_name}")
        if me.last_name:
            print(f"  Nama Lengkap: {me.first_name} {me.last_name}")
        print(f"  Username: @{me.username or 'tidak_ada'}")
        print(f"  User ID: {me.id}")
        print(f"  Telepon: {me.phone}")
        print("\n" + "="*60)
        
        await client.disconnect()
        
        return session_string
        
    except Exception as e:
        print(f"\n❌ Error generate session string: {e}")
        if client:
            try:
                await client.disconnect()
            except:
                pass
        return None


async def main():
    """Main function"""
    
    # Generate session string
    session_string = await generate_session()
    
    if not session_string:
        print("\n❌ Gagal generate session string!")
        print("\nSilakan coba lagi dan pastikan:")
        print("  - API ID dan API Hash benar")
        print("  - Format nomor HP benar (+628xxx)")
        print("  - Kode OTP dimasukkan dengan benar")
        print("  - Password 2FA benar (jika diaktifkan)")
        sys.exit(1)
    
    # Auto-save to .env
    print("\nLangkah 5/5: Menyimpan ke file .env")
    print("-" * 60)
    
    env_path = get_env_path()
    
    if write_env_file(env_path, session_string):
        print(f"✓ Session string tersimpan di: {env_path}")
        print("\n" + "="*60)
        print("  ✓ SETUP SELESAI!")
        print("="*60)
        print("\nAkun assistant sudah dikonfigurasi!")
        print("\nLangkah selanjutnya:")
        print("  1. Pastikan semua konfigurasi di .env sudah benar")
        print("  2. Jalankan bot: python main.py")
        print("\nAkun assistant akan:")
        print("  - Otomatis join voice chat saat dibutuhkan")
        print("  - Stream audio/video untuk perintah /play dan /vplay")
        print("\n⚠ PENTING: Rahasiakan file .env!")
        print("   STRING_SESSION = akses penuh ke akun")
        print("="*60 + "\n")
    else:
        print("\n⚠ Warning: Tidak bisa save otomatis ke .env")
        print("\nSilakan tambahkan manual ke file .env:")
        print("-" * 60)
        print(f'STRING_SESSION="{session_string}"')
        print("-" * 60 + "\n")
    
    # Also save to backup file
    try:
        backup_file = Path(__file__).parent / "string_session.txt"
        with open(backup_file, 'w', encoding='utf-8') as f:
            f.write(f"STRING_SESSION=\"{session_string}\"\n")
        print(f"✓ Backup tersimpan di: {backup_file}")
    except:
        pass


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n❌ Dibatalkan oleh user")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
