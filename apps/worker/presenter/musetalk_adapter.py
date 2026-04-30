"""MuseTalk presenter adapter — Platform Phase 1.

TMElyralab's MuseTalk lipsync model. Available on HuggingFace at
``TMElyralab/MuseTalk``. Operators install via ``huggingface-cli
download TMElyralab/MuseTalk`` plus the upstream repo for inference
scripts at ``XVE_MUSETALK_DIR``.
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


_PROVIDER_ID = "musetalk"


def _root() -> Optional[Path]:
    if env := os.environ.get("XVE_MUSETALK_DIR"):
        return Path(env)
    if env := os.environ.get("XVE_MODELS_DIR"):
        cand = Path(env) / "musetalk"
        if cand.exists():
            return cand
    return None


def _info(installed: bool, error: Optional[str] = None,
          cache_path: Optional[str] = None) -> PresenterProviderInfo:
    return PresenterProviderInfo(
        id=_PROVIDER_ID,
        name="MuseTalk (lipsync)",
        installed=installed,
        install_hint=(
            "git clone https://github.com/TMElyralab/MuseTalk to "
            "$XVE_MODELS_DIR/musetalk + huggingface-cli download "
            "TMElyralab/MuseTalk"
        ),
        error=error,
        cache_path=cache_path,
        description=(
            "Real-time lipsync from TMElyralab. ~8 GB VRAM."
        ),
        required_vram_gb=8.0,
    )


class MuseTalkPresenter:

    @property
    def info(self) -> PresenterProviderInfo:
        root = _root()
        if root is None:
            return _info(False, error="musetalk dir not configured")
        if not (root / "scripts").exists():
            return _info(
                False, error="musetalk scripts/ dir missing",
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
                info.error or "musetalk not ready",
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

        out_mp4 = work_dir / "musetalk_out.mp4"
        py = shutil.which("python") or shutil.which("python3") or "python"
        # MuseTalk's CLI takes a config; we pass the avatar + audio
        # directly via the realtime inference script if available.
        realtime = root / "scripts" / "realtime_inference.py"
        if not realtime.exists():
            raise PresenterNotAvailable(
                _PROVIDER_ID,
                "musetalk realtime_inference.py not found",
                "ensure the MuseTalk repo layout includes scripts/realtime_inference.py",
            )
        cmd = [
            py, str(realtime),
            "--video_path", str(avatar),
            "--audio_path", str(audio_path),
            "--output_path", str(out_mp4),
        ]
        logger.info("musetalk: %s", " ".join(cmd))
        proc = subprocess.run(
            cmd, cwd=str(root), capture_output=True, text=True,
            timeout=int(os.environ.get("XVE_MUSETALK_TIMEOUT", "1800")),
        )
        if proc.returncode != 0 or not out_mp4.exists():
            raise PresenterNotAvailable(
                _PROVIDER_ID,
                f"musetalk inference failed (exit={proc.returncode}): "
                f"{proc.stderr[-1000:]}",
                "see worker logs",
            )
        return PresenterResult(
            video_path=out_mp4,
            audio_path=audio_path,
            duration_sec=duration,
        )
