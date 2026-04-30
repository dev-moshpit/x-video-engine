"""SadTalker presenter adapter — Platform Phase 1.

Higher-quality lipsync (~8 GB VRAM) with face animation. Same install
contract as Wav2Lip — operators clone the upstream repo and place
checkpoints under ``XVE_MODELS_DIR/sadtalker/`` (or set
``XVE_SADTALKER_DIR``).
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional

from apps.worker.presenter._tts import fetch_image, synthesize_voice
from apps.worker.presenter.base import (
    PresenterNotAvailable,
    PresenterProviderInfo,
    PresenterRequest,
    PresenterResult,
)


logger = logging.getLogger(__name__)


_PROVIDER_ID = "sadtalker"


def _root() -> Optional[Path]:
    if env := os.environ.get("XVE_SADTALKER_DIR"):
        return Path(env)
    if env := os.environ.get("XVE_MODELS_DIR"):
        cand = Path(env) / "sadtalker"
        if cand.exists():
            return cand
    return None


def _info(installed: bool, error: Optional[str] = None,
          cache_path: Optional[str] = None) -> PresenterProviderInfo:
    return PresenterProviderInfo(
        id=_PROVIDER_ID,
        name="SadTalker (lipsync + face animation)",
        installed=installed,
        install_hint=(
            "git clone https://github.com/OpenTalker/SadTalker into "
            "$XVE_MODELS_DIR/sadtalker + run scripts/download_models.sh"
        ),
        error=error,
        cache_path=cache_path,
        description=(
            "Higher-quality lipsync with subtle head movements. ~8 GB VRAM."
        ),
        required_vram_gb=8.0,
    )


class SadTalkerPresenter:

    @property
    def info(self) -> PresenterProviderInfo:
        root = _root()
        if root is None:
            return _info(False, error="sadtalker dir not configured")
        # Standard sadtalker layout: checkpoints/ holds the downloaded models.
        ckpt_dir = root / "checkpoints"
        if not ckpt_dir.exists() or not any(ckpt_dir.iterdir()):
            return _info(
                False, error="sadtalker checkpoints/ missing or empty",
                cache_path=str(root),
            )
        if not (root / "inference.py").exists():
            return _info(
                False, error="sadtalker inference.py not found",
                cache_path=str(root),
            )
        return _info(True, cache_path=str(root))

    def render(
        self, req: PresenterRequest, work_dir: Path,
    ) -> PresenterResult:
        info = self.info
        if not info.installed:
            raise PresenterNotAvailable(
                _PROVIDER_ID,
                info.error or "sadtalker not ready",
                info.install_hint,
            )

        work_dir.mkdir(parents=True, exist_ok=True)
        avatar = fetch_image(req.avatar_image_url, work_dir / "avatar.png")
        audio_path, duration = synthesize_voice(
            text=req.script, voice=req.voice, rate=req.voice_rate,
            work_dir=work_dir,
        )

        root = _root()
        assert root is not None

        out_dir = work_dir / "sadtalker_out"
        out_dir.mkdir(exist_ok=True)
        py = shutil.which("python") or shutil.which("python3") or "python"
        cmd = [
            py, str(root / "inference.py"),
            "--driven_audio", str(audio_path),
            "--source_image", str(avatar),
            "--result_dir", str(out_dir),
            "--still",
            "--preprocess", "crop",
            "--enhancer", "gfpgan",
        ]
        logger.info("sadtalker: %s", " ".join(cmd))
        proc = subprocess.run(
            cmd, cwd=str(root), capture_output=True, text=True,
            timeout=int(os.environ.get("XVE_SADTALKER_TIMEOUT", "3600")),
        )
        if proc.returncode != 0:
            raise PresenterNotAvailable(
                _PROVIDER_ID,
                f"sadtalker inference failed (exit={proc.returncode}): "
                f"{proc.stderr[-1000:]}",
                "see worker logs; SadTalker often needs torchvision tweaks",
            )

        # SadTalker writes its output mp4 into a timestamped subdir; pick
        # the most recent .mp4 it produced.
        mp4s = sorted(out_dir.rglob("*.mp4"), key=lambda p: p.stat().st_mtime)
        if not mp4s:
            raise PresenterNotAvailable(
                _PROVIDER_ID, "sadtalker produced no mp4",
                "check worker logs",
            )
        return PresenterResult(
            video_path=mp4s[-1],
            audio_path=audio_path,
            duration_sec=duration,
        )
