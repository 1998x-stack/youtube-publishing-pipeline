# YouTube Publishing Pipeline

**Status: P0 implementation, not an unattended cloud deployment.**

Review-gated pipeline: Colab renders video assets → Google Drive stores each video folder → scanner registers approved manifests → worker uploads privately → reconciler attaches captions/thumbnail, schedules future publication, and checks YouTube status.

See [中文说明](README.zh.md), [architecture](docs/architecture.md), [security](docs/security.md), and [roadmap](docs/roadmap.md).

## Start locally

1. Use Python 3.11+; install with: python -m pip install -e '.[dev]'
2. Run tests: pytest -q
3. Create a video folder under my-assets containing real video.mp4, manifest.json, and optional thumbnail.png and subtitles.srt. Use [manifest example](examples/manifest.example.json).
4. Validate: ytp --assets-dir ./my-assets validate
5. Register: ytp --assets-dir ./my-assets scan
6. Inspect: ytp status

## Google OAuth

Enable YouTube Data API v3 and Google Drive API; configure the OAuth consent screen, create a Desktop OAuth client and save its JSON at secrets/client_secret.json. Run ytp auth locally to obtain secrets/token.json. Neither file may enter Git.

Set YTP_YOUTUBE_CHANNEL_ID to the *actual* channel ID. The uploader verifies it against the authenticated channel before making remote writes.

Set YTP_DRIVE_ROOT_ID to the folder containing one subfolder per video. Each child folder must contain a manifest.json, uploaded **last** after media files.

- ytp scan
- ytp upload --execute
- ytp reconcile --execute
- ytp status
- ytp recover-expired

**No remote upload or publish changes occur without --execute.** The user must provide the YouTube channel OAuth credentials. Uploads always begin private. Processing is confirmed before scheduling. The YouTube platform publishes at the configured time.

## Safety and limitations

- Every asset requires ready, review_approved, and rights_confirmed.
- If upload completion is ambiguous, state becomes UNKNOWN_UPLOAD_RESULT; there is no automatic re-upload.
- Job IDs are immutable across manifest changes, preventing silent duplicates.
- Scheduled timestamps require an explicit offset, stored as UTC.
- SQLite works for one persistent worker host, **not** concurrent ephemeral Cloud Run instances.
- Cloud Run/Firestore/Secret Manager deployment is P1 and is not included in this revision.
- Upload session persistence across crashes is not implemented; affected tasks are quarantined.

CI uses local fake media and a fake publisher. Live OAuth/video processing and real publishing require a separately verified test channel.

Colab handoff script and mounted-Drive instructions: [export guide](docs/colab-export.md).
