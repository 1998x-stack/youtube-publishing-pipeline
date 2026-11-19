# Security and policy

- rights_confirmed is an explicit content-owner attestation, not a derived AI conclusion.
- review_approved is separate from finished production (ready).
- made_for_kids must reflect the publisher's actual child-directed audience decision.
- contains_synthetic_media must reflect YouTube's altered/synthetic content disclosure requirements.
- OAuth requests Drive read-only, YouTube upload and YouTube force-ssl scopes for caption support.
- Store OAuth secrets outside git, restrict filesystem access, and use Secret Manager in P1.
- Verify the exact authorized YouTube channel ID before live uploads.
- Reject unsafe local paths and symlinks, and do not trust Drive filename hints as authorization.
- Quarantine unknown upload outcomes; never auto-upload the same video a second time.
- P0 SQLite must not be mounted as independent ephemeral state in Cloud Run replicas.
