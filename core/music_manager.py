#!/usr/bin/env python3
"""
Music Manager with Voice Chat Streaming
Uses py-tgcalls for real-time audio streaming

Author: VanZoel112
Version: 2.1.0 Python (Streaming)
"""

import asyncio
import logging
import os
import time
from typing import Dict, Optional, List
from pathlib import Path
import config

logger = logging.getLogger(__name__)

try:
    import yt_dlp
    YTDLP_AVAILABLE = True
except ImportError:
    YTDLP_AVAILABLE = False
    logger.warning("yt-dlp not available")

try:
    from pytgcalls import PyTgCalls
    from pytgcalls.types import MediaStream, AudioQuality, GroupCallConfig
    PYTGCALLS_AVAILABLE = True
except ImportError:
    PYTGCALLS_AVAILABLE = False
    logger.warning("py-tgcalls not available - install with: pip install py-tgcalls")
    MediaStream = None
    AudioQuality = None
    GroupCallConfig = None

class MusicManager:
    """Music manager with voice chat streaming support"""

    def __init__(self, client):
        self.client = client
        self.download_path = Path(config.DOWNLOAD_PATH)
        self.download_path.mkdir(exist_ok=True)

        # PyTgCalls instance
        self.pytgcalls = None
        self.streaming_available = PYTGCALLS_AVAILABLE

        # Queue per chat
        self.queues: Dict[int, List[Dict]] = {}

        # Currently playing
        self.current_song: Dict[int, Dict] = {}

        # Active voice chats
        self.active_calls: Dict[int, bool] = {}

        # Rate limiting
        self.last_request: Dict[int, float] = {}

        # Cache for join_as entity
        self._join_as_cache = None
        self._join_as_resolved = False

        # Initialize PyTgCalls if available
        if self.streaming_available:
            try:
                self.pytgcalls = PyTgCalls(client)
                logger.info("PyTgCalls initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize PyTgCalls: {e}")
                self.streaming_available = False

    async def start(self):
        """Start music manager"""
        if self.pytgcalls and self.streaming_available:
            try:
                await self.pytgcalls.start()
                logger.info("🎵 Music streaming system ready (voice chat mode)")
            except Exception as e:
                logger.error(f"Failed to start PyTgCalls: {e}")
                self.streaming_available = False

        if not self.streaming_available:
            logger.info("🎵 Music system ready (download mode - no streaming)")

    async def stop(self):
        """Stop music manager and leave all voice chats"""
        if self.pytgcalls:
            try:
                # Leave all active voice chats
                for chat_id in list(self.active_calls.keys()):
                    await self.leave_voice_chat(chat_id)
                logger.info("Stopped music manager")
            except Exception as e:
                logger.error(f"Error stopping music manager: {e}")

    async def search_song(self, query: str) -> Optional[Dict]:
        """Search for song on YouTube"""
        if not YTDLP_AVAILABLE:
            return None

        try:
            ydl_opts = {
                'format': 'bestaudio/best',
                'noplaylist': True,
                'quiet': True,
                'no_warnings': True,
                'extract_flat': False,
            }

            # Add cookies if configured
            if config.YOUTUBE_COOKIES_FROM_BROWSER:
                ydl_opts['cookiesfrombrowser'] = (config.YOUTUBE_COOKIES_FROM_BROWSER,)
            elif config.YOUTUBE_COOKIES_FILE and os.path.exists(config.YOUTUBE_COOKIES_FILE):
                ydl_opts['cookiefile'] = config.YOUTUBE_COOKIES_FILE

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # Search YouTube
                search_query = f"ytsearch:{query}" if not query.startswith('http') else query
                info = ydl.extract_info(search_query, download=False)

                if 'entries' in info:
                    info = info['entries'][0]

                return {
                    'title': info.get('title', 'Unknown'),
                    'url': info.get('url'),
                    'webpage_url': info.get('webpage_url'),
                    'duration': info.get('duration', 0),
                    'thumbnail': info.get('thumbnail'),
                }

        except Exception as e:
            logger.error(f"Error searching song: {e}")
            return None

    async def download_audio(self, url: str, title: str) -> Optional[str]:
        """Download audio from YouTube"""
        if not YTDLP_AVAILABLE:
            return None

        try:
            # Output path
            output_template = str(self.download_path / f"{title}.%(ext)s")

            ydl_opts = {
                'format': 'bestaudio/best',
                'outtmpl': output_template,
                'noplaylist': True,
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
                'quiet': True,
                'no_warnings': True,
            }

            # Add cookies
            if config.YOUTUBE_COOKIES_FROM_BROWSER:
                ydl_opts['cookiesfrombrowser'] = (config.YOUTUBE_COOKIES_FROM_BROWSER,)
            elif config.YOUTUBE_COOKIES_FILE and os.path.exists(config.YOUTUBE_COOKIES_FILE):
                ydl_opts['cookiefile'] = config.YOUTUBE_COOKIES_FILE

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])

            # Find downloaded file
            for ext in ['mp3', 'm4a', 'webm', 'opus']:
                file_path = self.download_path / f"{title}.{ext}"
                if file_path.exists():
                    return str(file_path)

            return None

        except Exception as e:
            logger.error(f"Error downloading audio: {e}")
            return None

    async def play_stream(self, chat_id: int, query: str, requester_id: int) -> Dict:
        """Play audio in voice chat (streaming mode) or download if streaming unavailable"""
        # Rate limiting
        current_time = time.time()
        if requester_id in self.last_request:
            if current_time - self.last_request[requester_id] < config.MUSIC_COOLDOWN:
                return {
                    'success': False,
                    'error': f"Please wait {config.MUSIC_COOLDOWN} seconds between requests"
                }

        self.last_request[requester_id] = current_time

        try:
            # Search song
            song_info = await self.search_song(query)
            if not song_info:
                return {'success': False, 'error': 'Song not found'}

            # STREAMING MODE - if py-tgcalls available
            if self.streaming_available and self.pytgcalls:
                # Check if already playing in this chat
                if chat_id in self.active_calls and self.active_calls[chat_id]:
                    # Add to queue
                    if chat_id not in self.queues:
                        self.queues[chat_id] = []
                    self.queues[chat_id].append(song_info)
                    return {
                        'success': True,
                        'queued': True,
                        'position': len(self.queues[chat_id]),
                        'song': song_info,
                        'streaming': True
                    }

                # Join voice chat and play
                try:
                    # Use YouTube URL for streaming
                    youtube_url = song_info.get('webpage_url')

                    # Build yt-dlp parameters with cookies
                    ytdlp_params = []
                    if config.YOUTUBE_COOKIES_FROM_BROWSER:
                        ytdlp_params.append(f'--cookies-from-browser {config.YOUTUBE_COOKIES_FROM_BROWSER}')
                    elif config.YOUTUBE_COOKIES_FILE and os.path.exists(config.YOUTUBE_COOKIES_FILE):
                        ytdlp_params.append(f'--cookies {config.YOUTUBE_COOKIES_FILE}')

                    ytdlp_parameters = ' '.join(ytdlp_params) if ytdlp_params else None

                    # Create MediaStream with YouTube URL
                    media_stream = MediaStream(
                        youtube_url,
                        AudioQuality.HIGH,
                        ytdlp_parameters=ytdlp_parameters
                    )

                    # Build group call config
                    group_config = await self._build_group_call_config(chat_id)

                    # Play in voice chat
                    await self.pytgcalls.play(
                        chat_id,
                        media_stream,
                        config=group_config
                    )

                    self.active_calls[chat_id] = True
                    self.current_song[chat_id] = song_info

                    logger.info(f"Started streaming in chat {chat_id}: {song_info['title']}")

                    return {
                        'success': True,
                        'song': song_info,
                        'streaming': True,
                        'joined_vc': True
                    }

                except Exception as e:
                    logger.error(f"Error starting stream: {e}")
                    # Fallback to download mode
                    self.streaming_available = False

            # DOWNLOAD MODE - fallback if streaming not available
            logger.info("Using download mode (streaming not available)")

            # Check if queue exists
            if chat_id in self.queues and len(self.queues[chat_id]) > 0:
                self.queues[chat_id].append(song_info)
                return {
                    'success': True,
                    'queued': True,
                    'position': len(self.queues[chat_id]),
                    'song': song_info,
                    'streaming': False
                }

            # Download audio
            file_path = await self.download_audio(song_info['url'], song_info['title'][:50])

            if not file_path:
                return {'success': False, 'error': 'Failed to download audio'}

            self.current_song[chat_id] = {
                **song_info,
                'file_path': file_path
            }

            return {
                'success': True,
                'song': song_info,
                'file_path': file_path,
                'streaming': False
            }

        except Exception as e:
            logger.error(f"Error in play_stream: {e}")
            return {'success': False, 'error': str(e)}

    async def stop_stream(self, chat_id: int) -> bool:
        """Stop stream and leave voice chat"""
        try:
            # Leave voice chat if in streaming mode
            if self.streaming_available and chat_id in self.active_calls:
                await self.leave_voice_chat(chat_id)

            # Clear queue and current song
            if chat_id in self.queues:
                self.queues[chat_id].clear()
            if chat_id in self.current_song:
                del self.current_song[chat_id]

            return True
        except Exception as e:
            logger.error(f"Error stopping: {e}")
            return False

    async def leave_voice_chat(self, chat_id: int):
        """Leave voice chat"""
        try:
            if self.pytgcalls and chat_id in self.active_calls:
                await self.pytgcalls.leave_call(chat_id)
                self.active_calls.pop(chat_id, None)
                logger.info(f"Left voice chat in {chat_id}")
        except Exception as e:
            logger.error(f"Error leaving voice chat: {e}")

    async def _build_group_call_config(self, chat_id: int) -> Optional['GroupCallConfig']:
        """Build group call configuration with optional join_as resolution"""
        if not self.pytgcalls or not GroupCallConfig:
            return None

        auto_start = getattr(config, 'VOICE_CHAT_AUTO_START', True)
        config_kwargs = {'auto_start': auto_start}

        join_as = await self._get_join_as_entity()
        if join_as is not None:
            config_kwargs['join_as'] = join_as

        try:
            return GroupCallConfig(**config_kwargs)
        except Exception as exc:
            logger.warning(f"Failed to build GroupCallConfig for chat {chat_id}: {exc}")
            return GroupCallConfig()

    async def _get_join_as_entity(self):
        """Resolve VOICE_CHAT_JOIN_AS setting to an entity once"""
        if self._join_as_resolved:
            return self._join_as_cache

        self._join_as_resolved = True
        join_as = getattr(config, 'VOICE_CHAT_JOIN_AS', None)

        if join_as in (None, ''):
            self._join_as_cache = None
            return None

        try:
            if isinstance(join_as, str) and join_as.lower() in {'me', 'self'}:
                entity = await self.client.get_me()
            else:
                entity = await self.client.get_entity(join_as)
            self._join_as_cache = entity
        except Exception as exc:
            logger.warning(f"Failed to resolve VOICE_CHAT_JOIN_AS='{join_as}': {exc}")
            self._join_as_cache = None

        return self._join_as_cache

    async def pause_stream(self, chat_id: int) -> bool:
        """Pause current stream"""
        try:
            if self.streaming_available and self.pytgcalls and chat_id in self.active_calls:
                await self.pytgcalls.pause_stream(chat_id)
                logger.info(f"Paused stream in {chat_id}")
                return True
        except Exception as e:
            logger.error(f"Error pausing: {e}")
        return False

    async def resume_stream(self, chat_id: int) -> bool:
        """Resume paused stream"""
        try:
            if self.streaming_available and self.pytgcalls and chat_id in self.active_calls:
                await self.pytgcalls.resume_stream(chat_id)
                logger.info(f"Resumed stream in {chat_id}")
                return True
        except Exception as e:
            logger.error(f"Error resuming: {e}")
        return False

    def get_current_song(self, chat_id: int) -> Optional[Dict]:
        """Get current song"""
        return self.current_song.get(chat_id)

    def get_queue(self, chat_id: int) -> List[Dict]:
        """Get queue"""
        return self.queues.get(chat_id, [])

    def get_stream_stats(self) -> Dict:
        """Get streaming statistics"""
        return {
            'active_songs': len(self.current_song),
            'active_calls': len(self.active_calls),
            'total_queued': sum(len(q) for q in self.queues.values()),
            'mode': 'streaming' if self.streaming_available else 'download',
            'streaming_available': self.streaming_available
        }
