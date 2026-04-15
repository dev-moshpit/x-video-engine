# Phase 1d Handoff — RTX 2080 Desktop

You are Claude Code running on the RTX 2080 desktop. The laptop session
finished Phase 0, 1a, 1b, 1c and proved the LAN protocol via a loopback
smoke test. Your job is to replace the fake generator in
`worker_runtime/wan21_worker.py` with real Wan 2.1 T2V-1.3B inference.

## Architecture recap

- Laptop = orchestrator (router, reranker, planner, cleanup)
- 2080 desktop = GPU worker (you)
- Transport = HTTP over LAN, JSON-RPC style
- Repo lives here; do not restructure

## Authoritative plan

`C:\Users\Zohaib ALI\.claude\plans\linear-painting-nova.md` on the laptop.
You may not have it locally — the gist:

- Phase 1 = Wan 2.1 1.3B on 2080, nothing fancier
- Phase 2+ = LTX / Wan 2.2 CPU offload / OmniWeaving (deferred)
- Target: `laptop sends job → 2080 worker runs Wan 2.1 → result returns
  → reranker selects best → export works`

## What is already done

- `worker_runtime/wan21_worker.py` — FastAPI service, endpoints working:
  - `GET /health`, `POST /generate`, `GET /jobs/{id}`,
    `POST /jobs/{id}/cancel`, `GET /jobs/{id}/download`
- `worker_runtime/schemas.py` — `GenerateRequest`, `JobStatusResponse`, etc.
- `_BackendRegistry.get()` returns `None` for any backend name (stub).
- `_run_job()` calls `_fake_generate()` which writes an ffmpeg `testsrc` mp4.

## What you need to do

### 1. Install deps on the 2080

```powershell
# CUDA 11.8 wheels (matches laptop environment cache torch_extensions/py311_cu118)
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu118
pip install -r worker_runtime/requirements.txt
```

Verify GPU:

```powershell
python -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"
```

Expected: `True NVIDIA GeForce RTX 2080` (or 2080 Ti).

### 2. Download Wan 2.1 weights

Model: `Wan-AI/Wan2.1-T2V-1.3B-Diffusers` (HuggingFace, ~5 GB).

```powershell
huggingface-cli download Wan-AI/Wan2.1-T2V-1.3B-Diffusers
```

Or let `diffusers.WanPipeline.from_pretrained(...)` auto-download on first call.

### 3. Implement real inference

Replace the `_fake_generate(...)` branch in `_run_job()` with real
Wan 2.1 inference.

Expected shape (verify against current `diffusers` API — WanPipeline class
name and init signature may differ; `pip show diffusers` ≥ 0.30):

```python
# In _BackendRegistry.get():
if backend_name == "wan21_t2v":
    from diffusers import WanPipeline   # or AutoPipelineForText2Video
    import torch
    pipe = WanPipeline.from_pretrained(
        "Wan-AI/Wan2.1-T2V-1.3B-Diffusers",
        torch_dtype=torch.float16,
    )
    pipe.to("cuda")
    # Optional if VRAM tight:
    # pipe.enable_model_cpu_offload()
    self._pipelines[backend_name] = pipe
    return pipe
```

New helper replacing `_fake_generate`:

```python
def _wan21_generate(req, out_path, cancel_evt, update, pipeline):
    import torch
    from diffusers.utils import export_to_video

    # Resolution mapping (9:16 portrait vs 16:9 landscape)
    w, h = (480, 832) if req.resolution == "480p" else (720, 1280)
    if req.aspect_ratio == "16:9":
        w, h = h, w

    num_frames = int(req.duration_sec * req.fps)

    generator = torch.Generator(device="cuda").manual_seed(req.seed)

    def callback(step, timestep, latents):
        if cancel_evt and cancel_evt.is_set():
            raise RuntimeError("cancelled")
        update(progress=min(0.95, step / max(1, req.num_inference_steps)))

    result = pipeline(
        prompt=req.prompt,
        negative_prompt=req.negative_prompt or None,
        height=h,
        width=w,
        num_frames=num_frames,
        num_inference_steps=req.num_inference_steps,
        guidance_scale=req.guidance_scale,
        generator=generator,
        callback=callback,
        callback_steps=1,
    )
    frames = result.frames[0]
    export_to_video(frames, str(out_path), fps=req.fps)
```

Then in `_run_job()`:

```python
pipeline = registry.get(req.backend)
if pipeline is None:
    _fake_generate(req, out_path, cancel_evt, update=_update)
else:
    _wan21_generate(req, out_path, cancel_evt, _update, pipeline)
```

### 4. Test

```powershell
# Terminal A (on the 2080):
python worker_runtime/wan21_worker.py --host 0.0.0.0 --port 8080
```

Note the 2080's LAN IP from `ipconfig`. Then from the LAPTOP:

```powershell
set XVIDEO_WAN21_ENDPOINT=http://<2080-lan-ip>:8080
python scripts/run_lan_smoke.py
```

Expected: a real 3-second 480p video arrives on the laptop in
`cache/takes/lan_smoke_000_<jobid>.mp4`.

### 5. Hand back

When real inference works end-to-end, commit + push. The laptop session
will pick up Phase 1e (two-candidate reranker) next.

## Known constraints

- RTX 2080 = 8 GB VRAM (or 11 GB if 2080 Ti). 1.3B model fits natively
  in fp16 with small room for activations. If OOM at 720p, drop to 480p.
- Turing (2080) has no bf16; use fp16 only.
- First inference after load takes extra time (warmup). Subsequent calls
  are faster.
- Keep `num_inference_steps=25-30` for reasonable time; Wan 2.1 reference
  uses 30-50.

## Do NOT

- Do not add Wan 2.2, HunyuanVideo, OmniWeaving, or LTX in this pass.
  Phase 1 is Wan 2.1 only.
- Do not change the HTTP protocol or schemas — the laptop client depends
  on them. If you need new fields, add them as optional and tell the
  laptop session.
- Do not delete `_fake_generate` — it remains the fallback for missing
  backends.
