data "google_project" "this" {
  project_id = var.project_id
}

locals {
  services = [
    "artifactregistry.googleapis.com",
    "billingbudgets.googleapis.com",
    "cloudbilling.googleapis.com",
    "cloudbuild.googleapis.com",
    "cloudfunctions.googleapis.com",
    "cloudresourcemanager.googleapis.com", # Bootstrapped by `make foundation`; managed here after
    "container.googleapis.com",
    "eventarc.googleapis.com",
    "iam.googleapis.com",
    "iamcredentials.googleapis.com",
    "monitoring.googleapis.com",
    "pubsub.googleapis.com",
    "run.googleapis.com",
    "secretmanager.googleapis.com",
    "serviceusage.googleapis.com", # Bootstrapped by `make foundation`; managed here after
    "sqladmin.googleapis.com",
    "storage.googleapis.com",
    "sts.googleapis.com",
  ]
}

resource "google_project_service" "enabled" {
  for_each = toset(local.services)
  service  = each.value

  # Keep APIs on when this stack is destroyed; disabling them can break other resources
  disable_on_destroy = false
}

# Enabling an API returns before it's usable everywhere; on a fresh project,
# resources created immediately afterwards fail with SERVICE_DISABLED. Every
# resource below depends on this gate instead of on the APIs directly.
resource "time_sleep" "apis_ready" {
  depends_on      = [google_project_service.enabled]
  create_duration = "90s"
}
