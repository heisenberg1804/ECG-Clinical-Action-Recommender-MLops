# Common workflows. Run `make help` for the list.
.DEFAULT_GOAL := help
TF := terraform -chdir=infra/terraform
PROJECT ?= $(shell grep -E '^project_id' infra/terraform/foundation/terraform.tfvars 2>/dev/null | cut -d'"' -f2)

.PHONY: help
help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

# ---------------- Development ----------------
.PHONY: lint test train promote serve mlflow
lint:  ## Ruff + terraform fmt check
	uv run ruff check src tests airflow infra
	terraform fmt -check -recursive infra/terraform

test:  ## Run the test suite
	uv run pytest

train:  ## Full training run (logs to MLflow, registers a challenger)
	uv run python scripts/train.py

promote:  ## Promote the challenger if it passes the release gates
	uv run python scripts/promote_model.py

serve:  ## Run the API locally on :8000
	uv run uvicorn src.api.main:app --reload

mlflow:  ## MLflow UI on :5001
	uv run mlflow ui --backend-store-uri sqlite:///mlflow.db --port 5001

# ---------------- Cloud (see infra/README.md) ----------------
.PHONY: foundation demo-up deploy seed-mlflow demo-down inventory
# Terraform bills its own API calls to the project (needed for the Budgets API),
# so on a fresh project these must be on before Terraform can do anything
BOOTSTRAP_APIS := cloudresourcemanager.googleapis.com serviceusage.googleapis.com \
	cloudbilling.googleapis.com billingbudgets.googleapis.com

foundation:  ## Apply the long-lived stack (budget kill switch, buckets, registry, WIF)
	@test -n "$(PROJECT)" || { echo "Set project_id in infra/terraform/foundation/terraform.tfvars"; exit 1; }
	gcloud services enable $(BOOTSTRAP_APIS) --project $(PROJECT)
	$(TF)/foundation init -input=false
	$(TF)/foundation apply

demo-up:  ## Create the billable platform (GKE Autopilot + Cloud SQL)
	$(TF)/platform init -input=false
	$(TF)/platform apply

deploy:  ## Deploy :latest images to GKE from this machine (CD does this on merge)
	scripts/deploy_gke.sh $(PROJECT)

seed-mlflow:  ## Copy the local champion run + model into MLflow on GKE (after deploy)
	@kubectl -n ecg-prod port-forward svc/mlflow 5055:5000 >/dev/null 2>&1 & PF=$$!; \
	trap "kill $$PF" EXIT; \
	until curl -s -o /dev/null localhost:5055/health; do sleep 1; done; \
	uv run python scripts/seed_mlflow.py --target-uri http://localhost:5055

demo-down:  ## Delete the app (releases its load balancer), destroy the platform, verify
	-kubectl delete namespace ecg-prod --wait --timeout=5m
	$(TF)/platform destroy
	$(MAKE) inventory

inventory:  ## List everything in the project that can bill
	scripts/gcp_inventory.sh $(PROJECT)
