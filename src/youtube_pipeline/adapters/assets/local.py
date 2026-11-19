"""Local-folder source mirrors the Colab -> Drive asset contract."""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any, Iterable


class LocalAssetStore:
    source_type = "local"

    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()

    def discover(self) -> Iterable[tuple[str, dict[str, Any]]]:
        if not self.root.is_dir():
            raise FileNotFoundError(self.root)
        for folder in sorted(self.root.iterdir()):
            if not folder.is_dir() or folder.is_symlink():
                continue
            manifest = folder / "manifest.json"
            if manifest.is_file() and not manifest.is_symlink():
                yield folder.name, json.loads(manifest.read_text(encoding="utf-8"))

    def materialize(self, asset_key: str, names: list[str], target: Path) -> dict[str, Path]:
        folder = (self.root / asset_key).resolve()
        if folder.parent != self.root or not folder.is_dir():
            raise ValueError("invalid asset key")
        target.mkdir(parents=True, exist_ok=True)
        result: dict[str, Path] = {}
        for name in names:
            if name in (".", "..") or Path(name).name != name:
                raise ValueError("unsafe asset name")
            source = folder / name
            if not source.is_file() or source.is_symlink() or source.resolve().parent != folder:
                raise FileNotFoundError(source)
            dest = target / name
            if source.suffix.lower() == ".mp4":
                limit = int(os.getenv("YTP_MAX_VIDEO_BYTES", "1073741824"))
                if source.stat().st_size > limit:
                    raise ValueError("Local video too large for configured runtime limit")
            with source.open("rb") as src, dest.open("wb") as out:
                shutil.copyfileobj(src, out, length=8 * 1024 * 1024)
            result[name] = dest
        return result
