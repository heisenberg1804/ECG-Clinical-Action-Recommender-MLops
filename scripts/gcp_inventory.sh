#!/usr/bin/env bash
# ============================================================
# FILE: scripts/gcp_inventory.sh
# ============================================================
# Read-only audit of everything in a GCP project that can cost money.
# Run it after every demo / `terraform destroy` to confirm nothing is left.
#
# Usage: scripts/gcp_inventory.sh <project-id> [account]
set -uo pipefail

PROJECT="${1:?usage: $0 <project-id> [account]}"
ACCOUNT_FLAG=()
[[ -n "${2:-}" ]] && ACCOUNT_FLAG=(--account="$2")
g() { gcloud "$@" --project="$PROJECT" "${ACCOUNT_FLAG[@]}" 2>&1 | grep -v "environment' tag"; }

section() { printf '\n== %s\n' "$1"; }

section "Project"
g projects describe "$PROJECT" --format="value(projectId,name,lifecycleState)"
g billing projects describe "$PROJECT" --format="value(billingEnabled,billingAccountName)"

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

section "Cloud Storage buckets"
for b in $(g storage buckets list --format="value(name)"); do
  printf '%s\t' "gs://$b"; g storage du -s -r "gs://$b" | awk '{print $1" bytes"}'
done

section "Cloud Run services"
g run services list --format="table(metadata.name,region,status.url)"
