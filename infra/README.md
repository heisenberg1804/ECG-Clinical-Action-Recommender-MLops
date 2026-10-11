# Infrastructure

Everything in GCP is defined in Terraform and split into two stacks with
different lifetimes:

| Stack | Contents | Lifetime | Approx. cost |
|---|---|---|---|
| `terraform/foundation` | Budget + **kill switch**, DVC and MLflow buckets, Artifact Registry, GitHub Workload Identity Federation | Permanent | Cents per month (storage) |
| `terraform/platform` | GKE Autopilot cluster, Cloud SQL Postgres (prediction log + MLflow backend), workload identities, DB passwords in Secret Manager | **Up for demos only** | Roughly $1–2 per day while up |

Costs are rough estimates; check the [GCP pricing calculator](https://cloud.google.com/products/calculator).
The kill switch exists because estimates can be wrong.

## Cost guardrails

1. **Budget alerts** at 50%, 90% and 100% of actual spend, plus 100% of
   forecast, emailed to `alert_emails`.
2. **Hard cap.** At 100% of *actual* spend, the `budget-kill-switch` Cloud
   Function unlinks billing from the project, which stops all billable
   resources. Budget data lags by a few hours, so spend can overshoot slightly.
   Re-link billing in the console to recover; GKE and Cloud SQL may need
   recreating with `make demo-up`.
3. **Ephemeral platform.** `make demo-down` destroys GKE and Cloud SQL, then
   runs `scripts/gcp_inventory.sh` to confirm nothing billable remains.

## One-time setup

```bash
# 1. Pin gcloud to the account that owns this project
gcloud config configurations create ecg
gcloud config set account chik.sahil18@gmail.com
gcloud auth login && gcloud auth application-default login

# 2. Create the project and link billing (pick a globally unique ID)
gcloud projects create ecg-mlops-<suffix> --name="ECG MLOps"
gcloud config set project ecg-mlops-<suffix>
gcloud billing projects link ecg-mlops-<suffix> --billing-account=<BILLING_ID>
gcloud auth application-default set-quota-project ecg-mlops-<suffix>

# 3. Apply the foundation stack
cp infra/terraform/foundation/terraform.tfvars.example infra/terraform/foundation/terraform.tfvars
#    edit project_id, billing_account, alert_emails
make foundation
```

Then, under GitHub → Settings → Secrets and variables → Actions → **Variables**,
add these repository variables from `terraform -chdir=infra/terraform/foundation output`:

| Variable | Value |
|---|---|
| `GCP_PROJECT_ID` | your project ID |
| `GCP_WIF_PROVIDER` | `github_wif_provider` output |
| `GCP_DEPLOYER_SA` | `github_deployer_sa` output |

Finally, point DVC at the new bucket and upload the dataset:

```bash
uvx --with dvc-gs dvc remote modify gcs url "$(terraform -chdir=infra/terraform/foundation output -raw dvc_remote)"
uvx --with dvc-gs dvc push
```

## Demo lifecycle

```bash
make demo-up           # ~10-15 min: GKE Autopilot + Cloud SQL
# set repo variable DEPLOY_ENABLED=true, then merge or re-run CD to deploy
make demo-down         # destroy + inventory check
# set DEPLOY_ENABLED back to false (or delete it)
```

## Notes

- **State is local** (`terraform.tfstate`, gitignored). The platform state
  contains the generated DB passwords, so keep it on your machine. A GCS
  backend is the natural next step if more than one person applies.
- Cloud SQL instance names can't be reused for about a week after deletion,
  so each `demo-up` creates a new name with a random suffix.
- WIF only issues credentials to workflows from this repository's `main`
  branch; there is no service-account key anywhere.
