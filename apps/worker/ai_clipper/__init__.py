"""AI clipper engine — Phase 1 of the platform expansion.

Long-form video / audio → ranked viral moments → short clips.

Pipeline:

  upload (mp4 / mp3 / wav)
    │
    ├── transcribe.transcribe_full()  → segments + word timings
    │
    ├── segment.find_moments()        → candidate windows (15-90s)
    │
    ├── score.score_moments()         → hook / emotion / question / energy
    │
    └── export.cut_clip()              → trimmed + captioned + reframed mp4

Each module is independent + side-effect-free except for filesystem
output to ``work_dir``. The api uses ``analyze_full`` to drive the
analyze flow end-to-end and ``export_one_clip`` for the single-clip
export endpoint.
"""

from __future__ import annotations

from apps.worker.ai_clipper.export import export_one_clip
from apps.worker.ai_clipper.score import (
    MomentScore,
    score_moment,
    score_moments,
)
from apps.worker.ai_clipper.segment import Moment, find_moments
from apps.worker.ai_clipper.transcribe import (
    Transcript,
    TranscriptSegment,
    TranscriptWord,
    transcribe_full,
)

__all__ = [
    "Transcript",
    "TranscriptSegment",
    "TranscriptWord",
    "Moment",
    "MomentScore",
    "transcribe_full",
    "find_moments",
    "score_moment",
    "score_moments",
    "export_one_clip",
]
