#!/usr/bin/env python3
"""
VBot Branding & Animation Utilities
Provides consistent branding and loading animations

Author: Vzoel Fox's
Version: 1.0.0
"""

import asyncio

class VBotBranding:
    """VBot branding and animation utilities"""

    HEADER = "╭━━━━━━━━━━━━━━━━━━━━━━━━━━╮\n│ **VBot Music By Vzoel Fox's** │\n╰━━━━━━━━━━━━━━━━━━━━━━━━━━╯"
    FOOTER = "╭━━━━━━━━━━━━━━━━━━━━━━━━━━╮\n│ **2025© Vzoel Fox's Lutpan** │\n│      **@VZLfxs**      │\n╰━━━━━━━━━━━━━━━━━━━━━━━━━━╯"

    # Loading animation frames
    LOADING_FRAMES = [
        "⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"
    ]

    @staticmethod
    def wrap_message(content: str, include_header: bool = True, include_footer: bool = True) -> str:
        """Wrap message with VBot branding"""
        parts = []

        if include_header:
            parts.append(VBotBranding.HEADER)

        parts.append(content)

        if include_footer:
            parts.append(VBotBranding.FOOTER)

        return "\n\n".join(parts)

    @staticmethod
    async def animate_loading(message, text: str, duration: float = 2.0):
        """Animate loading process"""
        frames = VBotBranding.LOADING_FRAMES
        iterations = int(duration / 0.2)

        for i in range(iterations):
            frame = frames[i % len(frames)]
            await message.edit(f"{frame} **{text}**")
            await asyncio.sleep(0.2)

    @staticmethod
    def format_music_info(song: dict, status: str = "Now Playing") -> str:
        """Format music info with branding"""
        title = song.get('title', 'Unknown')
        duration = song.get('duration', 0)
        duration_str = f"{duration // 60}:{duration % 60:02d}"

        content = (
            f"**{status}**\n\n"
            f"**Title:** {title}\n"
            f"**Duration:** {duration_str}"
        )

        return VBotBranding.wrap_message(content)

    @staticmethod
    def format_queue_info(current: dict, queue: list) -> str:
        """Format queue info with branding"""
        content = "**Music Queue**\n\n"

        if current:
            content += f"**Now Playing:**\n{current['title']}\n\n"

        if queue:
            content += "**Up Next:**\n"
            for i, song in enumerate(queue[:10], 1):
                content += f"{i}. {song['title']}\n"

            if len(queue) > 10:
                content += f"\n... and {len(queue) - 10} more songs"
        else:
            content += "No songs in queue"

        return VBotBranding.wrap_message(content)

    @staticmethod
    def format_command_list() -> str:
        """Format command list with branding"""
        content = (
            "**Music Commands**\n\n"
            "▸ /play <query> - Play audio\n"
            "▸ /vplay <query> - Play video\n"
            "▸ /pause - Pause playback\n"
            "▸ /resume - Resume playback\n"
            "▸ /skip - Skip to next\n"
            "▸ /stop - Stop & clear\n"
            "▸ /queue - View queue\n"
            "▸ /shuffle - Shuffle queue\n"
            "▸ /loop <mode> - Loop mode\n"
            "▸ /seek <time> - Seek position\n"
            "▸ /volume <0-200> - Set volume"
        )

        return VBotBranding.wrap_message(content)

    @staticmethod
    def format_error(error_msg: str) -> str:
        """Format error message with branding"""
        content = f"**Error**\n\n{error_msg}"
        return VBotBranding.wrap_message(content, include_footer=False)

    @staticmethod
    def format_success(success_msg: str) -> str:
        """Format success message with branding"""
        content = f"**Success**\n\n{success_msg}"
        return VBotBranding.wrap_message(content, include_footer=False)
