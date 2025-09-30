#!/usr/bin/env python3
"""
Music Manager with yt-dlp Integration
Handles music download, playback controls, and inline keyboards

Author: VanZoel112
Version: 2.0.0 Python
"""

import asyncio
import logging
import os
import json
import time
from typing import Dict, Optional, List, Tuple
from pathlib import Path
import aiohttp
import aiofiles
from telethon import Button
import config

logger = logging.getLogger(__name__)

try:
    import yt_dlp
    YTDLP_AVAILABLE = True
except ImportError:
    YTDLP_AVAILABLE = False
    logger.warning("yt-dlp not available, music features will be limited")

class MusicManager:
    """Manages music download and playback using yt-dlp"""

    def __init__(self):
        self.download_path = Path(config.DOWNLOAD_PATH)
        self.download_path.mkdir(exist_ok=True)

        # Current playback state per chat
        self.playback_state: Dict[int, Dict] = {}

        # Download cache
        self.download_cache: Dict[str, str] = {}

        # Rate limiting
        self.last_download: Dict[int, float] = {}

    async def search_music(self, query: str, max_results: int = 5) -> List[Dict]:
        """Search for music using yt-dlp"""
        if not YTDLP_AVAILABLE:
            return []

        try:
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'extract_flat': True,
                'default_search': 'ytsearch',
            }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                search_results = ydl.extract_info(
                    f"ytsearch{max_results}:{query}",
                    download=False
                )

            results = []
            if search_results and 'entries' in search_results:
                for entry in search_results['entries']:
                    if entry:
                        results.append({
                            'id': entry.get('id', ''),
                            'title': entry.get('title', 'Unknown'),
                            'url': entry.get('url', ''),
                            'duration': entry.get('duration', 0),
                            'uploader': entry.get('uploader', 'Unknown'),
                            'view_count': entry.get('view_count', 0)
                        })

            return results

        except Exception as e:
            logger.error(f"Error searching music: {e}")
            return []

    async def download_audio(self, url: str, user_id: int) -> Optional[Dict]:
        """Download audio from URL"""
        if not YTDLP_AVAILABLE:
            return None

        # Rate limiting check
        current_time = time.time()
        if user_id in self.last_download:
            if current_time - self.last_download[user_id] < self.config.music_cooldown:
                raise Exception(f"Rate limited. Wait {self.config.music_cooldown} seconds between downloads.")

        try:
            # Check cache first
            if url in self.download_cache:
                file_path = self.download_cache[url]
                if os.path.exists(file_path):
                    return {"file_path": file_path, "cached": True}

            # Download options
            output_template = str(self.download_path / "%(title)s.%(ext)s")
            ydl_opts = {
                'format': self.config.music.audio_quality,
                'outtmpl': output_template,
                'noplaylist': True,
                'extractaudio': True,
                'audioformat': 'mp3',
                'audioquality': '192K',
                'quiet': True,
                'no_warnings': True,
            }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # Extract info first
                info = ydl.extract_info(url, download=False)

                # Check file size
                filesize = info.get('filesize') or info.get('filesize_approx', 0)
                if filesize > self.config.music.max_file_size:
                    raise Exception(f"File too large: {filesize} bytes (max: {self.config.music.max_file_size})")

                # Download
                ydl.download([url])

                # Find downloaded file
                title = info.get('title', 'audio')
                possible_files = list(self.download_path.glob(f"{title}.*"))

                if possible_files:
                    downloaded_file = str(possible_files[0])

                    # Update cache and rate limiting
                    self.download_cache[url] = downloaded_file
                    self.last_download[user_id] = current_time

                    return {
                        "file_path": downloaded_file,
                        "title": title,
                        "duration": info.get('duration', 0),
                        "uploader": info.get('uploader', 'Unknown'),
                        "cached": False
                    }

            return None

        except Exception as e:
            logger.error(f"Error downloading audio: {e}")
            raise

    def create_music_keyboard(self, chat_id: int, song_id: str) -> List[List[Button]]:
        """Create inline keyboard for music controls"""
        state = self.playback_state.get(chat_id, {})
        is_playing = state.get('playing', False)

        keyboard = [
            [
                Button.inline("⏮️", f"music_prev_{chat_id}_{song_id}"),
                Button.inline("⏸️" if is_playing else "▶️", f"music_play_{chat_id}_{song_id}"),
                Button.inline("⏭️", f"music_next_{chat_id}_{song_id}")
            ],
            [
                Button.inline("🔊", f"music_volume_{chat_id}_{song_id}"),
                Button.inline("🔄", f"music_repeat_{chat_id}_{song_id}"),
                Button.inline("❌", f"music_stop_{chat_id}_{song_id}")
            ]
        ]

        return keyboard

    async def handle_music_callback(self, client, event):
        """Handle music control callbacks"""
        data = event.data.decode('utf-8')
        parts = data.split('_')

        if len(parts) < 4:
            return

        action = parts[1]
        chat_id = int(parts[2])
        song_id = parts[3]

        try:
            if action == "play":
                await self.toggle_playback(chat_id, song_id)
            elif action == "prev":
                await self.previous_track(chat_id)
            elif action == "next":
                await self.next_track(chat_id)
            elif action == "stop":
                await self.stop_playback(chat_id)
            elif action == "volume":
                await self.show_volume_controls(event)
            elif action == "repeat":
                await self.toggle_repeat(chat_id)

            # Update keyboard
            new_keyboard = self.create_music_keyboard(chat_id, song_id)
            await event.edit(buttons=new_keyboard)

        except Exception as e:
            logger.error(f"Error handling music callback: {e}")
            await event.answer("Error processing music control", alert=True)

    async def toggle_playback(self, chat_id: int, song_id: str):
        """Toggle play/pause"""
        if chat_id not in self.playback_state:
            self.playback_state[chat_id] = {'playing': False, 'current_song': song_id}

        state = self.playback_state[chat_id]
        state['playing'] = not state.get('playing', False)
        state['current_song'] = song_id

        logger.info(f"Toggled playback for chat {chat_id}: {'playing' if state['playing'] else 'paused'}")

    async def previous_track(self, chat_id: int):
        """Go to previous track"""
        state = self.playback_state.get(chat_id, {})
        # Implementation would depend on playlist management
        logger.info(f"Previous track for chat {chat_id}")

    async def next_track(self, chat_id: int):
        """Go to next track"""
        state = self.playback_state.get(chat_id, {})
        # Implementation would depend on playlist management
        logger.info(f"Next track for chat {chat_id}")

    async def stop_playback(self, chat_id: int):
        """Stop playback"""
        if chat_id in self.playback_state:
            self.playback_state[chat_id]['playing'] = False
        logger.info(f"Stopped playback for chat {chat_id}")

    async def show_volume_controls(self, event):
        """Show volume control options"""
        volume_keyboard = [
            [
                Button.inline("🔇", "volume_mute"),
                Button.inline("🔉", "volume_low"),
                Button.inline("🔊", "volume_high")
            ],
            [Button.inline("🔙 Back", "music_back")]
        ]
        await event.edit("🔊 Volume Control:", buttons=volume_keyboard)

    async def toggle_repeat(self, chat_id: int):
        """Toggle repeat mode"""
        if chat_id not in self.playback_state:
            self.playback_state[chat_id] = {}

        state = self.playback_state[chat_id]
        state['repeat'] = not state.get('repeat', False)
        logger.info(f"Toggled repeat for chat {chat_id}: {state['repeat']}")

    def get_playback_status(self, chat_id: int) -> Dict:
        """Get current playback status"""
        return self.playback_state.get(chat_id, {
            'playing': False,
            'current_song': None,
            'repeat': False
        })

    async def cleanup_old_downloads(self, max_age_hours: int = 24):
        """Clean up old downloaded files"""
        try:
            current_time = time.time()
            max_age_seconds = max_age_hours * 3600

            for file_path in self.download_path.glob("*"):
                if file_path.is_file():
                    file_age = current_time - file_path.stat().st_mtime
                    if file_age > max_age_seconds:
                        file_path.unlink()
                        logger.info(f"Cleaned up old download: {file_path.name}")

            # Clean cache entries for deleted files
            self.download_cache = {
                url: path for url, path in self.download_cache.items()
                if os.path.exists(path)
            }

        except Exception as e:
            logger.error(f"Error cleaning up downloads: {e}")

    async def get_download_stats(self) -> Dict:
        """Get download statistics"""
        try:
            download_files = list(self.download_path.glob("*"))
            total_files = len(download_files)
            total_size = sum(f.stat().st_size for f in download_files if f.is_file())

            return {
                'total_files': total_files,
                'total_size_mb': round(total_size / (1024 * 1024), 2),
                'cache_entries': len(self.download_cache),
                'active_chats': len(self.playback_state)
            }

        except Exception as e:
            logger.error(f"Error getting download stats: {e}")
            return {}

    def format_duration(self, seconds: int) -> str:
        """Format duration in MM:SS format"""
        if not seconds:
            return "Unknown"

        minutes, seconds = divmod(int(seconds), 60)
        return f"{minutes:02d}:{seconds:02d}"

    def format_music_info(self, info: Dict) -> str:
        """Format music info for display"""
        title = info.get('title', 'Unknown')
        uploader = info.get('uploader', 'Unknown')
        duration = self.format_duration(info.get('duration', 0))

        return f"🎵 **{title}**\n👤 {uploader}\n⏱️ {duration}"