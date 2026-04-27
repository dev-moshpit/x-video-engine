"""Worker R2 upload tests (PR 7) — moto mocks S3."""

from __future__ import annotations

import os
from pathlib import Path

import boto3
import pytest
from moto import mock_aws

from apps.worker import storage as worker_storage


@pytest.fixture
def moto_s3_client():
    """Spin up a moto-mocked S3, install it on the worker module."""
    with mock_aws():
        os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
        client = boto3.client("s3", region_name="us-east-1")
        worker_storage.set_s3_client(client)
        yield client
        worker_storage.set_s3_client(None)


def test_upload_render_mp4_creates_bucket_and_uploads(
    moto_s3_client, tmp_path: Path,
):
    fake = tmp_path / "final.mp4"
    fake.write_bytes(b"FAKE_MP4_BYTES" * 1000)

    url = worker_storage.upload_render_mp4(
        fake, user_id="user_alice", job_id="job_abc",
    )

    assert url.endswith("renders/user_alice/job_abc.mp4")

    obj = moto_s3_client.get_object(
        Bucket=worker_storage.R2_BUCKET,
        Key="renders/user_alice/job_abc.mp4",
    )
    assert obj["ContentType"] == "video/mp4"
    assert obj["ContentLength"] > 1000


def test_upload_missing_local_file_raises(moto_s3_client, tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        worker_storage.upload_render_mp4(
            tmp_path / "does_not_exist.mp4",
            user_id="u", job_id="j",
        )


def test_render_key_format():
    assert worker_storage.render_key_for("user_alice", "job_abc") == (
        "renders/user_alice/job_abc.mp4"
    )
