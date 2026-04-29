"""Sound-effect catalog hook for adapters.

We don't bundle sound assets in the repo (licensing risk) — instead
this module defines the *named* effects adapters can request, and
resolves them against an opt-in directory tree on disk:

    assets/sfx/{effect_id}.{ext}       (preferred)
    assets/sfx/{effect_id}/*           (random pick on each render)

When the asset is missing, the helper returns ``None`` and callers
silently skip the cue. Operators who want SFX drop royalty-free files
into ``assets/sfx/`` matching the catalog below; everything else
keeps working.

Future provider hooks (ElevenLabs SFX, Mubert, etc.) plug in via the
same ``resolve_sfx`` interface.
"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Literal, Optional


logger = logging.getLogger(__name__)


SfxId = Literal[
    "swipe", "whoosh", "pop", "tick", "bell", "reveal",
    "hit", "punch", "notification", "type", "drum_roll",
    "boom", "glitch", "transition_zoom",
]


@dataclass(frozen=True)
class SfxEntry:
    """Catalog entry — one named effect with a usage hint."""

    id: SfxId
    description: str
    suggested_volume_db: float    # relative to voiceover (0 = match)


_CATALOG: tuple[SfxEntry, ...] = (
    SfxEntry("swipe",            "Quick swipe between cards / panels", -8.0),
    SfxEntry("whoosh",            "Stronger whoosh for camera moves", -6.0),
    SfxEntry("pop",               "Reveal pop on icons / metrics",  -10.0),
    SfxEntry("tick",              "Clock tick for countdowns",       -12.0),
    SfxEntry("bell",              "Notification bell / chat ping",    -8.0),
    SfxEntry("reveal",            "Top-five rank reveal stinger",     -6.0),
    SfxEntry("hit",               "Impact for hooks / cuts",          -4.0),
    SfxEntry("punch",             "Heavy impact for chaotic cuts",    -3.0),
    SfxEntry("notification",      "Phone notification ding",          -8.0),
    SfxEntry("type",              "Typewriter tick for text reveal", -14.0),
    SfxEntry("drum_roll",         "Pre-reveal tension build",         -8.0),
    SfxEntry("boom",              "Sub-heavy boom for dramatic hooks", -2.0),
    SfxEntry("glitch",            "Glitch cut for cyber / horror",    -6.0),
    SfxEntry("transition_zoom",   "Crash-zoom whoosh on hard cut",    -5.0),
)


_AUDIO_EXTS = (".wav", ".mp3", ".ogg", ".m4a", ".flac")


def list_sfx() -> tuple[SfxEntry, ...]:
    return _CATALOG


def _root() -> Path:
    """Resolve the SFX asset root. ``assets/sfx/`` next to the repo."""
    # apps/worker/render_adapters/_sfx.py -> repo root
    return Path(__file__).resolve().parents[3] / "assets" / "sfx"


def resolve_sfx(effect_id: SfxId) -> Optional[Path]:
    """Return a usable audio path for ``effect_id`` or None.

    Looks first for ``assets/sfx/{id}.{ext}`` (single canonical file),
    then for a directory ``assets/sfx/{id}/`` with multiple takes.
    Picks one at random when multiple are available so consecutive
    renders don't sound identical.
    """
    root = _root()
    if not root.exists():
        return None
    for ext in _AUDIO_EXTS:
        single = root / f"{effect_id}{ext}"
        if single.exists():
            return single
    folder = root / effect_id
    if folder.is_dir():
        candidates = [p for p in folder.iterdir() if p.suffix.lower() in _AUDIO_EXTS]
        if candidates:
            return random.choice(candidates)
    return None


def has_sfx() -> bool:
    """True when at least one catalog effect is available on disk."""
    return any(resolve_sfx(e.id) is not None for e in _CATALOG)


def to_catalog_json() -> list[dict]:
    """Serialised view for an /api/sfx endpoint or settings panel."""
    return [
        {
            "id": e.id,
            "description": e.description,
            "suggested_volume_db": e.suggested_volume_db,
            "available": resolve_sfx(e.id) is not None,
        }
        for e in _CATALOG
    ]
