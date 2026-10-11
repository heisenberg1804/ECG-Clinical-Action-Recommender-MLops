variable "project_id" {
  description = "GCP project that hosts everything (created beforehand with gcloud)."
  type        = string
}

variable "region" {
  description = "Region for all regional resources."
  type        = string
  default     = "us-central1"
}

variable "billing_account" {
  description = "Billing account ID linked to the project, e.g. 01AB23-45CD67-89EF01."
  type        = string
}

variable "budget_usd" {
  description = "Monthly budget. At 100% of actual spend the kill switch unlinks billing."
  type        = number
  default     = 10 # Interview demos cost ~$0.35 each; this still leaves room for a forgotten weekend
}

variable "alert_emails" {
  description = "Addresses that receive budget alerts (use an inbox you actually read)."
  type        = list(string)
}

variable "github_repository" {
  description = "owner/name of the only GitHub repo allowed to deploy via Workload Identity Federation."
  type        = string
  default     = "heisenberg1804/ECG-Clinical-Action-Recommender-MLops"
}
