"""Wan 2.1 low-poly worker client — HTTP over LAN to the RTX 2080 desktop.

The laptop orchestrator uses this to dispatch low-poly generation jobs
to the FastAPI service defined in worker_runtime/wan21_worker.py.
"""

from __future__ import annotations

import logging
import time
import uuid
from pathlib import Path
from typing import Optional

import httpx

from xvideo.spec import BackendName, ShotPlan, Take
from xvideo.workers.base import WorkerClient

logger = logging.getLogger(__name__)


class Wan21LowPolyClient(WorkerClient):
    name = BackendName.WAN21_LOWPOLY

    def __init__(
        self,
        endpoint: str,
        auth_token: Optional[str] = None,
        timeout_sec: int = 600,
        poll_interval_sec: float = 1.0,
        cache_dir: str | Path = "./cache/takes",
    ):
        super().__init__(endpoint, auth_token, timeout_sec)
        self.poll_interval_sec = poll_interval_sec
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._client = httpx.Client(
            base_url=endpoint.rstrip("/"),
            timeout=httpx.Timeout(30.0, read=600.0),
            headers={"Authorization": f"Bearer {auth_token}"} if auth_token else {},
        )

    def is_available(self) -> bool:
        try:
            r = self._client.get("/health")
            r.raise_for_status()
            data = r.json()
            logger.info(
                "Worker %s health: gpu=%s vram_free=%sGB active=%d",
                self.endpoint, data.get("gpu_name"),
                data.get("vram_free_gb"), data.get("active_jobs", 0),
            )
            return data.get("status") == "ok"
        except Exception as e:
            logger.warning("Worker %s health check failed: %s", self.endpoint, e)
            return False

    def submit(self, shot: ShotPlan, ref_pack_url: Optional[str] = None) -> str:
        job_id = uuid.uuid4().hex[:12]
        payload = {
            "job_id": job_id,
            "backend": shot.backend.value,
            "mode": shot.mode.value,
            "prompt": shot.prompt,
            "negative_prompt": shot.negative_prompt,
            "seed": shot.seed,
            "duration_sec": shot.duration_sec,
            "resolution": shot.resolution,
            "fps": shot.fps,
            "aspect_ratio": shot.aspect_ratio,
            "num_inference_steps": shot.num_inference_steps,
            "guidance_scale": shot.guidance_scale,
            "style_config": shot.style_config.model_dump(),
        }
        r = self._client.post("/generate", json=payload)
        r.raise_for_status()
        data = r.json()
        logger.info("Submitted job %s to %s (status=%s)", job_id, self.endpoint, data.get("status"))
        return data["job_id"]

    def poll(self, job_id: str) -> dict:
        r = self._client.get(f"/jobs/{job_id}")
        r.raise_for_status()
        return r.json()

    def cancel(self, job_id: str) -> bool:
        try:
            r = self._client.post(f"/jobs/{job_id}/cancel")
            r.raise_for_status()
            return bool(r.json().get("ok"))
        except Exception as e:
            logger.warning("Cancel failed for %s: %s", job_id, e)
            return False

    def download(self, job_id: str, dest: Path) -> Path:
        dest.parent.mkdir(parents=True, exist_ok=True)
        with self._client.stream("GET", f"/jobs/{job_id}/download") as r:
            r.raise_for_status()
            with open(dest, "wb") as f:
                for chunk in r.iter_bytes():
                    f.write(chunk)
        return dest

    def generate_sync(self, shot: ShotPlan, ref_pack_url: Optional[str] = None) -> Optional[Take]:
        """Submit -> poll until terminal -> download -> return Take."""
        start = time.time()
        job_id = self.submit(shot, ref_pack_url)
        deadline = start + self.timeout_sec

        terminal = {"succeeded", "failed", "cancelled"}
        while True:
            if time.time() > deadline:
                logger.warning("Job %s exceeded timeout %ds; cancelling", job_id, self.timeout_sec)
                self.cancel(job_id)
                return None

            status = self.poll(job_id)
            s = status.get("status")
            if s in terminal:
                if s != "succeeded":
                    logger.warning(
                        "Job %s ended with status=%s code=%s err=%s",
                        job_id, s, status.get("failure_code"), status.get("error_message"),
                    )
                    return None
                break
            time.sleep(self.poll_interval_sec)

        dest = self.cache_dir / f"{shot.shot_id}_{job_id}.mp4"
        self.download(job_id, dest)

        return Take(
            take_id=f"{shot.shot_id}_{job_id}",
            shot_id=shot.shot_id,
            take_number=0,
            video_path=str(dest),
            seed=shot.seed,
            backend=shot.backend,
            generation_time_sec=status.get("generation_time_sec", time.time() - start),
            cost_usd=0.0,
        )

    def close(self):
        self._client.close()
