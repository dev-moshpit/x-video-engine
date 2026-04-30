# LowPoly Video Engine — Vision & Architecture

## Product Vision

**One-line pitch**: Generate stylized low-poly animated videos on a single
consumer GPU — no 3D software, no cloud credits, no expertise required.

LowPoly Video Engine turns text prompts (and optional reference images) into
faceted, geometric-art-style video clips optimized for:

- **Social media content** — scroll-stopping aesthetic that stands out
- **Indie game trailers & cutscenes** — stylised look without a 3D art team
- **Motion graphics & explainers** — clean geometric visuals
- **Music videos & VJ loops** — seamless, rhythmic low-poly animation
- **NFT / generative art** — unique collectible video art

The engine runs on a single RTX 2080 (8 GB VRAM). No cloud dependency required
for the core generation loop.

---

## Why Low-Poly?

1. **Aesthetic constraint = quality unlock.**  Low-poly's flat-shaded facets,
   limited palette, and geometric shapes play to the strengths of small
   diffusion models — less detail to hallucinate, fewer artifacts to mask.
2. **Consumer-GPU friendly.**  A 1.3B-parameter model generating 480p faceted
   animation at 24 fps fits comfortably in 8 GB VRAM with fp16.
3. **Under-served niche.**  No existing tool generates low-poly *video* from
   text. Blender requires manual modeling; AI video tools target photorealism.
4. **Style-LoRA sweet spot.**  Low-poly is a learnable distribution shift —
   a small LoRA (≤64 MB) fine-tuned on ~500 low-poly clips dramatically
   improves facet consistency vs. prompt engineering alone.

---

## Architecture (Refactored from Generic Platform)

### Before → After

| Layer | Generic Platform | LowPoly Engine |
|-------|-----------------|----------------|
| Input | Free-form multimodal spec | `LowPolySpec` with style knobs |
| Planner | MLLM routes across 11 backends | Deterministic: one backend, style presets |
| Router | Multi-backend dispatch | Single-backend focus (Wan 2.1 → LoRA) |
| Scoring | Generic CLIP reranker | `FacetScore` — facet clarity, palette cohesion, edge stability |
| Cleanup | Face restore, deflicker | Edge-sharpening post-process for facets |
| Audio | Full pipeline | Ambient/loop audio (optional, Phase 3) |
| Training | Generic LoRA | Low-poly style LoRA fine-tuning pipeline |

### Simplified Pipeline

```
Prompt ──► StylePreset ──► PromptCompiler ──► Wan21Worker ──► FacetScorer ──► EdgeSharpen ──► .mp4
              │                                    │
         palette, density,                    style LoRA
         lighting, camera                     (Phase 2)
```

### Component Responsibilities

| Component | Role |
|-----------|------|
| `LowPolySpec` | User intent: subject, action, style knobs (polygon density, palette, lighting) |
| `StylePreset` | Curated defaults: "crystal", "papercraft", "wireframe", "geometric-nature", etc. |
| `PromptCompiler` | Merges spec + preset → backend-ready prompt with negative prompt |
| `Wan21Worker` | Runs Wan 2.1 T2V-1.3B (+ optional LoRA) on RTX 2080 |
| `FacetScorer` | Scores takes on facet clarity, palette cohesion, temporal edge stability |
| `EdgeSharpen` | Post-process: bilateral filter to enhance facet edges in output video |

---

## Schema Design

### Core Enums

```
PolyDensity:   MINIMAL | LOW | MEDIUM | HIGH
                (≈20)   (≈80) (≈200)  (≈500 polygons per subject)

PaletteMode:   MONOCHROME | DUOTONE | TRICOLOR | PASTEL | NEON | EARTH | CUSTOM

LightingMode:  FLAT | GRADIENT | DRAMATIC | BACKLIT | AMBIENT_OCCLUSION

CameraMove:    STATIC | ORBIT | DOLLY_IN | DOLLY_OUT | PAN_LEFT | PAN_RIGHT
               TILT_UP | TILT_DOWN | CRANE | TRACKING

LoopMode:      NONE | SEAMLESS | PING_PONG
```

### LowPolySpec (replaces GenerationSpec)

```python
class LowPolySpec:
    subject: str             # "a fox", "a mountain landscape"
    action: str | None       # "running", "rotating slowly"
    environment: str | None  # "forest clearing", "abstract void"
    style_preset: str        # key into configs/styles/*.yaml
    poly_density: PolyDensity
    palette: PaletteMode
    custom_colors: list[str] | None   # hex codes when palette=CUSTOM
    lighting: LightingMode
    camera: CameraMove
    camera_speed: float       # 0.0 (static) → 1.0 (fast)
    loop_mode: LoopMode
    duration_sec: float       # 2.0 – 5.0
    seed: int | None
    reference_image: str | None  # optional style reference
    num_candidates: int       # 1-4 takes to score
```

### FacetScore (replaces generic reranker weights)

```python
class FacetScore:
    facet_clarity: float      # sharpness of polygon edges (0-1)
    palette_cohesion: float   # color consistency with target palette (0-1)
    edge_stability: float     # temporal consistency of edges across frames (0-1)
    prompt_alignment: float   # CLIP similarity to prompt (0-1)
    motion_quality: float     # smoothness and intentionality of motion (0-1)
    overall: float            # weighted composite
```

Default weights: facet_clarity 0.30, palette_cohesion 0.20,
edge_stability 0.20, prompt_alignment 0.20, motion_quality 0.10.

---

## Backend Strategy

### Phase 1: Prompt-Engineered Low-Poly (No LoRA)

Use Wan 2.1 T2V-1.3B with aggressive style prompting:

**Prompt template:**
```
low poly 3d render, faceted geometric {subject}, {action},
{environment}, flat shaded polygons, {palette} color palette,
{lighting} lighting, {camera} camera, stylized minimalist,
clean triangular faces, sharp geometric edges
```

**Negative prompt:**
```
photorealistic, smooth surfaces, organic textures, film grain,
bokeh, lens flare, motion blur, high detail skin, hair strands,
realistic lighting, ray tracing, subsurface scattering
```

### Phase 2: Style LoRA

Fine-tune a LoRA adapter (rank 16-32, ≤64 MB) on:
- 300-500 low-poly 3D render clips (Sketchfab turntables, Blender renders)
- Captioned with consistent "low poly" vocabulary
- Train on RTX 2080 with gradient checkpointing (fits in 8 GB)

### Phase 3: Specialized Post-Processing

- Bilateral filtering to enhance facet edges
- Palette quantization to enforce color constraints
- Optional: frame-by-frame Canny→edge overlay for wireframe variant

---

## Scoring Logic — FacetScorer

### Facet Clarity (weight: 0.30)
Extract Canny edges from each frame. Measure edge straightness via
Hough line transform. High ratio of straight edges to curved edges
= high facet clarity. Penalize organic curves.

### Palette Cohesion (weight: 0.20)
K-means cluster the frame pixels (k = target palette size).
Measure distance between cluster centers and target palette colors.
Low distance = high cohesion.

### Edge Stability (weight: 0.20)
Compare Canny edge maps between consecutive frames.
Compute structural similarity (SSIM) on edge maps.
High SSIM across frames = stable, non-flickering edges.

### Prompt Alignment (weight: 0.20)
Standard CLIP ViT-L/14 cosine similarity between prompt and
middle frame. Same as generic reranker but applied to the compiled
low-poly prompt.

### Motion Quality (weight: 0.10)
Optical flow magnitude histogram. Penalize both zero-flow (frozen)
and extreme-flow (chaotic). Reward smooth, directional flow that
matches the specified camera move.

---

## Implementation Phases

### Phase 1a — Schema & Config Pivot (This PR)
- [x] Replace `GenerationSpec` with `LowPolySpec`
- [x] Replace generic enums with low-poly enums
- [x] Add `FacetScore` dataclass
- [x] Create style preset YAML files
- [x] Update `default.yaml` with low-poly defaults
- [x] Simplify `capabilities.py` to single-backend focus
- [x] Update worker schemas for low-poly fields
- [x] Update smoke tests

### Phase 1b — Prompt Compiler
- [ ] Build `PromptCompiler` that merges spec + preset → prompt
- [ ] Implement negative prompt generation
- [ ] Template library for different style presets

### Phase 1c — Real Inference on 2080
- [ ] Wan 2.1 T2V-1.3B running on RTX 2080
- [ ] LAN smoke test generating actual low-poly video
- [ ] Tune inference params (steps, guidance scale) for faceted look

### Phase 2a — FacetScorer
- [ ] Implement Canny + Hough facet clarity metric
- [ ] Implement palette cohesion via k-means
- [ ] Implement edge stability via temporal SSIM
- [ ] Multi-candidate generation + scoring

### Phase 2b — Style LoRA
- [ ] Curate 500-clip low-poly training dataset
- [ ] Train LoRA adapter (rank 16-32)
- [ ] A/B test: LoRA vs. prompt-only quality
- [ ] Integrate LoRA loading into worker pipeline

### Phase 3 — Post-Processing & Polish
- [ ] Bilateral filter edge sharpening
- [ ] Palette quantization post-process
- [ ] Wireframe overlay variant
- [ ] Seamless loop generation (ping-pong + crossfade)

### Phase 4 — Audio & Export
- [ ] Ambient loop audio matching (optional)
- [ ] GIF export for social media
- [ ] Batch generation API
- [ ] Web UI prototype

---

## MVP Rollout Plan

### MVP (Phases 1a-1c) — "It generates low-poly video"

**Deliverable**: CLI that takes a text prompt + style preset and outputs
a 2-5 second low-poly .mp4 on a RTX 2080 over LAN.

**Success criteria**:
1. `python -m xvideo.cli "a fox running" --preset crystal` → .mp4
2. Output is recognizably low-poly (faceted, geometric, flat-shaded)
3. Generation completes in < 120 seconds on RTX 2080
4. Works on 8 GB VRAM (fp16, 480p, 24fps)

**Target**: Internal demo / Twitter post with 4-6 example clips.

### v0.2 (Phase 2a-2b) — "It generates *good* low-poly video"

**Deliverable**: Multi-candidate generation with FacetScorer ranking.
LoRA adapter for consistent faceted output.

**Success criteria**:
1. 4-candidate scoring picks visually best take ≥ 80% of the time
2. LoRA clips rated "clearly low-poly" by 5 blind reviewers ≥ 90%
3. FacetScorer correlates with human preference (Kendall τ > 0.6)

### v1.0 (Phase 3-4) — "Ship it"

**Deliverable**: Post-processing, loop support, audio, web UI.

**Success criteria**:
1. End-to-end: prompt → scored → post-processed → audio → final .mp4
2. Web UI for non-technical users
3. < 60s generation time with optimized pipeline
4. Public launch: ProductHunt / HackerNews
