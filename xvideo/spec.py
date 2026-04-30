"""Core data structures for the LowPoly Video Engine.

LowPolySpec is the structured user intent. StyleConfig holds resolved
preset + overrides. ShotPlan is the single-shot dispatch unit.
FacetScore captures low-poly-specific quality metrics.
StyleDiagnostic gives structured failure reasons per take.
TimingBreakdown captures performance telemetry.
ArtifactMeta captures the full reproducibility snapshot.
"""

from __future__ import annotations

import hashlib
from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field


# ─── Low-Poly Enums ──────────────────────────────────────────────────────

class PolyDensity(str, Enum):
    MINIMAL = "minimal"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

class PaletteMode(str, Enum):
    MONOCHROME = "monochrome"
    DUOTONE = "duotone"
    TRICOLOR = "tricolor"
    PASTEL = "pastel"
    NEON = "neon"
    EARTH = "earth"
    CUSTOM = "custom"

class LightingMode(str, Enum):
    FLAT = "flat"
    GRADIENT = "gradient"
    DRAMATIC = "dramatic"
    BACKLIT = "backlit"
    AMBIENT_OCCLUSION = "ambient_occlusion"

class CameraMove(str, Enum):
    STATIC = "static"
    ORBIT = "orbit"
    DOLLY_IN = "dolly_in"
    DOLLY_OUT = "dolly_out"
    PAN_LEFT = "pan_left"
    PAN_RIGHT = "pan_right"
    TILT_UP = "tilt_up"
    TILT_DOWN = "tilt_down"
    CRANE = "crane"
    TRACKING = "tracking"

class LoopMode(str, Enum):
    NONE = "none"
    SEAMLESS = "seamless"
    PING_PONG = "ping_pong"

class BackendName(str, Enum):
    WAN21_LOWPOLY = "wan21_lowpoly"
    WAN21_LOWPOLY_I2V = "wan21_lowpoly_i2v"
    SDXL_KEYFRAME = "sdxl_keyframe"

class Mode(str, Enum):
    T2V = "t2v"
    I2V = "i2v"

class Priority(str, Enum):
    HERO = "hero"
    STANDARD = "standard"

class RenderLane(str, Enum):
    PREVIEW = "preview"
    STANDARD = "standard"
    FIDELITY = "fidelity"

class SelectedVariant(str, Enum):
    RAW = "raw"
    POSTPROCESSED = "postprocessed"
    SALVAGED = "salvaged"

class HardwareTier(str, Enum):
    """Detected or configured hardware class."""
    LAPTOP_4GB = "laptop_4gb"     # GTX 1650 4GB — minimum viable
    DESKTOP_8GB = "desktop_8gb"   # RTX 2080 8GB — comfortable
    CLOUD = "cloud"               # 16GB+ — unconstrained


# ─── Render lane defaults — hardware-aware ───────────────────────────────
# Keyed by HardwareTier. The engine selects the right profile based on
# detected or configured VRAM. On 4GB, postprocess and salvage do more
# of the aesthetic work instead of inference steps or candidates.

RENDER_LANE_DEFAULTS: dict[HardwareTier, dict[RenderLane, dict]] = {
    HardwareTier.LAPTOP_4GB: {
        RenderLane.PREVIEW: {
            "resolution": "480p",
            "duration_sec": 2.0,
            "num_candidates": 1,
            "num_inference_steps": 15,
            "guidance_scale": 6.0,
            "postprocess_enabled": False,
        },
        RenderLane.STANDARD: {
            "resolution": "480p",
            "duration_sec": 3.0,
            "num_candidates": 1,
            "num_inference_steps": 20,
            "guidance_scale": 7.0,
            "postprocess_enabled": True,
        },
        RenderLane.FIDELITY: {
            "resolution": "480p",
            "duration_sec": 3.0,
            "num_candidates": 2,
            "num_inference_steps": 25,
            "guidance_scale": 7.5,
            "postprocess_enabled": True,
        },
    },
    HardwareTier.DESKTOP_8GB: {
        RenderLane.PREVIEW: {
            "resolution": "480p",
            "duration_sec": 3.0,
            "num_candidates": 1,
            "num_inference_steps": 20,
            "guidance_scale": 6.0,
            "postprocess_enabled": False,
        },
        RenderLane.STANDARD: {
            "resolution": "480p",
            "duration_sec": 4.0,
            "num_candidates": 2,
            "num_inference_steps": 25,
            "guidance_scale": 7.0,
            "postprocess_enabled": False,
        },
        RenderLane.FIDELITY: {
            "resolution": "480p",
            "duration_sec": 4.0,
            "num_candidates": 3,
            "num_inference_steps": 30,
            "guidance_scale": 7.5,
            "postprocess_enabled": True,
        },
    },
}
# Cloud tier inherits desktop defaults (unconstrained)
RENDER_LANE_DEFAULTS[HardwareTier.CLOUD] = RENDER_LANE_DEFAULTS[HardwareTier.DESKTOP_8GB]


def detect_hardware_tier() -> HardwareTier:
    """Detect GPU VRAM and return the appropriate hardware tier."""
    try:
        import torch
        if torch.cuda.is_available():
            _, total = torch.cuda.mem_get_info(0)
            vram_gb = total / (1024 ** 3)
            if vram_gb >= 12:
                return HardwareTier.CLOUD
            elif vram_gb >= 6:
                return HardwareTier.DESKTOP_8GB
            else:
                return HardwareTier.LAPTOP_4GB
    except ImportError:
        pass
    # No GPU or torch: assume tightest constraints
    return HardwareTier.LAPTOP_4GB


def get_lane_defaults(lane: RenderLane, tier: HardwareTier | None = None) -> dict:
    """Get render lane defaults for the given hardware tier."""
    if tier is None:
        tier = detect_hardware_tier()
    return RENDER_LANE_DEFAULTS[tier][lane]


# ─── Policy thresholds — config-driven ───────────────────────────────────
# Loaded from default.yaml at runtime. These are fallback defaults.
# Can be overridden per-lane or per-preset in config.

class PolicyConfig(BaseModel):
    """Regen-vs-salvage and scoring thresholds. Config-driven."""
    reject_floor: float = 0.25
    salvage_ceiling: float = 0.45
    postprocess_improvement_threshold: float = 0.03
    # Diagnostic thresholds (lenient for v1)
    palette_cohesion_min: float = 0.35
    facet_clarity_min: float = 0.25
    stylization_strength_min: float = 0.30
    edge_stability_min: float = 0.25
    prompt_alignment_min: float = 0.20

# Global default instance — overridden by config loading
DEFAULT_POLICY = PolicyConfig()


# ─── Style Configuration ────────────────────────────────────��────────────

class StyleConfig(BaseModel):
    """Resolved style parameters — merged from preset + user overrides."""
    preset_name: str = "crystal"
    poly_density: PolyDensity = PolyDensity.MEDIUM
    palette: PaletteMode = PaletteMode.PASTEL
    custom_colors: list[str] = Field(default_factory=list)
    lighting: LightingMode = LightingMode.GRADIENT
    background: str = "clean gradient"
    extra_tags: list[str] = Field(default_factory=list)


# ─── Top-level spec ──────────────────────────────────────────────────────

class LowPolySpec(BaseModel):
    subject: str
    action: str = ""
    environment: str = ""
    style: StyleConfig = Field(default_factory=StyleConfig)
    camera: CameraMove = CameraMove.ORBIT
    camera_speed: float = Field(default=0.5, ge=0.0, le=1.0)
    loop_mode: LoopMode = LoopMode.NONE
    duration_sec: float = Field(default=3.0, gt=0.0, le=60.0)
    resolution: Literal["480p", "720p"] = "480p"
    fps: Literal[24] = 24
    aspect_ratio: Literal["16:9", "9:16", "1:1"] = "16:9"
    seed: Optional[int] = None
    reference_image: Optional[str] = None
    num_candidates: int = Field(default=1, ge=1, le=4)
    render_lane: RenderLane = RenderLane.PREVIEW
    raw_prompt: Optional[str] = None


# ─── Composer output ─────────────────────────────────────────────────────

class ShotPlan(BaseModel):
    shot_id: str
    backend: BackendName = BackendName.WAN21_LOWPOLY
    mode: Mode = Mode.T2V
    prompt: str
    negative_prompt: str = ""
    style_config: StyleConfig = Field(default_factory=StyleConfig)
    duration_sec: float = 3.0
    resolution: Literal["480p", "720p"] = "480p"
    fps: Literal[24] = 24
    aspect_ratio: str = "16:9"
    priority: Priority = Priority.STANDARD
    num_candidates: int = 1
    seed: int = 0
    num_inference_steps: int = 25
    guidance_scale: float = 7.0
    render_lane: RenderLane = RenderLane.PREVIEW


class ExecutionPlan(BaseModel):
    spec_id: str
    shots: list[ShotPlan]
    estimated_cost_usd: float = 0.0
    notes: str = ""


# ─── Scoring ─────────────────────────────────────────────────────────────

SCORER_WEIGHTS_V1 = {
    "facet_clarity": 0.30,
    "palette_cohesion": 0.20,
    "prompt_alignment": 0.20,
    "edge_stability": 0.15,
    "stylization_strength": 0.15,
}

class FacetScore(BaseModel):
    """All metrics 0-1, higher is better."""
    facet_clarity: float = Field(default=0.0, ge=0.0, le=1.0)
    palette_cohesion: float = Field(default=0.0, ge=0.0, le=1.0)
    prompt_alignment: float = Field(default=0.0, ge=0.0, le=1.0)
    edge_stability: float = Field(default=0.0, ge=0.0, le=1.0)
    stylization_strength: float = Field(default=0.0, ge=0.0, le=1.0)
    overall: float = Field(default=0.0, ge=0.0, le=1.0)
    scored_postprocessed: bool = False

    def compute_overall(self, weights: dict[str, float] | None = None) -> float:
        w = weights or SCORER_WEIGHTS_V1
        self.overall = (
            self.facet_clarity * w.get("facet_clarity", 0.30)
            + self.palette_cohesion * w.get("palette_cohesion", 0.20)
            + self.prompt_alignment * w.get("prompt_alignment", 0.20)
            + self.edge_stability * w.get("edge_stability", 0.15)
            + self.stylization_strength * w.get("stylization_strength", 0.15)
        )
        return self.overall


# ─── Style diagnostics ───────────────────────────────────────────────────

class StyleDiagnostic(BaseModel):
    """Informational for debugging and salvage — not a hard gate on selection."""
    palette_too_noisy: bool = False
    edges_too_soft: bool = False
    too_photoreal: bool = False
    temporal_edge_flicker: bool = False
    prompt_subject_weak: bool = False
    reasons: list[str] = Field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not any([
            self.palette_too_noisy, self.edges_too_soft,
            self.too_photoreal, self.temporal_edge_flicker,
            self.prompt_subject_weak,
        ])


# ─── Guard mutations ─────────────────────────────────────────────────────

class GuardMutation(BaseModel):
    rule: str
    field: str
    from_value: str
    to_value: str


# ─── Salvage provenance ─────────────────────────────────────────────────

class SalvageRecord(BaseModel):
    applied: bool = False
    strategy: str = ""
    score_before: float = 0.0
    score_after: float = 0.0
    attempts: int = 0
    style_passed_after: bool = False


# ─── Performance telemetry ───────────────────────────────────────────────

class TimingBreakdown(BaseModel):
    """Wall-clock timing for each pipeline phase. All values in seconds."""
    planning_sec: float = 0.0
    generation_sec: float = 0.0
    scoring_sec: float = 0.0
    postprocess_sec: float = 0.0
    salvage_sec: float = 0.0
    total_sec: float = 0.0


# ─── Scoring breakdown for sidecar ──────────────────────────────────────

class ScoringBreakdown(BaseModel):
    raw_score: Optional[FacetScore] = None
    postprocessed_score: Optional[FacetScore] = None
    final_score: Optional[FacetScore] = None
    selected_variant: SelectedVariant = SelectedVariant.RAW
    salvage: Optional[SalvageRecord] = None
    diagnostic: Optional[StyleDiagnostic] = None


# ─── Artifact metadata — reproducibility contract ───────────────────────

class ArtifactMeta(BaseModel):
    spec_id: str
    seed: int
    preset_name: str
    compiled_prompt: str
    compiled_negative: str
    prompt_hash: str = ""
    style_config: StyleConfig = Field(default_factory=StyleConfig)
    render_lane: RenderLane = RenderLane.PREVIEW
    num_inference_steps: int = 25
    guidance_scale: float = 7.0
    resolution: str = "480p"
    fps: int = 24
    duration_sec: float = 3.0
    backend: BackendName = BackendName.WAN21_LOWPOLY
    engine_version: str = "0.3.0"
    postprocess_config: dict = Field(default_factory=dict)
    guard_mutations: list[GuardMutation] = Field(default_factory=list)
    scoring: Optional[ScoringBreakdown] = None
    timing: Optional[TimingBreakdown] = None

    def model_post_init(self, __context) -> None:
        if not self.prompt_hash:
            self.prompt_hash = hashlib.sha256(
                self.compiled_prompt.encode()
            ).hexdigest()[:16]


# ─── Results ─────────────────────────────────────────────────────────────

class Take(BaseModel):
    take_id: str
    shot_id: str
    take_number: int = 0
    video_path: str = ""
    postprocessed_path: str = ""
    seed: int = 0
    backend: BackendName = BackendName.WAN21_LOWPOLY
    generation_time_sec: float = 0.0
    cost_usd: float = 0.0
    facet_score: Optional[FacetScore] = None
    facet_score_raw: Optional[FacetScore] = None
    style_diagnostic: Optional[StyleDiagnostic] = None
    artifact_meta: Optional[ArtifactMeta] = None
    selected_variant: SelectedVariant = SelectedVariant.RAW
    salvage: Optional[SalvageRecord] = None
    timing: Optional[TimingBreakdown] = None
    decision_summary: str = ""


class ShotResult(BaseModel):
    shot_id: str
    takes: list[Take]
    winner_take_id: Optional[str] = None
    failure_codes: list[str] = Field(default_factory=list)


class GenerationResult(BaseModel):
    spec_id: str
    plan: ExecutionPlan
    shot_results: list[ShotResult]
    final_video_path: Optional[str] = None
    total_cost_usd: float = 0.0
    total_time_sec: float = 0.0
