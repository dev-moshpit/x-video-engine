"""FacetScorer — cheap low-poly quality metrics for candidate selection.

5 metrics (all higher-is-better), style diagnostics, postprocess-aware
scoring with raw/pp comparison, salvage/repair with provenance tracking,
config-driven policy thresholds, performance telemetry, and decision
summary strings.

Winner selection always ranks by overall score. Diagnostics are
informational — they inform salvage but never hard-gate selection.

Requires: opencv-python, numpy. Optional: open-clip-torch.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

from xvideo.spec import (
    DEFAULT_POLICY,
    FacetScore,
    PolicyConfig,
    SalvageRecord,
    SCORER_WEIGHTS_V1,
    SelectedVariant,
    StyleDiagnostic,
    Take,
    TimingBreakdown,
)

logger = logging.getLogger(__name__)


def _extract_frames(video_path: str, max_frames: int = 8) -> list[np.ndarray]:
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        logger.warning("Cannot open video: %s", video_path)
        return []
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if total <= 0:
        cap.release()
        return []
    indices = np.linspace(0, total - 1, min(max_frames, total), dtype=int)
    frames = []
    for idx in indices:
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(idx))
        ok, frame = cap.read()
        if ok:
            frames.append(frame)
    cap.release()
    return frames


# ─── Metrics (all higher-is-better) ─────────────────────────────────────

def _facet_clarity(frames: list[np.ndarray]) -> float:
    if not frames:
        return 0.0
    scores = []
    for frame in frames:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 80, 200)
        ratio = np.count_nonzero(edges) / max(edges.size, 1)
        scores.append(min(ratio / 0.08, 1.0))
    return float(np.mean(scores))


def _palette_cohesion(frames: list[np.ndarray], k: int = 6) -> float:
    if not frames:
        return 0.0
    scores = []
    for frame in frames:
        pixels = frame.reshape(-1, 3).astype(np.float32)
        if len(pixels) > 5000:
            idx = np.random.choice(len(pixels), 5000, replace=False)
            pixels = pixels[idx]
        criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 10, 1.0)
        compactness, _, _ = cv2.kmeans(pixels, k, None, criteria, 3, cv2.KMEANS_PP_CENTERS)
        scores.append(1.0 - min(compactness / 40000.0, 1.0))
    return float(np.mean(scores))


_clip_model = None
_clip_preprocess = None
_clip_tokenize = None

def _load_clip():
    global _clip_model, _clip_preprocess, _clip_tokenize
    if _clip_model is not None:
        return True
    try:
        import open_clip
        model, _, preprocess = open_clip.create_model_and_transforms("ViT-L-14", pretrained="openai")
        model.eval()
        _clip_model = model
        _clip_preprocess = preprocess
        _clip_tokenize = open_clip.get_tokenizer("ViT-L-14")
        return True
    except Exception as e:
        logger.info("CLIP unavailable, prompt_alignment defaults to 0.5: %s", e)
        return False

def _prompt_alignment(frames: list[np.ndarray], prompt: str) -> float:
    if not frames or not prompt:
        return 0.5
    if not _load_clip():
        return 0.5
    try:
        import torch
        from PIL import Image
        mid = frames[len(frames) // 2]
        img = Image.fromarray(cv2.cvtColor(mid, cv2.COLOR_BGR2RGB))
        img_tensor = _clip_preprocess(img).unsqueeze(0)
        text_tokens = _clip_tokenize([prompt])
        with torch.no_grad():
            img_f = _clip_model.encode_image(img_tensor)
            txt_f = _clip_model.encode_text(text_tokens)
            img_f /= img_f.norm(dim=-1, keepdim=True)
            txt_f /= txt_f.norm(dim=-1, keepdim=True)
            sim = (img_f @ txt_f.T).item()
        return min(max((sim - 0.15) / 0.20, 0.0), 1.0)
    except Exception as e:
        logger.warning("CLIP scoring failed: %s", e)
        return 0.5


def _edge_stability(frames: list[np.ndarray]) -> float:
    if len(frames) < 2:
        return 1.0
    overlaps = []
    prev_edges = None
    for frame in frames:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 80, 200)
        if prev_edges is not None:
            inter = np.count_nonzero(edges & prev_edges)
            union = np.count_nonzero(edges | prev_edges)
            overlaps.append(inter / max(union, 1))
        prev_edges = edges
    if not overlaps:
        return 1.0
    return min(float(np.mean(overlaps)) / 0.5, 1.0)


def _stylization_strength(frames: list[np.ndarray]) -> float:
    if not frames:
        return 0.5
    scores = []
    for frame in frames:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        lap_var = cv2.Laplacian(gray, cv2.CV_64F).var()
        texture_score = 1.0 - min(lap_var / 1000.0, 1.0)
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        hist = cv2.calcHist([hsv], [0], None, [32], [0, 180])
        hist = hist.flatten() / max(hist.sum(), 1)
        entropy = -np.sum(hist[hist > 0] * np.log2(hist[hist > 0]))
        entropy_score = 1.0 - min(entropy / 4.5, 1.0)
        scores.append(0.65 * texture_score + 0.35 * entropy_score)
    return float(np.mean(scores))


# ─── Score frames ────────────────────────────────────────────────────────

def _score_frames(
    frames: list[np.ndarray],
    prompt: str,
    weights: dict[str, float] | None = None,
    postprocessed: bool = False,
) -> FacetScore:
    fs = FacetScore(
        facet_clarity=_facet_clarity(frames),
        palette_cohesion=_palette_cohesion(frames),
        prompt_alignment=_prompt_alignment(frames, prompt),
        edge_stability=_edge_stability(frames),
        stylization_strength=_stylization_strength(frames),
        scored_postprocessed=postprocessed,
    )
    fs.compute_overall(weights or SCORER_WEIGHTS_V1)
    return fs


def score_take(
    take: Take,
    prompt: str,
    weights: dict[str, float] | None = None,
) -> FacetScore:
    path = take.postprocessed_path or take.video_path
    frames = _extract_frames(path)
    if not frames:
        logger.warning("No frames from %s; zero score", path)
        return FacetScore()
    return _score_frames(frames, prompt, weights, postprocessed=bool(take.postprocessed_path))


# ─── Style diagnostics (config-driven thresholds) ───────────────────────

def diagnose_style(score: FacetScore, policy: PolicyConfig | None = None) -> StyleDiagnostic:
    p = policy or DEFAULT_POLICY
    diag = StyleDiagnostic()
    if score.palette_cohesion < p.palette_cohesion_min:
        diag.palette_too_noisy = True
        diag.reasons.append(f"palette_cohesion={score.palette_cohesion:.2f} < {p.palette_cohesion_min}")
    if score.facet_clarity < p.facet_clarity_min:
        diag.edges_too_soft = True
        diag.reasons.append(f"facet_clarity={score.facet_clarity:.2f} < {p.facet_clarity_min}")
    if score.stylization_strength < p.stylization_strength_min:
        diag.too_photoreal = True
        diag.reasons.append(f"stylization_strength={score.stylization_strength:.2f} < {p.stylization_strength_min}")
    if score.edge_stability < p.edge_stability_min:
        diag.temporal_edge_flicker = True
        diag.reasons.append(f"edge_stability={score.edge_stability:.2f} < {p.edge_stability_min}")
    if score.prompt_alignment < p.prompt_alignment_min:
        diag.prompt_subject_weak = True
        diag.reasons.append(f"prompt_alignment={score.prompt_alignment:.2f} < {p.prompt_alignment_min}")
    return diag


# ─── Decision summary ───────────────────────────────────────────────────

def build_decision_summary(take: Take) -> str:
    """One-line human-readable summary of what happened to this take."""
    parts = []
    variant = take.selected_variant.value
    parts.append(f"selected {variant} variant")

    if take.salvage and take.salvage.applied:
        delta = take.salvage.score_after - take.salvage.score_before
        parts.append(f"via {take.salvage.strategy}")
        parts.append(f"{'+' if delta >= 0 else ''}{delta:.2f} over raw")

    if take.facet_score:
        parts.append(f"overall={take.facet_score.overall:.3f}")

    if take.style_diagnostic:
        if take.style_diagnostic.passed:
            parts.append("diagnostics=clear")
        else:
            failed = [r.split("=")[0] for r in take.style_diagnostic.reasons]
            parts.append(f"diagnostics=failed({','.join(failed)})")

    return "; ".join(parts)


# ─── Postprocess-aware scoring ───────────────────────────────────────────

def score_with_postprocess(
    take: Take,
    prompt: str,
    postprocess_fn: callable | None = None,
    weights: dict[str, float] | None = None,
    policy: PolicyConfig | None = None,
) -> FacetScore:
    p = policy or DEFAULT_POLICY
    t_start = time.monotonic()

    raw_frames = _extract_frames(take.video_path)
    if not raw_frames:
        return FacetScore()

    raw_score = _score_frames(raw_frames, prompt, weights, postprocessed=False)
    take.facet_score_raw = raw_score
    t_scored = time.monotonic()

    if postprocess_fn is None:
        take.facet_score = raw_score
        take.selected_variant = SelectedVariant.RAW
        _set_timing(take, scoring_sec=t_scored - t_start)
        return raw_score

    pp_path = take.video_path.replace(".mp4", ".pp.mp4")
    t_pp_start = time.monotonic()
    try:
        result_path = postprocess_fn(take.video_path, pp_path)
    except Exception as e:
        logger.warning("Postprocess failed for %s: %s", take.take_id, e)
        take.facet_score = raw_score
        take.selected_variant = SelectedVariant.RAW
        _set_timing(take, scoring_sec=t_scored - t_start)
        return raw_score
    t_pp_done = time.monotonic()

    pp_frames = _extract_frames(result_path)
    if not pp_frames:
        take.facet_score = raw_score
        take.selected_variant = SelectedVariant.RAW
        _set_timing(take, scoring_sec=t_scored - t_start, postprocess_sec=t_pp_done - t_pp_start)
        return raw_score

    pp_score = _score_frames(pp_frames, prompt, weights, postprocessed=True)
    t_pp_scored = time.monotonic()

    improvement = pp_score.overall - raw_score.overall
    if improvement >= p.postprocess_improvement_threshold:
        logger.info("Take %s: postprocess improved %.3f -> %.3f (+%.3f)",
                     take.take_id, raw_score.overall, pp_score.overall, improvement)
        take.postprocessed_path = result_path
        take.facet_score = pp_score
        take.selected_variant = SelectedVariant.POSTPROCESSED
    else:
        logger.info("Take %s: postprocess delta %.3f < threshold %.3f; keeping raw",
                     take.take_id, improvement, p.postprocess_improvement_threshold)
        try:
            Path(pp_path).unlink(missing_ok=True)
        except OSError:
            pass
        take.facet_score = raw_score
        take.selected_variant = SelectedVariant.RAW

    _set_timing(take,
                scoring_sec=(t_scored - t_start) + (t_pp_scored - t_pp_done),
                postprocess_sec=t_pp_done - t_pp_start)
    return take.facet_score


# ─── Salvage with provenance + timing ────────────────────────────────────

SALVAGE_STRATEGIES = [
    {"name": "strong_quantize", "palette_quantize": True, "quantize_colors": 6,
     "quantize_temporal_lock": True, "edge_sharpen": True, "edge_boost": 0.4},
    {"name": "heavy_posterize", "posterize": True, "posterize_levels": 4,
     "palette_quantize": True, "quantize_colors": 8, "quantize_temporal_lock": True},
    {"name": "max_salvage", "palette_quantize": True, "quantize_colors": 5,
     "quantize_temporal_lock": True, "posterize": True, "posterize_levels": 5,
     "edge_sharpen": True, "edge_boost": 0.5},
]


def attempt_salvage(
    take: Take,
    prompt: str,
    diagnostic: StyleDiagnostic,
    postprocess_fn: callable,
    weights: dict[str, float] | None = None,
    policy: PolicyConfig | None = None,
) -> bool:
    p = policy or DEFAULT_POLICY
    if diagnostic.passed:
        take.salvage = SalvageRecord(applied=False)
        return True

    score_before = take.facet_score.overall if take.facet_score else 0.0

    if score_before < p.reject_floor:
        logger.info("Take %s: score %.3f < reject floor %.3f; skipping salvage",
                     take.take_id, score_before, p.reject_floor)
        take.salvage = SalvageRecord(applied=False, score_before=score_before, attempts=0)
        return False

    t_start = time.monotonic()
    source = take.video_path
    best_score = score_before
    best_path = None
    best_fs = None
    best_strategy = ""
    attempts = 0

    for strategy in SALVAGE_STRATEGIES:
        attempts += 1
        name = strategy["name"]
        salvage_path = take.video_path.replace(".mp4", f".salvage_{name}.mp4")
        try:
            result_path = postprocess_fn(source, salvage_path, strategy)
        except Exception as e:
            logger.warning("Salvage %s failed for %s: %s", name, take.take_id, e)
            continue

        frames = _extract_frames(result_path)
        if not frames:
            continue

        fs = _score_frames(frames, prompt, weights, postprocessed=True)
        diag = diagnose_style(fs, p)

        if diag.passed:
            logger.info("Salvage %s succeeded for %s: %.3f -> %.3f",
                        name, take.take_id, score_before, fs.overall)
            take.postprocessed_path = result_path
            take.facet_score = fs
            take.style_diagnostic = diag
            take.selected_variant = SelectedVariant.SALVAGED
            take.salvage = SalvageRecord(
                applied=True, strategy=name,
                score_before=score_before, score_after=fs.overall,
                attempts=attempts, style_passed_after=True,
            )
            _add_timing(take, salvage_sec=time.monotonic() - t_start)
            return True

        if fs.overall > best_score:
            best_score = fs.overall
            best_path = result_path
            best_fs = fs
            best_strategy = name

    salvage_sec = time.monotonic() - t_start

    if best_path and best_fs and best_fs.overall > score_before:
        logger.info("Salvage partial for %s: %.3f -> %.3f via %s",
                     take.take_id, score_before, best_fs.overall, best_strategy)
        take.postprocessed_path = best_path
        take.facet_score = best_fs
        take.style_diagnostic = diagnose_style(best_fs, p)
        take.selected_variant = SelectedVariant.SALVAGED
        take.salvage = SalvageRecord(
            applied=True, strategy=best_strategy,
            score_before=score_before, score_after=best_fs.overall,
            attempts=attempts, style_passed_after=False,
        )
    else:
        take.salvage = SalvageRecord(
            applied=False, score_before=score_before,
            attempts=attempts, style_passed_after=False,
        )

    _add_timing(take, salvage_sec=salvage_sec)
    return False


# ─── Timing helpers ──────────────────────────────────────────────────────

def _set_timing(take: Take, **kwargs):
    if take.timing is None:
        take.timing = TimingBreakdown()
    for k, v in kwargs.items():
        setattr(take.timing, k, v)

def _add_timing(take: Take, **kwargs):
    if take.timing is None:
        take.timing = TimingBreakdown()
    for k, v in kwargs.items():
        cur = getattr(take.timing, k, 0.0)
        setattr(take.timing, k, cur + v)


# ─── Public API ──────────────────────────────────────────────────────────

def pick_winner(
    takes: list[Take],
    prompt: str,
    postprocess_fn: callable | None = None,
    policy: PolicyConfig | None = None,
) -> Optional[str]:
    """Score, diagnose, salvage, build decision summaries, pick best by score."""
    p = policy or DEFAULT_POLICY
    if not takes:
        return None
    if len(takes) == 1 and postprocess_fn is None:
        fs = score_take(takes[0], prompt)
        takes[0].facet_score = fs
        takes[0].selected_variant = SelectedVariant.RAW
        takes[0].style_diagnostic = diagnose_style(fs, p)
        takes[0].decision_summary = build_decision_summary(takes[0])
        return takes[0].take_id

    best_id = None
    best_score = -1.0

    for take in takes:
        if postprocess_fn:
            score_with_postprocess(take, prompt, postprocess_fn, policy=p)
        else:
            take.facet_score = score_take(take, prompt)
            take.selected_variant = SelectedVariant.RAW

        diag = diagnose_style(take.facet_score, p)
        take.style_diagnostic = diag

        if not diag.passed and postprocess_fn:
            attempt_salvage(take, prompt, diag, postprocess_fn, policy=p)

        take.decision_summary = build_decision_summary(take)

        final_score = take.facet_score.overall if take.facet_score else 0.0
        if final_score > best_score:
            best_score = final_score
            best_id = take.take_id

    return best_id
