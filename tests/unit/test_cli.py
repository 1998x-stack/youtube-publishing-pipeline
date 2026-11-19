from __future__ import annotations

from youtube_pipeline.cli import main


def test_no_remote_write_without_explicit_execute(ready_assets, tmp_path, capsys):
    args = ["--db", str(tmp_path / "db.sqlite3"), "--assets-dir", str(ready_assets)]
    assert main(args + ["scan"]) == 0
    assert main(args + ["upload"]) == 0
    assert "DRY RUN" in capsys.readouterr().out
    assert main(args + ["status"]) == 0
    assert "QUEUED" in capsys.readouterr().out


def test_validate_local_manifest(ready_assets, tmp_path):
    assert main(["--db", str(tmp_path / "db.sqlite3"),
                 "--assets-dir", str(ready_assets), "validate"]) == 0
