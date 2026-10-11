variable "project_id" {
  description = "Same project as the foundation stack."
  type        = string
}

variable "region" {
  type    = string
  default = "us-central1"
}

variable "namespace" {
  description = "Kubernetes namespace the app runs in (matches k8s/overlays/prod)."
  type        = string
  default     = "ecg-prod"
}

variable "db_tier" {
  description = "Cloud SQL machine tier. db-f1-micro is the cheapest shared-core tier."
  type        = string
  default     = "db-f1-micro"
}
