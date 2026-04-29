"""Motion / camera helpers — animated entry, exit, ken-burns, shakes.

Two surfaces:

  - **Frame-list animators** — ``with_entry_animation(frames, kind)``
    returns a new frame timeline whose first beat fades / slides /
    pops in. Adapters that build PNG timelines (top_five, twitter,
    would_you_rather, fake_text) feed the result into
    :mod:`apps.worker.render_adapters._image_seq`.

  - **ffmpeg filtergraph emitters** — ``ken_burns_filter(...)`` /
    ``slide_in_filter(...)`` produce a string adapters can drop into
    a ``-filter_complex`` chain when they're handing raw video to
    ffmpeg.

Pacing presets map a single operator-facing knob (``calm`` /
``medium`` / ``fast`` / ``chaotic`` / ``cinematic``) to consistent
zoom / pan / hold numbers across the templates that respect them.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Literal


PacingPreset = Literal["calm", "medium", "fast", "chaotic", "cinematic"]


@dataclass(frozen=True)
class PacingProfile:
    """Numeric knobs that adapters consume to stay consistent."""

    name: PacingPreset
    zoom_start: float
    zoom_end: float
    pan_amount: float          # fraction of frame width/height
    hold_seconds: float        # default hold per beat
    transition_seconds: float
    cut_frequency: float       # cuts per second (for AI Story bridge)


_PROFILES: dict[PacingPreset, PacingProfile] = {
    "calm":      PacingProfile("calm",      1.00, 1.10, 0.05, 4.0, 0.50, 0.25),
    "medium":    PacingProfile("medium",    1.00, 1.18, 0.10, 3.0, 0.35, 0.45),
    "fast":      PacingProfile("fast",      1.00, 1.28, 0.18, 2.2, 0.20, 0.75),
    "chaotic":   PacingProfile("chaotic",   1.00, 1.40, 0.30, 1.5, 0.10, 1.20),
    "cinematic": PacingProfile("cinematic", 1.00, 1.12, 0.06, 4.5, 0.65, 0.30),
}


def get_pacing(name: str | None) -> PacingProfile:
    if name and name in _PROFILES:
        return _PROFILES[name]
    return _PROFILES["medium"]


def list_pacing() -> list[str]:
    return list(_PROFILES.keys())


# ─── ffmpeg filter emitters ─────────────────────────────────────────────

def ken_burns_filter(
    *,
    width: int,
    height: int,
    duration_sec: float,
    fps: int = 24,
    zoom_start: float = 1.0,
    zoom_end: float = 1.18,
    pan: tuple[float, float] = (0.0, 0.0),
) -> str:
    """Return an ffmpeg ``zoompan`` filter string for a Ken-Burns drift.

    ``pan`` is fractional (-1..1) of frame, applied linearly across
    the duration. The output is a self-contained vfilter — chain it
    via ``-vf`` or as a clause inside ``-filter_complex``.
    """
    frames = max(int(duration_sec * fps), 1)
    pan_x, pan_y = pan
    # zoompan needs an integer frame count and cumulative zoom expression.
    # ``z`` ramps linearly between zoom_start..zoom_end across ``d``.
    return (
        f"zoompan="
        f"z='{zoom_start:.4f}+(({zoom_end - zoom_start:.4f})*on/{frames - 1 if frames > 1 else 1})'"
        f":x='iw/2-(iw/zoom/2)+iw*{pan_x:.4f}*on/{frames}'"
        f":y='ih/2-(ih/zoom/2)+ih*{pan_y:.4f}*on/{frames}'"
        f":d={frames}:s={width}x{height}:fps={fps}"
    )


def slide_in_filter(
    *,
    direction: Literal["left", "right", "up", "down"],
    duration_sec: float,
    fps: int = 24,
) -> str:
    """Return a slide-in transition for a layered overlay.

    Designed for use with ``[ov]overlay='x=...':y='...'`` in a
    filter_complex graph — returns the per-axis x/y expressions as a
    single string so callers can drop it into the right slot.
    """
    # 0.0 → 1.0 over duration_sec
    progress = f"min(t/{duration_sec:.3f}\\,1)"
    if direction == "left":
        return f"x='-W+(main_w+W)*{progress}':y='(main_h-H)/2'"
    if direction == "right":
        return f"x='main_w-(main_w+W)*{progress}':y='(main_h-H)/2'"
    if direction == "up":
        return f"x='(main_w-W)/2':y='-H+(main_h+H)*{progress}'"
    return f"x='(main_w-W)/2':y='main_h-(main_h+H)*{progress}'"


def shake_filter(
    *,
    intensity: float = 6.0,
    fps: int = 24,
) -> str:
    """Return a small ffmpeg perspective filter that shakes the frame.

    Used by Roblox Rant for the chaotic feel during peak-energy
    moments. Intensity is in source pixels; 6 px is a noticeable
    nudge at 576×1024.
    """
    p = max(1.0, intensity)
    return (
        f"perspective="
        f"x0='sin(t*8)*{p}':y0='cos(t*9)*{p}'"
        f":x1='W+sin(t*7)*{p}':y1='cos(t*11)*{p}'"
        f":x2='sin(t*10)*{p}':y2='H+cos(t*8)*{p}'"
        f":x3='W+sin(t*9)*{p}':y3='H+cos(t*7)*{p}'"
        f":interpolation=linear"
    )


# ─── Frame-timeline animators ───────────────────────────────────────────


def split_first_beat_for_entry(
    frame_durations: list[float],
    *,
    entry_seconds: float = 0.4,
) -> list[float]:
    """Reserve ``entry_seconds`` from the first beat for an entry hold.

    Adapters that want a "punch in" effect can split their first
    frame into a short entry beat + a steady-state beat. We do this
    purely with duration math — the same PNG is used for both, but
    the encoder can later be told to apply a zoompan filter to the
    first beat only.
    """
    if not frame_durations:
        return frame_durations
    first = frame_durations[0]
    if first <= entry_seconds * 2:
        return frame_durations
    return [entry_seconds, first - entry_seconds, *frame_durations[1:]]


def progress_bar_segments(
    *,
    total_seconds: float,
    fps: int = 24,
    segments: int = 60,
) -> list[float]:
    """Return per-segment widths for a progress / countdown bar overlay.

    Each segment represents an equal slice of the timer; adapters can
    blit a thin rectangle whose width grows monotonically. Returned
    list is ``segments`` floats in [0, 1].
    """
    if segments <= 0:
        return []
    return [(i + 1) / segments for i in range(segments)]
