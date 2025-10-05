# Panduan Kualitas Pemutaran Audio Tertinggi

Panduan ini membantu Anda mengatur VBot Python agar menghasilkan kualitas audio setinggi mungkin baik saat streaming di voice chat maupun saat mengunduh lagu.

## 1. Pastikan Dependensi Streaming Aktif

Fitur pengaturan bitrate streaming hanya aktif ketika bot dapat melakukan voice chat streaming melalui **PyTgCalls**. Pastikan Anda sudah:

1. Mengisi `STRING_SESSION` pada konfigurasi (lihat `config.py`).
2. Menginstal dependensi yang diperlukan di `requirements.txt`, termasuk `pytgcalls`.

Jika PyTgCalls tidak tersedia, VBot akan tetap berjalan tetapi tidak dapat menyesuaikan tingkat kualitas audio streaming otomatis.【F:core/music_manager.py†L28-L36】【F:core/music_manager.py†L388-L391】

## 2. Konfigurasi Streaming (Voice Chat)

Gunakan variabel lingkungan `STREAM_AUDIO_QUALITY` untuk menentukan profil bitrate saat streaming. Nilai default-nya adalah `8k` yang sudah diterjemahkan sebagai kualitas *studio* (paling tinggi). Anda bisa mengubah nilai ini di file `.env` atau `config_local.py`.

| Nilai yang Didukung | Profil Internal | Keterangan |
| --- | --- | --- |
| `studio`, `8k`, `96k`, `96khz`, `8000` | `AudioQuality.STUDIO` | Kualitas tertinggi, sample rate 48–96 kHz sesuai dukungan klien |
| `high`, `48k`, `48khz` | `AudioQuality.HIGH` | Bitrate tinggi, cocok untuk kebanyakan grup |
| `medium`, `36k`, `36khz` | `AudioQuality.MEDIUM` | Bitrate menengah |
| `low`, `24k`, `24khz` | `AudioQuality.LOW` | Bitrate rendah untuk koneksi lemah |

Untuk menjaga kualitas maksimum, pastikan `STREAM_AUDIO_QUALITY` diset ke salah satu alias *studio*. Jika Anda menuliskan angka lain dengan satuan `k`, sistem akan menaikkannya ke profil studio bila nilainya ≥ 80.【F:core/music_manager.py†L392-L426】【F:config.py†L84-L88】

### Contoh pengaturan `.env`
```env
STREAM_AUDIO_QUALITY=studio
```

## 3. Konfigurasi Unduhan (Mode MP3)

Saat Anda menggunakan mode unduhan, bot memanfaatkan yt-dlp + FFmpeg. Dua variabel berikut memengaruhi hasil audio:

- `AUDIO_QUALITY`: pemilihan format yt-dlp. Jika kosong atau berisi nilai bawaan `bestaudio[ext=m4a]/bestaudio`, bot otomatis menggantinya menjadi `bestaudio/best` agar selalu mengambil trek terbaik yang tersedia.
- `DOWNLOAD_AUDIO_BITRATE`: bitrate target untuk konversi MP3 melalui FFmpeg. Nilai numeric (mis. `320`) diasumsikan dalam kilobit per detik.

Untuk kualitas setinggi mungkin, gunakan kombinasi berikut:

```env
AUDIO_QUALITY=bestaudio/best
DOWNLOAD_AUDIO_BITRATE=320
```

Jika Anda mengisi angka non-numeric, bot akan kembali ke `320 kbps`. Nilai di atas 320 tidak memberikan manfaat karena encoder MP3 akan tetap dikunci pada batas maksimal codec.【F:core/music_manager.py†L167-L187】

## 4. Tips Tambahan

- **Pastikan FFmpeg Terpasang**: yt-dlp akan memanggil FFmpeg untuk mengekstrak audio. Tanpa FFmpeg, proses konversi MP3 gagal sehingga kualitas tertinggi tidak tercapai.
- **Periksa Batas File**: `MAX_FILE_SIZE` default 50 MB. Lagu lossless atau sangat panjang bisa melewati batas ini. Naikkan nilai tersebut jika Anda membutuhkan unduhan dengan bitrate tinggi.【F:core/music_manager.py†L162-L185】【F:config.py†L81-L87】
- **Gunakan Koneksi Stabil**: Kualitas tinggi membutuhkan bandwidth yang lebih besar ketika streaming. Pastikan jaringan akun asisten cukup baik agar tidak terjadi penurunan kualitas.

Dengan mengikuti langkah di atas, bot akan menggunakan format terbaik yang tersedia dan menjaga bitrate streaming maupun hasil unduhan di level tertinggi.
