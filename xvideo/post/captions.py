"""Caption timing + SRT writer.

Given the VO script lines and the total voiceover duration, distribute
each line across the timeline proportionally to its word count. Write
standard SRT (Excel/Sheets/FFmpeg-compatible).

MVP is simple:
    - no per-word timing (edge-tts does expose word boundaries; we can
      upgrade to that later)
    - each caption line is shown from its start until the next line starts
    - a 0.1s gap between lines keeps them from bleeding together on render
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class CaptionSegment:
    index: int
    start_sec: float
    end_sec: float
    text: str


def _count_words(text: str) -> int:
    return max(1, len(re.findall(r"\S+", text)))


def _format_srt_time(seconds: float) -> str:
    seconds = max(0.0, seconds)
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int(round((seconds - int(seconds)) * 1000))
    if ms == 1000:                              # guard the rounding edge
        s += 1
        ms = 0
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def distribute(lines: list[str], total_duration: float,
               gap_sec: float = 0.1, start_offset: float = 0.0) -> list[CaptionSegment]:
    """Split `total_duration` across `lines` proportionally to word count.

    `start_offset` shifts the whole timeline so captions begin *after* some
    intro period (typically the hook-overlay window). The remaining span
    (total_duration - start_offset) is what gets distributed.
    """
    if not lines or total_duration <= start_offset:
        return []

    usable = total_duration - start_offset
    word_counts = [_count_words(line) for line in lines]
    total_words = sum(word_counts)

    segs: list[CaptionSegment] = []
    cursor = start_offset
    for i, (line, n) in enumerate(zip(lines, word_counts), start=1):
        share = (n / total_words) * usable
        start = cursor
        end = min(total_duration, cursor + share)
        # Small gap before the next line appears
        if i < len(lines):
            end = max(start + 0.1, end - gap_sec)
        segs.append(CaptionSegment(index=i, start_sec=start, end_sec=end, text=line))
        cursor += share
    return segs


def write_srt(segments: list[CaptionSegment], out_path: Path) -> Path:
    """Write segments as a UTF-8 SRT file (Windows-agnostic \\n line endings)."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8", newline="\n") as f:
        for seg in segments:
            f.write(f"{seg.index}\n")
            f.write(f"{_format_srt_time(seg.start_sec)} --> "
                    f"{_format_srt_time(seg.end_sec)}\n")
            f.write(f"{seg.text}\n\n")
    return out_path


def build_captions(lines: list[str], total_duration: float,
                   out_srt: Path, start_offset: float = 0.0) -> list[CaptionSegment]:
    """One-shot: distribute + write SRT. Returns the segments."""
    segs = distribute(lines, total_duration, start_offset=start_offset)
    write_srt(segs, out_srt)
    return segs
