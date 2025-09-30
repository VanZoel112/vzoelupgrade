#!/usr/bin/env python3
"""
Music Manager with Streaming Support (PyTgCalls)
Real-time audio streaming to Telegram Voice Chat

Author: VanZoel112
Version: 2.0.0 Python (Streaming)
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
    from pytgcalls.types import MediaStream, AudioQuality
    from pytgcalls.exceptions import GroupCallNotFound, AlreadyJoinedError
    PYTGCALLS_AVAILABLE = True
except ImportError:
    PYTGCALLS_AVAILABLE = False
    logger.warning("PyTgCalls not available - voice chat features disabled")

class MusicManager:
    """Manages music streaming to Telegram Voice Chat"""

    def __init__(self, client):
        self.client = client
        self.pytgcalls = None

        # Streaming state per chat
        self.streams: Dict[int, Dict] = {}  # chat_id -> stream info
        self.queues: Dict[int, List] = {}  # chat_id -> song queue

        # Rate limiting
        self.last_request: Dict[int, float] = {}

        if PYTGCALLS_AVAILABLE:
            try:
                # Initialize PyTgCalls
                self.pytgcalls = PyTgCalls(client)
                logger.info("PyTgCalls initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize PyTgCalls: {e}")
                PYTGCALLS_AVAILABLE = False

    async def start(self):
        """Start PyTgCalls client"""
        if self.pytgcalls and PYTGCALLS_AVAILABLE:
            try:
                await self.pytgcalls.start()
                logger.info("PyTgCalls started")
            except Exception as e:
                logger.error(f"Failed to start PyTgCalls: {e}")

    async def stop(self):
        """Stop PyTgCalls client"""
        if self.pytgcalls:
            try:
                # Leave all active voice chats
                for chat_id in list(self.streams.keys()):
                    await self.leave_voice_chat(chat_id)
                logger.info("PyTgCalls stopped")
            except Exception as e:
                logger.error(f"Error stopping PyTgCalls: {e}")

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
                    # Take first result from search
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

    async def play_stream(self, chat_id: int, query: str, requester_id: int) -> Dict:
        """Play audio stream in voice chat"""
        if not PYTGCALLS_AVAILABLE:
            return {'success': False, 'error': 'PyTgCalls not available'}

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
            # Search for song
            song_info = await self.search_song(query)
            if not song_info:
                return {'success': False, 'error': 'Song not found'}

            # Check if already in voice chat
            is_active = chat_id in self.streams and self.streams[chat_id].get('active')

            if is_active:
                # Add to queue
                if chat_id not in self.queues:
                    self.queues[chat_id] = []
                self.queues[chat_id].append(song_info)
                return {
                    'success': True,
                    'queued': True,
                    'position': len(self.queues[chat_id]),
                    'song': song_info
                }

            # Join voice chat and play
            try:
                await self.pytgcalls.play(
                    chat_id,
                    MediaStream(
                        song_info['url'],
                        audio_parameters=AudioQuality.HIGH
                    )
                )

                self.streams[chat_id] = {
                    'active': True,
                    'song': song_info,
                    'requester': requester_id,
                    'start_time': time.time()
                }

                # Start monitoring for empty VC
                asyncio.create_task(self._monitor_voice_chat(chat_id))

                return {'success': True, 'song': song_info, 'joined': True}

            except AlreadyJoinedError:
                # Already in VC, just play
                await self.pytgcalls.play(
                    chat_id,
                    MediaStream(song_info['url'])
                )
                self.streams[chat_id] = {
                    'active': True,
                    'song': song_info,
                    'requester': requester_id
                }
                return {'success': True, 'song': song_info}

        except Exception as e:
            logger.error(f"Error playing stream: {e}")
            return {'success': False, 'error': str(e)}

    async def stop_stream(self, chat_id: int) -> bool:
        """Stop current stream and leave voice chat"""
        try:
            if chat_id in self.streams:
                # Stop streaming
                await self.pytgcalls.leave_call(chat_id)

                # Clear queue
                if chat_id in self.queues:
                    self.queues[chat_id].clear()

                # Remove stream info
                del self.streams[chat_id]

                logger.info(f"Stopped stream in chat {chat_id}")
                return True

        except GroupCallNotFound:
            # Not in voice chat
            if chat_id in self.streams:
                del self.streams[chat_id]
            return True

        except Exception as e:
            logger.error(f"Error stopping stream: {e}")

        return False

    async def pause_stream(self, chat_id: int) -> bool:
        """Pause current stream"""
        try:
            if chat_id in self.streams and self.streams[chat_id].get('active'):
                await self.pytgcalls.pause_stream(chat_id)
                self.streams[chat_id]['active'] = False
                return True
        except Exception as e:
            logger.error(f"Error pausing stream: {e}")
        return False

    async def resume_stream(self, chat_id: int) -> bool:
        """Resume paused stream"""
        try:
            if chat_id in self.streams and not self.streams[chat_id].get('active'):
                await self.pytgcalls.resume_stream(chat_id)
                self.streams[chat_id]['active'] = True
                return True
        except Exception as e:
            logger.error(f"Error resuming stream: {e}")
        return False

    async def leave_voice_chat(self, chat_id: int):
        """Leave voice chat"""
        try:
            await self.pytgcalls.leave_call(chat_id)
            if chat_id in self.streams:
                del self.streams[chat_id]
            if chat_id in self.queues:
                del self.queues[chat_id]
            logger.info(f"Left voice chat in {chat_id}")
        except GroupCallNotFound:
            pass
        except Exception as e:
            logger.error(f"Error leaving voice chat: {e}")

    async def _monitor_voice_chat(self, chat_id: int):
        """Monitor voice chat and leave if empty"""
        try:
            while chat_id in self.streams:
                await asyncio.sleep(30)  # Check every 30 seconds

                # Check if still in voice chat
                if chat_id not in self.streams:
                    break

                # Get voice chat info
                try:
                    chat = await self.client.get_entity(chat_id)
                    call = await self.client(GetFullChatRequest(chat_id))

                    # Check if voice chat has members besides bot
                    if call.full_chat.call:
                        participants = await self.client(GetGroupCallParticipantsRequest(
                            call=call.full_chat.call,
                            offset='',
                            limit=10
                        ))

                        # If only bot is in VC, leave
                        if len(participants.participants) <= 1:
                            logger.info(f"Voice chat empty in {chat_id}, leaving...")
                            await self.leave_voice_chat(chat_id)
                            break

                except Exception as e:
                    logger.debug(f"Error checking VC members: {e}")

        except Exception as e:
            logger.error(f"Error in VC monitor: {e}")

    def get_current_song(self, chat_id: int) -> Optional[Dict]:
        """Get currently playing song"""
        if chat_id in self.streams:
            return self.streams[chat_id].get('song')
        return None

    def get_queue(self, chat_id: int) -> List[Dict]:
        """Get song queue for chat"""
        return self.queues.get(chat_id, [])

    def get_stream_stats(self) -> Dict:
        """Get streaming statistics"""
        return {
            'active_streams': len(self.streams),
            'total_queued': sum(len(q) for q in self.queues.values()),
            'pytgcalls_available': PYTGCALLS_AVAILABLE
        }
