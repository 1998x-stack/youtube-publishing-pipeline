from __future__ import annotations

import pytest

from youtube_pipeline.domain.models import Manifest, ManifestError
from conftest import sample_manifest


def test_accepts_utc_offset():
    manifest = sample_manifest()
    manifest["publish_at"] = "2030-12-31T19:00:00+08:00"
    assert Manifest.parse(manifest).scheduled_at.isoformat() == "2030-12-31T11:00:00+00:00"


@pytest.mark.parametrize("bad", ["../secret.txt", "/root/file.mp4", ".", ".."])
def test_rejects_unsafe_paths(bad):
    manifest = sample_manifest()
    manifest["video_file"] = bad
    with pytest.raises(ManifestError):
        Manifest.parse(manifest)


def test_refuses_unapproved():
    manifest = sample_manifest()
    manifest["rights_confirmed"] = False
    with pytest.raises(ManifestError, match="rights_confirmed"):
        Manifest.parse(manifest).assert_approved()


def test_timezone_required():
    manifest = sample_manifest()
    manifest["publish_at"] = "2030-01-01T12:00:00"
    with pytest.raises(ManifestError):
        Manifest.parse(manifest)


def test_unknown_manifest_fields_rejected():
    manifest = sample_manifest()
    manifest["oauth_token"] = "should-never-be-in-manifest"
    with pytest.raises(ManifestError):
        Manifest.parse(manifest)
