"""Shared TTS step for the presenter pipeline.

Reuses the ``xvideo.post.tts.synthesize`` helper that the existing 10
templates use (edge-tts based). Keeps the presenter consistent with
the rest of the platform's voice catalog.
"""

from __future__ import annotations

import urllib.request
from pathlib import Path
from typing import Optional


def synthesize_voice(
    *, text: str, voice: Optional[str], rate: str, work_dir: Path,
) -> tuple[Path, float]:
    """Render ``text`` to an mp3 in ``work_dir``.

    Returns ``(audio_path, duration_sec)``. Raises if the TTS step
    fails — the presenter caller surfaces that to the api as a job
    failure with the message intact.
    """
    from xvideo.post.tts import synthesize

    out = work_dir / "presenter_voice.mp3"
    work_dir.mkdir(parents=True, exist_ok=True)
    res = synthesize(text, out, voice=voice, rate=rate, want_words=False)
    return res.audio_path, float(res.duration_sec)


def fetch_image(url_or_path: str, dst: Path) -> Path:
    """Resolve ``url_or_path`` (http(s) or local) into ``dst``."""
    if url_or_path.startswith(("http://", "https://")):
        urllib.request.urlretrieve(url_or_path, dst)
    else:
        src = Path(url_or_path)
        if not src.exists():
            raise FileNotFoundError(f"avatar image missing: {url_or_path}")
        dst.write_bytes(src.read_bytes())
    return dst
