"""Python API entry point for the X-Video Engine.

Usage:
    from xvideo.api import Engine
    from xvideo.spec import GenerationSpec

    engine = Engine()
    spec = GenerationSpec(subject="a cyberpunk street at night", duration_sec=5.0)
    result = engine.generate(spec)

Phase 0: skeleton only. Engine.generate() raises NotImplementedError.
Phase 1+ wires the real pipeline.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Optional

from xvideo.router import Router
from xvideo.spec import ExecutionPlan, GenerationResult, GenerationSpec


class Engine:
    def __init__(
        self,
        config_dir: str | Path = "configs",
    ):
        self.config_dir = Path(config_dir)
        self.router = Router(self.config_dir / "backends.yaml")

    def plan(self, spec: GenerationSpec) -> ExecutionPlan:
        """Layer 3 — produce an ExecutionPlan from a GenerationSpec.

        Phase 0: stub. Phase 5 implements the MLLM planner.
        """
        raise NotImplementedError("Planner lands in Phase 5.")

    def generate(self, spec: GenerationSpec) -> GenerationResult:
        """Run the full pipeline: compile → plan → dispatch → rerank → cleanup."""
        raise NotImplementedError(
            "Full generation pipeline lands incrementally through Phase 1-6."
        )

    @staticmethod
    def new_spec_id() -> str:
        return uuid.uuid4().hex[:12]
