"""Auto-Captions Video adapter — Phase 1 script-only path.

Same pipeline as the voiceover adapter (TTS → word captions → solid bg
→ ffmpeg compose). Phase 2 will add audio/video upload + faster-whisper
transcription so users can paste a recording instead of typing a script.
"""

from __future__ import annotations

from pathlib import Path

from apps.worker.render_adapters._common import (
    render_script_with_solid_bg,
)
from apps.worker.template_inputs import AutoCaptionsInput


def render(input: AutoCaptionsInput, work_dir: Path) -> Path:
    return render_script_with_solid_bg(
        script=input.script,
        voice_name=input.voice_name,
        aspect=input.aspect,
        background_color=input.background_color,
        work_dir=work_dir,
        base="auto_captions",
    )
