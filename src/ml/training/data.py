# ============================================================
# FILE: src/ml/training/data.py
# ============================================================
"""
PTB-XL data pipeline for training.

- Labels: official superclass aggregation via scp_statements.csv
- Splits: the dataset's recommended patient-wise stratified folds
  (folds 1-8 train, 9 validation, 10 test). All records of a patient share
  a fold, so no patient appears in more than one split.
- Signals: decoded once into a float16 memmap cache, then normalized per
  item with the same prepare_ecg() used at inference.
"""
import ast
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd
import torch
import wfdb
from torch.utils.data import Dataset
from tqdm import tqdm

from src.ml.preprocessing.signal import N_LEADS, TARGET_SAMPLES, prepare_ecg

SUPERCLASSES = ['NORM', 'MI', 'STTC', 'CD', 'HYP']
TRAIN_FOLDS = tuple(range(1, 9))
VAL_FOLDS = (9,)
TEST_FOLDS = (10,)


def load_metadata(data_dir: Path) -> pd.DataFrame:
    """
    Load PTB-XL metadata with multi-hot superclass labels.

    Records without any diagnostic superclass are dropped, as in the
    PTB-XL benchmark (Strodthoff et al., 2020).
    """
    df = pd.read_csv(data_dir / "ptbxl_database.csv", index_col="ecg_id")
    scp = pd.read_csv(data_dir / "scp_statements.csv", index_col=0)
    code_to_class = scp[scp.diagnostic == 1].diagnostic_class.to_dict()

    def superclasses(scp_codes: str) -> list[str]:
        codes = ast.literal_eval(scp_codes)
        return sorted({code_to_class[c] for c in codes if c in code_to_class})

    df["superclasses"] = df.scp_codes.apply(superclasses)
    df = df[df.superclasses.apply(len) > 0].copy()
    df["labels"] = df.superclasses.apply(lambda s: [int(c in s) for c in SUPERCLASSES])
    return df


def split_by_fold(df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Split on PTB-XL's strat_fold column."""
    return {
        "train": df[df.strat_fold.isin(TRAIN_FOLDS)],
        "val": df[df.strat_fold.isin(VAL_FOLDS)],
        "test": df[df.strat_fold.isin(TEST_FOLDS)],
    }


def _read_record(path: str) -> np.ndarray:
    signal, _ = wfdb.rdsamp(path)  # (5000, 12)
    return signal.T.astype(np.float16)


def build_signal_cache(df: pd.DataFrame, data_dir: Path, cache_dir: Path) -> Path:
    """
    Decode every record once into a (N, 12, 5000) float16 memmap.

    The index file maps ecg_id -> row so the cache is reusable across splits.
    Rebuilt only if the set of ecg_ids changes.
    """
    cache_dir.mkdir(parents=True, exist_ok=True)
    signals_path = cache_dir / "signals_500hz_f16.npy"
    index_path = cache_dir / "index.json"
    ecg_ids = [int(i) for i in df.index]

    if signals_path.exists() and index_path.exists():
        if json.loads(index_path.read_text()) == ecg_ids:
            return cache_dir

    paths = [str(data_dir / f) for f in df.filename_hr]
    cache = np.lib.format.open_memmap(
        signals_path, mode="w+", dtype=np.float16,
        shape=(len(paths), N_LEADS, TARGET_SAMPLES),
    )
    # Threads, not processes: record reads are I/O bound, and this avoids
    # spawn issues on macOS / inside Airflow workers
    with ThreadPoolExecutor(max_workers=8) as pool:
        for i, sig in enumerate(tqdm(
            pool.map(_read_record, paths),
            total=len(paths), desc="Caching signals",
        )):
            cache[i] = sig
    cache.flush()
    index_path.write_text(json.dumps(ecg_ids))
    return cache_dir


def augment_ecg(signal: np.ndarray, rng: np.random.Generator, fs: int = 500) -> np.ndarray:
    """
    Train-time augmentation on a preprocessed (z-scored) 12-lead signal.

    Only transforms that survive per-lead normalization are used. Amplitude
    scaling would be undone by the z-score at inference and would create a
    train/serve mismatch.
    - Gaussian noise (sensor noise)
    - Baseline wander: low-frequency drift from breathing or movement
    - Time shift of up to 0.5 s, padded with edge values (no wrap-around)
    - Lead dropout: one lead zeroed (a detached electrode)
    """
    x = signal.copy()
    n_leads, n = x.shape
    if rng.random() < 0.5:
        x += rng.normal(0, 0.05, size=x.shape).astype(np.float32)
    if rng.random() < 0.5:
        t = np.arange(n) / fs
        freq, phase = rng.uniform(0.05, 0.5), rng.uniform(0, 2 * np.pi)
        x += (rng.uniform(0.05, 0.2) * np.sin(2 * np.pi * freq * t + phase)).astype(np.float32)
    if rng.random() < 0.5:
        shift = int(rng.integers(-fs // 2, fs // 2 + 1))
        if shift > 0:
            x = np.concatenate([np.repeat(x[:, :1], shift, axis=1), x[:, :-shift]], axis=1)
        elif shift < 0:
            x = np.concatenate([x[:, -shift:], np.repeat(x[:, -1:], -shift, axis=1)], axis=1)
    if rng.random() < 0.2:
        x[rng.integers(n_leads)] = 0.0
    return x


class PTBXLDataset(Dataset):
    """Serves (signal, labels) from the memmap cache."""

    def __init__(self, df: pd.DataFrame, cache_dir: Path, augment: bool = False):
        index = json.loads((cache_dir / "index.json").read_text())
        row_of = {ecg_id: row for row, ecg_id in enumerate(index)}
        self.rows = np.array([row_of[int(i)] for i in df.index])
        self.labels = np.stack(df.labels.values).astype(np.float32)
        self.signals_path = cache_dir / "signals_500hz_f16.npy"
        self._signals = None  # Opened lazily so each DataLoader worker gets its own handle
        self.augment = augment
        self._rng = None  # Per worker, seeded from torch so runs are reproducible

    def __len__(self) -> int:
        return len(self.rows)

    def __getitem__(self, idx: int) -> tuple[torch.Tensor, torch.Tensor]:
        if self._signals is None:
            self._signals = np.load(self.signals_path, mmap_mode="r")
        signal = prepare_ecg(self._signals[self.rows[idx]].astype(np.float32))
        if self.augment:
            if self._rng is None:
                self._rng = np.random.default_rng(torch.initial_seed() % 2**32)
            signal = augment_ecg(signal, self._rng)
        return torch.from_numpy(signal), torch.from_numpy(self.labels[idx])
