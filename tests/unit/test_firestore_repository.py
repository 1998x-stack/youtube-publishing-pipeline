"""Offline Firestore transaction contract tests.

The fake client models document and transaction operations, not actual
Firestore isolation. Real distributed concurrency needs emulator/cloud E2E.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from itertools import count

import pytest
from conftest import sample_manifest

from youtube_pipeline.adapters.persistence.firestore import FirestoreRepository
from youtube_pipeline.domain.jobs import ManifestConflict
from youtube_pipeline.domain.models import Manifest
from youtube_pipeline.domain.states import State


class FakeSnapshot:
    def __init__(self, reference, data):
        self.reference = reference
        self.exists = data is not None
        self.data = deepcopy(data)

    def to_dict(self):
        return deepcopy(self.data)


class FakeDoc:
    def __init__(self, db, collection, id_):
        self.db, self.collection, self.id = db, collection, id_

    def get(self, transaction=None):
        return FakeSnapshot(
            self, self.db.data.get(self.collection, {}).get(self.id)
        )


class FakeQuery:
    def __init__(self, db, collection):
        self.db, self.collection = db, collection
        self.filters = []
        self.sort_field = None
        self.max_items = None

    def where(self, *, filter):
        self.filters.append(filter)
        return self

    def order_by(self, field):
        self.sort_field = field
        return self

    def limit(self, amount):
        self.max_items = amount
        return self

    def stream(self):
        pairs = list(self.db.data.get(self.collection, {}).items())
        for f in self.filters:
            field, op, target = f.field_path, f.op_string, f.value
            if op == "==":
                pairs = [(id_, d) for id_, d in pairs if d.get(field) == target]
            elif op == "in":
                pairs = [(id_, d) for id_, d in pairs if d.get(field) in target]
            elif op == "<":
                pairs = [(id_, d) for id_, d in pairs if d.get(field) is not None
                         and d[field] < target]
            else:
                raise ValueError(f"Unsupported fake filter {op}")
        if self.sort_field:
            pairs.sort(key=lambda x: x[1][self.sort_field])
        if self.max_items is not None:
            pairs = pairs[:self.max_items]
        return [
            FakeSnapshot(FakeDoc(self.db, self.collection, id_), data)
            for id_, data in pairs
        ]


class FakeCollection(FakeQuery):
    def document(self, id_=None):
        return FakeDoc(
            self.db, self.collection, id_ or f"auto-{next(self.db.counter)}"
        )


class FakeTransaction:
    def __init__(self, db):
        self.db = db

    def create(self, ref, data):
        collection = self.db.data.setdefault(ref.collection, {})
        if ref.id in collection:
            raise ValueError("document exists")
        collection[ref.id] = deepcopy(data)

    def update(self, ref, changes):
        self.db.data[ref.collection][ref.id].update(deepcopy(changes))


class FakeClient:
    def __init__(self):
        self.data = {}
        self.counter = count(1)

    def collection(self, name):
        return FakeCollection(self, name)


@pytest.fixture
def fstore():
    client = FakeClient()
    repo = FirestoreRepository(
        client=client,
        run_transaction=lambda action: action(FakeTransaction(client)),
    )
    return repo, client


def test_fingerprint_immutable_claim_and_owner(fstore):
    repo, _ = fstore
    raw = sample_manifest()
    m = Manifest.parse(raw)
    assert repo.register("folder-id", "drive", m)
    assert repo.register("folder-id", "drive", m) is False
    with pytest.raises(ManifestConflict):
        repo.register(
            "folder-id", "drive", Manifest.parse(dict(raw, title="other title"))
        )
    claim = repo.claim_next("worker-uuid", channel="main")
    assert claim.state == State.UPLOADING
    assert claim.attempt_count == 1
    assert repo.claim_next("other-worker", channel="main") is None
    with pytest.raises(PermissionError, match="owner"):
        repo.transition(claim.job_id, State.UPLOADED, owner="other-worker",
                        video_id="youtube-video-id")
    job = repo.transition(claim.job_id, State.UPLOADED, owner="worker-uuid",
                          video_id="youtube-video-id")
    assert job.youtube_video_id == "youtube-video-id"
    assert repo.events(job.job_id)[-1]["new_state"] == State.UPLOADED


def test_expired_upload_is_quarantined(fstore):
    repo, client = fstore
    repo.register("folder", "drive", Manifest.parse(sample_manifest()))
    repo.claim_next("worker-uuid")
    client.data["ytp_publish_jobs"]["test-001"]["lease_expires_at"] = (
        datetime.now(timezone.utc) - timedelta(hours=1)
    ).isoformat()
    assert repo.mark_expired_uploads_unknown() == 1
    assert repo.get("test-001").state == State.UNKNOWN_UPLOAD_RESULT
    assert repo.claim_next("new-worker") is None


def test_stale_decoration_is_quarantined(fstore):
    repo, client = fstore
    repo.register("folder", "drive", Manifest.parse(sample_manifest()))
    repo.claim_next("worker-uuid")
    repo.transition("test-001", State.UPLOADED, video_id="id", owner="worker-uuid")
    repo.transition("test-001", State.DECORATING)
    client.data["ytp_publish_jobs"]["test-001"]["updated_at"] = (
        datetime.now(timezone.utc) - timedelta(hours=3)
    ).isoformat()
    assert repo.mark_stale_decorating_for_review() == 1
    assert repo.get("test-001").state == State.NEEDS_REVIEW
    assert repo.mark_stale_decorating_for_review() == 0


def test_reject_illegal_transition_and_wrong_channel(fstore):
    repo, _ = fstore
    repo.register("folder", "drive", Manifest.parse(sample_manifest()))
    assert repo.claim_next("wrong", channel="other") is None
    with pytest.raises(ValueError, match="illegal state"):
        repo.transition("test-001", State.PUBLISHED)
    assert len(repo.list_jobs((State.QUEUED,))) == 1
