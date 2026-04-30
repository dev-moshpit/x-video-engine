"""Generation router — dispatches ShotPlans to the low-poly backend worker.

Phase 1: single backend (Wan 2.1 low-poly). Loads endpoint from
configs/backends.yaml and instantiates the worker client.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

import yaml

from xvideo.capabilities import CAPABILITIES
from xvideo.spec import BackendName, ExecutionPlan, ShotPlan, ShotResult, Take
from xvideo.workers.base import WorkerClient
from xvideo.workers.wan21 import Wan21LowPolyClient

logger = logging.getLogger(__name__)


class Router:
    """Dispatches shots to the low-poly backend worker."""

    def __init__(self, config_path: str | Path = "configs/backends.yaml"):
        self.config_path = Path(config_path)
        self.config = self._load_config()
        self.clients: dict[BackendName, WorkerClient] = {}
        self._init_clients()

    def _load_config(self) -> dict:
        if not self.config_path.exists():
            logger.warning("Router config not found at %s; using empty defaults.", self.config_path)
            return {"workers": {}, "storage": {"provider": "local", "local_root": "./cache"}}
        with open(self.config_path) as f:
            return yaml.safe_load(f)

    def _init_clients(self) -> None:
        """Instantiate client objects for each configured worker endpoint."""
        workers_cfg = self.config.get("workers", {})
        cache_root = self.config.get("storage", {}).get("local_root", "./cache")

        for backend_name in BackendName:
            cfg = workers_cfg.get(backend_name.value, {})
            endpoint = cfg.get("endpoint")
            if not endpoint:
                continue

            auth_token = os.getenv(cfg.get("auth_token_env") or "") or None
            timeout_sec = cfg.get("timeout_sec", 600)

            client = self._build_client(backend_name, endpoint, auth_token, timeout_sec, cache_root)
            if client is None:
                logger.info("No client builder for %s (skipping)", backend_name.value)
                continue
            self.clients[backend_name] = client
            logger.info("Registered client for %s at %s", backend_name.value, endpoint)

    def _build_client(
        self,
        name: BackendName,
        endpoint: str,
        auth_token: Optional[str],
        timeout_sec: int,
        cache_root: str,
    ) -> Optional[WorkerClient]:
        if name == BackendName.WAN21_LOWPOLY:
            return Wan21LowPolyClient(
                endpoint=endpoint,
                auth_token=auth_token,
                timeout_sec=timeout_sec,
                cache_dir=Path(cache_root) / "takes",
            )
        # Phase 2: add I2V and SDXL keyframe clients
        return None

    def available_backends(self) -> list[BackendName]:
        """Return backends with a registered client."""
        return list(self.clients.keys())

    def estimate_cost(self, plan: ExecutionPlan) -> float:
        total = 0.0
        for shot in plan.shots:
            cap = CAPABILITIES.get(shot.backend)
            if cap:
                total += cap.approx_cost_per_sec_usd * shot.duration_sec * shot.num_candidates
        return total

    def dispatch(self, shot: ShotPlan, ref_pack_url: Optional[str] = None) -> ShotResult:
        """Dispatch one shot. Phase 1: single-candidate. Phase 2a adds multi-take + scoring."""
        client = self.clients.get(shot.backend)
        if client is None:
            return ShotResult(
                shot_id=shot.shot_id,
                takes=[],
                failure_codes=["backend_unavailable"],
            )

        takes: list[Take] = []
        for take_num in range(max(1, shot.num_candidates)):
            take_shot = shot.model_copy(update={"seed": shot.seed + take_num})
            take = client.generate_sync(take_shot, ref_pack_url)
            if take is None:
                continue
            take.take_number = take_num
            take.take_id = f"{shot.shot_id}_take_{take_num}"
            takes.append(take)

        if not takes:
            return ShotResult(
                shot_id=shot.shot_id,
                takes=[],
                failure_codes=["all_takes_failed"],
            )

        # Phase 1: winner = first successful take.
        # Phase 2a wires the FacetScorer.
        return ShotResult(
            shot_id=shot.shot_id,
            takes=takes,
            winner_take_id=takes[0].take_id,
        )

    def health_check(self) -> dict[str, bool]:
        """Ping all registered workers. Returns {backend_name: is_available}."""
        results = {}
        for name, client in self.clients.items():
            results[name.value] = client.is_available()
        return results
