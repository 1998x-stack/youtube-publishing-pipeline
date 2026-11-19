variable "project_id" {
  type        = string
  description = "Existing billable Google Cloud project ID"
}
variable "region" {
  type = string
  default = "us-central1"
}
variable "image_uri" {
  type        = string
  description = "Pre-built image URI; prefer a pinned sha256 digest"
  validation {
    condition     = length(var.image_uri) > 15
    error_message = "Provide a fully qualified container image URI."
  }
}
variable "drive_root_id" {
  type        = string
  description = "Approved Google Drive parent folder ID"
}
variable "youtube_channel_id" {
  type        = string
  description = "Exact YouTube channel ID bound to the OAuth token"
}
variable "namespace" {
  type    = string
  default = "ytp"
  validation {
    condition     = can(regex("^[a-zA-Z0-9-]{1,32}$", var.namespace))
    error_message = "Namespace must contain 1-32 alphanumeric/hyphen characters."
  }
}
variable "name_prefix" {
  type = string
  default = "ytp"
}
variable "scheduler_paused" {
  type        = bool
  default     = true
  description = "Safest default: all cron triggers start paused"
}
variable "schedule_timezone" {
  type = string
  default = "Asia/Shanghai"
}
variable "ingest_schedule" {
  type = string
  default = "*/15 * * * *"
}
variable "upload_schedule" {
  type = string
  default = "5 * * * *"
}
variable "reconcile_schedule" {
  type = string
  default = "*/30 * * * *"
}
variable "manage_firestore_database" {
  type        = bool
  default     = false
  description = "Set true only when the default Firestore database does not exist"
}
variable "firestore_location" {
  type = string
  default = "nam5"
}
variable "max_video_bytes" {
  type = number
  default = 1073741824
}
