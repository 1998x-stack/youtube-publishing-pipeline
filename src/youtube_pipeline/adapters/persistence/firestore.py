"""Firestore-backed job repository for multiple Cloud Run Job invocations.

All allocation and state changes run inside Firestore transactions. A state
change writes a matching audit event atomically. Unknown upload outcomes
are never returned to the queue. Uses a custom transaction runner only in
unit tests; production always uses @firestore.transactional.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter

from youtube_pipeline.domain.jobs import Job, ManifestConflict
from youtube_pipeline.domain.models import Manifest
from youtube_pipeline.domain.states import State, require_transition

TransactionRunner = Callable[[Callable[[Any], Any]], Any]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def job_from_dict(data: dict[str, Any]) -> Job:
    return Job(
        job_id=data["job_id"],
        asset_key=data["asset_key"],
        source_type=data["source_type"],
        channel=data["channel"],
        manifest=data["manifest"],
        state=State(data["state"]),
        youtube_video_id=data.get("youtube_video_id"),
        attempt_count=data.get("attempt_count", 0),
        lease_owner=data.get("lease_owner"),
        lease_expires_at=data.get("lease_expires_at"),
        scheduled_at=data["scheduled_at"],
        last_error=data.get("last_error"),
    )


class FirestoreRepository:
    def __init__(
        self,
        client: Any | None = None,
        *,
        namespace: str = "ytp",
        run_transaction: TransactionRunner | None = None,
    ):
        if not namespace or len(namespace) > 32 or not namespace.replace("-", "").isalnum():
            raise ValueError("namespace must be 1–32 alphanumeric or hyphen characters")
        self.db = client or firestore.Client()
        self.jobs = self.db.collection(f"{namespace}_publish_jobs")
        self.events_collection = self.db.collection(f"{namespace}_job_events")
        self._runner = run_transaction or self._production_transaction

    def _production_transaction(self, callback: Callable[[Any], Any]) -> Any:
        @firestore.transactional
        def execute(transaction):
            return callback(transaction)

        return execute(self.db.transaction(max_attempts=5))

    def _event(self, tx, job_id: str, before: State | None, after: State,
               message: str | None) -> None:
        event = self.events_collection.document()
        tx.create(event, {
            "job_id": job_id, "old_state": before.value if before else None,
            "new_state": after.value, "event_time": now_iso(),
            "message": message,
        })

    def register(self, asset_key: str, source_type: str, manifest: Manifest) -> bool:
        manifest.assert_approved()
        if source_type not in ("local", "drive"):
            raise ValueError("invalid source type")
        ref = self.jobs.document(manifest.job_id)
        fingerprint = manifest.fingerprint()

        def insert(tx):
            snapshot = ref.get(transaction=tx)
            if snapshot.exists:
                old = snapshot.to_dict()
                if (old["fingerprint"] != fingerprint
                    or old["asset_key"] != asset_key
                    or old["source_type"] != source_type):
                    raise ManifestConflict(f"job_id {manifest.job_id} was changed")
                return False
            when = now_iso()
            tx.create(ref, {
                "job_id": manifest.job_id,
                "asset_key": asset_key,
                "source_type": source_type,
                "channel": manifest.channel,
                "manifest": manifest.data,
                "fingerprint": fingerprint,
                "state": State.QUEUED.value,
                "youtube_video_id": None,
                "attempt_count": 0,
                "lease_owner": None,
                "lease_expires_at": None,
                "scheduled_at": manifest.scheduled_at.isoformat(),
                "last_error": None,
                "created_at": when,
                "updated_at": when,
            })
            self._event(tx, manifest.job_id, None, State.QUEUED, "ingested")
            return True

        return self._runner(insert)

    def get(self, job_id: str) -> Job:
        doc = self.jobs.document(job_id).get()
        if not doc.exists:
            raise KeyError(job_id)
        return job_from_dict(doc.to_dict())

    def list_jobs(self, states: tuple[State, ...] | None = None) -> list[Job]:
        query = self.jobs
        if states:
            query = query.where(
                filter=FieldFilter("state", "in", [state.value for state in states])
            )
        return sorted(
            (job_from_dict(doc.to_dict()) for doc in query.stream()),
            key=lambda job: (job.scheduled_at, job.job_id),
        )

    def claim_next(self, owner: str, lease_seconds: int = 14400,
                   channel: str | None = None) -> Job | None:
        if not owner or lease_seconds <= 0:
            raise ValueError("invalid lease")
        query = self.jobs.where(filter=FieldFilter("state", "==", State.QUEUED.value))
        if channel:
            query = query.where(filter=FieldFilter("channel", "==", channel))
        query = query.order_by("scheduled_at").limit(30)
        # A separate transaction re-reads each candidate and compares its
        # latest state. Concurrent workers cannot both claim the same job.
        for candidate in query.stream():
            ref = candidate.reference

            def claim(tx):
                snapshot = ref.get(transaction=tx)
                if not snapshot.exists:
                    return None
                data = snapshot.to_dict()
                if data["state"] != State.QUEUED.value:
                    return None
                if channel and data["channel"] != channel:
                    return None
                expiration = (
                    datetime.now(timezone.utc) + timedelta(seconds=lease_seconds)
                ).isoformat()
                changes = {
                    "state": State.UPLOADING.value,
                    "attempt_count": data.get("attempt_count", 0) + 1,
                    "lease_owner": owner,
                    "lease_expires_at": expiration,
                    "updated_at": now_iso(),
                }
                tx.update(ref, changes)
                self._event(tx, data["job_id"], State.QUEUED, State.UPLOADING, owner)
                return job_from_dict({**data, **changes})

            result = self._runner(claim)
            if result is not None:
                return result
        return None

    def transition(
        self, job_id: str, to: State, *, video_id: str | None = None,
        error: str | None = None, owner: str | None = None,
    ) -> Job:
        ref = self.jobs.document(job_id)

        def update(tx):
            snapshot = ref.get(transaction=tx)
            if not snapshot.exists:
                raise KeyError(job_id)
            data = snapshot.to_dict()
            before = State(data["state"])
            require_transition(before, to)
            if before == State.UPLOADING:
                if not owner or owner != data.get("lease_owner"):
                    raise PermissionError("upload lease owner mismatch")
                if (data.get("lease_expires_at") is None
                    or data["lease_expires_at"] <= now_iso()):
                    raise PermissionError("upload lease expired; outcome requires review")
            if to == State.UPLOADED and not (video_id or data.get("youtube_video_id")):
                raise ValueError("UPLOADED requires youtube_video_id")
            changes = {
                "state": to.value,
                "youtube_video_id": video_id or data.get("youtube_video_id"),
                "last_error": error,
                "lease_owner": None,
                "lease_expires_at": None,
                "updated_at": now_iso(),
            }
            tx.update(ref, changes)
            self._event(tx, job_id, before, to, error)
            return job_from_dict({**data, **changes})

        return self._runner(update)

    def mark_expired_uploads_unknown(self) -> int:
        query = (
            self.jobs.where(filter=FieldFilter("state", "==", State.UPLOADING.value))
            .where(filter=FieldFilter("lease_expires_at", "<", now_iso()))
        )
        count = 0
        for item in query.stream():
            def quarantine(tx):
                snapshot = item.reference.get(transaction=tx)
                if not snapshot.exists:
                    return False
                data = snapshot.to_dict()
                if (data["state"] != State.UPLOADING.value
                    or not data.get("lease_expires_at")
                    or data["lease_expires_at"] >= now_iso()):
                    return False
                tx.update(item.reference, {
                    "state": State.UNKNOWN_UPLOAD_RESULT.value,
                    "lease_owner": None,
                    "lease_expires_at": None,
                    "updated_at": now_iso(),
                    "last_error": "upload lease expired; inspect YouTube Studio",
                })
                self._event(tx, data["job_id"], State.UPLOADING,
                            State.UNKNOWN_UPLOAD_RESULT, "expired lease")
                return True
            count += int(self._runner(quarantine))
        return count

    def mark_stale_decorating_for_review(self, max_age_seconds: int = 7200) -> int:
        if max_age_seconds <= 0:
            raise ValueError("max_age_seconds must be positive")
        cutoff = (
            datetime.now(timezone.utc) - timedelta(seconds=max_age_seconds)
        ).isoformat()
        query = (
            self.jobs.where(filter=FieldFilter("state", "==", State.DECORATING.value))
            .where(filter=FieldFilter("updated_at", "<", cutoff))
        )
        count = 0
        for item in query.stream():
            def quarantine(tx):
                snapshot = item.reference.get(transaction=tx)
                if not snapshot.exists:
                    return False
                data = snapshot.to_dict()
                if (data["state"] != State.DECORATING.value
                    or data["updated_at"] >= cutoff):
                    return False
                tx.update(item.reference, {
                    "state": State.NEEDS_REVIEW.value,
                    "updated_at": now_iso(),
                    "last_error": "decoration/scheduling timed out; inspect YouTube video",
                })
                self._event(tx, data["job_id"], State.DECORATING,
                            State.NEEDS_REVIEW, "stale decoration")
                return True
            count += int(self._runner(quarantine))
        return count

    def events(self, job_id: str) -> list[dict[str, Any]]:
        query = self.events_collection.where(filter=FieldFilter("job_id", "==", job_id))
        return sorted(
            (doc.to_dict() for doc in query.stream()),
            key=lambda event: event["event_time"],
        )
