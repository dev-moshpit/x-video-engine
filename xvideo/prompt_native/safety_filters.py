"""Safety filters — sanitize prompts and audit generated plans.

Two responsibilities:

1. ``sanitize_user_prompt`` — strip control characters / dangerous-shell
   characters / outsized whitespace from the user-supplied prompt before
   it lands in a sidecar / batch name / shell command. Cheap defensive
   layer; not a security boundary.

2. ``sanitize_visual_prompt`` — guarantee the per-scene SDXL prompt
   does not instruct the image model to render text, captions, or
   watermarks. Captions are added later by ffmpeg; burning them into
   the keyframe breaks reproducibility and platform safety reviews.

3. ``audit_plan`` — return a list of human-readable warnings about a
   ``VideoPlan`` (empty hook, missing CTA, scene duration outliers,
   etc.). Used by the UI to surface "this plan looks weak" hints
   before the operator commits GPU time.

None of these refuse or block; they sanitize and warn. Refusal is the
operator's job, not the engine's.
"""

from __future__ import annotations

import re
from typing import Iterable

from xvideo.prompt_native.schema import VideoPlan


# Strip ASCII control chars except common whitespace (tab, newline).
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0B-\x0C\x0E-\x1F\x7F]")
_MAX_PROMPT_LEN = 4000


def sanitize_user_prompt(prompt: str, max_len: int = _MAX_PROMPT_LEN) -> str:
    """Return a cleaned version of the user's prompt.

    - Strips control characters (which would corrupt JSON sidecars).
    - Collapses runs of whitespace.
    - Hard-limits length to ``max_len`` characters (truncates with ``…``).
    - Trims surrounding whitespace.
    Does not censor content — the engine is creator-side, not platform-side.
    """
    if prompt is None:
        return ""
    s = _CONTROL_CHARS_RE.sub("", str(prompt))
    s = re.sub(r"[ \t]+", " ", s)
    # Trim spaces hugging newlines so "foo \n\n bar" doesn't keep a stray
    # space before the line break.
    s = re.sub(r"[ \t]*\n[ \t]*", "\n", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    s = s.strip()
    if len(s) > max_len:
        s = s[: max_len - 1].rstrip() + "…"
    return s


# Tokens that, if present in a generated visual prompt, would push SDXL
# to render typography. We strip these defensively.
_TEXT_TOKEN_RE = re.compile(
    r"\b(subtitle[s]?|caption[s]?|watermark[s]?|logo[s]?|"
    r"title\s*card|lower\s*third|on[- ]screen\s*text|typography|"
    r"text\s*overlay)\b",
    re.IGNORECASE,
)


def sanitize_visual_prompt(visual_prompt: str) -> str:
    """Strip text-rendering instructions from a per-scene SDXL prompt.

    The director already avoids these tokens in its templates, but if a
    future LLM-mode planner injects them, the bridge calls this before
    sending to the renderer. Idempotent.
    """
    if not visual_prompt:
        return ""
    cleaned = _TEXT_TOKEN_RE.sub("", visual_prompt)
    # Collapse the commas + whitespace that may now be doubled up.
    cleaned = re.sub(r"\s*,\s*,+", ", ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,")
    return cleaned


def audit_plan(plan: VideoPlan) -> list[str]:
    """Return a list of warnings about a ``VideoPlan``.

    Empty list = nothing alarming. Used by the UI as a soft signal; not
    a gate. Pair with ``scoring.plan_meets_thresholds`` if you want a
    pass/fail decision.
    """
    warnings: list[str] = []

    if not plan.hook or len(plan.hook.strip()) < 4:
        warnings.append("hook is missing or extremely short")
    if not plan.cta or len(plan.cta.strip()) < 4:
        warnings.append("CTA is missing or extremely short")
    if not plan.scenes:
        warnings.append("plan has zero scenes")
    elif len(plan.scenes) < 3:
        warnings.append(f"only {len(plan.scenes)} scenes — feed risks single-shot pacing")
    elif len(plan.scenes) > 8:
        warnings.append(f"{len(plan.scenes)} scenes is high — risk of choppy edit")

    # Per-scene checks
    for s in plan.scenes:
        if not s.visual_prompt:
            warnings.append(f"scene {s.scene_id} has empty visual prompt")
        if _TEXT_TOKEN_RE.search(s.visual_prompt or ""):
            warnings.append(
                f"scene {s.scene_id} visual prompt instructs text rendering"
            )
        if s.duration <= 0.4:
            warnings.append(
                f"scene {s.scene_id} duration {s.duration:.2f}s is too short"
            )

    # Concept length sanity
    if plan.concept and len(plan.concept.split()) < 6:
        warnings.append("concept is too thin (< 6 words)")
    if plan.voiceover_lines and any(
        len(line.split()) > 24 for line in plan.voiceover_lines
    ):
        warnings.append("at least one voiceover line is long (>24 words)")

    return warnings


__all__ = [
    "sanitize_user_prompt",
    "sanitize_visual_prompt",
    "audit_plan",
]
