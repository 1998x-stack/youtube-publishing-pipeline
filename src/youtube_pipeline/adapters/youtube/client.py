"""Official YouTube Data API v3 adapter.

Never automatically repeat an upload when its remote outcome is unknown.
Metadata and publish operations can be reconciled by video ID.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from googleapiclient.http import MediaFileUpload


class YouTubePublisher:
    def __init__(self, service: Any):
        self.api = service

    def verify_channel(self, expected_channel_id: str) -> None:
        if not expected_channel_id:
            raise ValueError("YTP_YOUTUBE_CHANNEL_ID is required for live publishing")
        reply = self.api.channels().list(part="id", mine=True).execute()
        channel_ids = {item["id"] for item in reply.get("items", [])}
        if expected_channel_id not in channel_ids:
            raise PermissionError(
                "OAuth user/channel mismatch; refusing to upload to an unexpected channel"
            )

    def upload_private(self, video: Path, manifest: dict[str, Any]) -> str:
        if video.suffix.lower() != ".mp4" or not video.is_file() or video.stat().st_size == 0:
            raise ValueError("a nonempty .mp4 file is required")
        request = self.api.videos().insert(
            part="snippet,status",
            body={
                "snippet": {
                    "title": manifest["title"],
                    "description": manifest["description"],
                    "categoryId": manifest.get("category_id", "22"),
                    "tags": manifest.get("tags", []),
                },
                "status": {
                    "privacyStatus": "private",
                    "selfDeclaredMadeForKids": manifest["made_for_kids"],
                    "containsSyntheticMedia": manifest["contains_synthetic_media"],
                },
            },
            media_body=MediaFileUpload(
                str(video), mimetype="video/mp4",
                resumable=True, chunksize=8 * 1024 * 1024
            ),
        )
        response = None
        while response is None:
            _, response = request.next_chunk()
        video_id = response.get("id")
        if not video_id:
            raise RuntimeError("YouTube upload response is missing video ID")
        return video_id

    def _video(self, video_id: str, parts: str) -> dict[str, Any]:
        result = self.api.videos().list(part=parts, id=video_id).execute()
        items = result.get("items", [])
        if not items:
            raise RuntimeError(f"video not accessible to OAuth channel: {video_id}")
        return items[0]

    def processing_status(self, video_id: str) -> str:
        video = self._video(video_id, "processingDetails,status")
        status = video.get("status", {})
        if status.get("uploadStatus") in ("failed", "rejected", "deleted"):
            return "failed"
        return video.get("processingDetails", {}).get("processingStatus", "processing")

    def decorate(self, video_id: str, manifest: dict[str, Any],
                 files: dict[str, Path]) -> None:
        thumbnail = manifest.get("thumbnail_file")
        if thumbnail:
            path = files[thumbnail]
            self.api.thumbnails().set(
                videoId=video_id, media_body=MediaFileUpload(str(path))
            ).execute()
        subtitle = manifest.get("subtitle_file")
        if subtitle:
            path = files[subtitle]
            self.api.captions().insert(
                part="snippet",
                body={"snippet": {
                    "videoId": video_id,
                    "language": manifest.get("subtitle_language", "zh-CN"),
                    "name": "Original captions",
                    "isDraft": False,
                }},
                media_body=MediaFileUpload(
                    str(path), mimetype="application/octet-stream"
                ),
            ).execute()

    def set_schedule(self, video_id: str, publish_at_utc: str) -> None:
        target = datetime.fromisoformat(publish_at_utc.replace("Z", "+00:00"))
        if target.tzinfo is None or target <= datetime.now(timezone.utc):
            raise ValueError("publish_at must be a future UTC timestamp")
        self.api.videos().update(
            part="status",
            body={
                "id": video_id,
                "status": {
                    "privacyStatus": "private",
                    "publishAt": target.astimezone(timezone.utc)
                    .isoformat().replace("+00:00", "Z"),
                },
            },
        ).execute()

    def privacy_status(self, video_id: str) -> str:
        return self._video(video_id, "status").get("status", {}).get(
            "privacyStatus", "unknown"
        )
