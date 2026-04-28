"""Fake Text Video adapter.

Renders a chat-style screen recording (iOS / WhatsApp / Instagram /
Tinder, light or dark) as a 9:16 short. Each message arrives in two
beats — a "typing..." indicator from the message's sender, then the
revealed message — so the result looks like a live conversation.

Pipeline:
  1. If narration is requested, synthesize TTS *first* — its duration
     determines how long each reveal beat must hold so the chat video
     finishes when the narrator does. This avoids the bg-video-too-short
     case where the post-stack would otherwise freeze ffmpeg output.
  2. Build the chat-screen timeline via :mod:`_chat_render` with reveal
     holds scaled to fit the TTS duration.
  3. Encode the PNG sequence to mp4 (:mod:`_image_seq`).
  4. Mux via the existing post-stack
     (``render_prompt_native_final``) so caption styling matches the
     rest of the SaaS. Falls back to a silent mp4 when no voice is
     wanted.

Future hooks (not in v1):
  - avatars (Phase 2.5 media library will add image fetch)
  - background video underlay (overlay chat with translucent panel)
  - per-message audio cues (notification ping)
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

import imageio_ffmpeg

from xvideo.post.tts import synthesize, voice_for_pack
from xvideo.post.word_captions import build_ass
from xvideo.post.prompt_video_stitcher import render_prompt_native_final
from xvideo.prompt_native.schema import aspect_to_size

from apps.worker.render_adapters._chat_render import render_chat_frame
from apps.worker.render_adapters._image_seq import (
    Frame,
    encode_frame_sequence,
)
from apps.worker.template_inputs import FakeTextInput, FakeTextMessage


logger = logging.getLogger(__name__)


def _build_narration(messages: list[FakeTextMessage], chat_title: str) -> str:
    """Compose the TTS read-aloud script from the message list.

    Uses "<them_name>:" / "I said:" so the listener can follow the
    conversation without seeing the screen. Falls back to plain text
    when chat_title is empty.
    """
    them_name = chat_title.split()[0] if chat_title.strip() else "They"
    parts: list[str] = []
    for m in messages:
        speaker = "I said" if m.sender == "me" else f"{them_name} said"
        parts.append(f"{speaker}: {m.text}")
    return " ".join(parts).strip()


def _build_frame_timeline(
    inp: FakeTextInput,
    size: tuple[int, int],
    work_dir: Path,
    *,
    reveal_hold_scale: float = 1.0,
) -> list[Frame]:
    """Render one PNG per beat (typing → reveal) and return the timeline.

    ``reveal_hold_scale`` multiplies each message's ``hold_ms`` so the
    overall chat video can be stretched to match TTS narration without
    re-rendering frames.
    """
    frames: list[Frame] = []
    visible: list[tuple[str, str]] = []
    frame_dir = work_dir / "chat_frames"
    frame_dir.mkdir(parents=True, exist_ok=True)
    frame_idx = 0

    intro_path = frame_dir / f"frame_{frame_idx:04d}.png"
    render_chat_frame(
        style=inp.style, theme=inp.theme,
        chat_title=inp.chat_title,
        visible=[], typing=None,
        size=size, out_path=intro_path,
    )
    frames.append(Frame(intro_path, 0.6))
    frame_idx += 1

    for m in inp.messages:
        if m.typing_ms > 0:
            typing_path = frame_dir / f"frame_{frame_idx:04d}.png"
            render_chat_frame(
                style=inp.style, theme=inp.theme,
                chat_title=inp.chat_title,
                visible=visible.copy(),
                typing=m.sender,
                size=size, out_path=typing_path,
            )
            frames.append(Frame(typing_path, m.typing_ms / 1000.0))
            frame_idx += 1

        visible.append((m.sender, m.text))
        reveal_path = frame_dir / f"frame_{frame_idx:04d}.png"
        render_chat_frame(
            style=inp.style, theme=inp.theme,
            chat_title=inp.chat_title,
            visible=visible.copy(),
            typing=None,
            size=size, out_path=reveal_path,
        )
        hold_sec = max(m.hold_ms, 100) / 1000.0 * reveal_hold_scale
        frames.append(Frame(reveal_path, hold_sec))
        frame_idx += 1

    return frames


def _organic_duration_sec(messages: list[FakeTextMessage]) -> float:
    """Compute total seconds without rendering frames.

    Mirrors the beats produced by :func:`_build_frame_timeline` at
    ``reveal_hold_scale=1.0``: 0.6 s intro + per-message (typing + hold).
    """
    total = 0.6
    for m in messages:
        if m.typing_ms > 0:
            total += m.typing_ms / 1000.0
        total += max(m.hold_ms, 100) / 1000.0
    return total


def _silent_transcode(src: Path, out: Path) -> Path:
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    cmd = [
        ffmpeg, "-hide_banner", "-y",
        "-i", str(src),
        "-c:v", "copy", "-an",
        str(out),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            f"silent transcode failed (exit={proc.returncode}): "
            f"{proc.stderr[-1000:]}"
        )
    return out


def render(input: FakeTextInput, work_dir: Path) -> Path:
    work_dir.mkdir(parents=True, exist_ok=True)
    size = aspect_to_size(input.aspect)

    want_voice = input.narrate or bool(input.voice_name)

    # Silent path — encode chat frames straight to mp4.
    if not want_voice:
        frames = _build_frame_timeline(input, size, work_dir)
        chat_video = encode_frame_sequence(
            frames=frames,
            out_path=work_dir / "fake_text_chat.mp4",
            size=size,
        )
        return _silent_transcode(chat_video, work_dir / "fake_text.mp4")

    # Voiced path — synth TTS first so we can scale reveal holds to fit.
    narration = _build_narration(input.messages, input.chat_title)
    voice_path = work_dir / "fake_text_voice.mp3"
    chosen_voice = input.voice_name or voice_for_pack(None)
    tts = synthesize(
        text=narration,
        out_path=voice_path,
        voice=chosen_voice,
        want_words=True,
    )

    organic_dur = _organic_duration_sec(input.messages)
    target = max(tts.duration_sec + 0.4, organic_dur)
    scale = max(target / organic_dur, 1.0) if organic_dur > 0 else 1.0
    frames = _build_frame_timeline(input, size, work_dir,
                                   reveal_hold_scale=scale)
    chat_video = encode_frame_sequence(
        frames=frames,
        out_path=work_dir / "fake_text_chat.mp4",
        size=size,
    )

    captions_path: Path | None = None
    if tts.words and input.caption_style is not None:
        captions_path = work_dir / "fake_text_captions.ass"
        build_ass(
            words=tts.words,
            out_path=captions_path,
            video_width=size[0],
            video_height=size[1],
        )

    final_path = work_dir / "fake_text.mp4"
    render_prompt_native_final(
        bg_video=chat_video,
        voice_audio=voice_path,
        captions_path=captions_path,
        out_path=final_path,
        hook_text="",
        target_duration_sec=tts.duration_sec,
    )
    return final_path
