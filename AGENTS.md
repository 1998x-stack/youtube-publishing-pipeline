# Agent implementation instructions

- Maintain explicit editorial approval and rights confirmation before publishing.
- Preserve made_for_kids and contains_synthetic_media disclosures.
- Never commit OAuth credentials, refresh tokens, or upload session URLs.
- Never blindly retry an upload if remote completion is uncertain.
- Keep pure policy in domain, orchestration in application and SDK calls in adapters.
- Remote writes require explicit --execute. Always verify expected channel ID.
- Test idempotency, timezone normalization, traversal resistance and unexpected disconnects.
- Run ruff check src tests and pytest -q before merging.
- Do not assert Cloud Run production readiness before Firestore and Secret Manager exist.
