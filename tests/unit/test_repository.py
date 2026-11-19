from __future__ import annotations

import sqlite3

import pytest

from youtube_pipeline.adapters.persistence.sqlite import (
    ManifestConflict, SQLiteRepository,
)
from youtube_pipeline.domain.models import Manifest
from youtube_pipeline.domain.states import State
from conftest import sample_manifest


def test_register_is_idempotent_and_changed_manifest_is_conflict(tmp_path):
    repo = SQLiteRepository(tmp_path / "jobs.db")
    raw = sample_manifest()
    assert repo.register("test-001", "local", Manifest.parse(raw)) is True
    assert repo.register("test-001", "local", Manifest.parse(raw)) is False
    modified = dict(raw, title="changed title")
    with pytest.raises(ManifestConflict):
        repo.register("test-001", "local", Manifest.parse(modified))
    assert len(repo.list_jobs()) == 1


def test_claim_and_owner_protection(tmp_path):
    repo = SQLiteRepository(tmp_path / "jobs.db")
    repo.register("test-001", "local", Manifest.parse(sample_manifest()))
    claimed = repo.claim_next("worker-a")
    assert claimed.state == State.UPLOADING
    assert repo.claim_next("worker-b") is None
    with pytest.raises(PermissionError):
        repo.transition("test-001", State.UPLOADED, owner="worker-b", video_id="abc")
    repo.transition("test-001", State.UPLOADED, owner="worker-a", video_id="abc")
    assert repo.get("test-001").youtube_video_id == "abc"
    assert repo.get("test-001").attempt_count == 1


def test_stale_upload_quarantined_not_retried(tmp_path):
    repo = SQLiteRepository(tmp_path / "jobs.db")
    repo.register("test-001", "local", Manifest.parse(sample_manifest()))
    repo.claim_next("dead-worker")
    with sqlite3.connect(repo.path) as db:
        db.execute(
            "UPDATE publish_jobs SET lease_expires_at=? WHERE job_id=?",
            ("2000-01-01T00:00:00+00:00", "test-001")
        )
    assert repo.mark_expired_uploads_unknown() == 1
    assert repo.get("test-001").state == State.UNKNOWN_UPLOAD_RESULT
    assert repo.claim_next("new-worker") is None


def test_forbidden_state_transition(tmp_path):
    repo = SQLiteRepository(tmp_path / "jobs.db")
    repo.register("test-001", "local", Manifest.parse(sample_manifest()))
    with pytest.raises(ValueError, match="illegal state"):
        repo.transition("test-001", State.PUBLISHED)
