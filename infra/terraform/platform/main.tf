# Ephemeral, billable infrastructure: bring up for a demo, `terraform destroy` after.
# Long-lived pieces (buckets, registry, WIF, budget kill switch) live in ../foundation.

data "google_storage_bucket" "mlflow" {
  name = "${var.project_id}-mlflow" # Created by the foundation stack
}

# ---------------- GKE Autopilot ----------------
# Billed per pod resource request; GKE's free tier covers the cluster management
# fee for one Autopilot cluster per billing account.

resource "google_container_cluster" "main" {
  name                = "ecg-cluster"
  location            = var.region
  enable_autopilot    = true
  deletion_protection = false # Ephemeral by design

  release_channel {
    channel = "REGULAR"
  }
}

# ---------------- Cloud SQL (Postgres) ----------------
# One small instance holds two databases: the API's prediction log and MLflow's
# tracking/registry backend.

# Cloud SQL instance names can't be reused for about a week after deletion, so each
# up/down cycle gets a fresh suffix
resource "random_id" "sql_suffix" {
  byte_length = 2
}

resource "google_sql_database_instance" "main" {
  name                = "ecg-postgres-${random_id.sql_suffix.hex}"
  database_version    = "POSTGRES_15"
  region              = var.region
  deletion_protection = false

  settings {
    tier                        = var.db_tier
    edition                     = "ENTERPRISE" # Shared-core tiers need Enterprise edition
    availability_type           = "ZONAL"
    disk_type                   = "PD_HDD"
    disk_size                   = 10
    disk_autoresize             = false
    deletion_protection_enabled = false

    backup_configuration {
      enabled = false # Demo data only; the source of truth is git + DVC + MLflow artifacts in GCS
    }

    ip_configuration {
      # Public IP with no authorized networks: only the IAM-authenticated
      # Cloud SQL Auth Proxy can connect
      ipv4_enabled = true
    }
  }
}

locals {
  databases = {
    ecg    = { db = "ecg_predictions", user = "ecg_user" }
    mlflow = { db = "mlflow", user = "mlflow" }
  }
}

resource "google_sql_database" "db" {
  for_each = local.databases
  name     = each.value.db
  instance = google_sql_database_instance.main.name
}

resource "random_password" "db" {
  for_each = local.databases
  length   = 32
  special  = false
}

resource "google_sql_user" "user" {
  for_each = local.databases
  name     = each.value.user
  instance = google_sql_database_instance.main.name
  password = random_password.db[each.key].result
}

# Passwords live in Secret Manager; scripts read them from there to build k8s Secrets
resource "google_secret_manager_secret" "db_password" {
  for_each  = local.databases
  secret_id = "${each.key}-db-password"
  replication {
    auto {}
  }
}

# CD (scripts/deploy_gke.sh) copies these into k8s Secrets at deploy time
resource "google_secret_manager_secret_iam_member" "deployer_reads_db_password" {
  for_each  = local.databases
  secret_id = google_secret_manager_secret.db_password[each.key].id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:github-deployer@${var.project_id}.iam.gserviceaccount.com"
}

resource "google_secret_manager_secret_version" "db_password" {
  for_each    = local.databases
  secret      = google_secret_manager_secret.db_password[each.key].id
  secret_data = random_password.db[each.key].result
}

# ---------------- Workload identities ----------------
# Pods authenticate as Google service accounts through Workload Identity: no keys.

locals {
  workloads = {
    # KSA name in k8s/overlays/prod -> roles
    ecg-api = { ksa = "ecg-api", roles = ["roles/cloudsql.client"] }
    mlflow  = { ksa = "mlflow", roles = ["roles/cloudsql.client"] }
  }
  workload_roles = merge([
    for name, w in local.workloads : { for r in w.roles : "${name}:${r}" => { name = name, role = r } }
  ]...)
}

resource "google_service_account" "workload" {
  for_each     = local.workloads
  account_id   = "${each.key}-workload"
  display_name = "GKE workload: ${each.key}"
}

resource "google_project_iam_member" "workload" {
  for_each = local.workload_roles
  project  = var.project_id
  role     = each.value.role
  member   = "serviceAccount:${google_service_account.workload[each.value.name].email}"
}

resource "google_storage_bucket_iam_member" "mlflow_artifacts" {
  bucket = data.google_storage_bucket.mlflow.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.workload["mlflow"].email}"
}

resource "google_service_account_iam_member" "workload_identity" {
  for_each           = local.workloads
  service_account_id = google_service_account.workload[each.key].name
  role               = "roles/iam.workloadIdentityUser"
  member             = "serviceAccount:${var.project_id}.svc.id.goog[${var.namespace}/${each.value.ksa}]"

  # The workload identity pool only exists once the first cluster does
  depends_on = [google_container_cluster.main]
}
