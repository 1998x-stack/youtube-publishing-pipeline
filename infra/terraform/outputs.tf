output "job_names" {
  value = { for label, job in google_cloud_run_v2_job.worker : label => job.name }
}
output "scheduler_names" {
  value = { for label, schedule in google_cloud_scheduler_job.trigger : label => schedule.name }
}
output "oauth_secret_resource" { value = local.oauth_resource }
output "scheduler_paused" { value = var.scheduler_paused }
