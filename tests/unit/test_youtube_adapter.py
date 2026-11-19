from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from youtube_pipeline.adapters.youtube.client import YouTubePublisher
from conftest import sample_manifest


class Call:
    def __init__(self, result):
        self.result = result

    def execute(self):
        return self.result

    def next_chunk(self):
        return None, self.result


class Videos:
    def __init__(self):
        self.upload_body = None
        self.schedule_body = None

    def insert(self, **kwargs):
        self.upload_body = kwargs["body"]
        return Call({"id": "video-test-id"})

    def list(self, **kwargs):
        if "processingDetails" in kwargs["part"]:
            return Call({"items": [{
                "status": {"uploadStatus": "uploaded", "privacyStatus": "private"},
                "processingDetails": {"processingStatus": "succeeded"},
            }]})
        return Call({"items": [{"status": {"privacyStatus": "private"}}]})

    def update(self, **kwargs):
        self.schedule_body = kwargs["body"]
        return Call({"id": "video-test-id"})


class Channels:
    def list(self, **kwargs):
        return Call({"items": [{"id": "UC_expected"}]})


class Service:
    def __init__(self):
        self.video_api = Videos()

    def videos(self):
        return self.video_api

    def channels(self):
        return Channels()


def test_private_upload_disclosures_and_schedule(tmp_path):
    service = Service()
    publisher = YouTubePublisher(service)
    publisher.verify_channel("UC_expected")
    with pytest.raises(PermissionError):
        publisher.verify_channel("UC_wrong")
    video = tmp_path / "video.mp4"
    video.write_bytes(b"TEST_ONLY")
    manifest = sample_manifest()
    manifest["made_for_kids"] = True
    manifest["contains_synthetic_media"] = True
    assert publisher.upload_private(video, manifest) == "video-test-id"
    status = service.video_api.upload_body["status"]
    assert status["privacyStatus"] == "private"
    assert status["selfDeclaredMadeForKids"] is True
    assert status["containsSyntheticMedia"] is True
    assert publisher.processing_status("video-test-id") == "succeeded"
    due = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
    publisher.set_schedule("video-test-id", due, manifest)
    scheduled = service.video_api.schedule_body["status"]
    assert scheduled["privacyStatus"] == "private"
    assert scheduled["selfDeclaredMadeForKids"] is True
    assert scheduled["containsSyntheticMedia"] is True
    assert scheduled["publishAt"].endswith("Z")


def test_refuses_expired_schedule():
    publisher = YouTubePublisher(Service())
    due = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    with pytest.raises(ValueError):
        publisher.set_schedule("video-test-id", due, sample_manifest())
