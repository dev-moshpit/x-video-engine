"""Twitter / X tweet card video adapter.

For a single tweet: one card frame held for the full TTS duration.
For a thread: one frame per tweet, each held proportional to its TTS
share of the total narration.

Pipeline:
  1. Render one card frame per (display_name, text, metrics).
  2. Build a script that reads each tweet aloud — for threads we add
     "Tweet one. ... Tweet two. ..." spoken cues.
  3. Synthesize TTS once for the full script.
  4. Distribute the TTS duration proportionally across thread frames
     so each card stays on screen while its line is spoken.
  5. Mux through the shared overlay helper.
"""

from __future__ import annotations

from pathlib import Path

from xvideo.prompt_native.schema import aspect_to_size

from apps.worker.render_adapters._image_seq import Frame
from apps.worker.render_adapters._overlay import render_overlay_with_voice
from apps.worker.render_adapters._panels import render_tweet_card
from apps.worker.template_inputs import TwitterInput


def _build_script(inp: TwitterInput) -> str:
    """Build the TTS script — single tweet or thread."""
    parts: list[str] = [inp.text]
    if inp.thread:
        for i, t in enumerate(inp.thread, start=2):
            parts.append(f"{t}")
    return " ".join(parts)


def _build_frames(
    inp: TwitterInput, size: tuple[int, int], work_dir: Path,
) -> list[Frame]:
    panel_dir = work_dir / "twitter_frames"
    panel_dir.mkdir(parents=True, exist_ok=True)
    texts = [inp.text, *inp.thread]

    frames: list[Frame] = []
    # Provisional per-frame duration; the overlay helper clips to TTS
    # length anyway. Distribute evenly proportional to text length.
    total_chars = sum(max(len(t), 1) for t in texts)
    rough_total = max(6.0, total_chars * 0.06)
    for i, text in enumerate(texts):
        path = panel_dir / f"tweet_{i:02d}.png"
        render_tweet_card(
            handle=inp.handle,
            display_name=inp.display_name,
            text=text,
            likes=inp.likes if i == 0 else max(inp.likes // (i + 1), 0),
            retweets=inp.retweets if i == 0 else max(inp.retweets // (i + 1), 0),
            replies=inp.replies if i == 0 else max(inp.replies // (i + 1), 0),
            views=inp.views if i == 0 else max(inp.views // (i + 1), 0),
            verified=inp.verified,
            dark_mode=inp.dark_mode,
            background_color=inp.background_color,
            size=size,
            out_path=path,
        )
        share = max(len(text), 1) / total_chars
        frames.append(Frame(path, max(rough_total * share, 1.0)))
    return frames


def render(input: TwitterInput, work_dir: Path) -> Path:
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
        base="twitter",
        background_url=input.background_url,
        overlay_opacity=0.96,
    )
