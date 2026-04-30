"""Deterministic publish metadata generator — title, caption, hashtags, CTA,
platform variants — from pack config + row data.

No LLM. Template-driven. Fast, reproducible, cheap, easy to debug.
Seed-derived deterministic picks from CTA/hashtag pools ensure reruns
give the same output for the same clip.

Pack config schema (under `publish`):
    {
      "title_templates": {
        "default": "{quote}",
        "shorts":  "...",
        "tiktok":  "...",
        "reels":   "..."
      },
      "caption_templates": { ... same platforms ... },
      "cta_pool": ["Save this", "Keep going"],
      "base_hashtags": ["#motivation", "#shorts"],
      "dynamic_hashtags": {
        "tone": {
          "triumphant": ["#winning"],
          "reflective": ["#mindful"]
        }
      },
      "max_hashtags": 12
    }

Templates use the same language as packs.py row_transformer:
    {col}, {col|default}, {col|"literal"}, {TABLE[col].prop}, {col|OTHER}
Plus: {cta} is auto-injected after the CTA is chosen.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from typing import Any

from xvideo.packs import render_template

logger = logging.getLogger(__name__)


@dataclass
class PublishMetadata:
    """Publish-ready metadata for one clip."""
    title: str = ""
    caption: str = ""
    cta: str = ""
    hashtags: list[str] = field(default_factory=list)
    platforms: dict[str, dict[str, str]] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "caption": self.caption,
            "cta": self.cta,
            "hashtags": self.hashtags,
            "platforms": self.platforms,
        }


def _deterministic_pick(pool: list[str], seed: int, salt: str = "") -> str:
    """Pick one element from `pool` deterministically from seed + salt.

    Using hashlib (not random) so results are stable across Python versions
    and OSes. Empty pool → empty string.
    """
    if not pool:
        return ""
    key = f"{seed}:{salt}".encode("utf-8")
    digest = hashlib.sha256(key).digest()
    idx = int.from_bytes(digest[:4], "big") % len(pool)
    return pool[idx]


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for s in items:
        if s and s not in seen:
            out.append(s)
            seen.add(s)
    return out


def build_publish_metadata(
    pack_config: dict,
    row: dict,
    seed: int = 0,
    format_overrides: dict | None = None,
) -> PublishMetadata:
    """Build publish metadata for a single clip.

    Args:
        pack_config: full pack config dict (has `publish`, `tables`, `defaults`)
        row: the original pack CSV row (has quote/tone/topic/etc.)
        seed: numeric seed for deterministic pool picks (use clip seed)
        format_overrides: optional shape produced by
            xvideo.formats.format_as_publish_overrides(). Keys:
              - primary_platform: "shorts" | "tiktok" | "reels"  → used as
                the "main" title/caption (falls back to default if missing)
              - cta_pool_replace: optional list; replaces pack CTA pool
              - hashtag_additions: list appended to base_hashtags
              - max_hashtags: optional int; overrides pack cap

    Returns:
        PublishMetadata with title, caption, cta, hashtags, platforms.
    """
    publish_cfg = pack_config.get("publish", {})
    if not publish_cfg:
        return PublishMetadata()

    tables = pack_config.get("tables", {})
    defaults = pack_config.get("defaults", {})
    fmt = format_overrides or {}

    # Pick CTA deterministically first so it can be injected into templates.
    # Format layer may swap in its own pool without touching pack config.
    pack_cta_pool = list(publish_cfg.get("cta_pool", []))
    cta_pool = fmt.get("cta_pool_replace") or pack_cta_pool
    cta = _deterministic_pick(cta_pool, seed, salt="cta")

    # Context used for template rendering. Extends the original row with
    # publish-helper-local extras like {cta}.
    render_ctx = {**row, "cta": cta, "seed": str(seed)}

    # Default title + caption (pack-defined)
    title_tpls = publish_cfg.get("title_templates", {})
    caption_tpls = publish_cfg.get("caption_templates", {})
    default_title = render_template(title_tpls.get("default", ""), render_ctx, tables, defaults)
    default_caption = render_template(caption_tpls.get("default", ""), render_ctx, tables, defaults)

    # Hashtags: base + dynamic (row field mappings) + format additions + dedupe + cap.
    base = list(publish_cfg.get("base_hashtags", []))
    dyn = publish_cfg.get("dynamic_hashtags", {})
    extra: list[str] = []
    for field_name, mapping in dyn.items():
        key = row.get(field_name, "")
        extra.extend(mapping.get(key, []))
    format_adds = list(fmt.get("hashtag_additions") or [])
    max_tags = fmt.get("max_hashtags") or int(publish_cfg.get("max_hashtags", 15))
    hashtags = _dedupe(base + extra + format_adds)[:max_tags]

    # Platform variants (each platform can override title, caption, or both;
    # missing keys fall back to the default).
    platforms: dict[str, dict[str, str]] = {}
    for platform in ("shorts", "tiktok", "reels"):
        pv_title_tpl = title_tpls.get(platform)
        pv_caption_tpl = caption_tpls.get(platform)
        if not pv_title_tpl and not pv_caption_tpl:
            continue
        platforms[platform] = {
            "title": (
                render_template(pv_title_tpl, render_ctx, tables, defaults)
                if pv_title_tpl else default_title
            ),
            "caption": (
                render_template(pv_caption_tpl, render_ctx, tables, defaults)
                if pv_caption_tpl else default_caption
            ),
        }

    # Promote the format's primary platform variant to the top-level
    # title/caption so downstream consumers (gallery modal, manifest CSV,
    # publish_ready export) show the right copy first without extra logic.
    primary = fmt.get("primary_platform")
    if primary and primary in platforms:
        title = platforms[primary]["title"]
        caption = platforms[primary]["caption"]
    else:
        title = default_title
        caption = default_caption

    return PublishMetadata(
        title=title,
        caption=caption,
        cta=cta,
        hashtags=hashtags,
        platforms=platforms,
    )
