"""Prompt compiler — merges LowPolySpec + StyleConfig into backend-ready prompts.

Includes style guards that resolve contradictions between preset settings
and user overrides. Presets don't just add tokens — they suppress
conflicting language too.

apply_style_guards returns both the corrected spec AND a list of
GuardMutation records for artifact metadata.
"""

from __future__ import annotations

import logging

from xvideo.spec import (
    CameraMove,
    GuardMutation,
    LightingMode,
    LowPolySpec,
    PaletteMode,
    PolyDensity,
    StyleConfig,
)

logger = logging.getLogger(__name__)

# ─── Vocabulary maps ─────────────────────────────────────────────────────

_DENSITY_TERMS: dict[PolyDensity, str] = {
    PolyDensity.MINIMAL: "extremely low poly, abstract geometric silhouette, very few triangles",
    PolyDensity.LOW: "low poly, chunky geometric shapes, visible triangular faces",
    PolyDensity.MEDIUM: "low poly 3d render, clean triangular mesh, faceted surfaces",
    PolyDensity.HIGH: "detailed low poly, dense triangular mesh, sharp geometric facets",
}

_PALETTE_TERMS: dict[PaletteMode, str] = {
    PaletteMode.MONOCHROME: "monochrome color palette, single hue variations",
    PaletteMode.DUOTONE: "duotone color palette, two contrasting colors",
    PaletteMode.TRICOLOR: "three-color palette, bold color blocking",
    PaletteMode.PASTEL: "soft pastel color palette, muted gentle tones",
    PaletteMode.NEON: "neon color palette, vibrant glowing colors, electric tones",
    PaletteMode.EARTH: "earth tone palette, natural browns greens and ochres",
    PaletteMode.CUSTOM: "",
}

_LIGHTING_TERMS: dict[LightingMode, str] = {
    LightingMode.FLAT: "flat shading, uniform lighting, no shadows",
    LightingMode.GRADIENT: "gradient lighting, smooth light transitions across facets",
    LightingMode.DRAMATIC: "dramatic lighting, strong directional light, deep shadows",
    LightingMode.BACKLIT: "backlit silhouette, rim lighting, glowing edges",
    LightingMode.AMBIENT_OCCLUSION: "ambient occlusion, soft contact shadows between facets",
}

_NEGATIVE_PROMPT = (
    "photorealistic, smooth surfaces, organic textures, film grain, bokeh, "
    "lens flare, motion blur, high detail skin, hair strands, realistic lighting, "
    "ray tracing, subsurface scattering, noise, artifacts, blurry, watermark, "
    "text, signature, jpeg artifacts, deformed, ugly, duplicate"
)


# ─── Style guards — contradiction resolution ─────────────────────────────

def apply_style_guards(spec: LowPolySpec) -> tuple[LowPolySpec, list[GuardMutation]]:
    """Resolve contradictions and return (corrected_spec, mutations).

    The mutations list records every override for artifact metadata.
    """
    spec = spec.model_copy(deep=True)
    style = spec.style
    mutations: list[GuardMutation] = []

    # wireframe: enforce backlit, suppress flat shading tags
    if style.preset_name == "wireframe":
        if style.lighting == LightingMode.FLAT:
            mutations.append(GuardMutation(
                rule="wireframe_no_flat", field="lighting",
                from_value=style.lighting.value, to_value="backlit",
            ))
            style.lighting = LightingMode.BACKLIT
        if "flat shading" in " ".join(style.extra_tags).lower():
            mutations.append(GuardMutation(
                rule="wireframe_strip_flat_tags", field="extra_tags",
                from_value="[contained flat shading]", to_value="[removed]",
            ))
            style.extra_tags = [
                t for t in style.extra_tags
                if "flat shading" not in t.lower()
            ]

    # neon_arcade: enforce dark background + neon palette
    if style.preset_name == "neon_arcade":
        if style.palette not in (PaletteMode.NEON, PaletteMode.CUSTOM):
            mutations.append(GuardMutation(
                rule="neon_arcade_palette", field="palette",
                from_value=style.palette.value, to_value="neon",
            ))
            style.palette = PaletteMode.NEON
        if "dark" not in style.background.lower() and "black" not in style.background.lower():
            mutations.append(GuardMutation(
                rule="neon_arcade_background", field="background",
                from_value=style.background, to_value="dark space with neon glow",
            ))
            style.background = "dark space with neon glow"

    # monument: bias toward static or slow camera
    if style.preset_name == "monument":
        fast_moves = {CameraMove.TRACKING, CameraMove.CRANE, CameraMove.PAN_LEFT, CameraMove.PAN_RIGHT}
        if spec.camera in fast_moves:
            mutations.append(GuardMutation(
                rule="monument_fast_camera", field="camera",
                from_value=spec.camera.value, to_value="orbit",
            ))
            spec.camera = CameraMove.ORBIT
            old_speed = spec.camera_speed
            spec.camera_speed = min(spec.camera_speed, 0.3)
            if old_speed != spec.camera_speed:
                mutations.append(GuardMutation(
                    rule="monument_speed_cap", field="camera_speed",
                    from_value=str(old_speed), to_value=str(spec.camera_speed),
                ))
        elif spec.camera_speed > 0.4:
            mutations.append(GuardMutation(
                rule="monument_speed_cap", field="camera_speed",
                from_value=str(spec.camera_speed), to_value="0.4",
            ))
            spec.camera_speed = 0.4

    # papercraft: minimal density → low
    if style.preset_name == "papercraft" and style.poly_density == PolyDensity.MINIMAL:
        mutations.append(GuardMutation(
            rule="papercraft_min_density", field="poly_density",
            from_value="minimal", to_value="low",
        ))
        style.poly_density = PolyDensity.LOW

    for m in mutations:
        logger.info("Style guard: %s %s: %s → %s", m.rule, m.field, m.from_value, m.to_value)

    spec.style = style
    return spec, mutations


# ─── Prompt compilation ──────────────────────────────────────────────────

def compile_prompt(spec: LowPolySpec) -> tuple[str, str, list[GuardMutation]]:
    """Return (positive_prompt, negative_prompt, guard_mutations).

    Applies style guards before compiling.
    """
    spec, mutations = apply_style_guards(spec)
    style = spec.style
    parts: list[str] = []

    # Core aesthetic
    parts.append(_DENSITY_TERMS[style.poly_density])

    # Subject + action
    subject_phrase = spec.subject
    if spec.action:
        subject_phrase = f"{spec.subject} {spec.action}"
    parts.append(subject_phrase)

    # Environment
    if spec.environment:
        parts.append(spec.environment)

    # Palette
    if style.palette == PaletteMode.CUSTOM and style.custom_colors:
        color_str = " and ".join(style.custom_colors[:6])
        parts.append(f"color palette of {color_str}")
    else:
        palette_term = _PALETTE_TERMS.get(style.palette, "")
        if palette_term:
            parts.append(palette_term)

    # Lighting
    parts.append(_LIGHTING_TERMS[style.lighting])

    # Background
    if style.background:
        parts.append(f"{style.background} background")

    # Camera
    if spec.camera != CameraMove.STATIC:
        speed_word = "slow" if spec.camera_speed < 0.3 else "smooth" if spec.camera_speed < 0.7 else "dynamic"
        parts.append(f"{speed_word} {spec.camera.value.replace('_', ' ')} camera movement")

    # Core style reinforcement
    parts.append("stylized minimalist, clean geometric edges, sharp polygon faces")

    # Extra tags from preset
    if style.extra_tags:
        parts.extend(style.extra_tags)

    positive = ", ".join(parts)
    return positive, _NEGATIVE_PROMPT, mutations
