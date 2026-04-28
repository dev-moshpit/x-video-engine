"""Helpers for adapters that take user-uploaded video paths.

Phase 2 templates that overlay or composite an uploaded clip
(``split_video``, ``roblox_rant``, future media-library work) need to
resolve a stringly-typed ``*_url`` field into a local Path the worker
can hand to ffmpeg. We accept three shapes:

  - existing local absolute path (``D:\\foo.mp4`` or ``/tmp/foo.mp4``)
  - existing local relative path resolved against the project root
  - ``http(s)://`` URL → downloaded into ``work_dir`` once and cached

R2-presigned URLs are http(s) and so flow through the download branch
without a special case. Returning ``None`` on a missing/invalid input
lets the caller fall back to the solid-color background path.
"""

from __future__ import annotations

import logging
import urllib.request
from pathlib import Path
from typing import Optional


logger = logging.getLogger(__name__)


_VIDEO_SUFFIXES = (".mp4", ".mov", ".webm", ".mkv", ".m4v")
_AUDIO_SUFFIXES = (".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac", ".opus")
_MEDIA_SUFFIXES = _VIDEO_SUFFIXES + _AUDIO_SUFFIXES


def _looks_like_video(path: Path) -> bool:
    return path.suffix.lower() in _VIDEO_SUFFIXES


def _looks_like_media(path: Path) -> bool:
    return path.suffix.lower() in _MEDIA_SUFFIXES


def resolve_video_input(
    raw: Optional[str], work_dir: Path,
) -> Optional[Path]:
    """Return a readable local *video* Path or ``None``.

    Quiet on failure — callers fall back to solid-color backgrounds
    rather than crashing the render. If you need hard "must have an
    upload" semantics, validate at the schema layer.
    """
    return _resolve(raw, work_dir, allowed=_VIDEO_SUFFIXES, default_suffix=".mp4")


def resolve_media_input(
    raw: Optional[str], work_dir: Path,
) -> Optional[Path]:
    """Same as :func:`resolve_video_input` but also accepts audio formats.

    Used by the auto_captions adapter where ``audio_url`` is allowed
    alongside ``video_url``.
    """
    return _resolve(raw, work_dir, allowed=_MEDIA_SUFFIXES, default_suffix=".mp4")


def _resolve(
    raw: Optional[str],
    work_dir: Path,
    *,
    allowed: tuple[str, ...],
    default_suffix: str,
) -> Optional[Path]:
    if not raw:
        return None

    raw = raw.strip()
    if raw.startswith(("http://", "https://")):
        suffix = ""
        for s in allowed:
            if raw.lower().split("?")[0].endswith(s):
                suffix = s
                break
        suffix = suffix or default_suffix
        cache_path = work_dir / f"upload{suffix}"
        try:
            urllib.request.urlretrieve(raw, str(cache_path))
        except Exception as exc:
            logger.warning("media download failed for %s: %s", raw, exc)
            return None
        if cache_path.exists() and cache_path.stat().st_size > 1_000:
            return cache_path
        return None

    p = Path(raw)
    if not p.is_absolute():
        p = (work_dir / p).resolve()
    if p.exists() and p.suffix.lower() in allowed:
        return p
    return None
