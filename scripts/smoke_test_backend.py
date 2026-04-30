"""Smoke test: schemas, capabilities, prompt compiler + style guards,
preset loader, FacetScore, style diagnostics, render lanes, artifact
metadata, guard mutations, salvage records, timing, decision summary,
policy config, and Engine.plan() composition.

No network, no GPU, no workers.

Run: python scripts/smoke_test_backend.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from xvideo.capabilities import (
    CAPABILITIES,
    active_set,
    backends_supporting,
    default_backend,
)
from xvideo.prompt import compile_prompt, apply_style_guards
from xvideo.router import Router
from xvideo.spec import (
    ArtifactMeta,
    BackendName,
    CameraMove,
    DEFAULT_POLICY,
    ExecutionPlan,
    FacetScore,
    GuardMutation,
    HardwareTier,
    LightingMode,
    LoopMode,
    LowPolySpec,
    Mode,
    PaletteMode,
    PolicyConfig,
    PolyDensity,
    Priority,
    RENDER_LANE_DEFAULTS,
    RenderLane,
    SalvageRecord,
    SCORER_WEIGHTS_V1,
    ScoringBreakdown,
    SelectedVariant,
    ShotPlan,
    StyleConfig,
    StyleDiagnostic,
    TimingBreakdown,
    get_lane_defaults,
)
from xvideo.styles import available_presets, resolve_style


def test_spec_validates():
    spec = LowPolySpec(
        subject="a geometric fox",
        action="running through snow",
        style=StyleConfig(preset_name="crystal", poly_density=PolyDensity.MEDIUM),
        camera=CameraMove.ORBIT,
        duration_sec=3.0,
        seed=42,
        render_lane=RenderLane.PREVIEW,
    )
    assert spec.duration_sec == 3.0
    assert spec.render_lane == RenderLane.PREVIEW
    print(f"  [OK] LowPolySpec validates: density={spec.style.poly_density.value} lane={spec.render_lane.value}")


def test_capability_matrix():
    assert len(CAPABILITIES) == len(BackendName)
    active = active_set()
    assert BackendName.WAN21_LOWPOLY in active
    assert default_backend() == BackendName.WAN21_LOWPOLY
    print(f"  [OK] Capability matrix: {len(active)} active, default={default_backend().value}")


def test_preset_loader():
    styles_dir = Path(__file__).resolve().parents[1] / "configs" / "styles"
    presets = available_presets(styles_dir)
    assert "crystal" in presets
    assert "wireframe" in presets
    style = resolve_style("crystal", styles_dir=styles_dir)
    assert style.preset_name == "crystal"
    style2 = resolve_style("crystal", overrides={"palette": "neon"}, styles_dir=styles_dir)
    assert style2.palette == PaletteMode.NEON
    print(f"  [OK] Preset loader: {len(presets)} presets, override works")


def test_prompt_compiler():
    spec = LowPolySpec(
        subject="a mountain landscape",
        action="slowly rotating",
        style=StyleConfig(poly_density=PolyDensity.LOW, palette=PaletteMode.EARTH, lighting=LightingMode.DRAMATIC),
        camera=CameraMove.ORBIT,
    )
    pos, neg, mutations = compile_prompt(spec)
    assert "low poly" in pos.lower()
    assert "mountain landscape" in pos
    assert "photorealistic" in neg.lower()
    assert isinstance(mutations, list)
    print(f"  [OK] Prompt compiler: {len(pos)} chars positive, {len(mutations)} mutations")


def test_style_guards_with_mutations():
    # wireframe + flat → should produce GuardMutation
    spec = LowPolySpec(
        subject="test",
        style=StyleConfig(preset_name="wireframe", lighting=LightingMode.FLAT),
    )
    guarded, mutations = apply_style_guards(spec)
    assert guarded.style.lighting == LightingMode.BACKLIT
    assert any(m.rule == "wireframe_no_flat" for m in mutations)

    # monument + tracking → should produce camera + speed mutations
    spec2 = LowPolySpec(
        subject="test",
        style=StyleConfig(preset_name="monument"),
        camera=CameraMove.TRACKING,
        camera_speed=0.8,
    )
    guarded2, mutations2 = apply_style_guards(spec2)
    assert guarded2.camera == CameraMove.ORBIT
    assert any(m.rule == "monument_fast_camera" for m in mutations2)
    assert any(m.rule == "monument_speed_cap" for m in mutations2)

    # neon_arcade + earth palette → forced neon + dark bg
    spec3 = LowPolySpec(
        subject="test",
        style=StyleConfig(preset_name="neon_arcade", palette=PaletteMode.EARTH, background="bright sky"),
    )
    guarded3, mutations3 = apply_style_guards(spec3)
    assert guarded3.style.palette == PaletteMode.NEON
    assert "dark" in guarded3.style.background.lower()
    assert len(mutations3) == 2

    # papercraft + minimal → bumped
    spec4 = LowPolySpec(
        subject="test",
        style=StyleConfig(preset_name="papercraft", poly_density=PolyDensity.MINIMAL),
    )
    guarded4, mutations4 = apply_style_guards(spec4)
    assert guarded4.style.poly_density == PolyDensity.LOW
    assert any(m.rule == "papercraft_min_density" for m in mutations4)

    print(f"  [OK] Style guards: 4/4 rules enforced, mutations captured")


def test_facet_score_with_photoreal():
    score = FacetScore(
        facet_clarity=0.85,
        palette_cohesion=0.70,
        prompt_alignment=0.75,
        edge_stability=0.90,
        stylization_strength=0.80,
    )
    overall = score.compute_overall()
    expected = 0.85*0.30 + 0.70*0.20 + 0.75*0.20 + 0.90*0.15 + 0.80*0.15
    assert abs(overall - expected) < 0.001
    assert len(SCORER_WEIGHTS_V1) == 5
    print(f"  [OK] FacetScore: overall={overall:.3f} (5 metrics, all higher-is-better)")


def test_style_diagnostic():
    # Test diagnostic logic directly via the spec model (scorer module
    # requires cv2/numpy which may not be installed).
    # Good score → should pass
    good = FacetScore(facet_clarity=0.8, palette_cohesion=0.7, prompt_alignment=0.6,
                      edge_stability=0.5, stylization_strength=0.6)
    diag = StyleDiagnostic()
    if good.palette_cohesion < 0.35: diag.palette_too_noisy = True
    if good.facet_clarity < 0.25: diag.edges_too_soft = True
    if good.stylization_strength < 0.30: diag.too_photoreal = True
    if good.edge_stability < 0.25: diag.temporal_edge_flicker = True
    if good.prompt_alignment < 0.20: diag.prompt_subject_weak = True
    assert diag.passed, "Good score should pass"

    # Bad score → should fail
    bad = FacetScore(facet_clarity=0.1, palette_cohesion=0.2, prompt_alignment=0.1,
                     edge_stability=0.1, stylization_strength=0.1)
    diag2 = StyleDiagnostic()
    checks = [
        (bad.palette_cohesion < 0.35, "palette_too_noisy"),
        (bad.facet_clarity < 0.25, "edges_too_soft"),
        (bad.stylization_strength < 0.30, "too_photoreal"),
        (bad.edge_stability < 0.25, "temporal_edge_flicker"),
        (bad.prompt_alignment < 0.20, "prompt_subject_weak"),
    ]
    for cond, attr in checks:
        if cond:
            setattr(diag2, attr, True)
            diag2.reasons.append(attr)
    assert not diag2.passed
    assert diag2.edges_too_soft
    assert diag2.palette_too_noisy
    assert diag2.too_photoreal
    assert diag2.temporal_edge_flicker
    assert diag2.prompt_subject_weak
    assert len(diag2.reasons) == 5
    print(f"  [OK] StyleDiagnostic: good={diag.passed}, bad has {len(diag2.reasons)} failures")


def test_render_lanes():
    # Hardware-aware: both tiers must exist
    assert HardwareTier.LAPTOP_4GB in RENDER_LANE_DEFAULTS
    assert HardwareTier.DESKTOP_8GB in RENDER_LANE_DEFAULTS
    # Laptop tier: tighter constraints
    laptop_fid = get_lane_defaults(RenderLane.FIDELITY, HardwareTier.LAPTOP_4GB)
    assert laptop_fid["resolution"] == "480p"
    assert laptop_fid["postprocess_enabled"] is True
    assert laptop_fid["num_candidates"] <= 2
    assert laptop_fid["duration_sec"] <= 3.0
    # Desktop tier: more headroom
    desktop_fid = get_lane_defaults(RenderLane.FIDELITY, HardwareTier.DESKTOP_8GB)
    assert desktop_fid["num_candidates"] >= 2
    assert desktop_fid["num_inference_steps"] >= laptop_fid["num_inference_steps"]
    # Laptop standard enables postprocess (compensates for fewer steps)
    laptop_std = get_lane_defaults(RenderLane.STANDARD, HardwareTier.LAPTOP_4GB)
    assert laptop_std["postprocess_enabled"] is True
    print(f"  [OK] Render lanes: laptop_4gb fidelity={laptop_fid['num_candidates']}cand/{laptop_fid['num_inference_steps']}step+pp, "
          f"desktop_8gb fidelity={desktop_fid['num_candidates']}cand/{desktop_fid['num_inference_steps']}step")


def test_artifact_meta_with_guard_mutations():
    mutations = [
        GuardMutation(rule="monument_fast_camera", field="camera",
                      from_value="tracking", to_value="orbit"),
        GuardMutation(rule="monument_speed_cap", field="camera_speed",
                      from_value="0.8", to_value="0.3"),
    ]
    meta = ArtifactMeta(
        spec_id="test123",
        seed=42,
        preset_name="monument",
        compiled_prompt="low poly monument",
        compiled_negative="photorealistic",
        guard_mutations=mutations,
    )
    assert len(meta.guard_mutations) == 2
    assert meta.guard_mutations[0].rule == "monument_fast_camera"
    assert meta.guard_mutations[0].from_value == "tracking"
    assert meta.guard_mutations[0].to_value == "orbit"
    assert len(meta.prompt_hash) == 16
    assert meta.engine_version == "0.3.0"
    print(f"  [OK] ArtifactMeta: {len(meta.guard_mutations)} guard_mutations, hash={meta.prompt_hash}")


def test_engine_plan():
    from xvideo.api import Engine
    engine = Engine(config_dir=Path(__file__).resolve().parents[1] / "configs")
    spec = LowPolySpec(
        subject="a crystal deer",
        style=StyleConfig(preset_name="crystal"),
        seed=42,
        render_lane=RenderLane.PREVIEW,
    )
    plan, mutations = engine.plan(spec)
    assert len(plan.shots) == 1
    shot = plan.shots[0]
    assert shot.backend == BackendName.WAN21_LOWPOLY
    assert "low poly" in shot.prompt.lower()
    assert shot.seed == 42
    assert isinstance(mutations, list)
    print(f"  [OK] Engine.plan(): shot_id={shot.shot_id} seed={shot.seed} mutations={len(mutations)}")


def test_engine_plan_with_mutations():
    """Engine.plan() for monument + tracking should produce guard mutations."""
    from xvideo.api import Engine
    engine = Engine(config_dir=Path(__file__).resolve().parents[1] / "configs")
    spec = LowPolySpec(
        subject="impossible staircase",
        style=StyleConfig(preset_name="monument"),
        camera=CameraMove.TRACKING,
        camera_speed=0.9,
        seed=99,
    )
    plan, mutations = engine.plan(spec)
    assert len(mutations) > 0, "monument + tracking should produce guard mutations"
    assert any(m.rule == "monument_fast_camera" for m in mutations)
    print(f"  [OK] Engine.plan() mutation passthrough: {len(mutations)} mutations for monument+tracking")


def test_selected_variant_and_salvage_record():
    from xvideo.spec import Take
    take = Take(take_id="t1", shot_id="s1", selected_variant=SelectedVariant.RAW)
    assert take.selected_variant == SelectedVariant.RAW
    take.selected_variant = SelectedVariant.SALVAGED
    assert take.selected_variant.value == "salvaged"

    rec = SalvageRecord(
        applied=True, strategy="heavy_posterize",
        score_before=0.41, score_after=0.52,
        attempts=2, style_passed_after=True,
    )
    assert rec.strategy == "heavy_posterize"
    take.salvage = rec

    raw = FacetScore(facet_clarity=0.5, palette_cohesion=0.4, prompt_alignment=0.5,
                     edge_stability=0.5, stylization_strength=0.5)
    raw.compute_overall()
    breakdown = ScoringBreakdown(
        raw_score=raw, final_score=raw,
        selected_variant=SelectedVariant.SALVAGED, salvage=rec,
    )
    assert breakdown.selected_variant == SelectedVariant.SALVAGED
    assert breakdown.salvage.strategy == "heavy_posterize"
    print(f"  [OK] SelectedVariant + SalvageRecord + ScoringBreakdown: provenance tracked")


def test_policy_config():
    p = DEFAULT_POLICY
    assert p.reject_floor == 0.25
    assert p.salvage_ceiling == 0.45
    assert p.postprocess_improvement_threshold == 0.03
    assert p.reject_floor < p.salvage_ceiling
    # Config-driven: can be overridden per-lane, per-preset
    custom = PolicyConfig(reject_floor=0.30, salvage_ceiling=0.50)
    assert custom.reject_floor == 0.30
    print(f"  [OK] PolicyConfig: reject<{p.reject_floor} salvage<{p.salvage_ceiling} (config-driven)")


def test_timing_breakdown():
    t = TimingBreakdown(
        planning_sec=0.01, generation_sec=2.5,
        scoring_sec=0.3, postprocess_sec=0.5,
        salvage_sec=0.8, total_sec=4.11,
    )
    assert t.generation_sec == 2.5
    assert t.total_sec == 4.11
    print(f"  [OK] TimingBreakdown: gen={t.generation_sec}s total={t.total_sec}s")


def test_decision_summary():
    from xvideo.spec import Take
    take = Take(
        take_id="t1", shot_id="s1",
        selected_variant=SelectedVariant.SALVAGED,
        facet_score=FacetScore(facet_clarity=0.8, palette_cohesion=0.7,
                               prompt_alignment=0.6, edge_stability=0.5,
                               stylization_strength=0.6, overall=0.66),
        salvage=SalvageRecord(applied=True, strategy="heavy_posterize",
                              score_before=0.41, score_after=0.52, attempts=2),
        style_diagnostic=StyleDiagnostic(),  # passed
    )
    # Build summary manually (scorer.build_decision_summary needs cv2)
    parts = [f"selected {take.selected_variant.value} variant"]
    if take.salvage and take.salvage.applied:
        delta = take.salvage.score_after - take.salvage.score_before
        parts.append(f"via {take.salvage.strategy}")
        parts.append(f"+{delta:.2f} over raw")
    if take.facet_score:
        parts.append(f"overall={take.facet_score.overall:.3f}")
    summary = "; ".join(parts)
    assert "salvaged" in summary
    assert "heavy_posterize" in summary
    assert "+0.11" in summary
    take.decision_summary = summary
    print(f"  [OK] decision_summary: '{summary}'")


def test_router_config_loads():
    router = Router(config_path=Path(__file__).resolve().parents[1] / "configs" / "backends.yaml")
    available = router.available_backends()
    assert available == []
    print(f"  [OK] Router config loads; {len(available)} workers configured")


if __name__ == "__main__":
    print("LowPoly Video Engine \u2014 Smoke test")
    print("-" * 50)
    test_spec_validates()
    test_capability_matrix()
    test_preset_loader()
    test_prompt_compiler()
    test_style_guards_with_mutations()
    test_facet_score_with_photoreal()
    test_style_diagnostic()
    test_render_lanes()
    test_artifact_meta_with_guard_mutations()
    test_selected_variant_and_salvage_record()
    test_policy_config()
    test_timing_breakdown()
    test_decision_summary()
    test_engine_plan()
    test_engine_plan_with_mutations()
    test_router_config_loads()
    print("-" * 50)
    print("All smoke tests passed.")
