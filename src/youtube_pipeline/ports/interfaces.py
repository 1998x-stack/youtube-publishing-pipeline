"""Adapter contracts for assets and publishing."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Protocol


class AssetStore(Protocol):
    source_type: str

    def discover(self) -> Iterable[tuple[str, dict[str, Any]]]:
        """Return (stable asset_key, manifest JSON) pairs."""

    def materialize(self, asset_key: str, names: list[str], target: Path) -> dict[str, Path]:
        """Download/copy requested files; never hold video bytes in memory."""


class Publisher(Protocol):
    def upload_private(self, video: Path, manifest: dict[str, Any]) -> str: ...

    def processing_status(self, video_id: str) -> str: ...

    def decorate(
        self, video_id: str, manifest: dict[str, Any], files: dict[str, Path]
    ) -> None: ...

    def set_schedule(self, video_id: str, publish_at_utc: str, manifest: dict[str, Any]) -> None: ...

    def privacy_status(self, video_id: str) -> str: ...
