"""WorkerClient interface for remote GPU workers.

Workers run on GPU hosts and speak HTTP JSON-RPC. This module defines
the client-side interface the router uses to dispatch low-poly generation
jobs. Actual model inference lives in worker_runtime/.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from xvideo.spec import BackendName, ShotPlan, Take


class WorkerClient(ABC):
    """Client-side interface to a remote backend worker."""

    name: BackendName

    def __init__(self, endpoint: str, auth_token: Optional[str] = None, timeout_sec: int = 600):
        self.endpoint = endpoint
        self.auth_token = auth_token
        self.timeout_sec = timeout_sec

    @abstractmethod
    def is_available(self) -> bool: ...

    @abstractmethod
    def submit(self, shot: ShotPlan, ref_pack_url: Optional[str] = None) -> str: ...

    @abstractmethod
    def poll(self, job_id: str) -> dict: ...

    @abstractmethod
    def cancel(self, job_id: str) -> bool: ...

    def generate_sync(self, shot: ShotPlan, ref_pack_url: Optional[str] = None) -> Optional[Take]:
        """Submit + poll until done. Returns a Take on success, None on failure."""
        raise NotImplementedError("generate_sync implemented by subclass")
