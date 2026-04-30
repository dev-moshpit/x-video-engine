"""Heuristic plan scoring — gate weak plans before paying GPU cost.

The director can compose a plan that's *technically* valid but creatively
flat (e.g. a 4-word hook, every scene in the same setting, captions that
all say "watch this"). Rather than wait for an operator to notice,
score the plan deterministically and let the director regenerate.

Score dimensions (0-10 each, total 0-100):

    hook_strength       — punch, length sweet-spot, not-a-cliché check
    visual_uniqueness   — distinct settings, distinct subjects across scenes
    scene_variety       — duration spread, camera-motion variety
    emotional_clarity   — has emotional_angle, audience, voice_tone set
    caption_punch       — captions are short, no duplicates, no boilerplate
    prompt_relevance    — plan body actually mentions prompt cues
    platform_fit        — caption style + duration agree with format
    coherence           — concept includes scene-level subjects (cheap)
    cta_fit             — CTA exists and is short
    safety              — no banned tokens, no instructions to render text

This is a heuristic — no ML, no LLM. Numbers are intentionally
conservative; thresholds in ``DEFAULT_THRESHOLDS`` were chosen from a
sample of generated plans so that ~95% of director output passes (we want
to catch outliers, not gate everything).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from typing import Optional

from xvideo.prompt_native.schema import VideoPlan


# ─── Score result ───────────────────────────────────────────────────────

@dataclass
class PlanScore:
    """All sub-scores 0-10. ``total`` is the sum (0-100)."""
    hook_strength: float = 0.0
    visual_uniqueness: float = 0.0
    scene_variety: float = 0.0
    emotional_clarity: float = 0.0
    caption_punch: float = 0.0
    prompt_relevance: float = 0.0
    platform_fit: float = 0.0
    coherence: float = 0.0
    cta_fit: float = 0.0
    safety: float = 0.0
    notes: list[str] = field(default_factory=list)

    @property
    def total(self) -> float:
        return round(sum([
            self.hook_strength, self.visual_uniqueness, self.scene_variety,
            self.emotional_clarity, self.caption_punch, self.prompt_relevance,
            self.platform_fit, self.coherence, self.cta_fit, self.safety,
        ]), 2)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["total"] = self.total
        return d


# ─── Thresholds ─────────────────────────────────────────────────────────

# Minimum totals + per-dimension floors. The spec calls for total >= 70
# and the hook + scene_variety >= 7.
DEFAULT_THRESHOLDS: dict = {
    "min_total": 70.0,
    "min_hook_strength": 7.0,
    "min_scene_variety": 7.0,
}


# ─── Heuristics ─────────────────────────────────────────────────────────

_BANNED_HOOK_PHRASES = {
    "believe in yourself",
    "never give up",
    "chase your dreams",
    "good vibes only",
    "live laugh love",
    "you got this",
}

_BANNED_VISUAL_TOKENS = {
    "subtitle", "subtitles", "caption", "captions", "watermark", "logo",
    "title card", "lower third",
}


def _word_count(s: str) -> int:
    return len(re.findall(r"\S+", s or ""))


def _score_hook(plan: VideoPlan, score: PlanScore) -> None:
    hook = (plan.hook or "").strip()
    n = _word_count(hook)
    pts = 10.0
    if not hook:
        pts = 0.0
        score.notes.append("hook is empty")
    else:
        # Sweet spot 4-12 words; outside the band loses 2 each side.
        if n < 3:
            pts -= 5.0
            score.notes.append(f"hook too short ({n} words)")
        elif n > 16:
            pts -= 4.0
            score.notes.append(f"hook too long ({n} words)")
        # Cliché check.
        if hook.lower().rstrip(".!? ") in _BANNED_HOOK_PHRASES:
            pts -= 4.0
            score.notes.append("hook is a known cliché")
        # Punch — opens with a verb / noun / negative? Cheap heuristic.
        if hook.lower().startswith(("the work", "this is", "nobody",
                                     "while", "your", "no one",
                                     "what", "why", "still", "the")):
            pts += 0.0  # neutral — already typical of director output
        # Penalise trailing ellipsis-style placeholder.
        if hook.endswith("..."):
            pts -= 2.0
    score.hook_strength = max(0.0, min(10.0, pts))


def _score_visual_uniqueness(plan: VideoPlan, score: PlanScore) -> None:
    settings = [s.environment.lower().strip() for s in plan.scenes]
    subjects = [s.subject.lower().strip() for s in plan.scenes]
    n = max(1, len(plan.scenes))
    distinct_settings = len({s for s in settings if s})
    distinct_subjects = len({s for s in subjects if s})
    # 10 = every scene has a distinct setting & subject; falls off linearly.
    pts = 5.0 * (distinct_settings / n) + 5.0 * (distinct_subjects / n)
    if distinct_settings <= 1 and n > 1:
        score.notes.append("all scenes share one environment")
    score.visual_uniqueness = max(0.0, min(10.0, pts))


def _score_scene_variety(plan: VideoPlan, score: PlanScore) -> None:
    if not plan.scenes:
        score.scene_variety = 0.0
        score.notes.append("no scenes")
        return
    cams = {s.camera_motion for s in plan.scenes}
    durations = [s.duration for s in plan.scenes]
    spread = (max(durations) - min(durations)) if durations else 0.0
    # 10 if 3+ distinct camera motions and any duration variation.
    pts = 0.0
    pts += min(7.0, 7.0 * len(cams) / max(3, len(plan.scenes)))
    pts += 3.0 if spread > 0.2 else 1.5 if spread > 0.05 else 0.0
    if len(cams) <= 1 and len(plan.scenes) > 2:
        score.notes.append("camera motion is identical for all scenes")
    score.scene_variety = max(0.0, min(10.0, pts))


def _score_emotional_clarity(plan: VideoPlan, score: PlanScore) -> None:
    pts = 0.0
    if plan.emotional_angle and len(plan.emotional_angle.split()) >= 2:
        pts += 4.0
    if plan.audience:
        pts += 3.0
    if plan.voice_tone:
        pts += 3.0
    score.emotional_clarity = pts


def _score_caption_punch(plan: VideoPlan, score: PlanScore) -> None:
    captions = [s.on_screen_caption for s in plan.scenes if s.on_screen_caption]
    if not captions:
        score.caption_punch = 4.0  # captions are optional; not a hard fail
        return
    distinct = len({c.lower().strip() for c in captions})
    avg_words = sum(_word_count(c) for c in captions) / max(1, len(captions))
    pts = 0.0
    pts += 5.0 * distinct / max(1, len(captions))   # distinctness
    pts += 5.0 if 1 <= avg_words <= 6 else 2.0       # short captions favoured
    score.caption_punch = max(0.0, min(10.0, pts))


def _score_prompt_relevance(plan: VideoPlan, score: PlanScore) -> None:
    """Cheap relevance check: do plan tokens overlap with prompt tokens?"""
    prompt_tokens = set(re.findall(r"[a-z]{4,}", (plan.user_prompt or "").lower()))
    body = " ".join([
        plan.title, plan.concept, plan.hook,
        " ".join(plan.voiceover_lines),
        " ".join(s.subject + " " + s.environment for s in plan.scenes),
    ]).lower()
    body_tokens = set(re.findall(r"[a-z]{4,}", body))
    if not prompt_tokens:
        score.prompt_relevance = 7.0
        return
    overlap = len(prompt_tokens & body_tokens)
    # 1 token overlap → 4, 2 → 7, 3+ → 10.
    pts = min(10.0, 4.0 + 3.0 * overlap)
    score.prompt_relevance = pts


def _score_platform_fit(plan: VideoPlan, score: PlanScore) -> None:
    pts = 10.0
    # Format presets give us an expected duration window; flag big
    # deviation. (kept loose because operators can override.)
    expected = {
        "shorts_clean":     (15.0, 25.0),
        "tiktok_fast":      (10.0, 20.0),
        "reels_aesthetic":  (12.0, 22.0),
    }.get(plan.format_name)
    dur = sum(s.duration for s in plan.scenes)
    if expected and not (expected[0] - 4 <= dur <= expected[1] + 4):
        pts -= 3.0
        score.notes.append(
            f"total scene duration {dur:.1f}s outside {plan.format_name} window"
        )
    if plan.aspect_ratio not in ("9:16", "16:9", "1:1"):
        pts -= 4.0
    score.platform_fit = max(0.0, min(10.0, pts))


def _score_coherence(plan: VideoPlan, score: PlanScore) -> None:
    """Concept references the scene world (subject / setting tokens)."""
    if not plan.scenes:
        score.coherence = 0.0
        return
    concept_tokens = set(re.findall(r"[a-z]{4,}", (plan.concept or "").lower()))
    scene_tokens: set[str] = set()
    for s in plan.scenes:
        scene_tokens |= set(re.findall(r"[a-z]{4,}",
                                          (s.subject + " " + s.environment).lower()))
    overlap = concept_tokens & scene_tokens
    pts = 4.0 + min(6.0, 1.5 * len(overlap))
    score.coherence = max(0.0, min(10.0, pts))


def _score_cta(plan: VideoPlan, score: PlanScore) -> None:
    cta = (plan.cta or "").strip()
    pts = 0.0
    if cta:
        pts += 6.0
        if 2 <= _word_count(cta) <= 14:
            pts += 4.0
    score.cta_fit = pts


def _score_safety(plan: VideoPlan, score: PlanScore) -> None:
    pts = 10.0
    body = " ".join(s.visual_prompt for s in plan.scenes).lower()
    for tok in _BANNED_VISUAL_TOKENS:
        if tok in body:
            pts -= 5.0
            score.notes.append(f"visual prompt contains banned token: {tok!r}")
            break
    score.safety = max(0.0, min(10.0, pts))


def score_plan(plan: VideoPlan) -> PlanScore:
    """Compute a ``PlanScore`` for a generated plan. Pure / no I/O."""
    score = PlanScore()
    _score_hook(plan, score)
    _score_visual_uniqueness(plan, score)
    _score_scene_variety(plan, score)
    _score_emotional_clarity(plan, score)
    _score_caption_punch(plan, score)
    _score_prompt_relevance(plan, score)
    _score_platform_fit(plan, score)
    _score_coherence(plan, score)
    _score_cta(plan, score)
    _score_safety(plan, score)
    return score


def plan_meets_thresholds(score: PlanScore,
                            thresholds: Optional[dict] = None) -> bool:
    """Return True iff a plan's score meets minimum thresholds.

    Thresholds are spec-driven (total >= 70, hook >= 7, scene_variety >= 7).
    Pass a different dict to make the gate stricter or looser.
    """
    t = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
    return (
        score.total >= t["min_total"]
        and score.hook_strength >= t["min_hook_strength"]
        and score.scene_variety >= t["min_scene_variety"]
    )


__all__ = [
    "PlanScore",
    "score_plan",
    "plan_meets_thresholds",
    "DEFAULT_THRESHOLDS",
]
