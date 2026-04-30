"""Voiceover Video adapter.

User supplies the script. We do TTS, build word-level captions, render
a solid-color background, and mux it all into a final MP4. Bypasses the
prompt-native planner — no SDXL needed.

Future: when ``input.background_url`` points at an uploaded mp4 in R2
(PR 7+), download it and use it instead of the solid color. Phase 1
only honors a local path that already exists.
"""

from __future__ import annotations

from pathlib import Path

from apps.worker.render_adapters._common import render_script_with_background
from apps.worker.template_inputs import VoiceoverInput


def render(input: VoiceoverInput, work_dir: Path) -> Path:
    return render_script_with_background(
        script=input.script,
        voice_name=input.voice_name,
        aspect=input.aspect,
        background_color=input.background_color,
        background_url=input.background_url,
        caption_style=input.caption_style,
        work_dir=work_dir,
        base="voiceover",
        default_caption_style="clean_subtitle",
    )
