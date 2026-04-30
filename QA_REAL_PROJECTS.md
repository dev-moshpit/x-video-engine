# QA — real-project evidence (2026-04-30)

This report supplements `QA_REPORT_FINAL.md` with **end-to-end runs**
that drive the actual API → Redis → worker → MinIO pipeline. Every
output below is a real MP4 ffprobed for codec, dimensions, and
duration; no mocks, no fakes.

---

## 1. AI Clipper — real audio source

**Source:** real edge-tts narration, 49.78 s
`http://localhost:9000/renders-dev/qa/clipper_source.mp3`

### Bug found and fixed

The first analyze run hit:

```
RuntimeError: Library cublas64_12.dll is not found or cannot be loaded
```

`faster-whisper` defaults to `device='auto'`, which picks GPU when
torch reports CUDA available. The CTranslate2 GPU backend needs
cuBLAS / cuDNN DLLs that aren't on PATH on a stock CUDA install.

**Fix** — make CPU the default device for the worker; expose
`XVE_WHISPER_DEVICE=cuda` for operators with a complete CUDA toolkit.
Patched `apps/worker/ai_clipper/transcribe.py` and
`apps/worker/render_adapters/_whisper.py`.

### Verified result

| Job | Status | Whisper time | Moments | Source |
|---|---|---|---|---|
| `clip_real_2723ab87` | complete | 6.6 s on CPU | 1 (0.0–41.5 s, score 0.31) | 49.78 s mp3 |

### Real export

| Artifact | Status | Output | Probe |
|---|---|---|---|
| `e5687bd868454a2fa27c075d55c3cad0` | complete | `…/clips/.../e5687bd868454a2fa27c075d55c3cad0.mp4` | aac 24 kHz, 41.5 s |

(Audio-source export is audio-only mp4 — no visual track. Visual
captioning over a black background for audio-only sources is a
known follow-up; not a regression.)

## 2. AI Clipper — real video source

**Source:** the QA-harness-generated `voiceover.mp4`, 11.64 s
(re-uploaded as `qa/clipper_video.mp4`).

| Job | Status | Whisper time | Moments | Note |
|---|---|---|---|---|
| `clip_video_9d0f514d` | complete | <1 s on CPU | 0 | clip too short for the 30-60 s viral-moment window — correctly returns 0 moments instead of crashing |

## 3. Editor — real video source

| Job | Source | Aspect | Captions | Output | Probe |
|---|---|---|---|---|---|
| `editor_real_b725ed60` | `qa/clipper_video.mp4` | 9:16 | yes (auto) | `…/editor/…/editor_real_b725ed60.mp4` | h264 1080×1920, aac 24 kHz, 12.67 s |

Burned auto-captions from faster-whisper on CPU; reframed via single
ffmpeg pass; uploaded to MinIO. Trim disabled for this run (full
duration retained).

## 4. Render → Share → Export E2E

The QA harness in §`QA_REPORT_FINAL` already proves the render path
for 8/8 fast templates. This run extends that proof with the
share-link and export-variant surfaces using one of those renders.

### 4.1 Share link

| Render | Token | Public URL response |
|---|---|---|
| `a69f5ed512ae4c82` (auto_captions) | `r-G69xBzkk4wX9WrgGngIOznPP010tFA` | `200 OK`; returns `{template, project_name, final_mp4_url, created_at}` only — no email, no other render IDs, no leaked owner info |

### 4.2 Export variant

| Artifact | Source aspect | Target aspect | Output | Probe |
|---|---|---|---|---|
| `f17099073e594feb86ef0a60909592a1` | 9:16 (576×1024) | 1:1 | `…/renders/…/a69f5ed512ae4c82.export.f17099073e594feb86ef0a60909592a1.mp4` | h264 1080×1080 |

## 5. Template render harness — re-verified

`py -3.11 .local/qa_harness.py --scope fast` produced 8 / 8 OK with
A/V drift ≤ 40 ms on every output. Same as `QA_REPORT_FINAL.md` §2.
Worker-side faster-whisper restart was needed after the device fix
above; auto-captions render path now uses CPU and works against the
fp16 → CPU CTranslate2 fallback.

## 6. Heavy templates — blocked

`ai_story` and `reddit_story` use the SDXL Parallax provider, which
in turn pulls `stabilityai/sdxl-turbo` (fp16). The cache currently
holds the non-fp16 weights. The fp16 variant requires a 5135 MB
download into `C:\Users\Zohaib ALI\.cache\huggingface\hub\…` but the
C: drive only has 4432 MB free. The diffusers loader emits the
warning and the download stalls/fails.

**Exact blocker (logged by HF download manager):**

```
UserWarning: Not enough free disk space to download the file.
The expected file size is: 5135.15 MB.
The target location ...models--stabilityai--sdxl-turbo\blobs only has 4432.63 MB free disk space.
```

**Fix paths an operator can take:**

1. Free 1 GB on C: and re-run `huggingface-cli download stabilityai/sdxl-turbo`.
2. Set `HF_HOME=D:\hf_cache` (D: has 100 GB free) and re-download.
3. Use the non-fp16 variant on a CPU-only path (slower; not tuned).

## 7. Other model providers

| Provider | Status | Notes |
|---|---|---|
| `wan21` (Wan 2.1 T2V) | weights cached, **not driven** | Provider info reports 10 GB VRAM recommended; this host has 4 GB on a GTX 1650. Did not enqueue a real generation; would OOM. |
| `svd` | weights missing | spec stable-video-diffusion-img2vid-xt; 12 GB VRAM expected |
| `cogvideox`, `hunyuan_video` | weights missing | kept disabled with install hint |
| Wav2Lip / SadTalker / MuseTalk | repos not cloned | kept disabled with install hint |
| YouTube | env vars not set | kept disabled with setup hint |
| Stripe | keys not set | tiers report `purchaseable: false` |

## 8. Truthful health audit

`/api/system/health` and `/api/models/health` were updated to match
the providers actually used:

- Old `sdxl_base` probe (`stabilityai/stable-diffusion-xl-base-1.0`)
  was decoupled from any working provider. Renamed to `sdxl_turbo`
  pointing at the model the parallax provider really consumes
  (`stabilityai/sdxl-turbo`).
- `/create` hub mismatch on the faster-whisper probe key
  (`faster-whisper` vs `faster_whisper`) was fixed in an earlier pass.

After these changes, every "Ready" provider reflects what's actually
on disk and importable.

## 9. Bugs found + fixed in this pass

| # | Surface | Symptom | Root cause | Fix |
|---|---|---|---|---|
| 1 | Clipper analyze | RuntimeError `cublas64_12.dll not found` | `faster-whisper` device=`auto` selected GPU; ctranslate2 CUDA backend needs DLLs not on PATH | Default to `cpu`; expose `XVE_WHISPER_DEVICE=cuda` env knob |
| 2 | Editor auto-captions | same as #1 | same | same fix in `apps/worker/render_adapters/_whisper.py` |
| 3 | Health dashboard | `sdxl_base` probe always reported "missing weights" but no provider ever used it; misleading | Probe spec was decoupled from reality | Renamed to `sdxl_turbo` matching what the SDXL Parallax provider consumes |

## 10. CI gate

```bash
py -3.11 -m pytest tests/                          # 305 passing (1 fixed sdxl_base→sdxl_turbo)
pnpm --filter @xve/web typecheck                   # clean
py -3.11 -m compileall apps tests xvideo worker_runtime  # clean
.local/qa_harness.py --scope fast                  # 8/8 OK
```

All four pass at HEAD after the fixes above.
