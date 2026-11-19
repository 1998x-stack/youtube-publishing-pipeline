"""SQLite local/one-worker reference implementation; never store OAuth secrets here."""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from youtube_pipeline.domain.models import Manifest
from youtube_pipeline.domain.states import State, require_transition


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def stamp() -> str:
    return utcnow().isoformat()


class ManifestConflict(ValueError):
    """A job ID was reused with different content; explicit review is required."""


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


class SQLiteRepository:
    """BEGIN IMMEDIATE prevents two SQLite workers from claiming one job."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS publish_jobs (
                    job_id TEXT PRIMARY KEY,
                    asset_key TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    channel TEXT NOT NULL,
                    manifest_json TEXT NOT NULL,
                    fingerprint TEXT NOT NULL,
                    state TEXT NOT NULL,
                    youtube_video_id TEXT,
                    attempt_count INTEGER NOT NULL DEFAULT 0,
                    lease_owner TEXT,
                    lease_expires_at TEXT,
                    scheduled_at TEXT NOT NULL,
                    last_error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS job_events (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT NOT NULL,
                    old_state TEXT,
                    new_state TEXT NOT NULL,
                    event_time TEXT NOT NULL,
                    message TEXT,
                    FOREIGN KEY(job_id) REFERENCES publish_jobs(job_id)
                );
                CREATE INDEX IF NOT EXISTS idx_jobs_state_schedule
                    ON publish_jobs(state, scheduled_at);
            """)

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA busy_timeout=30000")
        db.execute("PRAGMA foreign_keys=ON")
        return db

    @staticmethod
    def _job(row: sqlite3.Row) -> Job:
        return Job(
            job_id=row["job_id"], asset_key=row["asset_key"],
            source_type=row["source_type"], channel=row["channel"],
            manifest=json.loads(row["manifest_json"]),
            state=State(row["state"]), youtube_video_id=row["youtube_video_id"],
            attempt_count=row["attempt_count"], lease_owner=row["lease_owner"],
            lease_expires_at=row["lease_expires_at"],
            scheduled_at=row["scheduled_at"], last_error=row["last_error"],
        )

    def register(self, asset_key: str, source_type: str, manifest: Manifest) -> bool:
        manifest.assert_approved()
        if source_type not in ("local", "drive"):
            raise ValueError("invalid source type")
        now = stamp()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute(
                "SELECT fingerprint, asset_key, source_type FROM publish_jobs WHERE job_id=?",
                (manifest.job_id,),
            ).fetchone()
            if existing:
                if (existing["fingerprint"] != manifest.fingerprint()
                    or existing["asset_key"] != asset_key
                    or existing["source_type"] != source_type):
                    raise ManifestConflict(f"job_id {manifest.job_id} was changed")
                return False
            db.execute("""
                INSERT INTO publish_jobs(
                    job_id, asset_key, source_type, channel, manifest_json, fingerprint,
                    state, scheduled_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                manifest.job_id, asset_key, source_type, manifest.channel,
                json.dumps(manifest.data, ensure_ascii=False), manifest.fingerprint(),
                State.QUEUED, manifest.scheduled_at.isoformat(), now, now,
            ))
            self._event(db, manifest.job_id, None, State.QUEUED, "ingested")
            return True

    @staticmethod
    def _event(db: sqlite3.Connection, job_id: str, before: State | None,
               after: State, message: str | None) -> None:
        db.execute("""
            INSERT INTO job_events(job_id, old_state, new_state, event_time, message)
            VALUES (?, ?, ?, ?, ?)
        """, (job_id, before, after, stamp(), message))

    def get(self, job_id: str) -> Job:
        with self._connect() as db:
            row = db.execute(
                "SELECT * FROM publish_jobs WHERE job_id=?", (job_id,)
            ).fetchone()
        if not row:
            raise KeyError(job_id)
        return self._job(row)

    def list_jobs(self, states: tuple[State, ...] | None = None) -> list[Job]:
        with self._connect() as db:
            if states:
                marks = ",".join("?" for _ in states)
                rows = db.execute(
                    f"SELECT * FROM publish_jobs WHERE state IN ({marks}) "
                    "ORDER BY scheduled_at, job_id", tuple(states)
                ).fetchall()
            else:
                rows = db.execute(
                    "SELECT * FROM publish_jobs ORDER BY scheduled_at, job_id"
                ).fetchall()
        return [self._job(r) for r in rows]

    def claim_next(self, owner: str, lease_seconds: int = 14400,
                   channel: str | None = None) -> Job | None:
        if not owner or lease_seconds <= 0:
            raise ValueError("invalid lease")
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if channel:
                row = db.execute("""
                    SELECT * FROM publish_jobs WHERE state=? AND channel=?
                    ORDER BY scheduled_at, job_id LIMIT 1
                """, (State.QUEUED, channel)).fetchone()
            else:
                row = db.execute("""
                    SELECT * FROM publish_jobs WHERE state=?
                    ORDER BY scheduled_at, job_id LIMIT 1
                """, (State.QUEUED,)).fetchone()
            if not row:
                return None
            expiry = (utcnow() + timedelta(seconds=lease_seconds)).isoformat()
            db.execute("""
                UPDATE publish_jobs SET state=?, attempt_count=attempt_count+1,
                lease_owner=?, lease_expires_at=?, updated_at=?
                WHERE job_id=? AND state=?
            """, (State.UPLOADING, owner, expiry, stamp(), row["job_id"], State.QUEUED))
            self._event(db, row["job_id"], State.QUEUED, State.UPLOADING, owner)
            updated = db.execute(
                "SELECT * FROM publish_jobs WHERE job_id=?", (row["job_id"],)
            ).fetchone()
            return self._job(updated)

    def transition(self, job_id: str, to: State, *,
                   video_id: str | None = None, error: str | None = None,
                   owner: str | None = None) -> Job:
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT * FROM publish_jobs WHERE job_id=?", (job_id,)
            ).fetchone()
            if row is None:
                raise KeyError(job_id)
            before = State(row["state"])
            require_transition(before, to)
            if before == State.UPLOADING and owner != row["lease_owner"]:
                raise PermissionError("upload lease owner mismatch")
            if to == State.UPLOADED and not (video_id or row["youtube_video_id"]):
                raise ValueError("UPLOADED requires youtube_video_id")
            db.execute("""
                UPDATE publish_jobs SET state=?,
                    youtube_video_id=COALESCE(?, youtube_video_id),
                    last_error=?, lease_owner=NULL, lease_expires_at=NULL,
                    updated_at=? WHERE job_id=?
            """, (to, video_id, error, stamp(), job_id))
            self._event(db, job_id, before, to, error)
            return self._job(db.execute(
                "SELECT * FROM publish_jobs WHERE job_id=?", (job_id,)
            ).fetchone())

    def mark_expired_uploads_unknown(self) -> int:
        """Safety stop: never retry a possibly successful upload blindly."""
        now = stamp()
        count = 0
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            rows = db.execute("""
                SELECT job_id FROM publish_jobs
                WHERE state=? AND lease_expires_at < ?
            """, (State.UPLOADING, now)).fetchall()
            for row in rows:
                db.execute("""
                    UPDATE publish_jobs SET state=?, lease_owner=NULL,
                        lease_expires_at=NULL, last_error=?, updated_at=?
                    WHERE job_id=?
                """, (State.UNKNOWN_UPLOAD_RESULT,
                      "upload lease expired; inspect YouTube Studio", now, row["job_id"]))
                self._event(db, row["job_id"], State.UPLOADING,
                            State.UNKNOWN_UPLOAD_RESULT, "expired upload lease")
                count += 1
        return count

    def events(self, job_id: str) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT * FROM job_events WHERE job_id=? ORDER BY seq", (job_id,)
            ).fetchall()
        return [dict(row) for row in rows]
