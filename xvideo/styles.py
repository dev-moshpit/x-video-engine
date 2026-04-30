"""Style preset loader — reads configs/styles/*.yaml and merges with user overrides.

Each preset YAML defines default values for StyleConfig fields. User
overrides take precedence. The loader is called by Engine.plan() to
resolve the final StyleConfig before prompt compilation.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import yaml

from xvideo.spec import LightingMode, PaletteMode, PolyDensity, StyleConfig

logger = logging.getLogger(__name__)

_STYLES_DIR = Path(__file__).resolve().parents[1] / "configs" / "styles"

# In-memory cache: loaded once, kept for the process lifetime.
_preset_cache: dict[str, dict] = {}


def _load_presets(styles_dir: Path | None = None) -> dict[str, dict]:
    """Load all *.yaml presets from the styles directory."""
    d = styles_dir or _STYLES_DIR
    if not d.is_dir():
        logger.warning("Styles directory not found: %s", d)
        return {}
    presets: dict[str, dict] = {}
    for f in sorted(d.glob("*.yaml")):
        try:
            raw = yaml.safe_load(f.read_text()) or {}
            name = raw.get("name", f.stem)
            presets[name] = raw
        except Exception as e:
            logger.warning("Failed to load preset %s: %s", f.name, e)
    return presets


def available_presets(styles_dir: Path | None = None) -> list[str]:
    """Return names of all available style presets."""
    global _preset_cache
    if not _preset_cache:
        _preset_cache = _load_presets(styles_dir)
    return list(_preset_cache.keys())


def resolve_style(
    preset_name: str,
    overrides: Optional[dict] = None,
    styles_dir: Path | None = None,
) -> StyleConfig:
    """Load a preset by name and apply user overrides on top.

    Precedence: user overrides > preset YAML > StyleConfig defaults.
    """
    global _preset_cache
    if not _preset_cache:
        _preset_cache = _load_presets(styles_dir)

    preset = _preset_cache.get(preset_name, {})
    if not preset and preset_name != "crystal":
        logger.warning("Unknown preset '%s'; falling back to defaults", preset_name)

    # Map YAML keys → StyleConfig field values
    merged: dict = {"preset_name": preset_name}

    _DENSITY_MAP = {v.value: v for v in PolyDensity}
    _PALETTE_MAP = {v.value: v for v in PaletteMode}
    _LIGHTING_MAP = {v.value: v for v in LightingMode}

    if "poly_density" in preset:
        merged["poly_density"] = _DENSITY_MAP.get(preset["poly_density"], PolyDensity.MEDIUM)
    if "palette" in preset:
        merged["palette"] = _PALETTE_MAP.get(preset["palette"], PaletteMode.PASTEL)
    if "lighting" in preset:
        merged["lighting"] = _LIGHTING_MAP.get(preset["lighting"], LightingMode.GRADIENT)
    if "background" in preset:
        merged["background"] = preset["background"]
    if "extra_tags" in preset:
        merged["extra_tags"] = list(preset["extra_tags"])

    # Apply user overrides last
    if overrides:
        for key, val in overrides.items():
            if key == "poly_density" and isinstance(val, str):
                merged[key] = _DENSITY_MAP.get(val, val)
            elif key == "palette" and isinstance(val, str):
                merged[key] = _PALETTE_MAP.get(val, val)
            elif key == "lighting" and isinstance(val, str):
                merged[key] = _LIGHTING_MAP.get(val, val)
            else:
                merged[key] = val

    return StyleConfig(**merged)
