"""Segment a transcript into candidate viral moments.

Strategy:

  1. Treat each whisper segment (sentence-ish) as a unit.
  2. Greedily merge consecutive segments into windows that fit a
     target clip length (15-90s by default; tunable per call).
  3. Prefer breaking on natural pauses — gaps > ``min_gap`` between
     consecutive segments end the current window early.
  4. Refuse degenerate windows (< ``min_duration`` or empty text).

The output is a list of :class:`Moment` candidates that the scorer
ranks. We deliberately keep this heuristic and dependency-free; an
LLM-based segmenter is a future enhancement gated on env config.
"""

from __future__ import annotations

from dataclasses import dataclass

from apps.worker.ai_clipper.transcribe import Transcript, TranscriptSegment


@dataclass(frozen=True)
class Moment:
    """One candidate clip — a contiguous span of segments.

    Times are absolute seconds within the source media. ``text`` is
    the joined transcript for the window — caption rendering can
    re-emit per-word timing from ``segments`` if needed.
    """
    moment_id: str
    start: float
    end: float
    text: str
    segments: tuple[TranscriptSegment, ...]

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)

    @property
    def word_count(self) -> int:
        return sum(len(s.words) or len(s.text.split()) for s in self.segments)


def find_moments(
    transcript: Transcript,
    *,
    min_duration: float = 12.0,
    target_duration: float = 35.0,
    max_duration: float = 75.0,
    min_gap: float = 1.5,
    overlap_seconds: float = 0.0,
) -> list[Moment]:
    """Greedily group transcript segments into clip-sized windows.

    Args:
        min_duration: Drop any window shorter than this.
        target_duration: Stop appending segments once the window is at
          least this long (we still respect ``max_duration``).
        max_duration: Hard cap on a single window.
        min_gap: Pauses longer than this seconds end the current
          window. Encourages cuts on natural breath/pause boundaries.
        overlap_seconds: When > 0, start each next window this far
          back. Useful for highlight reels where you want overlapping
          candidates to give the operator more choices.

    Returns:
        Ordered list of moments. Empty if the transcript has no
        usable segments.
    """
    if max_duration <= 0 or target_duration <= 0:
        raise ValueError("durations must be positive")
    if max_duration < min_duration:
        raise ValueError("max_duration < min_duration")

    segs = list(transcript.segments)
    if not segs:
        return []

    out: list[Moment] = []
    i = 0
    n = len(segs)

    while i < n:
        # Anchor window at segs[i].start. Append segments while the
        # window stays under target_duration AND the gap to the next
        # segment is acceptable.
        win: list[TranscriptSegment] = [segs[i]]
        win_start = segs[i].start
        j = i + 1
        while j < n:
            gap = segs[j].start - segs[j - 1].end
            tentative_end = segs[j].end
            tentative_dur = tentative_end - win_start
            if tentative_dur > max_duration:
                break
            # Hit a natural pause AND we're already long enough → stop.
            if gap >= min_gap and (segs[j - 1].end - win_start) >= min_duration:
                break
            win.append(segs[j])
            j += 1
            if (segs[j - 1].end - win_start) >= target_duration:
                # Look ahead one more; if the next segment fits without
                # blowing max, take it (avoids cliff endings on punchlines).
                if j < n:
                    look_dur = segs[j].end - win_start
                    look_gap = segs[j].start - segs[j - 1].end
                    if look_dur <= max_duration and look_gap < min_gap:
                        win.append(segs[j])
                        j += 1
                break

        win_end = win[-1].end
        text = " ".join(s.text for s in win).strip()
        if (win_end - win_start) >= min_duration and text:
            out.append(Moment(
                moment_id=f"m{len(out):03d}",
                start=win_start,
                end=win_end,
                text=text,
                segments=tuple(win),
            ))

        # Advance — supporting overlap by walking back a bit.
        if overlap_seconds > 0 and j < n:
            target_back = win_end - overlap_seconds
            new_i = j
            while new_i > i + 1 and segs[new_i - 1].start > target_back:
                new_i -= 1
            i = max(i + 1, new_i)
        else:
            i = j if j > i else i + 1

    return out
