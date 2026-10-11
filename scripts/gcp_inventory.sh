#!/usr/bin/env bash
# ============================================================
# FILE: scripts/gcp_inventory.sh
# ============================================================
# Read-only audit of everything in a GCP project that can cost money.
# Run it after every demo / `terraform destroy` to confirm nothing is left.
# Never prompts and never enables APIs.
#
# Usage: scripts/gcp_inventory.sh <project-id> [account]
set -uo pipefail
export CLOUDSDK_CORE_DISABLE_PROMPTS=1

PROJECT="${1:?usage: $0 <project-id> [account]}"
ACCOUNT_FLAG=""
[[ -n "${2:-}" ]] && ACCOUNT_FLAG="--account=$2"

# Run a gcloud list command; collapse well-known errors to one line.
g() {
  local out status
  # shellcheck disable=SC2086  # ACCOUNT_FLAG is intentionally unquoted (may be empty)
  out=$(gcloud "$@" --project="$PROJECT" $ACCOUNT_FLAG --quiet 2>&1)
  status=$?
  out=$(grep -v "environment' tag" <<<"$out")
  if grep -q "SERVICE_DISABLED\|has not been used in project" <<<"$out"; then
    echo "  (API not enabled: none of these exist)"
  elif grep -q "BILLING_DISABLED\|requires billing to be enabled" <<<"$out"; then
    echo "  (can't list: billing disabled, so not billable)"
  elif [[ $status -ne 0 ]]; then
    # Unknown failure: never report "none" when we couldn't actually look
    echo "  !! FAILED to list - check manually:"
    grep -m1 "ERROR" <<<"$out" | sed 's/^/     /'
  elif [[ -z "$out" ]]; then
    echo "  (none)"
  else
    sed 's/^/  /' <<<"$out"
  fi
}

section() { printf '\n== %s\n' "$1"; }

section "Project"
g projects describe "$PROJECT" --format="value(projectId,name,lifecycleState)"
# shellcheck disable=SC2086
billing=$(gcloud billing projects describe "$PROJECT" $ACCOUNT_FLAG \
          --format="value(billingEnabled)" 2>/dev/null)
case "$billing" in
  True)  echo "  Billing: ENABLED - resources below can accrue charges" ;;
  False) echo "  Billing: DISABLED - nothing in this project is accruing charges" ;;
  *)     echo "  !! Billing status unknown (no access?) - check the console" ;;
esac

section "GKE clusters"
g container clusters list --format="table(name,location,status,currentNodeCount,autopilot.enabled)"

section "Cloud SQL instances (billed per hour while RUNNABLE)"
g sql instances list --format="table(name,databaseVersion,settings.tier,state,region)"

section "Compute VMs"
g compute instances list --format="table(name,zone,status,machineType.basename())"

section "Persistent disks (billed even when unattached)"
g compute disks list --format="table(name,zone,sizeGb,users.len():label=ATTACHED)"

section "Static IPs (billed when reserved but unused)"
g compute addresses list --format="table(name,region,address,status)"

section "Load balancers / forwarding rules"
g compute forwarding-rules list --format="table(name,region,IPAddress,target.basename())"

section "Artifact Registry repositories"
g artifacts repositories list --format="table(name.basename(),location,format,sizeBytes.size())"

section "Cloud Storage buckets (sizes: console > Cloud Storage; listing objects is slow)"
g storage buckets list --format="table(name,location,default_storage_class)"

section "Cloud Run services"
g run services list --format="table(metadata.name,region,status.url)"
