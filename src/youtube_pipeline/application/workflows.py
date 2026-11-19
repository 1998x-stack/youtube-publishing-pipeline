"""Ingestion, upload and reconciliation orchestration."""
from __future__ import annotations

import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from youtube_pipeline.domain.models import Manifest, ManifestError
from youtube_pipeline.domain.states import State
from youtube_pipeline.adapters.persistence.sqlite import SQLiteRepository
from youtube_pipeline.ports.interfaces import AssetStore, Publisher


def ingest(store: AssetStore, repo: SQLiteRepository) -> dict[str, Any]:
    summary: dict[str, Any] = {"created": 0, "existing": 0, "skipped": 0, "errors": []}
    for asset_key, raw in store.discover():
        try:
            manifest = Manifest.parse(raw)
            if not all(raw[key] for key in ("ready", "review_approved", "rights_confirmed")):
                summary["skipped"] += 1
                continue
            created = repo.register(asset_key, store.source_type, manifest)
            summary["created" if created else "existing"] += 1
        except (ManifestError, ValueError, KeyError) as exc:
            summary["errors"].append({"asset": asset_key, "error": str(exc)})
    return summary


def upload_one(repo: SQLiteRepository, store: AssetStore,
               publisher: Publisher, *, worker_id: str,
               channel_alias: str) -> str | None:
    """One upload with fail-closed handling of ambiguous remote outcomes."""
    job = repo.claim_next(worker_id, channel=channel_alias)
    if job is None:
        return None
    if job.source_type != store.source_type:
        repo.transition(job.job_id, State.NEEDS_REVIEW, owner=worker_id,
                        error="job source does not match active asset store")
        return job.job_id
    manifest = Manifest.parse(job.manifest)
    if manifest.scheduled_at <= datetime.now(timezone.utc) + timedelta(hours=1):
        repo.transition(job.job_id, State.NEEDS_REVIEW, owner=worker_id,
                        error="not enough lead time before requested publication")
        return job.job_id
    try:
        with tempfile.TemporaryDirectory(prefix="ytp-upload-") as temp:
            files = store.materialize(
                job.asset_key, [manifest.data["video_file"]], Path(temp)
            )
            video = files[manifest.data["video_file"]]
            if video.stat().st_size == 0:
                raise ValueError("empty video file")
            # After this boundary any error can conceal a successful remote upload.
            try:
                video_id = publisher.upload_private(video, manifest.data)
            except Exception as exc:
                repo.transition(
                    job.job_id, State.UNKNOWN_UPLOAD_RESULT, owner=worker_id,
                    error=f"Upload outcome unknown: {type(exc).__name__}: {exc}",
                )
                return job.job_id
        repo.transition(job.job_id, State.UPLOADED, video_id=video_id, owner=worker_id)
    except Exception as exc:
        # Errors strictly before the remote call are safe but require review in P0.
        current = repo.get(job.job_id)
        if current.state == State.UPLOADING:
            repo.transition(job.job_id, State.NEEDS_REVIEW, owner=worker_id,
                            error=f"Preparation failed: {type(exc).__name__}: {exc}")
    return job.job_id


def reconcile(repo: SQLiteRepository, store: AssetStore,
              publisher: Publisher, *, channel_alias: str) -> dict[str, int]:
    summary = {"checked": 0, "processing": 0, "scheduled": 0, "published": 0,
               "needs_review": 0, "api_errors": 0}
    states = (State.UPLOADED, State.PROCESSING, State.SCHEDULED)
    for job in repo.list_jobs(states):
        if job.channel != channel_alias or job.source_type != store.source_type:
            continue
        summary["checked"] += 1
        video_id = job.youtube_video_id
        if not video_id:
            repo.transition(job.job_id, State.NEEDS_REVIEW, error="missing YouTube video ID")
            summary["needs_review"] += 1
            continue
        if job.state == State.SCHEDULED:
            try:
                visibility = publisher.privacy_status(video_id)
                if visibility == "public":
                    repo.transition(job.job_id, State.PUBLISHED)
                    summary["published"] += 1
                elif (datetime.fromisoformat(job.scheduled_at)
                      < datetime.now(timezone.utc) - timedelta(hours=1)):
                    repo.transition(job.job_id, State.NEEDS_REVIEW,
                                    error="video still private after scheduled publication")
                    summary["needs_review"] += 1
            except Exception:
                summary["api_errors"] += 1
            continue
        try:
            processing = publisher.processing_status(video_id)
        except Exception:
            summary["api_errors"] += 1
            continue
        if processing in ("failed", "terminated"):
            repo.transition(job.job_id, State.NEEDS_REVIEW,
                            error="YouTube processing failed")
            summary["needs_review"] += 1
            continue
        if processing != "succeeded":
            if job.state == State.UPLOADED:
                repo.transition(job.job_id, State.PROCESSING)
            summary["processing"] += 1
            continue
        target = datetime.fromisoformat(job.scheduled_at)
        if target <= datetime.now(timezone.utc) + timedelta(minutes=5):
            repo.transition(job.job_id, State.NEEDS_REVIEW,
                            error="publish_at is too close or expired")
            summary["needs_review"] += 1
            continue
        repo.transition(job.job_id, State.DECORATING)
        try:
            metadata = Manifest.parse(job.manifest)
            attachments = [name for key in ("thumbnail_file", "subtitle_file")
                           if (name := metadata.data.get(key))]
            with tempfile.TemporaryDirectory(prefix="ytp-decorate-") as temp:
                files = store.materialize(job.asset_key, attachments, Path(temp))
                publisher.decorate(video_id, job.manifest, files)
            publisher.set_schedule(video_id, target.isoformat(), job.manifest)
            repo.transition(job.job_id, State.SCHEDULED)
            summary["scheduled"] += 1
        except Exception as exc:
            repo.transition(job.job_id, State.NEEDS_REVIEW,
                            error=f"Decoration/scheduling requires review: {exc}")
            summary["needs_review"] += 1
    return summary
