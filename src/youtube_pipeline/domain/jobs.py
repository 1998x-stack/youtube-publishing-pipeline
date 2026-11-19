"""Shared job model and immutable-manifest conflict."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from youtube_pipeline.domain.states import State


class ManifestConflict(ValueError):
    """An existing job ID was reused with different content."""


@dataclass(frozen=True)
class Job:
    job_id: str
    asset_key: str
    source_type: str
    channel: str
    manifest: dict[str, Any]
    state: State
    youtube_video_id: str | None
    attempt_count: int
    lease_owner: str | None
    lease_expires_at: str | None
    scheduled_at: str
    last_error: str | None
