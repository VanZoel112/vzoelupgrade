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
