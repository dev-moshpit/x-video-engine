"""Creative director — the entry point for prompt-native generation.

A thin facade over the existing combinatorial director (which already owns
the theme pools, RNG seed math, and concept composition). The package's
public API funnels through this module so callers can write::

    from xvideo.prompt_native import generate_video_plan
    plans = generate_video_plan(prompt="...", variations=5)

without caring where the implementation lives.

Design notes
------------
- The director is **deterministic** given a seed. No LLM dependency, no
  network call, no GPU. Cheap to call from tests and the UI thread.
- The director's signature matches the spec section 4: it returns a
  ``list[VideoPlan]`` even when ``variations=1``. CLI/UI then iterate.
- An optional ``score_and_filter`` flag lets callers gate weak plans
  through ``scoring.py`` and regenerate up to ``regenerate_attempts``
  times if the heuristic score is below threshold. Default off (the
  scorer is opt-in so existing callers don't change behavior).
"""

from __future__ import annotations

import logging
import secrets
from typing import Optional

from xvideo.prompt_video_director import (
    available_themes,
    detect_theme,
    generate_variations as _generate_variations_impl,
    generate_video_plan as _generate_one_plan,
)
from xvideo.prompt_native.schema import VideoPlan
from xvideo.prompt_native.safety_filters import sanitize_user_prompt

logger = logging.getLogger(__name__)


def _resolve_seed_for_call(user_seed: Optional[int]) -> int:
    """Resolve the per-call seed.

    Spec: same prompt with no seed produces a *different* video every
    call. The flat-file director below us, given ``seed=None``, derives
    the RNG seed deterministically from ``(prompt_hash, variation_id)``
    — fine for reproducibility, wrong for "fresh by default". So when
    the caller didn't pin a seed, we mint one from OS entropy here. The
    minted seed is recorded in the plan so the operator can replay the
    same direction by passing it back as ``--seed``.
    """
    if user_seed is not None:
        return int(user_seed)
    # 31-bit so the result still fits a Python int comfortably and the
    # downstream xor-mix in ``_seed_for`` stays inside 32-bit.
    return secrets.randbelow(2 ** 31)


def generate_video_plan(
    prompt: str,
    platform: str = "shorts_clean",
    duration: Optional[float] = None,
    style: Optional[str] = None,
    seed: Optional[int] = None,
    variations: int = 1,
    aspect_ratio: str = "9:16",
    score_and_filter: bool = False,
    regenerate_attempts: int = 2,
) -> list[VideoPlan]:
    """Produce ``variations`` distinct ``VideoPlan``s from one user prompt.

    Args:
        prompt: free-form creative request (e.g. "Make a motivational
            video about discipline. Cinematic, intense.").
        platform: one of the format presets — ``shorts_clean`` /
            ``tiktok_fast`` / ``reels_aesthetic``. Drives target duration
            and primary platform packaging.
        duration: target final-MP4 duration in seconds. None → use the
            format preset's default.
        style: optional style cue layered on top of the prompt
            (e.g. ``"intense"``, ``"dreamy"``, ``"neon"``).
        seed: pin the variation RNG for reproducibility. None → every
            call to the same prompt produces a different plan.
        variations: how many distinct creative directions to produce.
        aspect_ratio: ``"9:16"`` (default) / ``"16:9"`` / ``"1:1"``.
        score_and_filter: if True, run each plan through ``scoring`` and
            regenerate (with a fresh per-attempt seed offset) up to
            ``regenerate_attempts`` times if it fails the thresholds.
            Default False to preserve the current variation behavior of
            existing callers (UI / e2e smoke).

    Returns:
        ``list[VideoPlan]`` of length ``variations``. Plans within the
        list have distinct ``variation_id`` values (0, 1, 2, …) and are
        ordered as generated.
    """
    if variations < 1:
        raise ValueError("variations must be >= 1")
    cleaned = sanitize_user_prompt(prompt)

    # Resolve seed once per call. None → fresh OS entropy so same prompt
    # produces a different video each call (spec). Explicit seed → pinned.
    resolved_seed = _resolve_seed_for_call(seed)
    plans = _generate_variations_impl(
        user_prompt=cleaned,
        n=variations,
        platform_format=platform,
        duration_target=duration,
        style_preference=style,
        seed=resolved_seed,
        aspect_ratio=aspect_ratio,
    )

    if not score_and_filter:
        return plans

    # Opt-in regenerate loop. We re-call with a different ``seed`` offset
    # because the RNG is fully deterministic from (seed, variation_id) —
    # the only knob the caller has to *force* a different direction is
    # the seed itself. Use a fresh per-attempt seed perturbation.
    from xvideo.prompt_native.scoring import (
        plan_meets_thresholds, score_plan,
    )

    out: list[VideoPlan] = []
    for i, plan in enumerate(plans):
        attempt = 0
        score = score_plan(plan)
        while not plan_meets_thresholds(score) and attempt < regenerate_attempts:
            attempt += 1
            attempt_seed = (seed if seed is not None else 0) + (attempt * 99991)
            logger.info(
                "[prompt_native] regenerate plan v%d attempt %d (score=%.1f)",
                i, attempt, score.total,
            )
            plan = _generate_one_plan(
                user_prompt=cleaned,
                platform_format=platform,
                duration_target=duration,
                style_preference=style,
                seed=attempt_seed,
                variation_id=i,
                aspect_ratio=aspect_ratio,
            )
            score = score_plan(plan)
        # Whether or not it passed, attach the score so the UI can render it.
        try:
            object.__setattr__(plan, "_score", score)  # dataclass not frozen
        except Exception:  # pragma: no cover — defensive
            pass
        out.append(plan)
    return out


def generate_variations(
    prompt: str,
    n: int = 1,
    **kwargs,
) -> list[VideoPlan]:
    """Spec alias for ``generate_video_plan(..., variations=n)``."""
    return generate_video_plan(prompt, variations=n, **kwargs)


__all__ = [
    "generate_video_plan",
    "generate_variations",
    "available_themes",
    "detect_theme",
]
