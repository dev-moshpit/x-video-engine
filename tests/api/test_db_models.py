"""SQLAlchemy ORM model smoke tests (PR 3).

Uses the sqlite in-memory engine wired by the conftest. Verifies the
five tables can be created, inserted into, joined across relationships,
and that template_input round-trips JSON.
"""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.models import Project, Render, Usage, User, VideoPlan
from app.db.session import SessionLocal, engine


@pytest.fixture
def db():
    """Fresh schema per test — drop on teardown."""
    Base.metadata.create_all(engine)
    session: Session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)


def test_user_inserts_with_defaults(db: Session):
    user = User(clerk_user_id="user_alpha", email="alpha@example.com")
    db.add(user)
    db.commit()
    db.refresh(user)

    assert user.id is not None
    assert user.tier == "free"
    assert user.created_at is not None


def test_clerk_user_id_is_unique(db: Session):
    db.add(User(clerk_user_id="user_dup"))
    db.commit()
    db.add(User(clerk_user_id="user_dup"))
    with pytest.raises(Exception):
        db.commit()


def test_project_round_trips_json_template_input(db: Session):
    user = User(clerk_user_id="user_beta")
    db.add(user)
    db.commit()

    project = Project(
        user_id=user.id,
        template="ai_story",
        name="My first short",
        template_input={"prompt": "a cinematic story", "duration": 20.0},
    )
    db.add(project)
    db.commit()
    db.refresh(project)

    assert project.template_input == {
        "prompt": "a cinematic story",
        "duration": 20.0,
    }
    assert project.user.clerk_user_id == "user_beta"


def test_full_chain_user_to_video_plan(db: Session):
    user = User(clerk_user_id="user_gamma")
    db.add(user); db.commit()
    project = Project(user_id=user.id, template="reddit_story", name="x")
    db.add(project); db.commit()
    render = Render(project_id=project.id, job_id="job_full_chain")
    db.add(render); db.commit()
    plan = VideoPlan(
        render_id=render.id,
        plan_json={"hook": "h", "scenes": []},
        score_json={"total": 73.5},
        prompt_hash="abc123",
        seed=42,
    )
    db.add(plan); db.commit()

    assert render.video_plan is not None
    assert render.video_plan.id == plan.id
    assert plan.render.project.user.clerk_user_id == "user_gamma"
    assert plan.score_json == {"total": 73.5}


def test_render_job_id_is_unique(db: Session):
    user = User(clerk_user_id="user_delta")
    db.add(user); db.commit()
    project = Project(user_id=user.id, template="voiceover", name="x")
    db.add(project); db.commit()

    db.add(Render(project_id=project.id, job_id="job_unique"))
    db.commit()
    db.add(Render(project_id=project.id, job_id="job_unique"))
    with pytest.raises(Exception):
        db.commit()


def test_usage_event_records(db: Session):
    user = User(clerk_user_id="user_epsilon")
    db.add(user); db.commit()
    db.add(Usage(user_id=user.id, kind="render_seconds", value=42.5))
    db.add(Usage(user_id=user.id, kind="exports", value=1))
    db.commit()

    assert len(user.usage) == 2
    kinds = sorted(u.kind for u in user.usage)
    assert kinds == ["exports", "render_seconds"]
