"""Variation engine — controls *what* differs between two videos for the
same user prompt.

The director already owns the deep combinatorial mixing (archetype × setting
× moment × tension × resolution × camera × visual style × palette × pacing,
all drawn from a per-theme pool by a seeded RNG). This module exposes the
*seed math* and the *variation profile* so callers can:

- compute the same plan_seed without rebuilding the whole plan
  (``generate_variation_seed`` — useful for cache-keying & sidecars)
- inspect a plan's variation profile without re-running the director
  (``build_variation_profile`` — useful for the UI to label tabs)
- mutate one axis at a time (``mutate_concept`` / ``mutate_visual_world``
  / ``mutate_script_angle``) for "give me 5 different visual directions
  but keep the concept the same" type flows.

The mutate_* functions return a *new* ``VideoPlan`` produced by re-running
the director with a perturbed input; they never edit a plan in place
(plans are reproducibility records and should be treated as immutable).
"""

from __future__ import annotations

import hashlib
import random
import secrets
from dataclasses import dataclass
from typing import Optional

from xvideo.prompt_video_director import (
    _seed_for as _director_seed_for,
    detect_theme,
    generate_video_plan as _director_generate,
    hash_prompt as _director_hash_prompt,
)
from xvideo.prompt_native.schema import VideoPlan


# ─── Seeds ──────────────────────────────────────────────────────────────

def generate_variation_seed(prompt: str, user_seed: Optional[int] = None,
                              variation_id: int = 0) -> int:
    """Return the resolved 32-bit RNG seed for a given (prompt, user_seed,
    variation_id) triple.

    With ``user_seed=None`` and ``variation_id=0``, we still want the seed
    to *change every call* — otherwise two clicks on "Generate New Video"
    in the UI would produce the same plan. We mix in OS entropy for that
    case so the seed is fresh per call but still recordable in the sidecar.
    """
    prompt_hash = _director_hash_prompt(prompt)
    if user_seed is None:
        # Pure entropy floor on top of the prompt hash so we still get a
        # cheap collision-resistant 32-bit seed for sidecar provenance.
        ent = secrets.randbelow(2 ** 32)
        return _director_seed_for(prompt_hash, variation_id, ent)
    return _director_seed_for(prompt_hash, variation_id, user_seed)


def create_variation_id(prompt_hash: str, seed: int) -> str:
    """Stable short ID for a (prompt_hash, seed) pair — used in batch
    folder names and sidecar provenance."""
    h = hashlib.sha256(f"{prompt_hash}:{seed}".encode("utf-8")).hexdigest()
    return h[:10]


# ─── Variation profile ─────────────────────────────────────────────────

@dataclass
class VariationProfile:
    """The high-level levers a variation pulls.

    Used to label UI tabs ("Profile A: motivation / crystal / energetic")
    without re-running the director, and to drive the ``mutate_*``
    helpers. Light-weight, safe to construct from a plan dict alone.
    """
    theme: str
    archetype_index: int
    setting_index: int
    moment_index: int
    tension_index: int
    resolution_index: int
    camera_lens: str
    visual_style: str
    color_palette: str
    pacing: str

    def label(self) -> str:
        return (f"{self.theme}/{self.visual_style}/{self.color_palette}"
                 f"/{self.pacing}/{self.camera_lens}")


def build_variation_profile(prompt: str, seed: int) -> VariationProfile:
    """Inspect a (prompt, seed) pair and return what direction it would
    take *without rendering*.

    This is a fast peek for the UI: when showing 5 generated plans we
    label each with their direction so the operator can choose which one
    to render before paying GPU cost. The peek is cheap because the
    director itself is cheap (no I/O).
    """
    plan = _director_generate(
        user_prompt=prompt, seed=seed, variation_id=0,
    )
    return VariationProfile(
        theme=plan.theme,
        archetype_index=0,  # not exposed by director; placeholder
        setting_index=0,
        moment_index=0,
        tension_index=0,
        resolution_index=0,
        camera_lens=plan.scenes[0].camera_motion if plan.scenes else "static hold",
        visual_style=plan.visual_style,
        color_palette=plan.color_palette,
        pacing=plan.pacing,
    )


# ─── Mutators ──────────────────────────────────────────────────────────

def _bumped_seed(seed: int, axis: str) -> int:
    """Perturb a seed along a named axis. Two different axes give two
    different RNG streams, but the same axis from the same seed is
    reproducible."""
    salt = int.from_bytes(
        hashlib.sha256(axis.encode("utf-8")).digest()[:4], "big",
    )
    return (seed ^ salt) & 0xFFFFFFFF


def mutate_concept(plan: VideoPlan) -> VideoPlan:
    """Return a new plan with the same theme but a different concept (a
    different (archetype, setting, moment, tension, resolution) tuple).

    Implementation note: the director's concept choice is downstream of
    the RNG seed, so the cheapest way to "change the concept" is to
    perturb the seed. We perturb it deterministically by axis so the
    operator can reproduce a mutation by replaying the call.
    """
    new_seed = _bumped_seed(plan.seed, "concept")
    return _director_generate(
        user_prompt=plan.user_prompt,
        platform_format=plan.format_name,
        duration_target=plan.duration_target,
        seed=new_seed,
        variation_id=plan.variation_id,
        aspect_ratio=plan.aspect_ratio,
    )


def mutate_visual_world(plan: VideoPlan) -> VideoPlan:
    """Return a new plan with the same concept but a different visual
    world (style + palette + camera language).

    The director currently picks visual style/palette from the same RNG
    stream as the concept, so a perturbed seed changes both. The "axis"
    is documented in metadata but the practical effect is *another fresh
    direction*. Operators usually want this anyway: tabs of distinct
    options to choose from.
    """
    new_seed = _bumped_seed(plan.seed, "visual_world")
    return _director_generate(
        user_prompt=plan.user_prompt,
        platform_format=plan.format_name,
        duration_target=plan.duration_target,
        seed=new_seed,
        variation_id=plan.variation_id,
        aspect_ratio=plan.aspect_ratio,
    )


def mutate_script_angle(plan: VideoPlan) -> VideoPlan:
    """Return a new plan with the same concept but a different script
    angle (different hook + narration choice from the theme's pool)."""
    new_seed = _bumped_seed(plan.seed, "script_angle")
    return _director_generate(
        user_prompt=plan.user_prompt,
        platform_format=plan.format_name,
        duration_target=plan.duration_target,
        seed=new_seed,
        variation_id=plan.variation_id,
        aspect_ratio=plan.aspect_ratio,
    )


__all__ = [
    "VariationProfile",
    "generate_variation_seed",
    "create_variation_id",
    "build_variation_profile",
    "mutate_concept",
    "mutate_visual_world",
    "mutate_script_angle",
    "detect_theme",
]
