#!/usr/bin/env python3
# ============================================================
# FILE: scripts/seed_mlflow.py
# ============================================================
"""
Copy the champion model's training run and registry entry from the local MLflow
into another MLflow server (e.g. the one on GKE after `make demo-up`).

The demo platform is ephemeral: destroying it deletes Cloud SQL, which holds
MLflow's run history and registry. Seeding recreates them from the local source
of truth, so a fresh demo shows the real run (params, full metric curves,
lineage tags, artifacts) and ecg-resnet1d@champion.

Idempotent: a run already seeded from the same source run is reused.

Usage (normally via `make seed-mlflow`, which handles the port-forward):
    uv run python scripts/seed_mlflow.py --target-uri http://localhost:5055
"""
import argparse
import sys
import tempfile
from pathlib import Path

import mlflow
import mlflow.pytorch
from mlflow.tracking import MlflowClient

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))  # The pickled model references src.ml.models

SEED_TAG = "seeded_from_run_id"


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--target-uri", required=True)
    p.add_argument("--source-uri", default=f"sqlite:///{PROJECT_ROOT}/mlflow.db")
    p.add_argument("--model-name", default="ecg-resnet1d")
    p.add_argument("--alias", default="champion")
    a = p.parse_args()

    # ---------------- Read everything from the source ----------------
    src = MlflowClient(tracking_uri=a.source_uri)
    mv = src.get_model_version_by_alias(a.model_name, a.alias)
    run = src.get_run(mv.run_id)
    experiment = src.get_experiment(run.info.experiment_id).name
    history = {k: src.get_metric_history(run.info.run_id, k) for k in run.data.metrics}
    print(f"Source: {a.model_name}@{a.alias} = v{mv.version}, run {run.info.run_id} "
          f"({experiment}/{run.info.run_name})")

    workdir = Path(tempfile.mkdtemp())
    artifacts = Path(src.download_artifacts(run.info.run_id, "", str(workdir / "artifacts")))
    mlflow.set_tracking_uri(a.source_uri)
    model = mlflow.pytorch.load_model(f"models:/{a.model_name}/{mv.version}", map_location="cpu")

    # ---------------- Write to the target ----------------
    dst = MlflowClient(tracking_uri=a.target_uri)
    mlflow.set_tracking_uri(a.target_uri)
    mlflow.set_experiment(experiment)
    exp_id = dst.get_experiment_by_name(experiment).experiment_id

    existing = dst.search_runs([exp_id], filter_string=f"tags.{SEED_TAG} = '{run.info.run_id}'")
    if existing:
        print(f"Target already has this run ({existing[0].info.run_id}); reusing it")
        target_run_id = existing[0].info.run_id
        versions = dst.search_model_versions(f"run_id = '{target_run_id}'")
        if versions:
            dst.set_registered_model_alias(a.model_name, a.alias, versions[0].version)
            print(f"{a.model_name}@{a.alias} -> v{versions[0].version}")
            return 0
    else:
        tags = {k: v for k, v in run.data.tags.items() if not k.startswith("mlflow.")}
        tags[SEED_TAG] = run.info.run_id
        with mlflow.start_run(run_name=run.info.run_name, tags=tags) as r:
            target_run_id = r.info.run_id
            mlflow.log_params(run.data.params)
            for key, points in history.items():
                for m in points:
                    dst.log_metric(target_run_id, key, m.value, timestamp=m.timestamp, step=m.step)
            mlflow.log_artifacts(str(artifacts))
        print(f"Copied run -> {target_run_id} ({len(run.data.params)} params, "
              f"{sum(len(v) for v in history.values())} metric points)")

    # Register under the target run so the registry links back to the real run
    with mlflow.start_run(run_id=target_run_id):
        # Pickle keeps forward_features/forward_head for Grad-CAM (see train.py)
        info = mlflow.pytorch.log_model(model, name="model", serialization_format="pickle",
                                        registered_model_name=a.model_name)
    dst.set_registered_model_alias(a.model_name, a.alias, info.registered_model_version)
    print(f"Registered {a.model_name} v{info.registered_model_version} -> @{a.alias}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
