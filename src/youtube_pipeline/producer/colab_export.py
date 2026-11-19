"""Copy completed Colab outputs into a Drive-mounted directory.

This is a synchronous, explicit producer hand-off. The manifest is published
last, so the scanner never sees an incomplete directory as an approved job.
"""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from youtube_pipeline.domain.models import Manifest


def export_to_mounted_drive(
    source_dir: str | Path, destination_root: str | Path,
) -> Path:
    """Export a validated, explicitly reviewed asset. Never overwrite."""
    source = Path(source_dir).resolve()
    root = Path(destination_root).resolve()
    if not source.is_dir():
        raise FileNotFoundError(source)
    raw = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
    manifest = Manifest.parse(raw)
    manifest.assert_approved()
    root.mkdir(parents=True, exist_ok=True)
    destination = root / manifest.job_id
    destination.mkdir(exist_ok=False)
    try:
        for name in manifest.file_names:
            src = source / name
            if not src.is_file() or src.is_symlink() or src.resolve().parent != source:
                raise FileNotFoundError(src)
            dest = destination / name
            with src.open("rb") as incoming, dest.open("wb") as outgoing:
                shutil.copyfileobj(incoming, outgoing, length=8 * 1024 * 1024)
            if src.stat().st_size == 0 or dest.stat().st_size != src.stat().st_size:
                raise IOError(f"incomplete/empty media copy: {name}")
        # Last file written is the discoverable commit marker.
        temporary = destination / ".manifest.json.partial"
        temporary.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(destination / "manifest.json")
        return destination
    except Exception:
        # Created solely by this invocation; safe to remove an incomplete copy.
        shutil.rmtree(destination)
        raise


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Export assets to mounted Google Drive")
    p.add_argument("--source-dir", required=True)
    p.add_argument("--output-root", required=True)
    args = p.parse_args(argv)
    print(export_to_mounted_drive(args.source_dir, args.output_root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
