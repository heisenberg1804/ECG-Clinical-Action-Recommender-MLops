#!/usr/bin/env bash
# ============================================================
# FILE: scripts/deploy-minikube.sh
# ============================================================
# Deploy the full local stack (API + Postgres + MLflow) to minikube.
# DB credentials are generated here, so none live in git.
set -euo pipefail
cd "$(dirname "$0")/.."
NAMESPACE=ecg-dev

minikube status >/dev/null 2>&1 || { echo "Minikube not running. Start with: minikube start --memory 6g"; exit 1; }

echo "==> Building images inside minikube"
eval "$(minikube docker-env)"
docker build -t ecg-api:local -f docker/Dockerfile.api .
docker build -t ecg-mlflow:local -f docker/Dockerfile.mlflow .

echo "==> Namespace and credentials"
kubectl create namespace "$NAMESPACE" --dry-run=client -o yaml | kubectl apply -f -
if ! kubectl -n "$NAMESPACE" get secret ecg-db >/dev/null 2>&1; then
  password=$(openssl rand -hex 16)
  # Locally, MLflow uses the same Postgres user (it owns the mlflow database)
  for name in ecg-db mlflow-db; do
    kubectl -n "$NAMESPACE" create secret generic "$name" \
      --from-literal=username=ecg_user --from-literal=password="$password"
  done
fi

echo "==> Applying k8s/base"
kubectl apply -k k8s/base/
for d in postgres mlflow ecg-api; do
  kubectl -n "$NAMESPACE" rollout status "deployment/$d" --timeout=5m
done

echo "==> Ready"
echo "    API:    kubectl -n $NAMESPACE port-forward svc/ecg-api 8000:80     -> http://localhost:8000/docs"
echo "    MLflow: kubectl -n $NAMESPACE port-forward svc/mlflow 5000:5000    -> http://localhost:5000"
