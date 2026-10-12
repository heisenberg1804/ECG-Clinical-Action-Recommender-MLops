# Budget alerts + a hard cap. GCP budgets only notify; the Cloud Function below
# unlinks billing once actual spend reaches var.budget_usd. Budget data lags real
# usage by hours, so the cap can be overshot slightly - size the budget with margin.

resource "google_pubsub_topic" "budget" {
  name       = "budget-alerts"
  depends_on = [time_sleep.apis_ready]
}

resource "google_monitoring_notification_channel" "email" {
  for_each     = toset(var.alert_emails)
  display_name = "Budget alerts: ${each.value}"
  type         = "email"
  labels = {
    email_address = each.value
  }
  depends_on = [time_sleep.apis_ready]
}

resource "google_billing_budget" "monthly" {
  billing_account = var.billing_account
  display_name    = "${var.project_id} monthly cap"

  budget_filter {
    projects = ["projects/${data.google_project.this.number}"]
  }

  amount {
    specified_amount {
      currency_code = "USD"
      units         = tostring(var.budget_usd)
    }
  }

  dynamic "threshold_rules" {
    for_each = [0.5, 0.9, 1.0]
    content {
      threshold_percent = threshold_rules.value
      spend_basis       = "CURRENT_SPEND"
    }
  }
  threshold_rules {
    threshold_percent = 1.0
    spend_basis       = "FORECASTED_SPEND" # Early warning only; never triggers the cap
  }

  all_updates_rule {
    pubsub_topic                     = google_pubsub_topic.budget.id
    schema_version                   = "1.0"
    monitoring_notification_channels = [for c in google_monitoring_notification_channel.email : c.id]
    disable_default_iam_recipients   = false
  }

  depends_on = [time_sleep.apis_ready]
}

# ---------------- Kill switch function ----------------

resource "google_service_account" "kill_switch" {
  account_id   = "budget-kill-switch"
  display_name = "Unlinks billing when the budget is exhausted"

  depends_on = [time_sleep.apis_ready]
}

# Project Billing Manager includes resourcemanager.projects.deleteBillingAssignment
resource "google_project_iam_member" "kill_switch_billing" {
  project = var.project_id
  role    = "roles/billing.projectManager"
  member  = "serviceAccount:${google_service_account.kill_switch.email}"
}

resource "google_project_iam_member" "kill_switch_events" {
  for_each = toset(["roles/eventarc.eventReceiver", "roles/run.invoker"])
  project  = var.project_id
  role     = each.value
  member   = "serviceAccount:${google_service_account.kill_switch.email}"
}

# Dedicated build identity (newer projects no longer grant Cloud Build broad defaults)
resource "google_service_account" "function_builder" {
  account_id   = "function-builder"
  display_name = "Builds Cloud Functions"

  depends_on = [time_sleep.apis_ready]
}

resource "google_project_iam_member" "function_builder" {
  for_each = toset([
    "roles/cloudbuild.builds.builder",
    "roles/logging.logWriter",
    "roles/artifactregistry.writer",
    "roles/storage.objectViewer",
  ])
  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.function_builder.email}"
}

resource "google_storage_bucket" "functions" {
  name                        = "${var.project_id}-functions"
  location                    = var.region
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = true
  depends_on                  = [time_sleep.apis_ready]
}

data "archive_file" "kill_switch" {
  type        = "zip"
  source_dir  = "${path.module}/kill_switch"
  output_path = "${path.module}/.build/kill_switch.zip"
  excludes    = ["__pycache__"]
}

resource "google_storage_bucket_object" "kill_switch" {
  # Content-addressed name so code changes redeploy the function
  name   = "kill_switch-${data.archive_file.kill_switch.output_md5}.zip"
  bucket = google_storage_bucket.functions.name
  source = data.archive_file.kill_switch.output_path
}

resource "google_cloudfunctions2_function" "kill_switch" {
  name     = "budget-kill-switch"
  location = var.region

  build_config {
    runtime         = "python312"
    entry_point     = "stop_billing"
    service_account = google_service_account.function_builder.id
    source {
      storage_source {
        bucket = google_storage_bucket.functions.name
        object = google_storage_bucket_object.kill_switch.name
      }
    }
  }

  service_config {
    max_instance_count    = 1
    available_memory      = "256M"
    timeout_seconds       = 60
    service_account_email = google_service_account.kill_switch.email
    environment_variables = {
      TARGET_PROJECT_ID = var.project_id
    }
  }

  event_trigger {
    trigger_region        = var.region
    event_type            = "google.cloud.pubsub.topic.v1.messagePublished"
    pubsub_topic          = google_pubsub_topic.budget.id
    retry_policy          = "RETRY_POLICY_RETRY"
    service_account_email = google_service_account.kill_switch.email
  }

  depends_on = [google_project_iam_member.function_builder, google_project_iam_member.kill_switch_events]
}
