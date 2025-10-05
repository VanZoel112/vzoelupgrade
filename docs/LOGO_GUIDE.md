# Logo Configuration Guide

## Overview

VBot memiliki 2 jenis logo yang dapat dikonfigurasi:

1. **Branding Image** - Logo resmi VBot untuk display branding
2. **Music Logo** - Cover art untuk music playback

---

## 1. Branding Image

### Lokasi File
```
assets/branding/vbot_branding.png
```

### Status
✅ **Sudah Tersedia** - File branding image sudah ada dan siap digunakan (1.3MB)

### Cara Menggunakan
- Otomatis dimuat oleh bot saat startup
- Bisa diakses via callback button "VBOT" di menu /start
- Test dengan command: `/showbranding`

---

## 2. Music Logo

### Problem
File ID untuk music logo bisa **expired** jika:
- File asli dihapus dari Telegram
- Sudah terlalu lama (cache Telegram)
- Bot di-redeploy tanpa backup

### Solusi: Set Logo Baru

#### Metode 1: Reply ke Foto (Termudah)
```
1. Upload foto logo ke private chat bot
2. Reply foto dengan: /setlogo
3. ✅ Selesai!
```

#### Metode 2: Menggunakan File ID
```
1. Upload foto logo
2. Reply dengan: /getfileid
3. Copy file_id yang muncul
4. Gunakan: /setlogo <file_id>
```

#### Metode 3: Reset Logo
```
/setlogo reset
```

---

## Commands Reference

### Diagnostic Commands

| Command | Fungsi |
|---------|--------|
| `/testlogo` | Cek status konfigurasi logo (branding & music) |
| `/showbranding` | Tampilkan branding image |
| `/fixlogo` | Panduan lengkap memperbaiki logo |

### Configuration Commands (Developer Only)

| Command | Fungsi |
|---------|--------|
| `/setlogo` (reply) | Set music logo dari foto yang direply |
| `/setlogo <file_id>` | Set music logo dari file ID |
| `/setlogo reset` | Reset music logo configuration |
| `/getfileid` (reply) | Dapatkan file_id dari media |

---

## Troubleshooting

### Logo Tidak Muncul di Music Player

**Gejala:**
- Command `/play` atau `/vplay` tidak menampilkan logo
- Hanya text tanpa gambar

**Penyebab:**
- File ID expired
- Logo belum di-set

**Solusi:**
1. Test status: `/testlogo`
2. Click button "🎵 Test Music Logo"
3. Jika gagal, upload logo baru
4. Reply dengan `/setlogo`

### Branding Image Tidak Muncul

**Gejala:**
- Button "VBOT" tidak mengirim gambar
- `/showbranding` menunjukkan error

**Penyebab:**
- File `assets/branding/vbot_branding.png` hilang atau corrupt

**Solusi:**
1. Cek file exists:
   ```bash
   ls -lh assets/branding/vbot_branding.png
   ```
2. Jika hilang, restore dari backup atau upload ulang

---

## Technical Details

### File ID System
- Telegram menyimpan media sebagai File ID (unique identifier)
- File ID bersifat **persistent** selama file asli tidak dihapus
- Bot menyimpan File ID di config untuk re-use

### Storage Locations
```
Config:
- config.MUSIC_LOGO_FILE_ID (default atau custom)
- config.MUSIC_LOGO_FILE_PATH (optional local path)

Runtime:
- bot._music_logo_file_id (runtime cache)
- bot._music_logo_file_path (runtime cache)
```

### Fallback System
Bot mencoba beberapa source secara berurutan:
1. File ID yang di-set via `/setlogo`
2. Local file path (jika ada)
3. Default config File ID
4. Jika semua gagal → text only

---

## Quick Reference

### Problem: "Logo tidak terlihat"

**Langkah cepat:**
```bash
# 1. Test status
/testlogo

# 2. Click button test yang sesuai

# 3. Jika gagal, set logo baru:
#    - Upload foto logo
#    - Reply dengan: /setlogo

# 4. Test lagi
/testlogo
```

### Auto-Fix Workflow

Gunakan plugin logo helper yang sudah tersedia:
```
/fixlogo  → Panduan lengkap step-by-step
/testlogo → Diagnostic dengan button interaktif
/showbranding → Test branding image
```

---

## Developer Notes

### Adding Logo to Music Commands

Logo otomatis ditambahkan via method:
```python
await self._send_music_logo_message(
    chat_id=chat_id,
    caption=formatted_caption,
    buttons=buttons
)
```

### Updating Logo Configuration

Update runtime dan persistent config:
```python
await self._persist_music_logo_settings(
    file_id="AgACAgUAAxUAAWjhWkqSMG...",
    file_path="/path/to/logo.jpg"  # optional
)
```

---

**2025© VBot - Vzoel Fox's**
