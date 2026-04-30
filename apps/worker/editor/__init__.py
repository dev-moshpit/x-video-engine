"""Editor pipeline — Platform Phase 1.

A single-pass editor for short-form creators. The user uploads a clip
(typically already short), trims it, picks an aspect, optionally
runs auto-caption generation, and exports.

Pipeline:

  upload (mp4)
    │
    ├── (optional) trim with -ss/-t into work_dir/trimmed.mp4
    │
    ├── (optional) faster-whisper → ASS captions
    │
    └── single ffmpeg pass: scale/crop to aspect + (optionally) burn ASS
"""

from apps.worker.editor.process import (
    EditorJobInput,
    process_editor_job,
)

__all__ = ["EditorJobInput", "process_editor_job"]
