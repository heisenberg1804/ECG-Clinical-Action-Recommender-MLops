output "artifact_registry" {
  description = "Image path prefix for docker push / kustomize."
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.images.repository_id}"
}

output "dvc_remote" {
  value = "gs://${google_storage_bucket.dvc.name}/dvc-cache"
}

output "mlflow_artifact_root" {
  value = "gs://${google_storage_bucket.mlflow.name}/artifacts"
}

output "github_wif_provider" {
  description = "Set as the GCP_WIF_PROVIDER repository variable."
  value       = google_iam_workload_identity_pool_provider.github.name
}

output "github_deployer_sa" {
  description = "Set as the GCP_DEPLOYER_SA repository variable."
  value       = google_service_account.github_deployer.email
}

output "budget" {
  value = "${google_billing_budget.monthly.display_name}: ${var.budget_usd} USD/month, hard cap via ${google_cloudfunctions2_function.kill_switch.name}"
}
