"""BackendWorker interface.

Workers are remote: they run on GPU hosts (RunPod/vast.ai) and speak JSON-RPC
over HTTP. This module defines the client-side interface the router uses.
Actual model inference lives in worker_runtime/, not here.
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
    def is_available(self) -> bool:
        """Health check. Returns True if the worker responds."""
        ...

    @abstractmethod
    def submit(self, shot: ShotPlan, ref_pack_url: Optional[str] = None) -> str:
        """Submit a job. Returns a job_id."""
        ...

    @abstractmethod
    def poll(self, job_id: str) -> dict:
        """Poll a job. Returns status dict: {status, progress, result_url, error}."""
        ...

    @abstractmethod
    def cancel(self, job_id: str) -> bool:
        """Cancel a running job."""
        ...

    def generate_sync(self, shot: ShotPlan, ref_pack_url: Optional[str] = None) -> Optional[Take]:
        """Submit + poll until done. Returns a Take on success, None on failure.

        Default implementation uses submit + poll. Subclasses can override
        for more efficient execution.
        """
        raise NotImplementedError("generate_sync will be implemented in Phase 1")
