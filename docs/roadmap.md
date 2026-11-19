# Roadmap

## P0: implemented in this PR

Manifest contract, review gates, local and Drive scanning, SQLite queue with idempotent registration and audit events, official YouTube private upload, processing checks, attachments, future-time schedule request, visibility reconciliation, CLI and offline tests.

## P1: NOT implemented yet

Transactional Firestore repository and distributed leases, Secret Manager OAuth token management, Cloud Scheduler and Cloud Run Jobs deployment, durable upload-session checkpointing, 429/5xx backoff, quota budgets, GCS staging for large videos, Drive changes cursor, alerting, Terraform.

## P2: operational dashboard

Queue inventory, publication calendar, manual review of unknown uploads, channel-isolated credentials and analytics.

## P3: additional publisher adapters

Separate ports/adapters for other platforms while retaining common asset and audit contracts.

## P1 delivered in this iteration

Implemented Firestore transactional queue, shared JobRepository port, Secret
Manager OAuth read access, guarded recovery for stale uploads/decorating,
Terraform for three Cloud Run Jobs, Scheduler, IAM and Firestore indexes.
Default schedule remains paused. Not yet implemented: durable resumable-upload
session persistence, dynamic quota budget, GCS streaming of >1GiB assets,
end-to-end live Google Cloud verification or a manual review UI.
