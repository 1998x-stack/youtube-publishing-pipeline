from __future__ import annotations

import json
from pathlib import Path

from youtube_pipeline.adapters.assets.local import LocalAssetStore
from youtube_pipeline.adapters.persistence.sqlite import SQLiteRepository
from youtube_pipeline.application.workflows import ingest, reconcile, upload_one
from youtube_pipeline.domain.states import State


class FakePublisher:
    def __init__(self):
        self.processing = "processing"
        self.visibility = "private"
        self.decorated = False
        self.scheduled = None
        self.uploads = 0

    def upload_private(self, video, manifest):
        assert Path(video).read_bytes().startswith(b"FAKE_MP4")
        self.uploads += 1
        return "youtube-test-video-1"

    def processing_status(self, video_id):
        return self.processing

    def decorate(self, video_id, manifest, files):
        assert files["cover.png"].is_file()
        assert files["captions.srt"].is_file()
        self.decorated = True

    def set_schedule(self, video_id, publish_at_utc):
        self.scheduled = publish_at_utc

    def privacy_status(self, video_id):
        return self.visibility


def test_end_to_end_without_external_api(ready_assets, tmp_path):
    repo = SQLiteRepository(tmp_path / "state.sqlite3")
    store = LocalAssetStore(ready_assets)
    pub = FakePublisher()

    assert ingest(store, repo)["created"] == 1
    assert ingest(store, repo)["existing"] == 1
    assert upload_one(repo, store, pub, worker_id="test", channel_alias="main") == "test-001"
    assert repo.get("test-001").state == State.UPLOADED
    assert upload_one(repo, store, pub, worker_id="test", channel_alias="main") is None
    assert pub.uploads == 1

    assert reconcile(repo, store, pub, channel_alias="main")["processing"] == 1
    assert repo.get("test-001").state == State.PROCESSING
    pub.processing = "succeeded"
    assert reconcile(repo, store, pub, channel_alias="main")["scheduled"] == 1
    assert pub.decorated
    assert pub.scheduled
    assert repo.get("test-001").state == State.SCHEDULED
    pub.visibility = "public"
    assert reconcile(repo, store, pub, channel_alias="main")["published"] == 1
    assert repo.get("test-001").state == State.PUBLISHED
    assert len(repo.events("test-001")) >= 6


def test_unknown_upload_outcome_never_retries(ready_assets, tmp_path):
    repo = SQLiteRepository(tmp_path / "state.sqlite3")
    store = LocalAssetStore(ready_assets)
    ingest(store, repo)

    class BrokenPublisher(FakePublisher):
        def upload_private(self, video, manifest):
            raise ConnectionError("connection dropped after upload request")

    pub = BrokenPublisher()
    upload_one(repo, store, pub, worker_id="test", channel_alias="main")
    assert repo.get("test-001").state == State.UNKNOWN_UPLOAD_RESULT
    assert upload_one(repo, store, pub, worker_id="test", channel_alias="main") is None


def test_unapproved_asset_skipped(ready_assets, tmp_path):
    path = ready_assets / "test-001" / "manifest.json"
    data = json.loads(path.read_text())
    data["review_approved"] = False
    path.write_text(json.dumps(data))
    repo = SQLiteRepository(tmp_path / "state.sqlite3")
    result = ingest(LocalAssetStore(ready_assets), repo)
    assert result["skipped"] == 1
    assert repo.list_jobs() == []
