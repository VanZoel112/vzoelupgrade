"""
Music Manager with Voice Chat Streaming
Uses py-tgcalls for real-time audio streaming

Author: Vzoel Fox's
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
    from pytgcalls.types import MediaStream, AudioQuality, VideoQuality, GroupCallConfig
    PYTGCALLS_AVAILABLE = True
except ImportError:
    PYTGCALLS_AVAILABLE = False
    logger.warning("py-tgcalls not available - install with: pip install py-tgcalls")
    MediaStream = None
    AudioQuality = None
    VideoQuality = None
    GroupCallConfig = None


class MusicManager:
    """Music manager with voice chat streaming support"""

    def __init__(self, bot_client, assistant_client=None):
        self.bot_client = bot_client  # For sending messages
        self.assistant_client = assistant_client  # For voice chat streaming
        self.download_path = Path(config.DOWNLOAD_PATH)
        self.download_path.mkdir(exist_ok=True)

        # PyTgCalls instance
        self.pytgcalls = None
        self.streaming_available = PYTGCALLS_AVAILABLE and assistant_client is not None

        # Queue per chat
        self.queues: Dict[int, List[Dict]] = {}

        # Currently playing
        self.current_song: Dict[int, Dict] = {}

        # Streaming mode per chat ('audio' or 'video')
        self.stream_mode: Dict[int, str] = {}

        # Active voice chats
        self.active_calls: Dict[int, bool] = {}

        # Playback state
        self.paused: Dict[int, bool] = {}
        self.loop_mode: Dict[int, str] = {}  # 'off', 'current', 'all'
        self.volume: Dict[int, int] = {}  # 0-200

        # Rate limiting
        self.last_request: Dict[int, float] = {}

        # Cache for join_as entity
        self._join_as_cache = None
        self._join_as_resolved = False

        # Initialize PyTgCalls if available
        if self.streaming_available:
            try:
                self.pytgcalls = PyTgCalls(self.assistant_client)
                logger.info("PyTgCalls initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize PyTgCalls: {e}")
                self.streaming_available = False

    async def start(self):
        """Placeholder for any async initialisation if needed."""
        return True

    # ---------------------------------------------------------------------
    # Search & Download helpers
    # ---------------------------------------------------------------------

    async def search_song(self, query: str) -> Optional[Dict]:
        """Search a song using yt-dlp and return basic metadata dict."""
        if not YTDLP_AVAILABLE:
            return None

        ydl_opts = {
            "quiet": True,
            "default_search": "ytsearch",
            "noplaylist": True,
            "skip_download": True,
            "extract_flat": False,
        }

        # cookies handling
        if config.YOUTUBE_COOKIES_FROM_BROWSER:
            ydl_opts["cookiesfrombrowser"] = (config.YOUTUBE_COOKIES_FROM_BROWSER,)
        elif config.YOUTUBE_COOKIES_FILE and os.path.exists(config.YOUTUBE_COOKIES_FILE):
            ydl_opts["cookiefile"] = config.YOUTUBE_COOKIES_FILE

        def _extract():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(query, download=False)
                if "_type" in info and info["_type"] == "playlist":
                    entries = info.get("entries") or []
                    info = entries[0] if entries else None
                return info

        loop = asyncio.get_running_loop()
        info = await loop.run_in_executor(None, _extract)
        if not info:
            return None

        return {
            "title": info.get("title"),
            "url": info.get("url") or info.get("webpage_url"),
            "webpage_url": info.get("webpage_url") or info.get("original_url") or info.get("url"),
            "duration": info.get("duration"),
            "uploader": info.get("uploader"),
            "thumbnail": info.get("thumbnail"),
        }

    async def download_audio(self, url: str, title_prefix: str, audio_only: bool = True) -> Optional[str]:
        """Download media (audio/video) using yt-dlp and return file path."""
        if not YTDLP_AVAILABLE:
            return None

        safe_prefix = "".join(c for c in title_prefix if c.isalnum() or c in " _-").rstrip()
        outtmpl = str(self.download_path / f"{safe_prefix} - %(id)s.%(ext)s")

        ydl_opts = {
            "outtmpl": outtmpl,
            "quiet": True,
            "noplaylist": True,
            "restrictfilenames": True,
            "ignoreerrors": True,
            "nocheckcertificate": True,
            "concurrent_fragment_downloads": 4,
            "overwrites": True,
            "max_filesize": getattr(config, "MAX_FILE_SIZE", 50 * 1024 * 1024),
        }

        if audio_only:
            ydl_opts.update({
                "format": getattr(config, "AUDIO_QUALITY", "bestaudio[ext=m4a]/bestaudio"),
                "postprocessors": [
                    {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}
                ],
            })
        else:
            ydl_opts.update({"format": "bv*+ba/b"})

        if config.YOUTUBE_COOKIES_FROM_BROWSER:
            ydl_opts["cookiesfrombrowser"] = (config.YOUTUBE_COOKIES_FROM_BROWSER,)
        elif config.YOUTUBE_COOKIES_FILE and os.path.exists(config.YOUTUBE_COOKIES_FILE):
            ydl_opts["cookiefile"] = config.YOUTUBE_COOKIES_FILE

        def _download():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                if not info:
                    return None
                if "requested_downloads" in info and info["requested_downloads"]:
                    return info["requested_downloads"][0]["filepath"]
                if "ext" in info and "id" in info:
                    return (self.download_path / f"{safe_prefix} - {info['id']}.{info['ext']}").as_posix()
                return None

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _download)

    # ---------------------------------------------------------------------
    # Playback
    # ---------------------------------------------------------------------

    async def play_stream(self, chat_id: int, query: str, requester_id: int, audio_only: bool = True) -> Dict:
        """Play media in voice chat (streaming mode) or download if streaming unavailable

        Args:
            audio_only: If True, extract audio only (MP3). If False, keep video.
        """
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
                requested_mode = 'audio' if audio_only else 'video'
                active_mode = self.stream_mode.get(chat_id)

                if active_mode and active_mode != requested_mode:
                    return {
                        'success': False,
                        'error': 'Different media type already playing. Use /stop before switching between audio and video.'
                    }

                song_entry = {**song_info, 'audio_only': audio_only}

                # Check if already playing in this chat
                if chat_id in self.active_calls and self.active_calls[chat_id]:
                    # Add to queue
                    if chat_id not in self.queues:
                        self.queues[chat_id] = []
                    self.queues[chat_id].append(song_entry)
                    return {
                        'success': True,
                        'queued': True,
                        'position': len(self.queues[chat_id]),
                        'song': song_entry,
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
                    media_stream_kwargs = {
                        'media_path': youtube_url,
                        'audio_parameters': AudioQuality.HIGH,
                        'ytdlp_parameters': ytdlp_parameters
                    }

                    if audio_only:
                        media_stream_kwargs['video_parameters'] = None
                        media_stream_kwargs['video_flags'] = MediaStream.Flags.IGNORE
                    else:
                        media_stream_kwargs['video_parameters'] = VideoQuality.HD_720p
                        media_stream_kwargs['video_flags'] = MediaStream.Flags.AUTO_DETECT

                    media_stream = MediaStream(**media_stream_kwargs)

                    # Build group call config
                    group_config = await self._build_group_call_config(chat_id)

                    # Play in voice chat
                    await self.pytgcalls.play(
                        chat_id,
                        media_stream,
                        config=group_config
                    )

                    self.active_calls[chat_id] = True
                    self.current_song[chat_id] = {**song_entry}
                    self.stream_mode[chat_id] = requested_mode

                    logger.info(f"Started streaming in chat {chat_id}: {song_info['title']}")

                    return {
                        'success': True,
                        'song': song_entry,
                        'streaming': True,
                        'joined_vc': True
                    }

                except Exception as e:
                    logger.error(f"Error starting stream: {e}")
                    # Fallback to download mode
                    self.streaming_available = False

            # DOWNLOAD MODE - fallback if streaming not available
            logger.info("Using download mode (streaming not available)")

            song_entry = {**song_info, 'audio_only': audio_only}

            # Check if queue exists
            if chat_id in self.queues and len(self.queues[chat_id]) > 0:
                self.queues[chat_id].append(song_entry)
                return {
                    'success': True,
                    'queued': True,
                    'position': len(self.queues[chat_id]),
                    'song': song_entry,
                    'streaming': False
                }

            # Download media (audio or video based on audio_only parameter)
            file_path = await self.download_audio(song_info['url'], song_info['title'][:50], audio_only)

            if not file_path:
                media_type = "audio" if audio_only else "video"
                return {'success': False, 'error': f'Failed to download {media_type}'}

            download_entry = {**song_entry, 'file_path': file_path}
            self.current_song[chat_id] = download_entry

            return {
                'success': True,
                'song': download_entry,
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
            self.stream_mode.pop(chat_id, None)

            return True
        except Exception as e:
            logger.error(f"Error stopping: {e}")
            return False

    async def join_voice_chat(self, chat_id: int) -> bool:
        """Join voice chat without playing"""
        try:
            if not self.streaming_available or not self.pytgcalls:
                return False

            # Check if already in call
            if chat_id in self.active_calls and self.active_calls[chat_id]:
                return True

            # Note: PyTgCalls joins automatically when play() is called
            # This is a placeholder - actual join happens with first play
            logger.info(f"Voice chat connection ready for {chat_id}")
            return True

        except Exception as e:
            logger.error(f"Error preparing voice chat: {e}")
            return False

    async def leave_voice_chat(self, chat_id: int) -> bool:
        """Leave voice chat"""
        try:
            if self.pytgcalls and chat_id in self.active_calls:
                await self.pytgcalls.leave_call(chat_id)
                self.active_calls.pop(chat_id, None)
                self.stream_mode.pop(chat_id, None)
                logger.info(f"Left voice chat in {chat_id}")
                return True
            return False
        except Exception as e:
            logger.error(f"Error leaving voice chat: {e}")
            return False

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
        """Resolve join_as entity once and cache it."""
        if self._join_as_resolved:
            return self._join_as_cache
        self._join_as_resolved = True
        try:
            join_as = getattr(config, "VOICE_CHAT_JOIN_AS", None)
            if not join_as:
                self._join_as_cache = None
            else:
                self._join_as_cache = join_as
        except Exception:
            self._join_as_cache = None
        return self._join_as_cache

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

    async def skip_song(self, chat_id: int) -> Dict:
        """Skip to next song in queue"""
        try:
            if chat_id not in self.queues or len(self.queues[chat_id]) == 0:
                # No songs in queue
                await self.stop_stream(chat_id)
                return {'success': False, 'error': 'No songs in queue'}

            # Get next song
            next_song = self.queues[chat_id].pop(0)
            audio_only = next_song.get('audio_only', True)

            # Stop current song
            if self.streaming_available and chat_id in self.active_calls:
                await self.pytgcalls.leave_call(chat_id)
                self.active_calls.pop(chat_id, None)

            # Play next song
            if self.streaming_available and self.pytgcalls:
                youtube_url = next_song.get('webpage_url')

                # Build yt-dlp parameters
                ytdlp_params = []
                if config.YOUTUBE_COOKIES_FROM_BROWSER:
                    ytdlp_params.append(f'--cookies-from-browser {config.YOUTUBE_COOKIES_FROM_BROWSER}')
                elif config.YOUTUBE_COOKIES_FILE and os.path.exists(config.YOUTUBE_COOKIES_FILE):
                    ytdlp_params.append(f'--cookies {config.YOUTUBE_COOKIES_FILE}')

                ytdlp_parameters = ' '.join(ytdlp_params) if ytdlp_params else None

                media_stream_kwargs = {
                    'media_path': youtube_url,
                    'audio_parameters': AudioQuality.HIGH,
                    'ytdlp_parameters': ytdlp_parameters
                }

                if audio_only:
                    media_stream_kwargs['video_parameters'] = None
                    media_stream_kwargs['video_flags'] = MediaStream.Flags.IGNORE
                else:
                    media_stream_kwargs['video_parameters'] = VideoQuality.HD_720p
                    media_stream_kwargs['video_flags'] = MediaStream.Flags.AUTO_DETECT

                media_stream = MediaStream(**media_stream_kwargs)

                group_config = await self._build_group_call_config(chat_id)
                await self.pytgcalls.play(chat_id, media_stream, config=group_config)

                self.active_calls[chat_id] = True
                self.current_song[chat_id] = next_song
                self.stream_mode[chat_id] = 'audio' if audio_only else 'video'

                return {
                    'success': True,
                    'song': next_song,
                    'remaining': len(self.queues[chat_id])
                }

            return {'success': False, 'error': 'Streaming not available'}

        except Exception as e:
            logger.error(f"Error skipping song: {e}")
            return {'success': False, 'error': str(e)}

    async def shuffle_queue(self, chat_id: int) -> bool:
        """Shuffle the queue"""
        try:
            import random
            if chat_id in self.queues and len(self.queues[chat_id]) > 0:
                random.shuffle(self.queues[chat_id])
                logger.info(f"Shuffled queue in {chat_id}")
                return True
            return False
        except Exception as e:
            logger.error(f"Error shuffling queue: {e}")
            return False
