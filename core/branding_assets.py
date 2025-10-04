"""Utility helpers for accessing VBot branding media assets."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

_ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets" / "branding"


@dataclass(frozen=True)
class BrandingAsset:
    """Represents a single branding asset stored on disk."""

    file_name: str
    caption: str

    @property
    def path(self) -> Path:
        """Return the absolute path to the asset on disk."""
        return _ASSETS_DIR / self.file_name

    def exists(self) -> bool:
        """Return ``True`` when the asset file exists on disk."""
        return self.path.exists()


class VBotBrandingAssets:
    """Centralised definitions for branding assets used by the bot."""

    PRIMARY_IMAGE = BrandingAsset(
        file_name="vbot_branding.png",
        caption=(
            "**VBot Official Branding**\n\n"
            "Representing the signature style of Vzoel Fox's for the VBot project."
        ),
    )

    @staticmethod
    def get_primary_image() -> Tuple[Optional[Path], str]:
        """Return the primary branding image path and its caption."""
        asset = VBotBrandingAssets.PRIMARY_IMAGE
        if asset.exists():
            return asset.path, asset.caption
        return None, asset.caption
