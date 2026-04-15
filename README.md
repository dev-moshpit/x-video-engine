# X-Video Engine

Generic multimodal video generation platform built on open foundation models
(Wan 2.2, HunyuanVideo-1.5, OmniWeaving, LTX-Video).

**Status**: Phase 0 — foundation scaffold. No generation capability yet.

## Architecture

Eight-layer pipeline:

1. **Input compiler** — natural language → structured `GenerationSpec`
2. **Reference pack builder** — normalize images/clips/audio/keyframes
3. **Planner** — MLLM decides backend + mode + shot split
4. **Generation router** — dispatch shots to GPU workers
5. **Quality reranker** — N candidates → scored → winner
6. **Detail / SR / cleanup** — upscale, face restore, deflicker, export
7. **Audio stage** — ambience, music, SFX, TTS, lip sync
8. **Training / adaptation** — style/character/environment LoRAs

See `C:\Users\Zohaib ALI\.claude\plans\linear-painting-nova.md` for the full plan.

## Deployment

Orchestrator runs on any machine (local laptop is fine). GPU-bound generation
runs on remote workers (RunPod, vast.ai, Lambda) over JSON-RPC. The local box
never tries to generate video itself.

## Repo layout

```
xvideo/                 # Orchestrator package
  spec.py               # GenerationSpec, ShotPlan, Reference dataclasses
  capabilities.py       # Backend capability matrix
  router.py             # Dispatch to workers
  api.py                # Python API entry point
  workers/              # Per-backend client stubs
worker_runtime/         # Docker image run on GPU pods (Phase 1+)
configs/                # YAML configs (backends, defaults)
scripts/                # Smoke tests, CLI entry points
tests/                  # pytest suite
```

## Phase 0 smoke test

```bash
pip install pydantic pyyaml
python scripts/smoke_test_backend.py
```

Should print `All Phase 0 smoke tests passed.`
