"""Drive folder asset store; paginated folder listing and chunked file downloads."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Iterable

from googleapiclient.http import MediaIoBaseDownload


class DriveAssetStore:
    source_type = "drive"

    def __init__(self, drive_service: Any, root_folder_id: str):
        if not root_folder_id:
            raise ValueError("Drive folder ID required")
        self.drive = drive_service
        self.root_folder_id = root_folder_id

    def _children(self, folder_id: str) -> Iterable[dict[str, Any]]:
        token = None
        while True:
            response = self.drive.files().list(
                q=f"'{folder_id}' in parents and trashed=false",
                fields="nextPageToken,files(id,name,mimeType,size)",
                pageSize=1000, pageToken=token,
                supportsAllDrives=True, includeItemsFromAllDrives=True,
            ).execute()
            yield from response.get("files", [])
            token = response.get("nextPageToken")
            if not token:
                break

    def _download(self, file_id: str, dest: Path) -> None:
        request = self.drive.files().get_media(
            fileId=file_id, supportsAllDrives=True
        )
        with dest.open("wb") as out:
            downloader = MediaIoBaseDownload(out, request, chunksize=8 * 1024 * 1024)
            done = False
            while not done:
                _, done = downloader.next_chunk()

    def discover(self) -> Iterable[tuple[str, dict[str, Any]]]:
        for folder in self._children(self.root_folder_id):
            if folder["mimeType"] != "application/vnd.google-apps.folder":
                continue
            files = {f["name"]: f for f in self._children(folder["id"])}
            descriptor = files.get("manifest.json")
            if not descriptor:
                continue
            if int(descriptor.get("size", 0)) > 256 * 1024:
                raise ValueError(f"manifest too large: {folder['id']}")
            import tempfile
            with tempfile.TemporaryDirectory() as tempdir:
                path = Path(tempdir) / "manifest.json"
                self._download(descriptor["id"], path)
                if path.stat().st_size > 256 * 1024:
                    raise ValueError("manifest exceeds 256 KiB")
                manifest = json.loads(path.read_text(encoding="utf-8"))
            yield folder["id"], manifest

    def materialize(self, asset_key: str, names: list[str], target: Path) -> dict[str, Path]:
        files = {f["name"]: f for f in self._children(asset_key)}
        target.mkdir(parents=True, exist_ok=True)
        result = {}
        for name in names:
            if name in (".", "..") or Path(name).name != name:
                raise ValueError("unsafe asset filename")
            if name not in files or files[name]["mimeType"] == "application/vnd.google-apps.folder":
                raise FileNotFoundError(f"Drive asset {asset_key}/{name}")
            path = target / name
            if files[name].get("mimeType", "").startswith("video/"):
                limit = int(os.getenv("YTP_MAX_VIDEO_BYTES", "1073741824"))
                if int(files[name].get("size", "0")) > limit:
                    raise ValueError("Drive video too large for configured runtime limit")
            self._download(files[name]["id"], path)
            result[name] = path
        return result
