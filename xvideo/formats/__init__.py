"""Social-format preset layer.

A **format** is a thin, deterministic modifier on top of a pack:
    duration window, motion bias, primary platform choice, and publish-
    metadata overrides (CTA pool, hashtag additions, max tags).

Formats are NOT a second brain. They cannot:
    - change required columns
    - rewrite pack-specific negative prompts
    - touch subject/action/environment logic
    - override motion beyond pack.allowed_motion

Override order (highest wins):
    format overrides > row values > pack defaults

JSON schema (see *.json in this dir):
    {
      "name": "shorts_clean",
      "description": "...",
      "primary_platform": "shorts" | "tiktok" | "reels",
      "duration":   {"min": 18.0, "max": 22.0},      // optional clamp window
      "motion_bias": "up" | "down" | "keep",
      "publish_overrides": {
          "cta_pool_replace":   [...],               // optional; replaces pack CTA pool
          "hashtag_additions":  [...],               // appended to pack base_hashtags
          "max_hashtags":       10                   // optional; overrides pack cap
      }
    }
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_MOTION_LADDER: list[str] = ["calm", "medium", "energetic"]


@dataclass
class FormatConfig:
    name: str
    description: str = ""
    primary_platform: str = "shorts"
    duration_min: float | None = None
    duration_max: float | None = None
    motion_bias: str = "keep"            # "up" | "down" | "keep"
    cta_pool_replace: list[str] | None = None
    hashtag_additions: list[str] = field(default_factory=list)
    max_hashtags: int | None = None

    # ── Load / discover ──────────────────────────────────────────────────

    @classmethod
    def load(cls, path: str | Path) -> "FormatConfig":
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Format config not found: {path}")
        cfg = json.loads(path.read_text(encoding="utf-8"))
        return cls.from_dict(cfg)

    @classmethod
    def from_dict(cls, cfg: dict) -> "FormatConfig":
        duration = cfg.get("duration") or {}
        pub = cfg.get("publish_overrides") or {}
        return cls(
            name=cfg.get("name", "unnamed"),
            description=cfg.get("description", ""),
            primary_platform=cfg.get("primary_platform", "shorts"),
            duration_min=(float(duration["min"]) if "min" in duration else None),
            duration_max=(float(duration["max"]) if "max" in duration else None),
            motion_bias=cfg.get("motion_bias", "keep"),
            cta_pool_replace=pub.get("cta_pool_replace"),
            hashtag_additions=list(pub.get("hashtag_additions", [])),
            max_hashtags=(int(pub["max_hashtags"]) if "max_hashtags" in pub else None),
        )

    # ── Serialize (for sidecar / manifest provenance) ────────────────────

    def to_sidecar(self) -> dict:
        return {
            "name": self.name,
            "primary_platform": self.primary_platform,
            "duration_min": self.duration_min,
            "duration_max": self.duration_max,
            "motion_bias": self.motion_bias,
            "cta_pool_replaced": self.cta_pool_replace is not None,
            "hashtag_additions": self.hashtag_additions,
            "max_hashtags": self.max_hashtags,
        }


def _formats_dir() -> Path:
    return Path(__file__).resolve().parent


def list_formats() -> list[str]:
    """Names of all format JSONs under xvideo/formats/."""
    d = _formats_dir()
    return sorted(p.stem for p in d.glob("*.json"))


def load_format(name: str) -> FormatConfig:
    d = _formats_dir()
    path = d / f"{name}.json"
    if not path.exists():
        raise FileNotFoundError(
            f"Format '{name}' not found in {d}. Available: {list_formats()}"
        )
    return FormatConfig.load(path)


# ─── Apply helpers ──────────────────────────────────────────────────────

def _shift_motion(current: str, bias: str, allowed: list[str]) -> str:
    """Shift motion one step along the ladder, clamped to pack's allowed list.

    Never returns a motion the pack disallows. If the shifted motion isn't
    allowed, tries one more step in the same direction. If neither is
    allowed, falls back to `current` unchanged.
    """
    if bias == "keep" or current not in _MOTION_LADDER:
        return current
    idx = _MOTION_LADDER.index(current)
    direction = 1 if bias == "up" else -1

    for step in (1, 2):
        new_idx = idx + direction * step
        if 0 <= new_idx < len(_MOTION_LADDER):
            candidate = _MOTION_LADDER[new_idx]
            if candidate in allowed:
                return candidate
    return current


def clamp_duration(duration: float, fmt: FormatConfig) -> float:
    """Clamp a duration into the format's window. No window = unchanged."""
    if fmt.duration_min is not None and duration < fmt.duration_min:
        return fmt.duration_min
    if fmt.duration_max is not None and duration > fmt.duration_max:
        return fmt.duration_max
    return duration


def apply_format_to_job(job, fmt: FormatConfig, pack_allowed_motion: list[str] | None) -> None:
    """Mutate a BatchJob in place: shift motion (if allowed), clamp duration,
    stamp format name. Format wins over row values by design.

    Motion bias respects pack.allowed_motion; if the shifted motion isn't
    in that list, the job keeps its current motion.
    """
    allowed = pack_allowed_motion or _MOTION_LADDER
    if fmt.motion_bias != "keep":
        job.motion = _shift_motion(job.motion, fmt.motion_bias, allowed)
    job.duration_sec = clamp_duration(job.duration_sec, fmt)
    job.format = fmt.name


def format_as_publish_overrides(fmt: FormatConfig) -> dict:
    """Shape a FormatConfig as the override dict accepted by
    build_publish_metadata(format_overrides=...).
    """
    return {
        "primary_platform": fmt.primary_platform,
        "cta_pool_replace": fmt.cta_pool_replace,
        "hashtag_additions": fmt.hashtag_additions,
        "max_hashtags": fmt.max_hashtags,
    }
