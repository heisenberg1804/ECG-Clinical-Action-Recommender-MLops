# ============================================================
# FILE: src/ml/training/train.py
# ============================================================
"""
Train the 1D ResNet-18 on PTB-XL with full MLflow lineage.

Every run records: git commit, DVC data hash, split definition, config,
per-epoch curves, test metrics (overall, per class, per demographic subgroup),
calibration, tuned thresholds, and the model itself, registered in the MLflow
Model Registry under the alias "challenger". Promotion to "champion" is a
separate, explicit step (scripts/promote_model.py).
"""
import hashlib
import json
import os
import random
import subprocess
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import mlflow  # noqa: E402
import mlflow.pytorch  # noqa: E402
import numpy as np  # noqa: E402
import torch  # noqa: E402
import torch.nn as nn  # noqa: E402
import torch.nn.functional as fn  # noqa: E402
from mlflow.models import infer_signature  # noqa: E402
from mlflow.tracking import MlflowClient  # noqa: E402
from torch.utils.data import DataLoader  # noqa: E402
from tqdm import tqdm  # noqa: E402

from src.ml.models.resnet1d import resnet18_1d  # noqa: E402
from src.ml.training import metrics as m  # noqa: E402
from src.ml.training.data import (  # noqa: E402
    SUPERCLASSES,
    PTBXLDataset,
    build_signal_cache,
    load_metadata,
    split_by_fold,
)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SPLIT_NAME = "ptbxl-strat_fold: train 1-8 / val 9 / test 10"


@dataclass
class TrainConfig:
    data_dir: Path
    cache_dir: Path = PROJECT_ROOT / "data" / "cache"
    output_dir: Path = PROJECT_ROOT / "models" / "runs"
    epochs: int = 30
    batch_size: int = 64
    lr: float = 1e-3
    weight_decay: float = 1e-4
    dropout: float = 0.3
    patience: int = 5
    loss: str = "bce"  # "bce" or "focal"
    augment: bool = False  # Train-time augmentation (training split only)
    focal_gamma: float = 2.0
    num_workers: int = 4
    seed: int = 42
    device: str | None = None
    limit: int | None = None  # Records per split, for smoke tests only
    experiment: str = "ecg-ptbxl"
    run_name: str | None = None
    registered_model: str | None = "ecg-resnet1d"
    tags: dict[str, str] = field(default_factory=dict)  # e.g. {"study": "seed-variance"}


class FocalLoss(nn.Module):
    """Binary focal loss (Lin et al., 2017) for multi-label outputs."""

    def __init__(self, gamma: float = 2.0):
        super().__init__()
        self.gamma = gamma

    def forward(self, logits: torch.Tensor, targets: torch.Tensor) -> torch.Tensor:
        bce = fn.binary_cross_entropy_with_logits(logits, targets, reduction="none")
        p_t = torch.exp(-bce)
        return ((1 - p_t) ** self.gamma * bce).mean()


def seed_everything(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)


def pick_device(name: str | None) -> torch.device:
    if name:
        return torch.device(name)
    if torch.cuda.is_available():
        return torch.device("cuda")
    if torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")


def lineage_tags() -> dict[str, str]:
    """Git and DVC identifiers so any model can be traced to code + data."""
    def git(*args: str) -> str:
        try:
            return subprocess.run(
                ["git", *args], cwd=PROJECT_ROOT, capture_output=True, text=True, check=True
            ).stdout.strip()
        except (subprocess.CalledProcessError, FileNotFoundError):
            return "unknown"

    dvc_file = PROJECT_ROOT / "data" / "ptb-xl.dvc"
    data_md5 = "unknown"
    if dvc_file.exists():
        for line in dvc_file.read_text().splitlines():
            if "md5:" in line:
                data_md5 = line.split("md5:")[1].strip()
                break
    return {
        "git_commit": git("rev-parse", "HEAD"),
        "git_dirty": str(bool(git("status", "--porcelain", "--untracked-files=no"))),
        "data_dvc_md5": data_md5,
        "split": SPLIT_NAME,
    }


def run_epoch(
    model, loader, criterion, device, optimizer=None
) -> tuple[float, np.ndarray, np.ndarray]:
    """One pass over loader. Trains if an optimizer is given; returns loss, probs, labels."""
    training = optimizer is not None
    model.train(training)
    total, probs, labels = 0.0, [], []
    with torch.set_grad_enabled(training):
        for x, y in tqdm(loader, desc="train" if training else "eval", leave=False):
            x, y = x.to(device), y.to(device)
            logits = model(x)
            loss = criterion(logits, y)
            if training:
                optimizer.zero_grad()
                loss.backward()
                optimizer.step()
            total += loss.item() * len(x)
            probs.append(torch.sigmoid(logits).detach().cpu().numpy())
            labels.append(y.cpu().numpy())
    return total / len(loader.dataset), np.concatenate(probs), np.concatenate(labels)


def reliability_plot(y_true: np.ndarray, y_prob: np.ndarray, path: Path) -> None:
    fig, ax = plt.subplots(figsize=(5, 5))
    ax.plot([0, 1], [0, 1], "k--", lw=1, label="perfect")
    edges = np.linspace(0, 1, 11)
    for i, c in enumerate(SUPERCLASSES):
        idx = np.digitize(y_prob[:, i], edges[1:-1])
        conf = [y_prob[idx == b, i].mean() for b in range(10) if (idx == b).any()]
        acc = [y_true[idx == b, i].mean() for b in range(10) if (idx == b).any()]
        ax.plot(conf, acc, marker="o", ms=3, label=c)
    ax.set(xlabel="Predicted probability", ylabel="Observed frequency",
           title="Calibration (test fold 10)")
    ax.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def train(cfg: TrainConfig) -> dict:
    seed_everything(cfg.seed)
    device = pick_device(cfg.device)
    data_dir = Path(cfg.data_dir).expanduser()

    # ---------------- Data ----------------
    df = load_metadata(data_dir)
    splits = split_by_fold(df)
    if cfg.limit:
        splits = {k: v.sample(min(cfg.limit, len(v)), random_state=cfg.seed)
                  for k, v in splits.items()}
    cache_dir = build_signal_cache(df, data_dir, Path(cfg.cache_dir))
    datasets = {k: PTBXLDataset(v, cache_dir, augment=cfg.augment and k == "train")
                for k, v in splits.items()}
    loader_kw = dict(batch_size=cfg.batch_size, num_workers=cfg.num_workers,
                     persistent_workers=cfg.num_workers > 0)
    loaders = {k: DataLoader(ds, shuffle=(k == "train"), **loader_kw) for k, ds in datasets.items()}
    print(f"Device {device} | " + " | ".join(f"{k}: {len(v)}" for k, v in splits.items()))

    # ---------------- Model ----------------
    model = resnet18_1d(num_classes=len(SUPERCLASSES), dropout_rate=cfg.dropout).to(device)
    criterion = FocalLoss(cfg.focal_gamma) if cfg.loss == "focal" else nn.BCEWithLogitsLoss()
    optimizer = torch.optim.AdamW(model.parameters(), lr=cfg.lr, weight_decay=cfg.weight_decay)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(optimizer, mode="max", factor=0.5,
                                                           patience=2)

    mlflow.set_tracking_uri(os.getenv("MLFLOW_TRACKING_URI", f"sqlite:///{PROJECT_ROOT}/mlflow.db"))
    mlflow.set_experiment(cfg.experiment)

    with mlflow.start_run(run_name=cfg.run_name) as run:
        # Captured once, at start: commits made mid-run must not change the recorded lineage
        lineage = lineage_tags()
        mlflow.set_tags({**lineage, **cfg.tags})
        mlflow.log_params({k: str(v) for k, v in asdict(cfg).items() if k != "tags"})
        mlflow.log_params({f"n_{k}": len(v) for k, v in splits.items()})

        # ---------------- Train with early stopping on val macro AUC ----------------
        best_auc, best_state, best_epoch, stale = -1.0, None, 0, 0
        t0 = time.time()
        for epoch in range(1, cfg.epochs + 1):
            train_loss, _, _ = run_epoch(model, loaders["train"], criterion, device, optimizer)
            val_loss, val_prob, val_true = run_epoch(model, loaders["val"], criterion, device)
            val_auc = m.macro_auc(val_true, val_prob, SUPERCLASSES)
            scheduler.step(val_auc)
            mlflow.log_metrics({
                "train_loss": train_loss, "val_loss": val_loss, "val_macro_auc": val_auc,
                "lr": optimizer.param_groups[0]["lr"],
            }, step=epoch)
            print(f"epoch {epoch:2d} | train {train_loss:.4f} | val {val_loss:.4f} "
                  f"| val AUC {val_auc:.4f}")

            if val_auc > best_auc:
                best_auc, best_epoch, stale = val_auc, epoch, 0
                best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
            else:
                stale += 1
                if stale >= cfg.patience:
                    print(f"Early stopping at epoch {epoch} (best {best_epoch})")
                    break

        model.load_state_dict(best_state)
        mlflow.log_metrics({"best_val_macro_auc": best_auc, "best_epoch": best_epoch,
                            "train_minutes": (time.time() - t0) / 60})

        # ---------------- Evaluate: thresholds from val, metrics on test ----------------
        _, val_prob, val_true = run_epoch(model, loaders["val"], criterion, device)
        _, test_prob, test_true = run_epoch(model, loaders["test"], criterion, device)
        ev = m.evaluate(val_true, val_prob, test_true, test_prob, splits["test"], SUPERCLASSES)
        mlflow.log_metrics(m.flat_metrics(ev))
        thresholds = ev["thresholds"]
        test_auc, class_auc = ev["test_macro_auc"], ev["test_per_class_auc"]

        # ---------------- Artifacts ----------------
        out_dir = Path(cfg.output_dir) / run.info.run_id
        out_dir.mkdir(parents=True, exist_ok=True)
        weights_path = out_dir / "best_model.pth"
        model_cpu = model.to("cpu").eval()
        torch.save(model_cpu.state_dict(), weights_path)
        digest = hashlib.sha256(weights_path.read_bytes()).hexdigest()[:12]

        meta = {
            "model_version": f"resnet18-{digest}",
            "mlflow_run_id": run.info.run_id,
            "classes": SUPERCLASSES,
            "thresholds": thresholds,
            "split": SPLIT_NAME,
            **{k: v for k, v in ev.items() if k != "thresholds"},
            **lineage,
        }
        (out_dir / "model_meta.json").write_text(json.dumps(meta, indent=2))
        reliability_plot(test_true, test_prob, out_dir / "reliability.png")
        # Exact serving artifacts: promotion copies these, so the sha in
        # model_version matches the file the API loads
        mlflow.log_artifact(str(weights_path), artifact_path="serving")
        mlflow.log_artifact(str(out_dir / "model_meta.json"), artifact_path="serving")
        mlflow.log_artifact(str(out_dir / "reliability.png"))

        example = np.zeros((1, 12, 5000), dtype=np.float32)
        with torch.no_grad():
            signature = infer_signature(example, model_cpu(torch.from_numpy(example)).numpy())
        info = mlflow.pytorch.log_model(
            model_cpu, name="model", signature=signature,
            registered_model_name=cfg.registered_model,
        )
        if cfg.registered_model and info.registered_model_version:
            MlflowClient().set_registered_model_alias(
                cfg.registered_model, "challenger", info.registered_model_version
            )
            mlflow.set_tag("registered_version", info.registered_model_version)

        print(f"\nTest macro AUC {test_auc:.4f} | per class "
              + ", ".join(f"{c} {v:.3f}" for c, v in class_auc.items()))
        print(f"Artifacts: {out_dir}\nMLflow run: {run.info.run_id}")
        return meta
