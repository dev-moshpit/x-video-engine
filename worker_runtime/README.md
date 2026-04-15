# Worker Runtime (RTX 2080 desktop)

FastAPI service that runs Wan 2.1 T2V-1.3B inference. The laptop orchestrator
submits jobs over HTTP LAN.

## Install (on the 2080 desktop)

```bash
# Match CUDA 11.8 toolkit
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu118
pip install -r worker_runtime/requirements.txt
```

## Run

```bash
python worker_runtime/wan21_worker.py --host 0.0.0.0 --port 8080
```

Confirm with:

```bash
curl http://<2080-lan-ip>:8080/health
```

## Phase status

- **Phase 1b (current)**: HTTP protocol live, job queue works, generation is
  faked via `ffmpeg testsrc`. Proves the laptop↔desktop loop end-to-end.
- **Phase 1d**: Real Wan 2.1 inference via diffusers `WanPipeline`.
  Swap the `_fake_generate` call for `_wan21_generate`.

## Protocol

| Method | Path                       | Purpose                        |
|--------|----------------------------|--------------------------------|
| GET    | `/health`                  | GPU info, active jobs          |
| POST   | `/generate`                | Submit job, returns job_id     |
| GET    | `/jobs/{job_id}`           | Poll status + progress         |
| POST   | `/jobs/{job_id}/cancel`    | Cancel running/queued job      |
| GET    | `/jobs/{job_id}/download`  | Stream .mp4 result             |

Request/response schemas live in `schemas.py`.
