"""faster-whisper transcription wrapper.

Used by the Phase 2 ``auto_captions`` adapter when the operator uploads
an audio or video file instead of typing a script. Returns a duration
+ a list of ``WordEvent`` records that the existing
:func:`xvideo.post.word_captions.build_ass` can render directly.

Lazy-import: ``faster_whisper`` is a heavy dep (CTranslate2 + bundled
model weights). We don't want to force the import at worker startup —
it's only needed for the upload path. Module is loaded on first use
and the model is cached via :func:`functools.lru_cache` so repeated
transcriptions in one worker process reuse the same model.

Model size:
  - Default ``base`` (~140MB, English-only ``base.en`` if language=en).
    Fast enough for 1-min uploads on CPU. Override via
    ``XVIDEO_WHISPER_MODEL`` env var ("tiny", "small", "medium",
    "large-v3").
"""

from __future__ import annotations

import logging
import os
import subprocess
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Optional

import imageio_ffmpeg

if TYPE_CHECKING:
    from xvideo.post.tts import WordEvent


logger = logging.getLogger(__name__)


class WhisperUnavailable(RuntimeError):
    """Raised when faster_whisper isn't importable on this machine.

    The auto_captions adapter catches this and falls back to the
    TTS-from-script path so a missing GPU dep doesn't fail the render.
    """


@lru_cache(maxsize=1)
def _get_model(model_name: str, device: str, compute_type: str):
    try:
        from faster_whisper import WhisperModel  # type: ignore
    except ImportError as e:
        raise WhisperUnavailable(
            "faster-whisper not installed; pip install -r "
            "apps/worker/requirements.txt"
        ) from e
    logger.info(
        "loading faster-whisper model %s (device=%s, compute=%s)",
        model_name, device, compute_type,
    )
    return WhisperModel(model_name, device=device, compute_type=compute_type)


def _resolve_model_for_language(language: str) -> str:
    """Pick a default model per language.

    English gets ``base.en`` (faster, English-only). Other languages
    get the multilingual ``base``. Operator can override via env var.
    """
    if env := os.environ.get("XVIDEO_WHISPER_MODEL"):
        return env
    return "base.en" if language.lower().startswith("en") else "base"


def _extract_audio_track(
    media: Path, work_dir: Path, base: str = "whisper_input",
) -> Path:
    """Extract a 16kHz mono PCM wav from ``media`` for Whisper.

    Whisper accepts video directly through its internal ffmpeg, but
    extracting once lets us reuse the audio as the final video's audio
    track without a second decode pass.
    """
    out_path = work_dir / f"{base}.wav"
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


def transcribe_to_words(
    *,
    media: Path,
    language: str,
    work_dir: Path,
    model_name: Optional[str] = None,
    device: Optional[str] = None,
) -> tuple[Path, float, list["WordEvent"]]:
    """Transcribe ``media`` and return (audio_wav, duration, words).

    ``words`` are the per-word timing events ready to feed
    :func:`xvideo.post.word_captions.build_ass`. Empty list if Whisper
    couldn't extract any words.

    ``device=None`` reads ``XVE_WHISPER_DEVICE`` from env, defaulting
    to ``cpu``. The CTranslate2 GPU backend needs cuBLAS/cuDNN DLLs
    that aren't on PATH on a stock CUDA install, so CPU is safer.
    """
    import os
    from xvideo.post.tts import WordEvent  # local to avoid cycle on test

    audio = _extract_audio_track(media, work_dir)
    name = model_name or _resolve_model_for_language(language)
    if device is None:
        device = os.environ.get("XVE_WHISPER_DEVICE", "cpu").strip() or "cpu"

    # int8 is the safest CPU compute_type — float16 needs CUDA.
    compute_type = "int8" if device in ("cpu", "auto") else "float16"
    model = _get_model(name, device, compute_type)

    segments, info = model.transcribe(
        str(audio),
        language=None if language == "auto" else language,
        word_timestamps=True,
        vad_filter=True,
    )

    words: list[WordEvent] = []
    duration = 0.0
    for seg in segments:
        duration = max(duration, float(seg.end))
        if not getattr(seg, "words", None):
            continue
        for w in seg.words:
            text = (w.word or "").strip()
            if not text:
                continue
            words.append(
                WordEvent(
                    text=text,
                    start_sec=float(w.start),
                    end_sec=float(w.end),
                    timing_source="whisper",
                )
            )

    if duration == 0.0:
        duration = float(getattr(info, "duration", 0.0) or 0.0)

    return audio, duration, words
