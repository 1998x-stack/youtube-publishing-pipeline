"""Validated publishing manifests and job records."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from jsonschema import Draft202012Validator, FormatChecker

SCHEMA = (
    Path(__file__).resolve().parents[1] / "contracts" / "manifest.schema.json"
)


class ManifestError(ValueError):
    """Manifest is not fit to be ingested."""


@dataclass(frozen=True)
class Manifest:
    data: dict[str, Any]

    @classmethod
    def parse(cls, raw: Mapping[str, Any]) -> "Manifest":
        data = dict(raw)
        try:
            schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
            Draft202012Validator(schema, format_checker=FormatChecker()).validate(data)
        except Exception as exc:
            raise ManifestError(str(exc)) from exc
        for key in ("video_file", "thumbnail_file", "subtitle_file"):
            if key in data and data[key] in (".", ".."):
                raise ManifestError(f"unsafe filename: {key}")
        dt = datetime.fromisoformat(data["publish_at"].replace("Z", "+00:00"))
        if dt.tzinfo is None or dt.utcoffset() is None:
            raise ManifestError("publish_at must have an explicit UTC offset")
        return cls(data)

    @property
    def job_id(self) -> str:
        return self.data["job_id"]

    @property
    def channel(self) -> str:
        return self.data["target_channel"]

    @property
    def scheduled_at(self) -> datetime:
        return datetime.fromisoformat(
            self.data["publish_at"].replace("Z", "+00:00")
        ).astimezone(timezone.utc)

    @property
    def file_names(self) -> list[str]:
        return [
            self.data[key]
            for key in ("video_file", "thumbnail_file", "subtitle_file")
            if self.data.get(key)
        ]

    def assert_approved(self) -> None:
        for key in ("ready", "review_approved", "rights_confirmed"):
            if self.data[key] is not True:
                raise ManifestError(f"{key} must be true before publishing")

    def fingerprint(self) -> str:
        import hashlib
        raw = json.dumps(self.data, sort_keys=True, ensure_ascii=False).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()
