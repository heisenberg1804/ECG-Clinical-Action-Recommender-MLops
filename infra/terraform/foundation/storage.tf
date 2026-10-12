# Long-lived, cheap storage: survives `terraform destroy` of the platform stack.

resource "google_storage_bucket" "dvc" {
  name                        = "${var.project_id}-dvc"
  location                    = var.region
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = false # Holds the versioned dataset

  depends_on = [time_sleep.apis_ready]
}

resource "google_storage_bucket" "mlflow" {
  name                        = "${var.project_id}-mlflow"
  location                    = var.region
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = false # Holds registered model artifacts

  depends_on = [time_sleep.apis_ready]
}

resource "google_artifact_registry_repository" "images" {
  repository_id = "ecg-repo"
  location      = var.region
  format        = "DOCKER"
  description   = "ECG API images"

  # Storage is billed per GB: keep the 5 newest images, drop anything older than 14 days
  cleanup_policy_dry_run = false
  cleanup_policies {
    id     = "keep-recent"
    action = "KEEP"
    most_recent_versions {
      keep_count = 5
    }
  }
  cleanup_policies {
    id     = "delete-old"
    action = "DELETE"
    condition {
      older_than = "1209600s"
    }
  }

  depends_on = [time_sleep.apis_ready]
}
