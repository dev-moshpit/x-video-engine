"""Worker queue + status writer tests (PR 6)."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

import fakeredis
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

# Use sqlite in-memory for the worker tests too. Set BEFORE worker
# modules import so DATABASE_URL is picked up by their lazy engines.
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

# Ensure the api package is importable so we can build the schema
# via Base.metadata (the worker uses raw SQL but the schema needs to
# exist somewhere — easiest is to lean on the api's ORM models).
_API_ROOT = Path(__file__).resolve().parents[2] / "apps" / "api"
if str(_API_ROOT) not in sys.path:
    sys.path.insert(0, str(_API_ROOT))


from apps.worker import queue as worker_queue  # noqa: E402
from apps.worker.schemas import RenderJobRequest, RenderStage  # noqa: E402


@pytest.fixture
def fake_redis():
    r = fakeredis.FakeRedis(decode_responses=True)
    worker_queue.set_redis(r)
    yield r
    worker_queue.set_redis(None)


@pytest.fixture
def shared_engine():
    """Sqlite engine the api models AND the worker queue share."""
    eng = create_engine(
        "sqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    # Build schema via api's ORM models
    from app.db.base import Base
    from app.db import models  # noqa: F401  — register tables
    Base.metadata.create_all(eng)

    worker_queue.set_engine(eng)
    yield eng
    worker_queue.set_engine(None)
    Base.metadata.drop_all(eng)


def _seed_render(engine, *, job_id: str, project_id: str, user_id: str):
    """Insert minimal user/project/render rows so we can update by job_id."""
    import uuid as _uuid
    from datetime import datetime, timezone
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO users (id, clerk_user_id, tier, created_at) "
                "VALUES (:id, :cuid, 'free', :now)"
            ),
            {"id": user_id, "cuid": "cuid_" + user_id[:8],
             "now": datetime.now(timezone.utc)},
        )
        conn.execute(
            text(
                "INSERT INTO projects (id, user_id, template, name, "
                "template_input, created_at, updated_at) "
                "VALUES (:id, :uid, 'ai_story', 'p', '{}', :now, :now)"
            ),
            {"id": project_id, "uid": user_id,
             "now": datetime.now(timezone.utc)},
        )
        conn.execute(
            text(
                "INSERT INTO renders (id, project_id, job_id, stage, "
                "progress, started_at) "
                "VALUES (:id, :pid, :job, 'pending', 0.0, :now)"
            ),
            {"id": str(_uuid.uuid4()), "pid": project_id, "job": job_id,
             "now": datetime.now(timezone.utc)},
        )


def test_consume_one_returns_none_on_empty_queue(fake_redis):
    res = worker_queue.consume_one(timeout_sec=1)
    assert res is None


def test_consume_one_pops_a_job(fake_redis):
    req = RenderJobRequest(
        job_id="abc", user_id="u1", project_id="p1",
        template="ai_story", template_input={"prompt": "x"},
    )
    fake_redis.rpush("saas:render:jobs", req.model_dump_json())

    out = worker_queue.consume_one(timeout_sec=1)
    assert out is not None
    assert out.job_id == "abc"
    assert out.template == "ai_story"


def test_update_render_status_changes_stage(fake_redis, shared_engine):
    import uuid as _uuid
    user_id = str(_uuid.uuid4())
    project_id = str(_uuid.uuid4())
    job_id = "job_test_1"
    _seed_render(shared_engine, job_id=job_id, project_id=project_id, user_id=user_id)

    worker_queue.mark_stage(job_id, RenderStage.RENDERING, progress=0.10)
    worker_queue.mark_stage(job_id, RenderStage.COMPLETE, progress=1.0)

    with shared_engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT stage, progress, completed_at FROM renders "
                "WHERE job_id = :j"
            ),
            {"j": job_id},
        ).one()
    assert row.stage == "complete"
    assert row.progress == 1.0
    assert row.completed_at is not None


def test_update_render_status_records_error(fake_redis, shared_engine):
    import uuid as _uuid
    user_id = str(_uuid.uuid4())
    project_id = str(_uuid.uuid4())
    job_id = "job_test_err"
    _seed_render(shared_engine, job_id=job_id, project_id=project_id, user_id=user_id)

    worker_queue.update_render_status(
        job_id,
        stage=RenderStage.FAILED.value,
        error="ValueError: bad template_input",
        set_completed_now=True,
    )
    with shared_engine.connect() as conn:
        row = conn.execute(
            text("SELECT stage, error FROM renders WHERE job_id = :j"),
            {"j": job_id},
        ).one()
    assert row.stage == "failed"
    assert "ValueError" in row.error


def test_run_one_job_dispatches_and_marks_complete(fake_redis, shared_engine, tmp_path):
    """End-to-end of the worker loop with mocked render adapter."""
    import uuid as _uuid

    # Seed a render row so the status updates target an existing one.
    user_id = str(_uuid.uuid4())
    project_id = str(_uuid.uuid4())
    job_id = "job_dispatch_ok"
    _seed_render(shared_engine, job_id=job_id, project_id=project_id, user_id=user_id)

    fake_mp4 = tmp_path / "fake.mp4"
    fake_mp4.write_bytes(b"x" * 32_000)

    from apps.worker import main as worker_main
    # Mock both the heavy adapter and the R2 upload — those are
    # exercised in their own test files (dispatcher / storage).
    with patch.object(worker_main, "WORK_ROOT", tmp_path), \
         patch.object(worker_main, "render_for_template", return_value=fake_mp4), \
         patch.object(
             worker_main, "upload_render_mp4",
             return_value="http://example.invalid/foo/job_dispatch_ok.mp4",
         ):
        req = RenderJobRequest(
            job_id=job_id, user_id="u", project_id=project_id,
            template="ai_story",
            template_input={
                "prompt": "Make a real test video about discipline.",
            },
        )
        worker_main.run_one_job(req)

    with shared_engine.connect() as conn:
        row = conn.execute(
            text("SELECT stage, progress, final_mp4_url, completed_at "
                  "FROM renders WHERE job_id=:j"),
            {"j": job_id},
        ).one()
    assert row.stage == "complete"
    assert row.progress == 1.0
    assert row.final_mp4_url == "http://example.invalid/foo/job_dispatch_ok.mp4"
    assert row.completed_at is not None


def test_run_one_job_marks_failed_on_exception(fake_redis, shared_engine, tmp_path):
    import uuid as _uuid
    user_id = str(_uuid.uuid4())
    project_id = str(_uuid.uuid4())
    job_id = "job_dispatch_err"
    _seed_render(shared_engine, job_id=job_id, project_id=project_id, user_id=user_id)

    from apps.worker import main as worker_main

    def _boom(*a, **k):
        raise ValueError("synthetic adapter failure")

    with patch.object(worker_main, "WORK_ROOT", tmp_path), \
         patch.object(worker_main, "render_for_template", side_effect=_boom):
        req = RenderJobRequest(
            job_id=job_id, user_id="u", project_id=project_id,
            template="ai_story",
            template_input={"prompt": "Won't matter, the adapter will throw."},
        )
        worker_main.run_one_job(req)

    with shared_engine.connect() as conn:
        row = conn.execute(
            text("SELECT stage, error FROM renders WHERE job_id=:j"),
            {"j": job_id},
        ).one()
    assert row.stage == "failed"
    assert "synthetic adapter failure" in row.error


# ─── Schema parity ──────────────────────────────────────────────────────

def test_render_schema_parity_with_api():
    from app.schemas.render import (
        RenderJobRequest as APIReq,
        RenderJobStatus as APIStatus,
        RenderStage as APIStage,
    )
    assert (
        RenderJobRequest.model_json_schema() == APIReq.model_json_schema()
    )
    assert (
        worker_queue.RenderJobRequest.__name__
        == APIReq.__name__
    )
    # Worker copy of RenderStage should have the same members.
    assert {s.value for s in RenderStage} == {s.value for s in APIStage}
