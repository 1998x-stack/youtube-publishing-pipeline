from __future__ import annotations

import json

import pytest

from youtube_pipeline.producer.colab_export import export_to_mounted_drive


def test_manifest_written_after_media(ready_assets, tmp_path):
    dest = export_to_mounted_drive(ready_assets / "test-001", tmp_path / "drive")
    assert (dest / "video.mp4").read_bytes().startswith(b"FAKE_MP4")
    assert json.loads((dest / "manifest.json").read_text())["ready"] is True
    with pytest.raises(FileExistsError):
        export_to_mounted_drive(ready_assets / "test-001", tmp_path / "drive")


def test_never_exports_unapproved_asset(ready_assets, tmp_path):
    source = ready_assets / "test-001"
    path = source / "manifest.json"
    manifest = json.loads(path.read_text())
    manifest["review_approved"] = False
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="review_approved"):
        export_to_mounted_drive(source, tmp_path / "drive")
    assert not (tmp_path / "drive" / "test-001").exists()
