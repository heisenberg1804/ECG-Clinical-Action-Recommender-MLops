# The tutor's credentials (D-71). Terraform creates the secrets empty; their values are
# added by hand (README), so the Anthropic API key never enters Terraform state or git.
# They live here, not in the platform stack, because the platform is destroyed after
# every demo and the key has to outlive it.
locals {
  tutor_secrets = toset(["tutor-anthropic-api-key", "tutor-passcode"])
}

resource "google_secret_manager_secret" "tutor" {
  for_each  = local.tutor_secrets
  secret_id = each.value
  replication {
    auto {}
  }
  depends_on = [time_sleep.apis_ready]
}

# deploy_gke.sh copies them into a k8s Secret; without both, the tutor stays off
resource "google_secret_manager_secret_iam_member" "deployer_reads_tutor" {
  for_each  = local.tutor_secrets
  secret_id = google_secret_manager_secret.tutor[each.key].id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.github_deployer.email}"
}
