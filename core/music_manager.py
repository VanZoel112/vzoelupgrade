"""
Music Manager with Voice Chat Streaming
Uses py-tgcalls for real-time audio streaming

Author: Vzoel Fox's
Version: 2.1.1 Python (Streaming)
"""

import asyncio
import logging
import os
import time
from typing import Dict, Optional, List, Tuple
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
    from pytgcalls.types import StreamEnded
    from pytgcalls.filters import stream_end as StreamEndFilter
    PYTGCALLS_AVAILABLE = True
except ImportError:
    PYTGCALLS_AVAILABLE = False
    logger.warning("py-tgcalls not available - install with: pip install py-tgcalls")
    MediaStream = None
    AudioQuality = None
    VideoQuality = None
    GroupCallConfig = None
    StreamEnded = None
    StreamEndFilter = None


class MusicManager:
    """Music manager with voice chat streaming support"""

    def __init__(self, bot_client, assistant_client=None, auth_manager=None):
        self.bot_client = bot_client  # For sending messages
        self.assistant_client = assistant_client  # For voice chat streaming
        self.auth_manager = auth_manager
        self.download_path = Path(config.DOWNLOAD_PATH)
        self.download_path.mkdir(exist_ok=True)

        # PyTgCalls instance
        self.pytgcalls = None
        self.streaming_available = PYTGCALLS_AVAILABLE and assistant_client is not None

        # Authorization caches & fallbacks
        self._developer_ids = set(getattr(config, "DEVELOPER_IDS", []) or [])
        self._owner_id = getattr(config, "OWNER_ID", 0) or 0
        self._access_cache: Dict[Tuple[int, int], Tuple[bool, float]] = {}
        self._access_cache_ttl = getattr(config, "MUSIC_ACCESS_CACHE_TTL", 120)

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
        self._ignored_stream_ends: Dict[int, int] = {}

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
                self._register_stream_events()
            except Exception as e:
                logger.error(f"Failed to initialize PyTgCalls: {e}")
                self.streaming_available = False

    async def start(self):
        """Initialise background clients such as PyTgCalls."""
        if self.pytgcalls:
            try:
                await self.pytgcalls.start()
                logger.info("PyTgCalls client started")
            except Exception as exc:
                logger.error(f"Failed to start PyTgCalls client: {exc}")
                self.streaming_available = False
                self.pytgcalls = None
        return True

    # ------------------------------------------------------------------
    # Authorization helpers
    # ------------------------------------------------------------------

    def _is_configured_developer(self, user_id: Optional[int]) -> bool:
        if not user_id:
            return False

        if self.auth_manager:
            if self.auth_manager.is_developer(user_id) or self.auth_manager.is_owner(user_id):
                return True

        if user_id in self._developer_ids:
            return True

        return bool(self._owner_id) and user_id == self._owner_id

    async def user_has_access(
        self,
        chat_id: Optional[int],
        user_id: Optional[int],
        client=None,
        *,
        use_cache: bool = True,
    ) -> bool:
        """Determine whether a user can control music in the given chat."""

        if not user_id or not chat_id:
            return False

        if self._is_configured_developer(user_id):
            return True

        cache_key = (chat_id, user_id)
        current_time = time.time()
        if use_cache and cache_key in self._access_cache:
            cached_allowed, cached_ts = self._access_cache[cache_key]
            if current_time - cached_ts < self._access_cache_ttl:
                return cached_allowed

        client = client or self.bot_client
        if client is None:
            return False

        allowed = False
        if self.auth_manager:
            try:
                allowed = await self.auth_manager.is_admin_in_chat(client, user_id, chat_id)
            except Exception:
                logger.warning("MusicManager failed to query AuthManager admin status", exc_info=True)
        else:
            try:
                perms = await client.get_permissions(chat_id, user_id)
            except Exception:
                logger.debug("MusicManager could not fetch chat permissions", exc_info=True)
            else:
                allowed = bool(getattr(perms, "is_admin", False) or getattr(perms, "is_creator", False))

        if use_cache:
            self._access_cache[cache_key] = (allowed, current_time)

        return allowed

    def clear_access_cache(self, chat_id: Optional[int] = None, user_id: Optional[int] = None):
        """Invalidate cached authorization decisions."""

        if chat_id is None and user_id is None:
            self._access_cache.clear()
            return

        keys_to_remove = []
        for cached_chat_id, cached_user_id in self._access_cache:
            if chat_id is not None and cached_chat_id != chat_id:
                continue
            if user_id is not None and cached_user_id != user_id:
                continue
            keys_to_remove.append((cached_chat_id, cached_user_id))

        for key in keys_to_remove:
            self._access_cache.pop(key, None)

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
            configured_quality = getattr(config, "AUDIO_QUALITY", None)
            if not configured_quality or configured_quality == "bestaudio[ext=m4a]/bestaudio":
                configured_quality = "bestaudio/best"
            bitrate = str(getattr(config, "DOWNLOAD_AUDIO_BITRATE", "320"))
            if not bitrate.isdigit():
                bitrate = "320"
            ydl_opts.update({
                "format": configured_quality,
                "postprocessors": [
                    {
                        "key": "FFmpegExtractAudio",
                        "preferredcodec": "mp3",
                        "preferredquality": bitrate,
                    }
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
        has_access = await self.user_has_access(chat_id, requester_id)
        if not has_access:
            logger.info(
                "Denied music control for user %s in chat %s", requester_id, chat_id
            )
            return {
                'success': False,
                'error': 'User is not permitted to control music in this chat',
                'error_code': 'not_authorized',
            }

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

            song_entry = self._build_song_entry(song_info, audio_only)

            # STREAMING MODE - if py-tgcalls available
            if self.streaming_available and self.pytgcalls:
                requested_mode = 'audio' if audio_only else 'video'
                active_mode = self.stream_mode.get(chat_id)

                if active_mode and active_mode != requested_mode:
                    return {
                        'success': False,
                        'error': 'Different media type already playing. Use /stop before switching between audio and video.'
                    }

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
                    await self._play_stream_entry(chat_id, song_entry)

                    logger.info(f"Started streaming in chat {chat_id}: {song_entry['title']}")

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
                self._ignored_stream_ends[chat_id] = self._ignored_stream_ends.get(chat_id, 0) + 1
                await self.leave_voice_chat(chat_id)

            # Clear queue and current song
            self.queues.pop(chat_id, None)
            self.current_song.pop(chat_id, None)
            self.active_calls.pop(chat_id, None)
            self.stream_mode.pop(chat_id, None)
            self.paused.pop(chat_id, None)
            self.loop_mode.pop(chat_id, None)
            self.volume.pop(chat_id, None)
            self._ignored_stream_ends.pop(chat_id, None)

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

    def _resolve_audio_quality(self):
        """Resolve preferred audio quality for streaming."""
        if not AudioQuality:
            return None

        preferred = str(getattr(config, "STREAM_AUDIO_QUALITY", "HIGH") or "HIGH").strip().lower()
        mapping = {
            "studio": AudioQuality.STUDIO,
            "high": AudioQuality.HIGH,
            "medium": AudioQuality.MEDIUM,
            "low": AudioQuality.LOW,
            "8k": AudioQuality.STUDIO,
            "8000": AudioQuality.STUDIO,
            "96k": AudioQuality.STUDIO,
            "96khz": AudioQuality.STUDIO,
            "48k": AudioQuality.HIGH,
            "48khz": AudioQuality.HIGH,
            "36k": AudioQuality.MEDIUM,
            "36khz": AudioQuality.MEDIUM,
            "24k": AudioQuality.LOW,
            "24khz": AudioQuality.LOW,
        }

        if preferred in mapping:
            return mapping[preferred]

        # Default to studio quality when requesting very high bitrates
        if preferred.endswith("k"):
            try:
                value = int(preferred[:-1])
                if value >= 80:
                    return AudioQuality.STUDIO
                if value >= 40:
                    return AudioQuality.HIGH
                if value >= 30:
                    return AudioQuality.MEDIUM
            except ValueError:
                pass

        return AudioQuality.HIGH

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
            if not self.streaming_available or not self.pytgcalls:
                return {'success': False, 'error': 'Streaming not available'}

            next_song = self._dequeue_next_song(chat_id)

            if not next_song:
                await self.stop_stream(chat_id)
                return {'success': False, 'error': 'Queue empty'}

            await self._play_stream_entry(chat_id, next_song)

            return {
                'success': True,
                'song': next_song,
                'remaining': len(self.queues.get(chat_id, []))
            }

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

    # ------------------------------------------------------------------
    # Public command helpers used by bot handlers
    # ------------------------------------------------------------------

    def _build_song_entry(self, info: Dict, audio_only: bool) -> Dict:
        """Normalise song information for queue handling."""
        entry = {
            'title': info.get('title'),
            'url': info.get('url') or info.get('webpage_url'),
            'webpage_url': info.get('webpage_url') or info.get('original_url') or info.get('url'),
            'duration': info.get('duration'),
            'uploader': info.get('uploader'),
            'thumbnail': info.get('thumbnail'),
            'audio_only': audio_only,
        }
        entry['duration_string'] = self._format_duration(entry.get('duration'))
        return entry

    def _format_duration(self, duration: Optional[int]) -> str:
        """Return hh:mm:ss/mm:ss formatted duration string."""
        if duration in (None, ""):
            return "Unknown"
        try:
            seconds = int(duration)
        except (TypeError, ValueError):
            return "Unknown"
        if seconds < 0:
            return "Unknown"
        minutes, sec = divmod(seconds, 60)
        hours, minutes = divmod(minutes, 60)
        if hours:
            return f"{hours:02d}:{minutes:02d}:{sec:02d}"
        return f"{minutes:02d}:{sec:02d}"

    async def pause(self, chat_id: int) -> str:
        """Pause the active stream."""
        if not self.streaming_available or not self.pytgcalls:
            return "Error: Pause only available in streaming mode"
        if chat_id not in self.active_calls:
            return "Error: Nothing is playing"
        if self.paused.get(chat_id):
            return "Error: Stream already paused"
        try:
            await self.pytgcalls.pause(chat_id)
            self.paused[chat_id] = True
            return "⏸️ Paused"
        except Exception as exc:
            logger.error(f"Pause failed in chat {chat_id}: {exc}")
            return f"Error pausing: {exc}"

    async def resume(self, chat_id: int) -> str:
        """Resume a paused stream."""
        if not self.streaming_available or not self.pytgcalls:
            return "Error: Resume only available in streaming mode"
        if chat_id not in self.active_calls:
            return "Error: Nothing is playing"
        if not self.paused.get(chat_id):
            return "Error: Stream is already playing"
        try:
            await self.pytgcalls.resume(chat_id)
            self.paused[chat_id] = False
            return "▶️ Resumed"
        except Exception as exc:
            logger.error(f"Resume failed in chat {chat_id}: {exc}")
            return f"Error resuming: {exc}"

    async def stop(self, chat_id: int) -> str:
        """Stop playback and clear queue."""
        stopped = await self.stop_stream(chat_id)
        if stopped:
            return "Stopped playback and cleared queue"
        return "Error: Nothing to stop"

    async def skip(self, chat_id: int) -> str:
        """Skip to the next song in queue."""
        result = await self.skip_song(chat_id)
        if result.get('success'):
            song = result.get('song', {})
            title = song.get('title', 'Unknown')
            remaining = result.get('remaining', 0)
            return f"Skipped to **{title}**\n**Queue:** {remaining} remaining"
        return f"Error: {result.get('error', 'Unable to skip')}"

    async def show_queue(self, chat_id: int) -> str:
        """Return a formatted queue list."""
        current = self.current_song.get(chat_id)
        queue = self.queues.get(chat_id, [])
        if not current and not queue:
            return "Queue kosong"

        lines = ["**Music Queue**"]
        loop_mode = self.loop_mode.get(chat_id, 'off')
        if loop_mode != 'off':
            loop_label = {
                'current': 'current track',
                'all': 'entire queue'
            }.get(loop_mode, loop_mode)
            lines.append(f"**Loop:** {loop_label}")

        if current:
            lines.append(
                f"**Now Playing:** {current.get('title', 'Unknown')} ({current.get('duration_string', 'Unknown')})"
            )
        if queue:
            lines.append("\n**Up Next:**")
            for index, item in enumerate(queue, start=1):
                lines.append(
                    f"{index}. {item.get('title', 'Unknown')} ({item.get('duration_string', 'Unknown')})"
                )
        return "\n".join(lines)

    async def shuffle(self, chat_id: int) -> str:
        """Shuffle queue entries."""
        if chat_id not in self.queues or len(self.queues[chat_id]) < 2:
            return "Error: Queue kurang dari 2 lagu"
        success = await self.shuffle_queue(chat_id)
        return "Queue diacak" if success else "Error: Gagal mengacak queue"

    async def set_loop(self, chat_id: int, mode: str) -> str:
        """Configure loop behaviour."""
        valid_modes = {'off', 'current', 'all'}
        current_mode = self.loop_mode.get(chat_id, 'off')

        if mode == 'toggle':
            order = ['off', 'current', 'all']
            try:
                next_index = (order.index(current_mode) + 1) % len(order)
            except ValueError:
                next_index = 0
            new_mode = order[next_index]
        elif mode in {'single', 'song', 'track'}:
            new_mode = 'current'
        elif mode in {'queue'}:
            new_mode = 'all'
        elif mode in valid_modes:
            new_mode = mode
        else:
            return "Error: Mode loop tidak dikenal. Gunakan: off/current/all"

        if new_mode == 'off':
            self.loop_mode.pop(chat_id, None)
        else:
            self.loop_mode[chat_id] = new_mode

        human_readable = {
            'off': 'Loop dimatikan',
            'current': 'Loop lagu saat ini',
            'all': 'Loop seluruh queue'
        }
        return f"🔁 {human_readable.get(new_mode, new_mode)}"

    async def seek(self, chat_id: int, seconds: int) -> str:
        """Seek is not available because PyTgCalls does not expose this yet."""
        return "Error: Seek belum didukung"

    async def set_volume(self, chat_id: int, volume: int) -> str:
        """Adjust stream volume (0-200)."""
        if not self.streaming_available or not self.pytgcalls:
            return "Error: Volume hanya bisa diubah saat streaming"
        if chat_id not in self.active_calls:
            return "Error: Tidak ada stream aktif"
        try:
            await self.pytgcalls.change_volume_call(chat_id, volume)
            self.volume[chat_id] = volume
            return f"Volume diatur ke {volume}%"
        except Exception as exc:
            logger.error(f"Failed to set volume in chat {chat_id}: {exc}")
            return f"Error mengatur volume: {exc}"

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _play_stream_entry(self, chat_id: int, song_entry: Dict):
        """Play a prepared song entry via PyTgCalls."""
        if not self.pytgcalls:
            raise RuntimeError("Streaming client is not available")

        youtube_url = song_entry.get('webpage_url')

        # Build yt-dlp parameters with cookies
        ytdlp_params = []
        if config.YOUTUBE_COOKIES_FROM_BROWSER:
            ytdlp_params.append(f'--cookies-from-browser {config.YOUTUBE_COOKIES_FROM_BROWSER}')
        elif config.YOUTUBE_COOKIES_FILE and os.path.exists(config.YOUTUBE_COOKIES_FILE):
            ytdlp_params.append(f'--cookies {config.YOUTUBE_COOKIES_FILE}')

        ytdlp_parameters = ' '.join(ytdlp_params) if ytdlp_params else None

        audio_quality = self._resolve_audio_quality()
        media_stream_kwargs = {
            'media_path': youtube_url,
            'ytdlp_parameters': ytdlp_parameters
        }
        if audio_quality is not None:
            media_stream_kwargs['audio_parameters'] = audio_quality

        if song_entry.get('audio_only', True):
            media_stream_kwargs['video_flags'] = MediaStream.Flags.IGNORE
        else:
            media_stream_kwargs['video_parameters'] = VideoQuality.HD_720p
            media_stream_kwargs['video_flags'] = MediaStream.Flags.AUTO_DETECT

        media_stream = MediaStream(**media_stream_kwargs)

        group_config = await self._build_group_call_config(chat_id)

        if not song_entry.get('_autoplay', False) and self.active_calls.get(chat_id):
            self._ignored_stream_ends[chat_id] = self._ignored_stream_ends.get(chat_id, 0) + 1

        await self.pytgcalls.play(chat_id, media_stream, config=group_config)

        self.active_calls[chat_id] = True
        self.current_song[chat_id] = {**song_entry}
        self.stream_mode[chat_id] = 'audio' if song_entry.get('audio_only', True) else 'video'
        self.paused[chat_id] = False
        self.current_song[chat_id].pop('_autoplay', None)

    def _dequeue_next_song(self, chat_id: int) -> Optional[Dict]:
        """Fetch the next song taking loop settings into account."""
        queue = self.queues.get(chat_id, [])
        current = self.current_song.get(chat_id)
        loop_mode = self.loop_mode.get(chat_id, 'off')

        if loop_mode == 'current' and current:
            return {**current}

        if queue:
            next_song = queue.pop(0)
            if loop_mode == 'all' and current:
                queue.append({**current})
            return next_song

        if loop_mode == 'all' and current:
            return {**current}

        return None

    # ------------------------------------------------------------------
    # Internal event handlers
    # ------------------------------------------------------------------

    def _register_stream_events(self):
        """Attach PyTgCalls update listeners for autoplay handling."""
        if not self.pytgcalls or not StreamEndFilter:
            return

        @self.pytgcalls.on_update(StreamEndFilter())
        async def _on_stream_end(_, update: 'StreamEnded'):
            chat_id = getattr(update, "chat_id", None)
            if chat_id is None:
                return

            if chat_id in self._ignored_stream_ends:
                remaining = self._ignored_stream_ends[chat_id] - 1
                if remaining > 0:
                    self._ignored_stream_ends[chat_id] = remaining
                else:
                    self._ignored_stream_ends.pop(chat_id, None)
                logger.debug(
                    "Ignoring stream end in chat %s (pending manual transition)",
                    chat_id,
                )
                return

            logger.info("Stream ended in chat %s, attempting autoplay", chat_id)
            asyncio.create_task(self._handle_stream_completion(chat_id))

    async def _handle_stream_completion(self, chat_id: int):
        """Autoplay the next song or clean up when playback ends."""
        next_song = self._dequeue_next_song(chat_id)

        if next_song:
            logger.info(
                "Autoplaying next track in chat %s: %s",
                chat_id,
                next_song.get('title', 'Unknown'),
            )
            try:
                autoplay_entry = {**next_song, '_autoplay': True}
                await self._play_stream_entry(chat_id, autoplay_entry)
            except Exception as exc:
                logger.error(
                    "Failed to autoplay next track in chat %s: %s",
                    chat_id,
                    exc,
                )
                await self._finalize_stream(chat_id)
            return

        logger.info("Queue finished in chat %s. Leaving voice chat.", chat_id)
        await self._finalize_stream(chat_id)

    async def _finalize_stream(self, chat_id: int):
        """Reset playback state and leave the voice chat if necessary."""
        if self.pytgcalls and self.active_calls.get(chat_id):
            self._ignored_stream_ends[chat_id] = self._ignored_stream_ends.get(chat_id, 0) + 1
            await self.leave_voice_chat(chat_id)

        self.active_calls.pop(chat_id, None)
        self.current_song.pop(chat_id, None)
        self.stream_mode.pop(chat_id, None)
        self.paused.pop(chat_id, None)
        self.loop_mode.pop(chat_id, None)
        self.volume.pop(chat_id, None)
        self._ignored_stream_ends.pop(chat_id, None)
        self.queues.pop(chat_id, None)
