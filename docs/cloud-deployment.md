# P1: Google Cloud deployment runbook

The P1 stack provisions Firestore indexes, Secret Manager, three Cloud Run
Jobs and three Cloud Scheduler triggers. Terraform defaults to
scheduler_paused=true. Creating cloud resources or billing is not automatic.

## Prerequisites

Use a GCP project with billing and administrative permission. Install gcloud,
Terraform 1.5+, Docker, Python 3.11+. Configure OAuth Desktop credentials
for the target YouTube channel and Drive assets. OAuth user access is distinct
from the Cloud Run service-account ADC identity.

    export PROJECT=your-project-id
    export REGION=us-central1
    gcloud config set project "$PROJECT"
    gcloud services enable run.googleapis.com cloudscheduler.googleapis.com \
      firestore.googleapis.com iam.googleapis.com secretmanager.googleapis.com \
      artifactregistry.googleapis.com cloudbuild.googleapis.com \
      youtube.googleapis.com drive.googleapis.com

Create Artifact Registry if needed:

    gcloud artifacts repositories create ytp --repository-format=docker \
      --location="$REGION"

Build from a verified repository commit:

    gcloud builds submit --tag us-central1-docker.pkg.dev/your-project-id/ytp/publisher:p1

Replace the project and registry region, then obtain the immutable image
digest and set image_uri accordingly in terraform.tfvars.

## Terraform apply (safe paused mode)

If Firestore (default) Native already exists, leave
manage_firestore_database=false. Otherwise set true after choosing a
supported location. Never delete a database to satisfy Terraform.

    cd infra/terraform
    cp terraform.tfvars.example terraform.tfvars
    # Edit project_id, image_uri, drive_root_id, youtube_channel_id.
    terraform init
    terraform fmt -recursive
    terraform validate
    terraform plan -out=plan.tfplan
    terraform apply plan.tfplan

This creates IAM identities, Firestore indexes, Cloud Run Jobs, paused
Cloud Scheduler jobs, and an EMPTY Secret Manager secret. Existing resources
must be imported, not deleted.

## Upload OAuth secret (outside Terraform)

Locally save a Desktop OAuth client to secrets/client_secret.json and
run ytp auth. Confirm token.json contains refresh_token for scopes
drive.readonly, youtube.upload, youtube.force-ssl, and is authorized for
the exact channel ID. Add it as a secret version:

    gcloud secrets versions add ytp-youtube-oauth --data-file=secrets/token.json

Never store OAuth JSON in GitHub Actions, Docker, tfvars, logs, or state.
The job accesses the secret using its service account and refreshes OAuth
access tokens in memory only.

## Manual smoke test

Place one approved, rights-cleared video in the configured Drive folder
with a publication time at least 24 hours ahead and alias main.

    gcloud run jobs execute ytp-ingest --region="$REGION" --wait
    gcloud run jobs execute ytp-upload --region="$REGION" --wait
    gcloud run jobs execute ytp-reconcile --region="$REGION" --wait

Reconcile again after YouTube processing if needed. Verify channel ID,
private status, attached captions/thumbnail, scheduled time, Firestore
events and the needed Firestore indexes being READY.

## Enable only after manual validation

    terraform apply -var-file=terraform.tfvars -var=scheduler_paused=false

Default timezone Asia/Shanghai. Ingest every 15 min, upload one every hour,
reconcile every 30 min. Retries for uploading are disabled on the infrastructure;
unknown upload results always require operator reconciliation.

## Incident recovery

Pause by applying scheduler_paused=true. Never delete job records or requeue
UNKNOWN_UPLOAD_RESULT without checking YouTube Studio. Decoration timeout
also enters manual review. Cloud Run has ephemeral memory-backed storage;
video size cap 1Gi by default. Durable upload-session recovery and streaming
large assets are later improvements.
