#!/usr/bin/env python3
"""VBot branding utilities and helpers.

This module centralises all formatting helpers, placeholder handling, and
branding asset lookups used throughout the project.
"""

import asyncio
from pathlib import Path
from typing import Dict, Optional, Tuple

from .branding_assets import VBotBrandingAssets

class VBotBranding:
    """VBot branding and animation utilities"""

    HEADER = "**VBot Music & Clear Chat Management**"
    FOOTER = "**{plugins} by VBot**"
    DEFAULT_PLUGIN_NAME = "VBot"
    BRANDING_MISSING_MESSAGE = (
        "**Branding Asset Tidak Ditemukan**\n\n"
        "Unggah gambar resmi ke `assets/branding/vbot_branding.png` untuk "
        "menampilkan branding visual secara otomatis."
    )

    # Loading animation frames
    LOADING_FRAMES = [
        "⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"
    ]

    class _SafeFormatDict(dict):
        """Dictionary that leaves unknown placeholders untouched."""

        def __missing__(self, key: str) -> str:
            return f"{{{key}}}"

    @staticmethod
    def _build_placeholder_values(
        plugin_name: Optional[str] = None,
        extra: Optional[Dict[str, str]] = None,
    ) -> Dict[str, str]:
        values: Dict[str, str] = {
            "plugins": plugin_name or VBotBranding.DEFAULT_PLUGIN_NAME,
        }
        if extra:
            values.update(extra)
        return values

    @staticmethod
    def apply_placeholders(
        text: str,
        *,
        plugin_name: Optional[str] = None,
        extra: Optional[Dict[str, str]] = None,
    ) -> str:
        """Replace branding placeholders within ``text`` safely."""

        if not text:
            return text

        values = VBotBranding._build_placeholder_values(
            plugin_name=plugin_name,
            extra=extra,
        )
        return text.format_map(VBotBranding._SafeFormatDict(values))

    @staticmethod
    def wrap_message(
        content: str,
        include_header: bool = True,
        include_footer: bool = True,
        *,
        plugin_name: Optional[str] = None,
        placeholders: Optional[Dict[str, str]] = None,
    ) -> str:
        """Wrap message with VBot branding, replacing placeholders when provided."""

        parts = []

        if include_header:
            parts.append(
                VBotBranding.apply_placeholders(
                    VBotBranding.HEADER,
                    plugin_name=plugin_name,
                    extra=placeholders,
                )
            )

        parts.append(
            VBotBranding.apply_placeholders(
                content,
                plugin_name=plugin_name,
                extra=placeholders,
            )
        )

        if include_footer:
            parts.append(
                VBotBranding.apply_placeholders(
                    VBotBranding.FOOTER,
                    plugin_name=plugin_name,
                    extra=placeholders,
                )
            )

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

    # ------------------------------------------------------------------
    # Branding asset helpers
    # ------------------------------------------------------------------
    @staticmethod
    def get_branding_media() -> Tuple[Optional[Path], str]:
        """Return the branding media asset path and a formatted caption."""

        path, caption = VBotBrandingAssets.get_primary_image()
        formatted_caption = VBotBranding.wrap_message(
            caption,
            include_footer=False,
            plugin_name="Branding",
        )
        return path, formatted_caption

    @staticmethod
    def get_branding_missing_notice() -> str:
        """Return a formatted notice when the branding asset is absent."""

        return VBotBranding.wrap_message(
            VBotBranding.BRANDING_MISSING_MESSAGE,
            include_footer=False,
            plugin_name="Branding",
        )
