resource "google_firestore_index" "queue_by_schedule" {
  project = var.project_id
  database = "(default)"
  collection = "${var.namespace}_publish_jobs"
  fields {
    field_path = "state"
    order = "ASCENDING"
  }
  fields {
    field_path = "scheduled_at"
    order = "ASCENDING"
  }
  depends_on = [google_firestore_database.default, google_project_service.apis]
}
resource "google_firestore_index" "channel_queue" {
  project = var.project_id
  database = "(default)"
  collection = "${var.namespace}_publish_jobs"
  fields {
    field_path = "state"
    order = "ASCENDING"
  }
  fields {
    field_path = "channel"
    order = "ASCENDING"
  }
  fields {
    field_path = "scheduled_at"
    order = "ASCENDING"
  }
  depends_on = [google_firestore_database.default, google_project_service.apis]
}
resource "google_firestore_index" "expired_uploads" {
  project = var.project_id
  database = "(default)"
  collection = "${var.namespace}_publish_jobs"
  fields {
    field_path = "state"
    order = "ASCENDING"
  }
  fields {
    field_path = "lease_expires_at"
    order = "ASCENDING"
  }
  depends_on = [google_firestore_database.default, google_project_service.apis]
}
resource "google_firestore_index" "stale_decoration" {
  project = var.project_id
  database = "(default)"
  collection = "${var.namespace}_publish_jobs"
  fields {
    field_path = "state"
    order = "ASCENDING"
  }
  fields {
    field_path = "updated_at"
    order = "ASCENDING"
  }
  depends_on = [google_firestore_database.default, google_project_service.apis]
}
