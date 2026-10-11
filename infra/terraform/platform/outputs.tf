output "get_credentials" {
  value = "gcloud container clusters get-credentials ${google_container_cluster.main.name} --region ${var.region} --project ${var.project_id}"
}

output "cluster_name" {
  value = google_container_cluster.main.name
}

output "sql_connection_name" {
  description = "Instance connection name for the Cloud SQL Auth Proxy."
  value       = google_sql_database_instance.main.connection_name
}

output "db_password_secrets" {
  value = { for k, s in google_secret_manager_secret.db_password : k => s.secret_id }
}

output "workload_service_accounts" {
  description = "Annotate the matching KSAs with iam.gke.io/gcp-service-account."
  value       = { for k, sa in google_service_account.workload : local.workloads[k].ksa => sa.email }
}
