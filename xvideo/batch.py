"""Production batch runner for Shorts.

CSV in, folder of clips out. Handles resume, retry, validation, per-job
logs, and KPI collection. The CLI in scripts/run_shorts_batch.py is a
thin wrapper around BatchRunner.

Output folder layout:
    cache/batches/{batch_name}/
      manifest.csv          # one row per job attempt with status
      stats.json            # batch-level KPIs
      errors.log            # per-job failure messages
      clips/
        {job_id}_s{seed}.mp4
        {job_id}_s{seed}.png
        {job_id}_s{seed}.meta.json
      logs/
        {job_id}_s{seed}.log
"""

from __future__ import annotations

import csv
import json
import logging
import os
import signal
import time
import traceback
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Callable, Optional

import yaml

logger = logging.getLogger(__name__)


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class BatchJob:
    """One clip to render. Each row+seed in the CSV becomes a job."""
    job_id: str                    # e.g. "fox_run_s42"
    row_id: str                    # original CSV row id (shared across seed variants)
    subject: str
    action: str
    environment: str
    preset: str
    motion: str
    duration_sec: float
    aspect_ratio: str
    seed: int
    status: JobStatus = JobStatus.PENDING
    attempts: int = 0
    total_sec: float = 0.0
    image_gen_sec: float = 0.0
    error: str = ""
    output_path: str = ""
    # Optional: populated by content pack expansion
    extra_negative: str = ""       # pack-contributed negative prompt fragments
    pack_name: str = ""            # pack identifier (empty if running raw CSV)
    pack_row: dict = field(default_factory=dict)  # original pack CSV row (for publish helper)
    # Optional: populated by --format layer (social packaging preset)
    format: str = ""               # e.g. "shorts_clean", "tiktok_fast"
    # Populated by generate_fn when publish metadata is computed:
    title: str = ""
    caption: str = ""
    hashtags: str = ""             # space-separated hashtags for manifest column


@dataclass
class BatchStats:
    """Rolling KPIs for the batch."""
    batch_name: str = ""
    started_at: str = ""
    finished_at: str = ""
    total_jobs: int = 0
    completed: int = 0
    failed: int = 0
    skipped_resumed: int = 0
    total_wall_sec: float = 0.0
    avg_image_gen_sec: float = 0.0
    avg_total_sec: float = 0.0
    clips_per_minute: float = 0.0
    per_preset: dict[str, dict] = field(default_factory=dict)
    per_motion: dict[str, dict] = field(default_factory=dict)


class BatchRunner:
    """Runs a list of BatchJobs through the SDXL+parallax backend.

    Responsibilities:
      - Resume: skip jobs whose output already exists and validates.
      - Retry: up to N attempts with backoff on failure.
      - Validate: check file size + frame readability after each render.
      - Log: per-job .log file with full exception traceback.
      - KPI: rolling stats.json + manifest.csv updated after every job.
      - Signal-safe: SIGINT marks current running job as failed so next
        run can resume cleanly.
    """

    def __init__(
        self,
        batch_name: str,
        jobs: list[BatchJob],
        output_root: Path,
        batch_config: dict,
        generate_fn: Callable,
    ):
        self.batch_name = batch_name
        self.jobs = jobs
        self.output_root = Path(output_root)
        self.config = batch_config
        self.generate_fn = generate_fn

        self.batch_dir = self.output_root / batch_name
        self.clips_dir = self.batch_dir / "clips"
        self.logs_dir = self.batch_dir / "logs"
        self.manifest_path = self.batch_dir / "manifest.csv"
        self.stats_path = self.batch_dir / "stats.json"
        self.errors_path = self.batch_dir / "errors.log"

        for d in (self.clips_dir, self.logs_dir):
            d.mkdir(parents=True, exist_ok=True)

        self.stats = BatchStats(
            batch_name=batch_name,
            started_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
            total_jobs=len(jobs),
        )
        self._interrupted = False
        self._current_job: Optional[BatchJob] = None

    # ── Resume logic ─────────────────────────────────────────────────────

    def _output_valid(self, job: BatchJob) -> bool:
        """Check whether a job's output exists and passes validation."""
        clip_path = self.clips_dir / f"{job.job_id}.mp4"
        if not clip_path.exists():
            return False

        val = self.config.get("validation", {})
        min_kb = val.get("min_file_size_kb", 20)
        if clip_path.stat().st_size < min_kb * 1024:
            logger.info("Invalid output (too small): %s", clip_path)
            return False

        if val.get("require_readable_frames", True):
            try:
                import cv2
                cap = cv2.VideoCapture(str(clip_path))
                ok = cap.isOpened() and int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) > 0
                cap.release()
                if not ok:
                    logger.info("Invalid output (unreadable): %s", clip_path)
                    return False
            except Exception as e:
                logger.warning("Frame validation skipped (%s): %s", e, clip_path)

        # Sidecar must exist for resume safety
        sidecar = clip_path.with_suffix(".meta.json")
        if not sidecar.exists():
            return False

        return True

    # ── Manifest + stats I/O (append-safe, atomic) ────────────────────────

    def _write_manifest(self) -> None:
        tmp = self.manifest_path.with_suffix(".tmp")
        with open(tmp, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow([
                "job_id", "row_id", "subject", "preset", "motion", "seed",
                "duration_sec", "aspect_ratio", "format", "status", "attempts",
                "image_gen_sec", "total_sec", "output_path",
                "title", "caption", "hashtags", "error",
            ])
            for j in self.jobs:
                w.writerow([
                    j.job_id, j.row_id, j.subject, j.preset, j.motion, j.seed,
                    j.duration_sec, j.aspect_ratio, j.format,
                    j.status.value, j.attempts,
                    f"{j.image_gen_sec:.2f}", f"{j.total_sec:.2f}",
                    j.output_path,
                    (j.title or "")[:200], (j.caption or "")[:500], (j.hashtags or "")[:300],
                    (j.error or "")[:300],
                ])
        tmp.replace(self.manifest_path)

    def _write_stats(self) -> None:
        self.stats.finished_at = time.strftime("%Y-%m-%dT%H:%M:%S")
        tmp = self.stats_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(asdict(self.stats), indent=2))
        tmp.replace(self.stats_path)

    def _log_error(self, job: BatchJob, exc: Exception) -> None:
        msg = (f"[{time.strftime('%H:%M:%S')}] {job.job_id}  attempt={job.attempts}\n"
               f"  {type(exc).__name__}: {exc}\n")
        with open(self.errors_path, "a", encoding="utf-8") as f:
            f.write(msg)
        log_path = self.logs_dir / f"{job.job_id}.log"
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(msg)
            f.write(traceback.format_exc())
            f.write("\n---\n")

    # ── KPI aggregation ──────────────────────────────────────────────────

    def _update_kpis(self) -> None:
        completed = [j for j in self.jobs if j.status == JobStatus.COMPLETED]
        self.stats.completed = len(completed)
        self.stats.failed = sum(1 for j in self.jobs if j.status == JobStatus.FAILED)
        self.stats.skipped_resumed = sum(1 for j in self.jobs if j.status == JobStatus.SKIPPED)

        if completed:
            total_sec_sum = sum(j.total_sec for j in completed)
            img_sec_sum = sum(j.image_gen_sec for j in completed)
            self.stats.avg_total_sec = round(total_sec_sum / len(completed), 2)
            self.stats.avg_image_gen_sec = round(img_sec_sum / len(completed), 2)
            elapsed_min = max(self.stats.total_wall_sec / 60, 1e-6)
            self.stats.clips_per_minute = round(len(completed) / elapsed_min, 2)

        per_preset: dict = {}
        per_motion: dict = {}
        for j in self.jobs:
            for bucket, key in ((per_preset, j.preset), (per_motion, j.motion)):
                b = bucket.setdefault(key, {"count": 0, "completed": 0, "failed": 0,
                                            "avg_total_sec": 0.0, "sum_total_sec": 0.0})
                b["count"] += 1
                if j.status == JobStatus.COMPLETED:
                    b["completed"] += 1
                    b["sum_total_sec"] += j.total_sec
                elif j.status == JobStatus.FAILED:
                    b["failed"] += 1
        for bucket in (per_preset, per_motion):
            for k, v in bucket.items():
                v["avg_total_sec"] = round(v["sum_total_sec"] / v["completed"], 2) if v["completed"] else 0.0
                del v["sum_total_sec"]
        self.stats.per_preset = per_preset
        self.stats.per_motion = per_motion

    # ── Per-job execution with retry ─────────────────────────────────────

    def _run_one(self, job: BatchJob) -> bool:
        """Attempt one job up to max_attempts times. Returns True on success."""
        max_attempts = self.config.get("retry", {}).get("max_attempts", 3)
        backoffs = self.config.get("retry", {}).get("backoff_sec", [5, 15, 30])

        motion_profiles = self.config.get("motion_profiles", {})
        profile = motion_profiles.get(job.motion, motion_profiles.get("medium", {}))

        for attempt in range(1, max_attempts + 1):
            if self._interrupted:
                return False
            job.attempts = attempt
            job.status = JobStatus.RUNNING
            self._current_job = job
            self._write_manifest()

            try:
                t0 = time.time()
                result = self.generate_fn(
                    job=job,
                    output_dir=self.clips_dir,
                    motion_profile=profile,
                )
                job.total_sec = round(time.time() - t0, 2)
                job.image_gen_sec = result.get("image_gen_sec", 0.0)
                job.output_path = str(result["video_path"])

                # Post-render validation
                if not self._output_valid(job):
                    raise RuntimeError(
                        f"output failed validation (size/readable): {job.output_path}"
                    )

                job.status = JobStatus.COMPLETED
                return True

            except Exception as exc:
                job.error = f"{type(exc).__name__}: {exc}"
                self._log_error(job, exc)
                if attempt < max_attempts and not self._interrupted:
                    backoff = backoffs[min(attempt - 1, len(backoffs) - 1)]
                    logger.warning(
                        "[%s] attempt %d/%d failed: %s — retry in %ds",
                        job.job_id, attempt, max_attempts, exc, backoff,
                    )
                    time.sleep(backoff)
                else:
                    job.status = JobStatus.FAILED
                    logger.error("[%s] FAILED after %d attempts: %s",
                                 job.job_id, attempt, exc)
                    return False
        return False

    # ── Main loop ────────────────────────────────────────────────────────

    def run(self) -> BatchStats:
        """Run all jobs. Safe to call multiple times — completed jobs are skipped."""

        def _handle_sigint(signum, frame):
            logger.warning("SIGINT received — will stop after current job.")
            self._interrupted = True
            if self._current_job and self._current_job.status == JobStatus.RUNNING:
                self._current_job.status = JobStatus.FAILED
                self._current_job.error = "interrupted"

        prev_handler = signal.signal(signal.SIGINT, _handle_sigint)
        wall_start = time.time()

        try:
            for job in self.jobs:
                # Resume: skip if output already valid
                if self._output_valid(job):
                    job.status = JobStatus.SKIPPED
                    job.output_path = str(self.clips_dir / f"{job.job_id}.mp4")
                    logger.info("[%s] SKIP (completed in prior run)", job.job_id)
                    self.stats.total_wall_sec = round(time.time() - wall_start, 2)
                    self._update_kpis()
                    self._write_manifest()
                    self._write_stats()
                    continue

                if self._interrupted:
                    break

                logger.info("[%s] start  preset=%s motion=%s seed=%d",
                            job.job_id, job.preset, job.motion, job.seed)
                self._run_one(job)

                self.stats.total_wall_sec = round(time.time() - wall_start, 2)
                self._update_kpis()
                self._write_manifest()
                self._write_stats()

                if job.status == JobStatus.COMPLETED:
                    logger.info("[%s] OK in %.1fs", job.job_id, job.total_sec)
        finally:
            signal.signal(signal.SIGINT, prev_handler)
            self.stats.total_wall_sec = round(time.time() - wall_start, 2)
            self._update_kpis()
            self._write_manifest()
            self._write_stats()
            # Auto-generate the review gallery so the operator can start
            # selecting the moment the batch ends.
            try:
                from xvideo.gallery import build_gallery
                build_gallery(self.batch_dir)
            except Exception as e:
                logger.warning("Gallery generation skipped: %s", e)

        return self.stats


# ─── CSV loader ──────────────────────────────────────────────────────────

def load_jobs_from_csv(
    csv_path: Path,
    batch_config: dict,
    allow_backlog: bool = False,
) -> list[BatchJob]:
    """Parse prompts CSV into BatchJobs, one per (row, seed) pair."""

    ship = set(batch_config.get("ship_presets", []))
    backlog = set(batch_config.get("backlog_presets", []))
    allowed = ship | backlog if allow_backlog else ship

    motion_profiles = batch_config.get("motion_profiles", {})
    defaults = batch_config.get("defaults", {})

    jobs: list[BatchJob] = []
    seen_job_ids: set[str] = set()

    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for rownum, row in enumerate(reader, start=2):
            row_id = (row.get("id") or f"row{rownum}").strip()
            preset = (row.get("preset") or defaults.get("preset", "crystal")).strip()
            if preset not in allowed:
                raise ValueError(
                    f"Row {rownum} ({row_id}): preset '{preset}' not in ship set {sorted(ship)}. "
                    f"Pass --allow-backlog to use {sorted(backlog)}."
                )

            motion = (row.get("motion") or defaults.get("motion", "medium")).strip()
            if motion not in motion_profiles:
                raise ValueError(
                    f"Row {rownum} ({row_id}): motion '{motion}' not in "
                    f"{sorted(motion_profiles)}"
                )

            profile = motion_profiles[motion]
            duration_raw = (row.get("duration") or "").strip()
            duration = float(duration_raw) if duration_raw else profile["default_duration_sec"]
            aspect = (row.get("aspect") or defaults.get("aspect_ratio", "9:16")).strip()

            seeds_raw = (row.get("seeds") or "").strip()
            if seeds_raw:
                seeds = [int(s.strip()) for s in seeds_raw.split(",") if s.strip()]
            else:
                seeds = [int(defaults.get("seed", 42))]

            for seed in seeds:
                job_id = f"{row_id}_s{seed}"
                if job_id in seen_job_ids:
                    raise ValueError(f"Duplicate job_id '{job_id}' — check CSV for dupes.")
                seen_job_ids.add(job_id)

                jobs.append(BatchJob(
                    job_id=job_id,
                    row_id=row_id,
                    subject=(row.get("subject") or "").strip(),
                    action=(row.get("action") or "").strip(),
                    environment=(row.get("environment") or "").strip(),
                    preset=preset,
                    motion=motion,
                    duration_sec=duration,
                    aspect_ratio=aspect,
                    seed=seed,
                ))

    return jobs
