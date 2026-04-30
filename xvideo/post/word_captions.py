"""Word-level captions.

Given a VO script and the sentence boundaries reported by the TTS engine,
estimate per-word on/off timing (by syllable count within each sentence)
and write an ASS subtitle file styled for the bold bottom-center single-
word look popular on Shorts/TikTok/Reels.

Why syllable-proportional anchored to sentences:
    Edge-TTS stopped emitting WordBoundary events (Microsoft backend
    change). Sentence boundaries are still accurate. Splitting each
    sentence's duration by syllable count gives per-word timing with
    bounded drift — the error resets at each sentence start, and for
    our typical 5-8 word sentences the per-word error is <~100ms.

    If tighter sync is needed later, `estimate_word_events` can be
    replaced with a forced-aligner (faster-whisper / aeneas) without
    touching the ASS writer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, TYPE_CHECKING

if TYPE_CHECKING:
    from xvideo.post.tts import SentenceSegment, WordEvent


# ─── Syllable estimation ────────────────────────────────────────────────

_VOWEL_GROUP_RE = re.compile(r"[aeiouy]+", re.IGNORECASE)


def count_syllables(word: str) -> int:
    """Rough English syllable count. Good enough for timing proportionality.

    Heuristic: count vowel groups; subtract a final silent 'e' if there's
    more than one vowel group. Clamped to at least 1.
    """
    w = re.sub(r"[^a-zA-Z]", "", word).lower()
    if not w:
        return 1
    groups = len(_VOWEL_GROUP_RE.findall(w))
    if groups > 1 and w.endswith("e"):
        groups -= 1
    return max(1, groups)


# ─── Sentence -> per-word timing ────────────────────────────────────────

_WORD_SPLIT_RE = re.compile(r"\S+")


def _split_script_into_sentences(script_text: str) -> list[str]:
    """Split on sentence-ending punctuation, keep non-empty fragments.

    We split on . ! ? and on newlines so it lines up with how edge-tts
    tends to segment.
    """
    parts = re.split(r"(?<=[.!?])\s+|\n+", script_text.strip())
    return [p.strip() for p in parts if p.strip()]


def estimate_word_events(
    script_text: str,
    sentences: "list[SentenceSegment]",
    total_duration: float,
) -> "list[WordEvent]":
    """Emit one WordEvent per word in script_text.

    Aligns the script's sentence splits with the TTS's sentence boundaries
    by order. Within each sentence, distributes the duration by syllable
    count. If sentence counts mismatch (rare punctuation edge cases), falls
    back to one global syllable distribution across total_duration.
    """
    from xvideo.post.tts import WordEvent

    script_sentences = _split_script_into_sentences(script_text)

    def _words_in(s: str) -> list[str]:
        return _WORD_SPLIT_RE.findall(s)

    events: list[WordEvent] = []

    use_global = len(script_sentences) != len(sentences) or not sentences
    if use_global:
        # Single bucket: distribute all words across total_duration by syllables.
        words = _words_in(script_text)
        syl = [count_syllables(w) for w in words]
        total = sum(syl) or 1
        cursor = 0.0
        for w, n in zip(words, syl):
            share = (n / total) * total_duration
            events.append(WordEvent(
                text=w,
                start_sec=round(cursor, 3),
                end_sec=round(cursor + share, 3),
                timing_source="syllable_est_global",
            ))
            cursor += share
        return events

    # Happy path: iterate sentence-by-sentence, distributing each sentence's
    # duration by syllable count across its words.
    for script_sent, tts_sent in zip(script_sentences, sentences):
        words = _words_in(script_sent)
        if not words:
            continue
        syl = [count_syllables(w) for w in words]
        total = sum(syl) or 1
        sent_dur = max(0.0, tts_sent.end_sec - tts_sent.start_sec)
        cursor = tts_sent.start_sec
        for w, n in zip(words, syl):
            share = (n / total) * sent_dur
            events.append(WordEvent(
                text=w,
                start_sec=round(cursor, 3),
                end_sec=round(cursor + share, 3),
                timing_source="syllable_est",
            ))
            cursor += share
    return events


# ─── ASS writer ─────────────────────────────────────────────────────────

# ASS colour format is &HAABBGGRR (yes, reversed BGR). AA=alpha (00=opaque).
_ASS_HEADER_TMPL = """\
[Script Info]
ScriptType: v4.00+
PlayResX: {w}
PlayResY: {h}
ScaledBorderAndShadow: yes
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Word,Arial,{fontsize},&H00FFFFFF,&H000000FF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,{outline},3,2,40,40,{marginv},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def _ass_time(seconds: float) -> str:
    seconds = max(0.0, seconds)
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    cs = int(round((seconds - int(seconds)) * 100))
    if cs == 100:
        s += 1
        cs = 0
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _escape_ass_text(text: str) -> str:
    # Only { and } are special in ASS text (override blocks). Newlines -> \\N.
    return text.replace("{", r"\{").replace("}", r"\}").replace("\n", r"\N")


def build_ass(
    words: "Iterable[WordEvent]",
    out_path: Path,
    video_width: int = 576,
    video_height: int = 1024,
    font_size: int = 72,
    outline: int = 6,
    margin_v: int = 250,
    min_event_sec: float = 0.12,
) -> Path:
    """Write per-word ASS captions. One Dialogue event per word.

    Very short words (<min_event_sec) are stretched to min_event_sec so
    they're legible; this can push them past the next word's start if the
    next word is also very short, but ASS renders the latter on top.
    """
    header = _ASS_HEADER_TMPL.format(
        w=video_width, h=video_height,
        fontsize=font_size, outline=outline, marginv=margin_v,
    )
    lines = [header]
    for w in words:
        start = w.start_sec
        end = max(w.end_sec, start + min_event_sec)
        text = _escape_ass_text(w.text)
        lines.append(
            f"Dialogue: 0,{_ass_time(start)},{_ass_time(end)},Word,,0,0,0,,{text}"
        )

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out_path
