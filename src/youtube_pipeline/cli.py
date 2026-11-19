"""CLI used identically in local environments and scheduled container jobs."""
from __future__ import annotations

import argparse
import json
import os
import socket
import sys

from youtube_pipeline.adapters.assets.local import LocalAssetStore
from youtube_pipeline.adapters.persistence.sqlite import SQLiteRepository
from youtube_pipeline.application.workflows import ingest, reconcile, upload_one
from youtube_pipeline.domain.models import Manifest


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="ytp", description="Drive-to-YouTube publisher")
    p.add_argument("--db", default=os.getenv("YTP_DATABASE", "./workdir/publishing.sqlite3"))
    p.add_argument("--assets-dir", default=os.getenv("YTP_ASSETS_DIR", "./examples/ready"))
    p.add_argument("--drive-root-id", default=os.getenv("YTP_DRIVE_ROOT_ID"))
    p.add_argument("--channel-alias", default="main")
    p.add_argument("--channel-id", default=os.getenv("YTP_YOUTUBE_CHANNEL_ID"))
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("auth", help="Run local OAuth consent once")
    sub.add_parser("scan", help="Validate and register review-approved assets")
    sub.add_parser("status", help="Display current job states; no external calls")
    sub.add_parser("recover-expired", help="Quarantine expired upload leases")
    sub.add_parser("validate", help="Validate manifests without ingesting")
    for name in ("upload", "reconcile"):
        cmd = sub.add_parser(name, help="Execute one publishing stage")
        cmd.add_argument("--execute", action="store_true",
                         help="Required for all remote writes")
    return p


def store_for(args: argparse.Namespace, credentials=None):
    if args.drive_root_id:
        from googleapiclient.discovery import build
        from youtube_pipeline.adapters.assets.drive import DriveAssetStore
        return DriveAssetStore(
            build("drive", "v3", credentials=credentials, cache_discovery=False),
            args.drive_root_id,
        )
    return LocalAssetStore(args.assets_dir)


def remote_publisher(creds):
    from googleapiclient.discovery import build
    from youtube_pipeline.adapters.youtube.client import YouTubePublisher
    return YouTubePublisher(build("youtube", "v3", credentials=creds, cache_discovery=False))


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "auth":
            from youtube_pipeline.adapters.google_auth import credentials
            credentials(interactive=True)
            print("OAuth token prepared. Keep the token file private.")
            return 0
        repo = SQLiteRepository(args.db)
        if args.command == "status":
            for job in repo.list_jobs():
                print(json.dumps({
                    "job_id": job.job_id, "state": job.state,
                    "channel": job.channel, "youtube_video_id": job.youtube_video_id,
                    "scheduled_at": job.scheduled_at, "last_error": job.last_error,
                }, ensure_ascii=False))
            return 0
        if args.command == "recover-expired":
            print(json.dumps({"quarantined": repo.mark_expired_uploads_unknown()}))
            return 0
        if args.command in ("upload", "reconcile") and not args.execute:
            print("DRY RUN: no remote writes. Add --execute to perform this action.")
            return 0
        from youtube_pipeline.adapters.google_auth import credentials
        creds = credentials() if (args.drive_root_id or args.command in ("upload", "reconcile")) else None
        store = store_for(args, creds)
        if args.command == "validate":
            results = []
            for key, raw in store.discover():
                try:
                    m = Manifest.parse(raw)
                    m.assert_approved()
                    results.append({"asset": key, "valid": True})
                except ValueError as exc:
                    results.append({"asset": key, "valid": False, "error": str(exc)})
            print(json.dumps(results, ensure_ascii=False, indent=2))
            return 1 if any(not r["valid"] for r in results) else 0
        if args.command == "scan":
            result = ingest(store, repo)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 1 if result["errors"] else 0
        if not args.channel_id:
            raise ValueError("--channel-id or YTP_YOUTUBE_CHANNEL_ID required")
        publisher = remote_publisher(creds)
        publisher.verify_channel(args.channel_id)
        if args.command == "upload":
            identifier = upload_one(
                repo, store, publisher, worker_id=f"{socket.gethostname()}:{os.getpid()}",
                channel_alias=args.channel_alias,
            )
            print(json.dumps({"job_id": identifier, "result": "processed" if identifier else "idle"}))
            return 0
        if args.command == "reconcile":
            result = reconcile(repo, store, publisher, channel_alias=args.channel_alias)
            print(json.dumps(result))
            return 0 if not result["needs_review"] else 1
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
