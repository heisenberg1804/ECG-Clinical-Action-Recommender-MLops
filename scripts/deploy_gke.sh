#!/usr/bin/env bash
# ============================================================
# FILE: scripts/deploy_gke.sh
# ============================================================
# Deploy the prod overlay to the GKE cluster created by infra/terraform/platform.
# Used by CD and runnable locally. Needs only gcloud + kubectl + envsubst:
# everything project-specific is discovered, so no Terraform state is required.
#
# Usage: scripts/deploy_gke.sh <project-id> [image-tag]   (tag defaults to latest)
set -euo pipefail

PROJECT_ID="${1:?usage: $0 <project-id> [image-tag]}"
TAG="${2:-latest}"
REGION="${REGION:-us-central1}"
NAMESPACE=ecg-prod
REGISTRY="$REGION-docker.pkg.dev/$PROJECT_ID/ecg-repo"
cd "$(dirname "$0")/.."

echo "==> Cluster credentials"
gcloud container clusters get-credentials ecg-cluster --region "$REGION" --project "$PROJECT_ID"

echo "==> Discovering Cloud SQL instance"
SQL_CONNECTION=$(gcloud sql instances list --project "$PROJECT_ID" \
  --filter="name~^ecg-postgres-" --format="value(connectionName)" | head -1)
[[ -n "$SQL_CONNECTION" ]] || { echo "No ecg-postgres-* instance. Run 'make demo-up' first."; exit 1; }
echo "    $SQL_CONNECTION"

echo "==> Namespace and DB credentials (from Secret Manager)"
kubectl create namespace "$NAMESPACE" --dry-run=client -o yaml | kubectl apply -f -
sync_secret() {  # <k8s-secret> <db-user> <secret-manager-id>
  local password
  password=$(gcloud secrets versions access latest --secret="$3" --project "$PROJECT_ID")
  kubectl -n "$NAMESPACE" create secret generic "$1" \
    --from-literal=username="$2" --from-literal=password="$password" \
    --dry-run=client -o yaml | kubectl apply -f -
}
sync_secret ecg-db ecg_user ecg-db-password
sync_secret mlflow-db mlflow mlflow-db-password

echo "==> Tutor credentials (optional: the tutor stays off without them)"
if KEY=$(gcloud secrets versions access latest --secret=tutor-anthropic-api-key \
           --project "$PROJECT_ID" 2>/dev/null) &&
   PASS=$(gcloud secrets versions access latest --secret=tutor-passcode \
           --project "$PROJECT_ID" 2>/dev/null); then
  # Derived, so sessions survive redeploys without a third secret to manage
  SESSION_SECRET=$(printf 'ecg-tutor-session:%s' "$KEY" | shasum -a 256 | cut -c1-64)
  # Values go through a pipe, not the command line, so they never show up in `ps`
  kubectl -n "$NAMESPACE" create secret generic tutor --dry-run=client -o yaml \
    --from-env-file=<(printf 'CHAT_ENABLED=true\nANTHROPIC_API_KEY=%s\nTUTOR_PASSCODE=%s\nTUTOR_SESSION_SECRET=%s\n' \
                        "$KEY" "$PASS" "$SESSION_SECRET") | kubectl apply -f -
  TUTOR_CONFIG=$(printf '%s|%s' "$KEY" "$PASS" | shasum -a 256 | cut -c1-12)
  echo "    tutor on"
else
  kubectl -n "$NAMESPACE" delete secret tutor --ignore-not-found
  TUTOR_CONFIG=off
  echo "    tutor off (no values in Secret Manager)"
fi
unset KEY PASS SESSION_SECRET

echo "==> Applying manifests (images tagged $TAG)"
export PROJECT_ID SQL_CONNECTION
export API_IMAGE="$REGISTRY/ecg-api:$TAG"
export MLFLOW_IMAGE="$REGISTRY/ecg-mlflow:$TAG"
kubectl kustomize k8s/overlays/prod \
  | envsubst '${PROJECT_ID} ${SQL_CONNECTION} ${API_IMAGE} ${MLFLOW_IMAGE}' \
  | kubectl apply -f -

# Env from a Secret is read at pod start: roll the API only when the tutor config changes
kubectl -n "$NAMESPACE" patch deployment ecg-api --type merge \
  -p "{\"spec\":{\"template\":{\"metadata\":{\"annotations\":{\"ecg/tutor-config\":\"$TUTOR_CONFIG\"}}}}}"

echo "==> Waiting for rollouts"
kubectl -n "$NAMESPACE" rollout status deployment/mlflow --timeout=10m
kubectl -n "$NAMESPACE" rollout status deployment/ecg-api --timeout=10m

IP=$(kubectl -n "$NAMESPACE" get svc ecg-api -o jsonpath='{.status.loadBalancer.ingress[0].ip}' || true)
echo "==> Done. API: http://${IP:-<pending: re-check in a minute>}/docs"
echo "    MLflow: kubectl -n $NAMESPACE port-forward svc/mlflow 5000:5000"
