"""Top 5 / Countdown adapter.

Renders one panel per ranked item (counting *down* — N…1 if 5 items
were given). TTS reads each item with cues like "Number five." so the
viewer follows along even without captions.
"""

from __future__ import annotations

from pathlib import Path

from xvideo.prompt_native.schema import aspect_to_size

from apps.worker.render_adapters._image_seq import Frame
from apps.worker.render_adapters._overlay import render_overlay_with_voice
from apps.worker.render_adapters._panels import render_top_five_panel
from apps.worker.template_inputs import TopFiveInput


_NUMBER_WORDS = [
    "zero", "one", "two", "three", "four", "five",
    "six", "seven", "eight", "nine", "ten",
]


def _number_word(n: int) -> str:
    return _NUMBER_WORDS[n] if 0 <= n < len(_NUMBER_WORDS) else str(n)


def _build_script(inp: TopFiveInput) -> str:
    parts: list[str] = [inp.title + "."]
    n = len(inp.items)
    for idx, item in enumerate(inp.items):
        rank = n - idx
        parts.append(f"Number {_number_word(rank)}: {item.title}.")
        if item.description:
            parts.append(item.description.rstrip(".") + ".")
    return " ".join(parts)


def _build_frames(
    inp: TopFiveInput, size: tuple[int, int], work_dir: Path,
) -> list[Frame]:
    panel_dir = work_dir / "top_five_frames"
    panel_dir.mkdir(parents=True, exist_ok=True)
    n = len(inp.items)
    frames: list[Frame] = []
    for idx, item in enumerate(inp.items):
        rank = n - idx
        path = panel_dir / f"rank_{rank:02d}.png"
        render_top_five_panel(
            rank=rank,
            rank_total=n,
            list_title=inp.title,
            item_title=item.title,
            item_description=item.description,
            background_color=inp.background_color,
            size=size,
            out_path=path,
        )
        frames.append(Frame(path, inp.per_item_seconds))
    return frames


def render(input: TopFiveInput, work_dir: Path) -> Path:
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
        base="top_five",
    )
