locals {
  job_commands = {
    ingest    = ["scan"]
    upload    = ["upload", "--execute"]
    reconcile = ["reconcile", "--execute"]
  }
  job_schedules = {
    ingest    = var.ingest_schedule
    upload    = var.upload_schedule
    reconcile = var.reconcile_schedule
  }
  oauth_resource = "projects/${var.project_id}/secrets/${google_secret_manager_secret.youtube_oauth.secret_id}/versions/latest"
  environment = {
    YTP_BACKEND                = "firestore"
    YTP_FIRESTORE_NAMESPACE    = var.namespace
    YTP_DRIVE_ROOT_ID         = var.drive_root_id
    YTP_YOUTUBE_CHANNEL_ID    = var.youtube_channel_id
    YTP_OAUTH_SECRET_RESOURCE = local.oauth_resource
    YTP_MAX_VIDEO_BYTES       = tostring(var.max_video_bytes)
  }
}
resource "google_project_service" "apis" {
  for_each = toset([
    "run.googleapis.com", "cloudscheduler.googleapis.com",
    "firestore.googleapis.com", "secretmanager.googleapis.com", "iam.googleapis.com"
  ])
  project            = var.project_id
  service            = each.value
  disable_on_destroy = false
}
resource "google_service_account" "runner" {
  project      = var.project_id
  account_id   = "${var.name_prefix}-runner"
  display_name = "YouTube publishing worker"
  depends_on   = [google_project_service.apis]
}
resource "google_service_account" "scheduler" {
  project      = var.project_id
  account_id   = "${var.name_prefix}-scheduler"
  display_name = "YouTube publishing job invoker"
  depends_on   = [google_project_service.apis]
}
resource "google_project_iam_member" "firestore_user" {
  project = var.project_id
  role    = "roles/datastore.user"
  member  = "serviceAccount:${google_service_account.runner.email}"
}
resource "google_project_iam_member" "logging_writer" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.runner.email}"
}
resource "google_secret_manager_secret" "youtube_oauth" {
  project   = var.project_id
  secret_id = "${var.name_prefix}-youtube-oauth"
  replication {
    auto {}
  }
  depends_on = [google_project_service.apis]
}
# The OAuth secret VALUE is supplied outside Terraform (never in tfstate).
resource "google_secret_manager_secret_iam_member" "oauth_access" {
  project   = var.project_id
  secret_id = google_secret_manager_secret.youtube_oauth.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.runner.email}"
}
resource "google_firestore_database" "default" {
  count                   = var.manage_firestore_database ? 1 : 0
  project                 = var.project_id
  name                    = "(default)"
  location_id             = var.firestore_location
  type                    = "FIRESTORE_NATIVE"
  delete_protection_state = "DELETE_PROTECTION_ENABLED"
  deletion_policy         = "ABANDON"
  depends_on              = [google_project_service.apis]
}
resource "google_cloud_run_v2_job" "worker" {
  for_each = local.job_commands
  project  = var.project_id
  name     = "${var.name_prefix}-${each.key}"
  location = var.region
  template {
    task_count  = 1
    parallelism = 1
    template {
      service_account = google_service_account.runner.email
      timeout         = each.key == "upload" ? "3600s" : "1800s"
      max_retries     = 0
      containers {
        image   = var.image_uri
        command = ["ytp"]
        args    = each.value
        resources {
          limits = { cpu = "1", memory = "4Gi" }
        }
        dynamic "env" {
          for_each = local.environment
          content {
            name  = env.key
            value = env.value
          }
        }
      }
    }
  }
  depends_on = [
    google_project_service.apis,
    google_secret_manager_secret_iam_member.oauth_access,
    google_project_iam_member.firestore_user,
  ]
}
resource "google_cloud_run_v2_job_iam_member" "scheduler_run" {
  for_each = local.job_commands
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_job.worker[each.key].name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.scheduler.email}"
}
resource "google_cloud_scheduler_job" "trigger" {
  for_each         = local.job_schedules
  project          = var.project_id
  region           = var.region
  name             = "${var.name_prefix}-${each.key}-trigger"
  schedule         = each.value
  time_zone        = var.schedule_timezone
  paused           = var.scheduler_paused
  attempt_deadline = "320s"
  retry_config { retry_count = 0 }
  http_target {
    http_method = "POST"
    uri         = "https://run.googleapis.com/v2/projects/${var.project_id}/locations/${var.region}/jobs/${google_cloud_run_v2_job.worker[each.key].name}:run"
    body        = base64encode("{}")
    headers     = { "Content-Type" = "application/json" }
    oauth_token {
      service_account_email = google_service_account.scheduler.email
    }
  }
  depends_on = [google_cloud_run_v2_job_iam_member.scheduler_run, google_project_service.apis]
}
