# P0 validation

Offline: python -m pip install -e '.[dev]' ; ruff check src tests ; pytest -q ; python -m compileall -q src.

Test groups: validation, timezone, path safety, job immutability, SQLite transactional claim and stale quarantine, full fake publishing workflow and fail-closed unknown upload, CLI default no-write behavior.

Real smoke test is NOT included in CI. To verify real YouTube behavior, obtain OAuth consent on a controlled test channel, provide rights-cleared MP4, scan and upload privately, inspect video ID and status in YouTube Studio, reconcile until processing succeeds, check attached cover/subtitles and scheduled publishAt, then confirm public visibility after target time. Record API quota, permissions and latency separately.
