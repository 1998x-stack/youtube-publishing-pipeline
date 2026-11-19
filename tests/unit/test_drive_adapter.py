from __future__ import annotations

import json
from pathlib import Path

from youtube_pipeline.adapters.assets.drive import DriveAssetStore
from conftest import sample_manifest


class Call:
    def __init__(self, result):
        self.result = result

    def execute(self):
        return self.result


class Files:
    def list(self, **kwargs):
        query = kwargs["q"]
        if "'root' in parents" in query:
            if not kwargs["pageToken"]:
                return Call({"nextPageToken": "next", "files": [{
                    "id": "folder-a", "name": "A",
                    "mimeType": "application/vnd.google-apps.folder",
                }]})
            return Call({"files": []})
        if "'folder-a' in parents" in query:
            return Call({"files": [
                {"id": "manifest-id", "name": "manifest.json",
                 "mimeType": "application/json", "size": "500"},
                {"id": "video-id", "name": "video.mp4",
                 "mimeType": "video/mp4", "size": "12"},
            ]})
        return Call({"files": []})


class Drive:
    def files(self):
        return Files()


def test_drive_pagination_and_materialization(tmp_path, monkeypatch):
    store = DriveAssetStore(Drive(), "root")
    manifest = sample_manifest()
    def fake_download(file_id, dest):
        if file_id == "manifest-id":
            dest.write_text(json.dumps(manifest), encoding="utf-8")
        else:
            dest.write_bytes(b"FAKE_VIDEO")
    monkeypatch.setattr(store, "_download", fake_download)
    items = list(store.discover())
    assert len(items) == 1 and items[0][0] == "folder-a"
    files = store.materialize("folder-a", ["video.mp4"], Path(tmp_path))
    assert files["video.mp4"].read_bytes() == b"FAKE_VIDEO"
