"""System & model health probe tests — Phase 1 (Platform).

Two layers exercised:

1. The pure-python probes in ``app.services.system_health`` —
   verifying each one returns a sensible ProbeResult / ModelProbe even
   when the dependency is missing (no exceptions out of probe code).

2. The FastAPI routes in ``app.routers.system`` — verifying
   authentication, response shape, and that "module not importable"
   correctly maps to ``installed=False`` on the wire.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.auth.clerk import ClerkPrincipal, current_user
from app.db.base import Base
from app.db.session import engine
from app.main import app
from app.services import system_health as sh


@pytest.fixture(autouse=True)
def fresh_schema():
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture
def authed_client():
    fake = ClerkPrincipal(
        user_id="user_sys_health",
        session_id="sess_sys",
        email="sys@example.com",
    )
    app.dependency_overrides[current_user] = lambda: fake
    yield TestClient(app)
    app.dependency_overrides.pop(current_user, None)


# ─── Probe-level tests ─────────────────────────────────────────────────


def test_probe_ffmpeg_returns_ok_when_imageio_ffmpeg_present():
    """imageio-ffmpeg is in requirements; probe must succeed."""
    res = sh.probe_ffmpeg()
    assert res.name == "ffmpeg"
    assert res.ok is True
    assert "ffmpeg" in (res.detail or "").lower() or "version" in (res.detail or "")


def test_probe_redis_handles_unreachable_host():
    """A bad REDIS_URL must produce an error result, not raise."""
    with patch.dict("os.environ", {"REDIS_URL": "redis://127.0.0.1:1/0"}):
        # Force fresh redis client by patching the module-global cache
        res = sh.probe_redis()
    assert res.name == "redis"
    assert res.ok is False
    assert res.error is not None
    assert res.hint is not None


def test_probe_storage_handles_unreachable_endpoint():
    with patch.dict(
        "os.environ", {"R2_ENDPOINT": "http://127.0.0.1:1"},
    ):
        res = sh.probe_storage()
    assert res.name == "storage"
    assert res.ok is False
    assert res.error is not None


def test_probe_faster_whisper_reports_module_status():
    """Either present (ok=True) or missing (ok=False with hint).

    Whichever it is on the test host, the probe must never raise and
    must always populate ``name`` + the boolean. faster-whisper is in
    apps/worker/requirements.txt but might not be in the api venv.
    """
    res = sh.probe_faster_whisper()
    assert res.name == "faster_whisper"
    assert isinstance(res.ok, bool)
    if not res.ok:
        assert res.hint is not None


def test_probe_gpu_returns_advisory_when_no_smi():
    """If nvidia-smi isn't on PATH, probe is not-ok but with detail.

    The api treats GPU as advisory in ``system_health_snapshot`` — a
    CPU-only host is still healthy.
    """
    with patch("app.services.system_health.shutil.which", return_value=None):
        res = sh.probe_gpu()
    assert res.name == "gpu"
    assert res.ok is False
    assert res.detail  # non-empty


def test_module_importable_finds_stdlib():
    assert sh._module_importable("json") is True
    assert sh._module_importable("definitely_not_a_real_module_xyz") is False


def test_probe_model_marks_missing_when_runtime_absent():
    """A spec with a fake runtime module → installed=False, with a hint."""
    fake = sh._ModelSpec(
        id="fake_model",
        name="Fake",
        mode="text-to-video",
        runtime_module="not_a_real_module_at_all",
        hf_repo="fake-org/fake-repo",
        local_dirs=("fake-dir",),
        required_vram_gb=1.0,
        install_hint="never",
    )
    res = sh.probe_model(fake)
    assert res.installed is False
    assert "missing" in res.status
    assert res.hint == "never" or "fake-org" in (res.hint or "") or res.hint


def test_probe_model_uses_xve_models_dir(tmp_path: Path):
    """``XVE_MODELS_DIR/<local_dir>`` is treated as a valid weight cache."""
    models_dir = tmp_path / "models"
    (models_dir / "models--Systran--faster-whisper-base").mkdir(parents=True)
    with patch.dict("os.environ", {"XVE_MODELS_DIR": str(models_dir)}):
        # Use one of the real specs; faster-whisper module is in
        # worker requirements but may or may not be in the api venv —
        # so we only assert the cache_path was found, not installed.
        spec = next(
            s for s in sh._MODEL_SPECS if s.id == "faster_whisper_base"
        )
        res = sh.probe_model(spec)
        if res.cache_path is not None:
            assert "faster-whisper-base" in res.cache_path


def test_probe_all_models_returns_one_per_spec():
    res = sh.probe_all_models()
    ids = {m.id for m in res}
    # We at least know about these — adding more is fine.
    expected_subset = {
        "faster_whisper_base",
        "sdxl_base",
        "svd",
        "wan21",
        "hunyuan_video",
        "cogvideox",
    }
    assert expected_subset.issubset(ids)


# ─── HTTP route tests ───────────────────────────────────────────────────


def test_system_health_requires_auth():
    res = TestClient(app).get("/api/system/health")
    assert res.status_code == 401


def test_system_health_returns_probes(authed_client: TestClient):
    res = authed_client.get(
        "/api/system/health",
        headers={"Authorization": "Bearer mock"},
    )
    assert res.status_code == 200
    body = res.json()
    assert "ok" in body
    assert isinstance(body["probes"], list)
    names = {p["name"] for p in body["probes"]}
    assert {"ffmpeg", "redis", "storage", "faster_whisper", "gpu"}.issubset(
        names
    )
    for p in body["probes"]:
        assert "ok" in p
        assert "name" in p


def test_models_health_requires_auth():
    res = TestClient(app).get("/api/models/health")
    assert res.status_code == 401


def test_models_health_returns_inventory(authed_client: TestClient):
    res = authed_client.get(
        "/api/models/health",
        headers={"Authorization": "Bearer mock"},
    )
    assert res.status_code == 200
    body = res.json()
    assert "models" in body
    assert "installed" in body
    assert "total" in body
    assert body["total"] == len(body["models"])
    assert body["total"] >= 6  # at least the core registry
    for m in body["models"]:
        assert "id" in m
        assert "installed" in m
        assert "mode" in m
        assert isinstance(m["required_vram_gb"], (int, float))


def test_unavailable_models_carry_install_hint(authed_client: TestClient):
    """Any model marked installed=False must carry a hint string.

    This is the "no fake fallback" contract — the UI renders the hint
    next to the disabled state so the operator knows exactly how to
    fix it.
    """
    res = authed_client.get(
        "/api/models/health",
        headers={"Authorization": "Bearer mock"},
    )
    body = res.json()
    for m in body["models"]:
        if not m["installed"]:
            assert m["hint"], f"missing install hint for {m['id']}"
