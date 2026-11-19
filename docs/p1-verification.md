# P1 acceptance matrix

| Control | Offline check | Real-cloud requirement |
| --- | --- | --- |
| Firestore claim / consistency | Mocked transaction tests | Firestore emulator / parallel jobs |
| Expired lease | Quarantine tests | Controlled disconnection |
| Decoration recovery | Stale state tests | YouTube Studio inspection |
| Secret Manager token | Stub payload test | Human OAuth consent + secret version |
| Cloud Run / Scheduler | Terraform fmt and validate | Human-approved plan/apply |
| Scheduled publication | Fake API | Real rights-cleared test video |

No cloud resources or live uploads are created by repository CI.
See cloud-deployment.md for the operator runbook.
