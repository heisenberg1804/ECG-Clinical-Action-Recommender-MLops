#!/usr/bin/env python3
# ============================================================
# FILE: scripts/evaluate_ensemble.py
# ============================================================
"""
Evaluate a probability-averaging ensemble of already-trained runs and log it to
MLflow as its own run, with the same metrics as a training run.

Members are selected by study tag (e.g. the seed-variance runs) or by run ID.
Every member was trained on the same patient-wise split, so averaging is valid.
Nothing is registered: an ensemble that wins goes through the normal gates.

Usage:
    uv run python scripts/evaluate_ensemble.py --study seed-variance
    uv run python scripts/evaluate_ensemble.py --runs <id1> <id2> <id3>
"""
import argparse
import json
import sys
from pathlib import Path

import mlflow
import numpy as np
import torch
from mlflow.tracking import MlflowClient
from torch.utils.data import DataLoader

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.ml.models.resnet1d import resnet18_1d  # noqa: E402
from src.ml.training import metrics as m  # noqa: E402
from src.ml.training.data import (  # noqa: E402
    SUPERCLASSES,
    PTBXLDataset,
    build_signal_cache,
    load_metadata,
    split_by_fold,
)
from src.ml.training.train import lineage_tags, pick_device, reliability_plot  # noqa: E402

DEFAULT_DATA = "data/ptb-xl/ptb-xl-a-large-publicly-available-electrocardiography-dataset-1.0.3"


def member_weights(client: MlflowClient, run_id: str) -> Path:
    local = PROJECT_ROOT / "models" / "runs" / run_id / "best_model.pth"
    if local.exists():
        return local
    return Path(client.download_artifacts(run_id, "serving/best_model.pth"))


@torch.no_grad()
def predict(model, loader, device) -> tuple[np.ndarray, np.ndarray]:
    probs, labels = [], []
    for x, y in loader:
        probs.append(torch.sigmoid(model(x.to(device))).cpu().numpy())
        labels.append(y.numpy())
    return np.concatenate(probs), np.concatenate(labels)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--study", help="use every finished run with tags.study = STUDY")
    g.add_argument("--runs", nargs="+", help="explicit member run IDs")
    p.add_argument("--experiment", default="ecg-ptbxl")
    p.add_argument("--data-dir", default=DEFAULT_DATA)
    p.add_argument("--run-name", default=None)
    a = p.parse_args()

    mlflow.set_tracking_uri(f"sqlite:///{PROJECT_ROOT}/mlflow.db")
    client = MlflowClient()
    exp_id = client.get_experiment_by_name(a.experiment).experiment_id
    if a.study:
        runs = client.search_runs(
            [exp_id], f"tags.study = '{a.study}' and attributes.status = 'FINISHED'"
        )
        member_ids = [r.info.run_id for r in runs]
    else:
        member_ids = a.runs
    if len(member_ids) < 2:
        print(f"Need at least 2 members, found {len(member_ids)}")
        return 1

    data_dir = PROJECT_ROOT / a.data_dir  # Absolute paths pass through `/` unchanged
    df = load_metadata(data_dir)
    splits = split_by_fold(df)
    cache = build_signal_cache(df, data_dir, PROJECT_ROOT / "data" / "cache")
    loaders = {k: DataLoader(PTBXLDataset(splits[k], cache), batch_size=128)
               for k in ("val", "test")}
    device = pick_device(None)

    val_probs, test_probs, member_auc = [], [], {}
    for run_id in member_ids:
        model = resnet18_1d(num_classes=len(SUPERCLASSES))
        model.load_state_dict(torch.load(member_weights(client, run_id), map_location="cpu",
                                         weights_only=True))
        model = model.to(device).eval()
        vp, val_true = predict(model, loaders["val"], device)
        tp, test_true = predict(model, loaders["test"], device)
        val_probs.append(vp)
        test_probs.append(tp)
        member_auc[run_id] = m.macro_auc(test_true, tp, SUPERCLASSES)
        print(f"member {run_id[:8]}: test macro AUC {member_auc[run_id]:.4f}")

    val_prob, test_prob = np.mean(val_probs, axis=0), np.mean(test_probs, axis=0)
    ev = m.evaluate(val_true, val_prob, test_true, test_prob, splits["test"], SUPERCLASSES)

    name = a.run_name or f"ensemble-{a.study or 'custom'}-{len(member_ids)}"
    with mlflow.start_run(experiment_id=exp_id, run_name=name) as run:
        mlflow.set_tags({**lineage_tags(), "study": "ensemble", "kind": "ensemble",
                         "member_study": a.study or ""})
        mlflow.log_params({"n_members": len(member_ids), "aggregation": "mean_probability",
                           "member_run_ids": ",".join(member_ids)})
        mlflow.log_metrics(m.flat_metrics(ev))
        mlflow.log_metrics({"member_auc_mean": float(np.mean(list(member_auc.values()))),
                            "member_auc_std": float(np.std(list(member_auc.values()), ddof=1))})
        out = PROJECT_ROOT / "models" / "runs" / run.info.run_id
        out.mkdir(parents=True, exist_ok=True)
        (out / "ensemble_meta.json").write_text(json.dumps(
            {"members": member_ids, "member_test_macro_auc": member_auc, **ev}, indent=2))
        reliability_plot(test_true, test_prob, out / "reliability.png")
        mlflow.log_artifacts(str(out))

    single = np.array(list(member_auc.values()))
    print(f"\nEnsemble of {len(member_ids)}: test macro AUC {ev['test_macro_auc']:.4f} "
          f"(members {single.mean():.4f} ± {single.std(ddof=1):.4f}, best {single.max():.4f})")
    print("per class: " + ", ".join(f"{c} {v:.3f}" for c, v in ev["test_per_class_auc"].items()))
    print(f"MLflow run: {run.info.run_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
