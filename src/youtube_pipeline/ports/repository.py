"""Repository operations shared by local and distributed runtimes."""
from __future__ import annotations

from typing import Any, Protocol

from youtube_pipeline.domain.jobs import Job
from youtube_pipeline.domain.models import Manifest
from youtube_pipeline.domain.states import State


class JobRepository(Protocol):
    def register(self, asset_key: str, source_type: str, manifest: Manifest) -> bool: ...

    def get(self, job_id: str) -> Job: ...

    def list_jobs(self, states: tuple[State, ...] | None = None) -> list[Job]: ...

    def claim_next(
        self, owner: str, lease_seconds: int = 14400, channel: str | None = None
    ) -> Job | None: ...

    def transition(
        self, job_id: str, to: State, *, video_id: str | None = None,
        error: str | None = None, owner: str | None = None,
    ) -> Job: ...

    def mark_expired_uploads_unknown(self) -> int: ...

    def mark_stale_decorating_for_review(self, max_age_seconds: int = 7200) -> int: ...

    def events(self, job_id: str) -> list[dict[str, Any]]: ...
