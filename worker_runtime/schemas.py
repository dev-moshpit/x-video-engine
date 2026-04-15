"""Shared job schemas between laptop router and 2080 worker.

Copied (not imported) from xvideo.spec to keep the worker runtime
deployable as a standalone directory on the desktop without the
full xvideo package.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class FailureCode(str, Enum):
    TIMEOUT = "timeout"
    OOM = "oom"
    INVALID_INPUT = "invalid_input"
    MODEL_LOAD_FAILED = "model_load_failed"
    INFERENCE_CRASH = "inference_crash"
    CANCELLED = "cancelled"
    UNKNOWN = "unknown"


class GenerateRequest(BaseModel):
    """Laptop → worker job submission."""
    job_id: str
    backend: Literal["wan21_t2v", "sdxl_image", "wan22_ti2v"]
    mode: Literal["t2v", "i2v"] = "t2v"
    prompt: str
    negative_prompt: str = ""
    seed: int = 0
    duration_sec: float = 5.0
    resolution: Literal["480p", "720p"] = "480p"
    fps: Literal[24, 30] = 24
    aspect_ratio: Literal["16:9", "9:16", "1:1"] = "16:9"
    num_inference_steps: int = 25
    guidance_scale: float = 6.0
    init_image_path: Optional[str] = None       # local path on worker host (for i2v)


class GenerateResponse(BaseModel):
    """Worker → laptop job submission ack."""
    job_id: str
    status: JobStatus


class JobStatusResponse(BaseModel):
    """Worker → laptop poll response."""
    job_id: str
    status: JobStatus
    progress: float = 0.0                       # 0..1
    video_path: Optional[str] = None            # local path on worker (served via /jobs/{id}/download)
    generation_time_sec: float = 0.0
    failure_code: Optional[FailureCode] = None
    error_message: Optional[str] = None


class HealthResponse(BaseModel):
    status: Literal["ok", "busy", "degraded"]
    gpu_name: Optional[str] = None
    vram_total_gb: Optional[float] = None
    vram_free_gb: Optional[float] = None
    active_jobs: int = 0
    loaded_backends: list[str] = Field(default_factory=list)
