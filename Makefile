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
.PHONY: foundation demo-up demo-down inventory
foundation:  ## Apply the long-lived stack (budget kill switch, buckets, registry, WIF)
	$(TF)/foundation init -input=false
	$(TF)/foundation apply

demo-up:  ## Create the billable platform (GKE Autopilot + Cloud SQL)
	$(TF)/platform init -input=false
	$(TF)/platform apply

demo-down:  ## Destroy the billable platform, then verify nothing is left
	$(TF)/platform destroy
	$(MAKE) inventory

inventory:  ## List everything in the project that can bill
	scripts/gcp_inventory.sh $(PROJECT)
