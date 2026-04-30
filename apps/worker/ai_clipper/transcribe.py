"""Full-video transcription via faster-whisper.

Used by the AI clipper to convert a long upload (video or audio) into
segments + word-level timing. Mirrors the tighter
``render_adapters._whisper`` wrapper but returns richer structured
results (segment-level + word-level) for the segmenter and scorer.

Lazy-import: ``faster_whisper`` is heavy (CTranslate2 + bundled model
weights). The module itself is light to import; the model loads on
first ``transcribe_full`` call and is cached via :func:`functools.lru_cache`.
"""

from __future__ import annotations

import logging
import os
import subprocess
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Optional

import imageio_ffmpeg


logger = logging.getLogger(__name__)


class WhisperUnavailable(RuntimeError):
    """Raised when faster_whisper isn't importable on this machine."""


@dataclass(frozen=True)
class TranscriptWord:
    text: str
    start: float
    end: float


@dataclass(frozen=True)
class TranscriptSegment:
    """One whisper segment — a sentence-ish span with its words."""
    id: int
    start: float
    end: float
    text: str
    words: tuple[TranscriptWord, ...] = field(default_factory=tuple)
    avg_logprob: float = 0.0
    no_speech_prob: float = 0.0


@dataclass(frozen=True)
class Transcript:
    """Full transcription result."""
    duration: float
    language: str
    segments: tuple[TranscriptSegment, ...]
    audio_path: Path

    @property
    def text(self) -> str:
        return " ".join(s.text.strip() for s in self.segments).strip()

    @property
    def all_words(self) -> tuple[TranscriptWord, ...]:
        out: list[TranscriptWord] = []
        for seg in self.segments:
            out.extend(seg.words)
        return tuple(out)


@lru_cache(maxsize=2)
def _get_model(model_name: str, device: str, compute_type: str):
    try:
        from faster_whisper import WhisperModel  # type: ignore
    except ImportError as e:
        raise WhisperUnavailable(
            "faster-whisper not installed; pip install faster-whisper>=1.0"
        ) from e
    logger.info(
        "loading faster-whisper %s (device=%s, compute=%s)",
        model_name, device, compute_type,
    )
    return WhisperModel(model_name, device=device, compute_type=compute_type)


def _resolve_default_model(language: str) -> str:
    if env := os.environ.get("XVIDEO_WHISPER_MODEL"):
        return env
    return "base.en" if language.lower().startswith("en") else "base"


def _extract_audio(media: Path, work_dir: Path) -> Path:
    """Extract a 16kHz mono WAV via the bundled ffmpeg.

    faster-whisper accepts video directly through its internal ffmpeg,
    but extracting once lets the export step reuse the audio without a
    second decode pass.
    """
    out_path = work_dir / "ai_clipper_input.wav"
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    cmd = [
        ffmpeg, "-hide_banner", "-y",
        "-i", str(media),
        "-vn", "-ac", "1", "-ar", "16000",
        "-f", "wav",
        str(out_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0 or not out_path.exists():
        raise RuntimeError(
            f"audio extraction failed (exit={proc.returncode}):\n"
            f"{proc.stderr[-1500:]}"
        )
    return out_path


def transcribe_full(
    *,
    media: Path,
    work_dir: Path,
    language: str = "auto",
    model_name: Optional[str] = None,
    device: str = "auto",
    beam_size: int = 1,
) -> Transcript:
    """Transcribe a full upload into segments with word timings.

    ``language="auto"`` lets Whisper detect; otherwise pass an ISO code
    ("en", "es", ...). ``beam_size=1`` (greedy) is the fastest sane
    default — operators tuning quality can pass higher via env or
    explicit arg.

    Raises :class:`WhisperUnavailable` if faster-whisper isn't
    installed; callers (the api router) translate to a 503.
    """
    work_dir.mkdir(parents=True, exist_ok=True)
    audio = _extract_audio(media, work_dir)
    name = model_name or _resolve_default_model(language)
    compute_type = "int8" if device in ("cpu", "auto") else "float16"
    model = _get_model(name, device, compute_type)

    segments_iter, info = model.transcribe(
        str(audio),
        language=None if language == "auto" else language,
        word_timestamps=True,
        vad_filter=True,
        beam_size=beam_size,
    )

    segs: list[TranscriptSegment] = []
    duration = 0.0
    for s in segments_iter:
        words: list[TranscriptWord] = []
        for w in (getattr(s, "words", None) or []):
            txt = (w.word or "").strip()
            if not txt:
                continue
            words.append(TranscriptWord(
                text=txt, start=float(w.start), end=float(w.end),
            ))
        text = (s.text or "").strip()
        if not text and not words:
            continue
        seg = TranscriptSegment(
            id=int(getattr(s, "id", len(segs))),
            start=float(s.start),
            end=float(s.end),
            text=text,
            words=tuple(words),
            avg_logprob=float(getattr(s, "avg_logprob", 0.0) or 0.0),
            no_speech_prob=float(getattr(s, "no_speech_prob", 0.0) or 0.0),
        )
        segs.append(seg)
        duration = max(duration, seg.end)

    if duration == 0.0:
        duration = float(getattr(info, "duration", 0.0) or 0.0)

    return Transcript(
        duration=duration,
        language=str(getattr(info, "language", language)),
        segments=tuple(segs),
        audio_path=audio,
    )
