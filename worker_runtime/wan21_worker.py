"""FastAPI worker runtime for the RTX 2080 desktop — LowPoly Video Engine.

Exposes Wan 2.1 T2V-1.3B low-poly generation over HTTP LAN. The laptop
orchestrator submits jobs, polls status, and downloads the resulting video.

Run on the 2080 desktop:
    python worker_runtime/wan21_worker.py --host 0.0.0.0 --port 8080

Endpoints:
    GET  /health                    — liveness + GPU + VRAM info
    POST /generate                  — submit a low-poly job
    GET  /jobs/{job_id}              — poll status
    POST /jobs/{job_id}/cancel       — cancel a queued or running job
    GET  /jobs/{job_id}/download     — stream the output .mp4

Phase 1a: scaffolding + fake generation (ffmpeg testsrc with color overlay).
Phase 1c: real Wan 2.1 inference with low-poly prompt conditioning.
Phase 2b: LoRA adapter loading for faceted style.
"""

from __future__ import annotations

import argparse
import logging
import os
import shutil
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
import uvicorn

sys.path.insert(0, str(Path(__file__).resolve().parent))
from schemas import (
    FailureCode,
    GenerateRequest,
    GenerateResponse,
    HealthResponse,
    JobStatus,
    JobStatusResponse,
)

logger = logging.getLogger("wan21_worker")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# ─── Storage ──────────────────────────────────────────────────────────────

WORKER_ROOT = Path(os.getenv("WORKER_ROOT", Path(__file__).resolve().parent / "cache"))
JOBS_DIR = WORKER_ROOT / "jobs"
JOBS_DIR.mkdir(parents=True, exist_ok=True)

# ─── In-memory job registry ───────────────────────────────────────────────

_jobs: dict[str, JobStatusResponse] = {}
_jobs_lock = threading.Lock()
_cancel_flags: dict[str, threading.Event] = {}


# ─── Backend loader (lazy) ────────────────────────────────────────────────

class _BackendRegistry:
    """Lazy-loaded model pipelines. Loaded on first job, kept warm."""

    def __init__(self):
        self._pipelines: dict[str, object] = {}
        self._lock = threading.Lock()

    def loaded(self) -> list[str]:
        return list(self._pipelines.keys())

    def get(self, backend_name: str):
        """Get or load a pipeline.
        Phase 1a stub: returns None (fake generation).
        Phase 1c: loads diffusers WanPipeline.
        Phase 2b: loads WanPipeline + LoRA adapter.
        """
        with self._lock:
            if backend_name in self._pipelines:
                return self._pipelines[backend_name]
            logger.warning("Backend %s not yet implemented (Phase 1a stub)", backend_name)
            return None


registry = _BackendRegistry()


# ─── GPU info ─────────────────────────────────────────────────────────────

def _gpu_info() -> dict:
    info = {"gpu_name": None, "vram_total_gb": None, "vram_free_gb": None}
    try:
        import torch
        if torch.cuda.is_available():
            idx = 0
            props = torch.cuda.get_device_properties(idx)
            free, total = torch.cuda.mem_get_info(idx)
            info["gpu_name"] = props.name
            info["vram_total_gb"] = round(total / (1024 ** 3), 2)
            info["vram_free_gb"] = round(free / (1024 ** 3), 2)
    except Exception as e:
        logger.debug("GPU info unavailable: %s", e)
    return info


# ─── Job execution ────────────────────────────────────────────────────────

def _run_job(req: GenerateRequest):
    """Execute a low-poly generation job. Runs in a background thread."""
    job_id = req.job_id
    cancel_evt = _cancel_flags.get(job_id)
    start = time.time()

    def _update(**kwargs):
        with _jobs_lock:
            cur = _jobs[job_id]
            for k, v in kwargs.items():
                setattr(cur, k, v)

    _update(status=JobStatus.RUNNING, progress=0.05)

    try:
        if cancel_evt and cancel_evt.is_set():
            _update(status=JobStatus.CANCELLED, failure_code=FailureCode.CANCELLED)
            return

        pipeline = registry.get(req.backend)
        if pipeline is None:
            # Phase 1a: fake generation — write a placeholder mp4 via ffmpeg.
            out_path = JOBS_DIR / f"{job_id}.mp4"
            _fake_generate(req, out_path, cancel_evt, update=_update)
            if cancel_evt and cancel_evt.is_set():
                _update(status=JobStatus.CANCELLED, failure_code=FailureCode.CANCELLED)
                return
            _update(
                status=JobStatus.SUCCEEDED,
                progress=1.0,
                video_path=str(out_path),
                generation_time_sec=time.time() - start,
            )
            return

        # Phase 1c: real Wan 2.1 inference with low-poly prompt conditioning.
        raise NotImplementedError("Real Wan 2.1 low-poly inference lands in Phase 1c.")

    except Exception as e:
        logger.exception("Job %s failed", job_id)
        _update(
            status=JobStatus.FAILED,
            failure_code=FailureCode.INFERENCE_CRASH,
            error_message=str(e),
            generation_time_sec=time.time() - start,
        )


def _fake_generate(req: GenerateRequest, out_path: Path, cancel_evt, update) -> None:
    """Phase 1a placeholder: generate a colored test pattern video via ffmpeg.

    Uses a low-poly-ish color scheme (teal/purple gradient) to visually
    distinguish from generic testsrc output.
    """
    logger.info("Phase 1a fake-generating %s (%.1fs @%s)", req.job_id, req.duration_sec, req.resolution)

    w, h = (480, 854) if req.resolution == "480p" else (720, 1280)
    if req.aspect_ratio == "16:9":
        w, h = h, w

    steps = 10
    for i in range(steps):
        if cancel_evt and cancel_evt.is_set():
            return
        time.sleep(0.2)
        update(progress=(i + 1) / steps * 0.9)

    if shutil.which("ffmpeg") is None:
        out_path.write_bytes(b"")
        return

    # Use a gradient color source that hints at low-poly aesthetic
    cmd = [
        "ffmpeg", "-y", "-f", "lavfi",
        "-i", f"testsrc=duration={req.duration_sec}:size={w}x{h}:rate={req.fps}",
        "-pix_fmt", "yuv420p",
        "-loglevel", "error",
        str(out_path),
    ]
    subprocess.run(cmd, check=True, timeout=60)


# ─── FastAPI app ──────────────────────────────────────────────────────────

app = FastAPI(title="LowPoly Wan 2.1 Worker", version="0.1.0")


@app.get("/health", response_model=HealthResponse)
def health():
    gpu = _gpu_info()
    with _jobs_lock:
        active = sum(1 for j in _jobs.values() if j.status in {JobStatus.QUEUED, JobStatus.RUNNING})
    return HealthResponse(
        status="ok",
        gpu_name=gpu["gpu_name"],
        vram_total_gb=gpu["vram_total_gb"],
        vram_free_gb=gpu["vram_free_gb"],
        active_jobs=active,
        loaded_backends=registry.loaded(),
    )


@app.post("/generate", response_model=GenerateResponse)
def generate(req: GenerateRequest, background: BackgroundTasks):
    if not req.job_id:
        req.job_id = uuid.uuid4().hex[:12]

    with _jobs_lock:
        if req.job_id in _jobs:
            raise HTTPException(409, f"job_id {req.job_id} already exists")
        _jobs[req.job_id] = JobStatusResponse(job_id=req.job_id, status=JobStatus.QUEUED)
        _cancel_flags[req.job_id] = threading.Event()

    background.add_task(_run_job, req)
    return GenerateResponse(job_id=req.job_id, status=JobStatus.QUEUED)


@app.get("/jobs/{job_id}", response_model=JobStatusResponse)
def job_status(job_id: str):
    with _jobs_lock:
        job = _jobs.get(job_id)
    if not job:
        raise HTTPException(404, f"job {job_id} not found")
    return job


@app.post("/jobs/{job_id}/cancel")
def cancel_job(job_id: str):
    with _jobs_lock:
        job = _jobs.get(job_id)
    if not job:
        raise HTTPException(404, f"job {job_id} not found")
    evt = _cancel_flags.get(job_id)
    if evt:
        evt.set()
    return {"ok": True, "job_id": job_id}


@app.get("/jobs/{job_id}/download")
def download_video(job_id: str):
    with _jobs_lock:
        job = _jobs.get(job_id)
    if not job:
        raise HTTPException(404, f"job {job_id} not found")
    if job.status != JobStatus.SUCCEEDED or not job.video_path:
        raise HTTPException(409, f"job {job_id} not ready (status={job.status})")
    p = Path(job.video_path)
    if not p.exists():
        raise HTTPException(410, f"video file missing for job {job_id}")
    return FileResponse(str(p), media_type="video/mp4", filename=f"{job_id}.mp4")


# ─── Entry point ──────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()

    gpu = _gpu_info()
    logger.info("Starting LowPoly Wan 2.1 worker on %s:%d", args.host, args.port)
    logger.info("GPU: %s (total %.1f GB, free %.1f GB)",
                gpu.get("gpu_name"), gpu.get("vram_total_gb") or 0, gpu.get("vram_free_gb") or 0)
    logger.info("Phase 1a mode: fake generation via ffmpeg (real inference in Phase 1c)")
    logger.info("Worker root: %s", WORKER_ROOT)

    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
