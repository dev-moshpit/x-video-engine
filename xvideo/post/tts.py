"""Text-to-speech adapter.

Default engine: edge-tts (Microsoft Edge cloud voices, free, no API key).
Output: MP3 file + synthesis duration.

Engine is pluggable via a small interface in case we later want offline
TTS (pyttsx3) or a paid API (ElevenLabs). For MVP the one engine is plenty.

edge-tts runs async under the hood; this module wraps it in a sync API so
the rest of the pipeline is ordinary imperative code.
"""

from __future__ import annotations

import asyncio
import logging
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import edge_tts
import imageio_ffmpeg

logger = logging.getLogger(__name__)


@dataclass
class SentenceSegment:
    """A sentence boundary reported by edge-tts (10-ns units converted to sec)."""
    text: str
    start_sec: float
    end_sec: float


@dataclass
class WordEvent:
    """A single word with estimated on/off timing."""
    text: str
    start_sec: float
    end_sec: float
    # Where the timing came from — be honest in provenance.
    timing_source: str = "syllable_est"   # or "edge_word_boundary" | "whisper"


# Tasteful defaults per pack tone. Operator overrides via --voice-name.
DEFAULT_VOICE = "en-US-AriaNeural"

PACK_VOICE_HINTS: dict[str, str] = {
    "motivational_quotes": "en-US-JennyNeural",
    "ai_facts":            "en-US-GuyNeural",
    "music_visualizer":    "en-US-AriaNeural",
    "product_teaser":      "en-US-AndrewNeural",
    "history_mystery":     "en-US-GuyNeural",
    "abstract_loop":       "en-US-AriaNeural",
}


@dataclass
class TTSResult:
    audio_path: Path
    voice: str
    duration_sec: float
    engine: str
    sentences: list[SentenceSegment] = field(default_factory=list)
    words: list[WordEvent] = field(default_factory=list)


def voice_for_pack(pack_name: str | None) -> str:
    if pack_name and pack_name in PACK_VOICE_HINTS:
        return PACK_VOICE_HINTS[pack_name]
    return DEFAULT_VOICE


def _ffprobe_duration(audio_path: Path) -> float:
    """Get media duration in seconds by parsing ffmpeg stderr (ffprobe is
    not bundled with imageio-ffmpeg, so we use ffmpeg -i)."""
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    proc = subprocess.run(
        [ffmpeg, "-hide_banner", "-i", str(audio_path)],
        capture_output=True, text=True,
    )
    m = re.search(r"Duration:\s+(\d+):(\d+):([\d.]+)", proc.stderr)
    if not m:
        return 0.0
    h, mm, s = int(m.group(1)), int(m.group(2)), float(m.group(3))
    return h * 3600 + mm * 60 + s


async def _edge_synthesize_stream(
    text: str, voice: str, out_path: Path, rate: str = "+0%",
) -> list[SentenceSegment]:
    """Stream TTS audio to disk and collect sentence boundaries.

    Edge-TTS v7+ no longer emits WordBoundary events from Microsoft's
    backend — only SentenceBoundary. Per-word timing is derived later from
    sentence anchors (syllable-proportional) or, optionally, from a forced
    aligner. Here we just capture the sentence timeline exactly.
    """
    communicate = edge_tts.Communicate(text=text, voice=voice, rate=rate)
    sentences: list[SentenceSegment] = []
    with open(out_path, "wb") as f:
        async for chunk in communicate.stream():
            ctype = chunk.get("type")
            if ctype == "audio":
                f.write(chunk["data"])
            elif ctype == "SentenceBoundary":
                offset = chunk.get("offset", 0) / 1e7
                dur = chunk.get("duration", 0) / 1e7
                sentences.append(SentenceSegment(
                    text=chunk.get("text", ""),
                    start_sec=round(offset, 3),
                    end_sec=round(offset + dur, 3),
                ))
    return sentences


def synthesize(
    text: str,
    out_path: Path,
    voice: str | None = None,
    rate: str = "+0%",
    engine: str = "edge-tts",
    want_words: bool = False,
) -> TTSResult:
    """Render `text` to an audio file. Returns TTSResult with duration +
    (optionally) sentence boundaries and estimated word events.

    `rate` uses edge-tts notation: "+0%" normal, "+10%" faster, "-5%" slower.
    `want_words=True` populates result.sentences and result.words (via
    syllable-proportional estimation within each sentence).
    """
    if engine != "edge-tts":
        raise ValueError(f"Unsupported TTS engine: {engine}")

    if not text.strip():
        raise ValueError("TTS input text is empty")

    voice = voice or DEFAULT_VOICE
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    sentences = asyncio.run(_edge_synthesize_stream(text, voice, out_path, rate=rate))

    if not out_path.exists() or out_path.stat().st_size < 512:
        raise RuntimeError(f"TTS output missing or empty: {out_path}")

    dur = _ffprobe_duration(out_path)
    result = TTSResult(
        audio_path=out_path,
        voice=voice,
        duration_sec=round(dur, 2),
        engine=engine,
        sentences=sentences,
    )

    if want_words:
        # Import lazily to keep word-mode deps isolated.
        from xvideo.post.word_captions import estimate_word_events
        result.words = estimate_word_events(text, sentences, total_duration=dur)

    return result
