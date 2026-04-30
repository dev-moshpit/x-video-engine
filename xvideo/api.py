"""Python API entry point for the LowPoly Video Engine.

Usage:
    from xvideo.api import Engine
    from xvideo.spec import LowPolySpec

    engine = Engine()
    spec = LowPolySpec(subject="a fox", action="running through snow")
    plan, mutations = engine.plan(spec)
    result = engine.generate(spec)
"""

from __future__ import annotations

import logging
import random
import sys
import time
import uuid
from pathlib import Path
from typing import Optional

import yaml

from xvideo.prompt import compile_prompt
from xvideo.router import Router
from xvideo.spec import (
    ArtifactMeta,
    BackendName,
    DEFAULT_POLICY,
    ExecutionPlan,
    GenerationResult,
    GuardMutation,
    HardwareTier,
    LowPolySpec,
    Mode,
    PolicyConfig,
    Priority,
    RENDER_LANE_DEFAULTS,
    RenderLane,
    ScoringBreakdown,
    SelectedVariant,
    ShotPlan,
    TimingBreakdown,
    detect_hardware_tier,
    get_lane_defaults,
)
from xvideo.styles import resolve_style

logger = logging.getLogger(__name__)


def _load_policy(config_dir: Path) -> PolicyConfig:
    """Load policy thresholds from default.yaml, falling back to defaults."""
    cfg_path = config_dir / "default.yaml"
    if not cfg_path.exists():
        return DEFAULT_POLICY
    try:
        with open(cfg_path) as f:
            raw = yaml.safe_load(f) or {}
        policy_raw = raw.get("policy", {})
        scorer_raw = raw.get("scorer", {})
        diag_raw = scorer_raw.get("diagnostics", {})
        return PolicyConfig(
            reject_floor=policy_raw.get("reject_floor", 0.25),
            salvage_ceiling=policy_raw.get("salvage_ceiling", 0.45),
            postprocess_improvement_threshold=scorer_raw.get(
                "postprocess_improvement_threshold", 0.03
            ),
            palette_cohesion_min=diag_raw.get("palette_cohesion_min", 0.35),
            facet_clarity_min=diag_raw.get("facet_clarity_min", 0.25),
            stylization_strength_min=diag_raw.get("stylization_strength_min", 0.30),
            edge_stability_min=diag_raw.get("edge_stability_min", 0.25),
            prompt_alignment_min=diag_raw.get("prompt_alignment_min", 0.20),
        )
    except Exception as e:
        logger.warning("Failed to load policy from config: %s", e)
        return DEFAULT_POLICY


class Engine:
    def __init__(self, config_dir: str | Path = "configs", hardware_tier: HardwareTier | None = None):
        self.config_dir = Path(config_dir)
        self.router = Router(self.config_dir / "backends.yaml")
        self.policy = _load_policy(self.config_dir)
        self.hardware_tier = hardware_tier or detect_hardware_tier()
        logger.info("Engine initialized: hardware=%s", self.hardware_tier.value)

    def plan(self, spec: LowPolySpec) -> tuple[ExecutionPlan, list[GuardMutation]]:
        """Deterministic composition. Returns (plan, guard_mutations)."""
        spec_id = self.new_spec_id()

        resolved_style = resolve_style(
            preset_name=spec.style.preset_name,
            overrides=spec.style.model_dump(exclude={"preset_name"}),
            styles_dir=self.config_dir / "styles",
        )
        spec = spec.model_copy(update={"style": resolved_style})

        lane = get_lane_defaults(spec.render_lane, self.hardware_tier)
        resolution = spec.resolution or lane["resolution"]
        duration_sec = spec.duration_sec or lane["duration_sec"]
        num_candidates = spec.num_candidates or lane["num_candidates"]

        positive, negative, mutations = compile_prompt(spec)
        seed = spec.seed if spec.seed is not None else random.randint(0, 2**32 - 1)

        shot = ShotPlan(
            shot_id=f"{spec_id}_s0",
            backend=BackendName.WAN21_LOWPOLY,
            mode=Mode.T2V,
            prompt=positive,
            negative_prompt=negative,
            style_config=resolved_style,
            duration_sec=duration_sec,
            resolution=resolution,
            fps=spec.fps,
            aspect_ratio=spec.aspect_ratio,
            priority=Priority.HERO if num_candidates > 1 else Priority.STANDARD,
            num_candidates=num_candidates,
            seed=seed,
            num_inference_steps=lane["num_inference_steps"],
            guidance_scale=lane["guidance_scale"],
            render_lane=spec.render_lane,
        )

        plan = ExecutionPlan(
            spec_id=spec_id,
            shots=[shot],
            estimated_cost_usd=self.router.estimate_cost(
                ExecutionPlan(spec_id=spec_id, shots=[shot])
            ),
            notes=f"lane={spec.render_lane.value} preset={resolved_style.preset_name}",
        )
        return plan, mutations

    def _build_postprocess_fn(self, lane: RenderLane):
        lane_cfg = get_lane_defaults(lane, self.hardware_tier)
        if not lane_cfg.get("postprocess_enabled", False):
            return None
        try:
            sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "worker_runtime"))
            from postprocess.pipeline import PostprocessConfig, run_postprocess
        except ImportError:
            logger.info("Postprocess module not available; skipping")
            return None

        default_cfg = PostprocessConfig(
            enabled=True, palette_quantize=True, quantize_colors=8,
            quantize_temporal_lock=True, edge_sharpen=True, edge_boost=0.3,
        )

        def _pp(input_path: str, output_path: str, overrides: dict | None = None) -> str:
            cfg = default_cfg
            if overrides:
                cfg = PostprocessConfig(enabled=True, **{
                    k: v for k, v in overrides.items() if k != "name"
                })
            return run_postprocess(input_path, output_path, cfg)
        return _pp

    def generate(self, spec: LowPolySpec) -> GenerationResult:
        """Full pipeline: plan -> dispatch -> score -> salvage -> result.

        Tracks wall-clock timing for each phase.
        """
        t_total = time.monotonic()

        # Plan
        t0 = time.monotonic()
        plan, mutations = self.plan(spec)
        t_plan = time.monotonic() - t0

        pp_fn = self._build_postprocess_fn(spec.render_lane)

        shot_results = []
        for shot in plan.shots:
            # Dispatch (generation)
            t1 = time.monotonic()
            result = self.router.dispatch(shot)
            t_gen = time.monotonic() - t1

            # Build artifact metadata
            pp_config = {}
            lane_cfg = get_lane_defaults(shot.render_lane, self.hardware_tier)
            if lane_cfg.get("postprocess_enabled"):
                pp_config = {"enabled": True, "palette_quantize": True, "edge_sharpen": True}

            for take in result.takes:
                take.artifact_meta = ArtifactMeta(
                    spec_id=plan.spec_id, seed=take.seed,
                    preset_name=shot.style_config.preset_name,
                    compiled_prompt=shot.prompt,
                    compiled_negative=shot.negative_prompt,
                    style_config=shot.style_config,
                    render_lane=shot.render_lane,
                    num_inference_steps=shot.num_inference_steps,
                    guidance_scale=shot.guidance_scale,
                    resolution=shot.resolution, fps=shot.fps,
                    duration_sec=shot.duration_sec, backend=shot.backend,
                    postprocess_config=pp_config,
                    guard_mutations=mutations,
                )
                # Initialize timing with generation phase
                take.timing = TimingBreakdown(
                    planning_sec=round(t_plan, 4),
                    generation_sec=round(take.generation_time_sec or t_gen, 4),
                )

            # Score + salvage (scorer adds its own timing to take.timing)
            t_score_start = time.monotonic()
            if len(result.takes) > 1 or pp_fn:
                try:
                    from xvideo.scorer import pick_winner as _pick
                    winner_id = _pick(result.takes, shot.prompt, pp_fn, self.policy)
                    if winner_id:
                        result.winner_take_id = winner_id
                except ImportError:
                    logger.info("Scorer not available; using first take")
            t_score_total = time.monotonic() - t_score_start

            # Finalize metadata: scoring breakdown + timing
            for take in result.takes:
                if take.timing:
                    take.timing.total_sec = round(
                        take.timing.planning_sec + take.timing.generation_sec
                        + take.timing.scoring_sec + take.timing.postprocess_sec
                        + take.timing.salvage_sec, 4
                    )
                if take.artifact_meta:
                    if take.facet_score:
                        take.artifact_meta.scoring = ScoringBreakdown(
                            raw_score=take.facet_score_raw,
                            postprocessed_score=(
                                take.facet_score if take.selected_variant != SelectedVariant.RAW
                                else None
                            ),
                            final_score=take.facet_score,
                            selected_variant=take.selected_variant,
                            salvage=take.salvage,
                            diagnostic=take.style_diagnostic,
                        )
                    take.artifact_meta.timing = take.timing

            shot_results.append(result)

        winner_path = None
        if shot_results and shot_results[0].winner_take_id:
            winner = next(
                (t for t in shot_results[0].takes
                 if t.take_id == shot_results[0].winner_take_id), None,
            )
            if winner:
                winner_path = winner.postprocessed_path or winner.video_path

        return GenerationResult(
            spec_id=plan.spec_id, plan=plan, shot_results=shot_results,
            final_video_path=winner_path,
            total_cost_usd=sum(t.cost_usd for sr in shot_results for t in sr.takes),
            total_time_sec=round(time.monotonic() - t_total, 4),
        )

    @staticmethod
    def new_spec_id() -> str:
        return uuid.uuid4().hex[:12]
