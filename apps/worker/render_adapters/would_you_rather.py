"""Would You Rather adapter.

Pipeline:
  1. Render two beats — countdown frames (5, 4, 3, 2, 1) and a reveal
     frame with both percentages — using
     :func:`apps.worker.render_adapters._panels.render_wyr_panel`.
  2. TTS reads "Would you rather <A> or <B>? <X> percent chose <A>,
     <Y> percent chose <B>." That gives word-level captions for the
     viewer to follow.
  3. Mux through the shared overlay helper.
"""

from __future__ import annotations

from pathlib import Path
import random

from xvideo.prompt_native.schema import aspect_to_size

from apps.worker.render_adapters._image_seq import Frame
from apps.worker.render_adapters._overlay import render_overlay_with_voice
from apps.worker.render_adapters._panels import render_wyr_panel
from apps.worker.template_inputs import WouldYouRatherInput


def _build_script(inp: WouldYouRatherInput) -> str:
    pct_a = _reveal_percent(inp)
    pct_b = 100 - pct_a
    return (
        f"Would you rather {inp.option_a}, or {inp.option_b}? "
        f"{pct_a} percent chose {inp.option_a}. "
        f"{pct_b} percent chose {inp.option_b}."
    )


def _reveal_percent(inp: WouldYouRatherInput) -> int:
    """Deterministic reveal when a seed is supplied and the default is kept."""
    if inp.seed is None or inp.reveal_percent_a != 50:
        return inp.reveal_percent_a
    rng = random.Random(f"{inp.seed}:{inp.question}:{inp.option_a}:{inp.option_b}")
    return rng.randint(35, 65)


def _build_frames(
    inp: WouldYouRatherInput, size: tuple[int, int], work_dir: Path,
) -> list[Frame]:
    frames: list[Frame] = []
    panel_dir = work_dir / "wyr_frames"
    panel_dir.mkdir(parents=True, exist_ok=True)

    # Countdown beats — one frame per timer tick at 1s each.
    for i in range(inp.timer_seconds, 0, -1):
        path = panel_dir / f"timer_{i:02d}.png"
        render_wyr_panel(
            question=inp.question,
            option_a=inp.option_a,
            option_b=inp.option_b,
            color_a=inp.color_a,
            color_b=inp.color_b,
            timer_label=str(i),
            pct_a=None, pct_b=None,
            size=size,
            out_path=path,
        )
        frames.append(Frame(path, 1.0))

    # Reveal beat — held for 4s so the percentage lingers.
    reveal_path = panel_dir / "reveal.png"
    render_wyr_panel(
        question=inp.question,
        option_a=inp.option_a,
        option_b=inp.option_b,
        color_a=inp.color_a,
        color_b=inp.color_b,
        timer_label="RESULTS",
        pct_a=_reveal_percent(inp),
        pct_b=100 - _reveal_percent(inp),
        size=size,
        out_path=reveal_path,
    )
    frames.append(Frame(reveal_path, 4.0))
    return frames


def render(input: WouldYouRatherInput, work_dir: Path) -> Path:
    work_dir.mkdir(parents=True, exist_ok=True)
    size = aspect_to_size(input.aspect)
    frames = _build_frames(input, size, work_dir)
    return render_overlay_with_voice(
        frames=frames,
        script=_build_script(input),
        voice_name=input.voice_name,
        caption_style=input.caption_style,
        size=size,
        work_dir=work_dir,
        base="would_you_rather",
        background_url=input.background_url,
        overlay_opacity=0.94,
    )
