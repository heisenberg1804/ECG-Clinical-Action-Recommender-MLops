# ============================================================
# FILE: src/casebank/store.py
# ============================================================
"""
On-disk format and loader for the case bank (D-54).

The case bank is a fixed set of test-fold ECGs with every model output
precomputed, so the UI and the tutor read lookups instead of running the model.

Layout of a bank directory:
    manifest.json      schema version, model_version, lineage, display rates
    cases.json         per-case metadata, labels and model outputs (no signals)
    signals.npz        display signals, float16 mV, shape (N, 12, n_display)
    explanations.npz   per-case, per-class attributions at the heatmap rate:
                       lead_importance (N, C, 12) float16,
                       temporal (N, C, T) uint8, heatmap (N, C, 12, T) uint8
"""
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

SCHEMA_VERSION = 1


def quantize(x: np.ndarray) -> np.ndarray:
    """Map [0, 1] attributions to uint8 (1/255 resolution is far below what a heatmap shows)."""
    return np.round(np.clip(x, 0.0, 1.0) * 255).astype(np.uint8)


def dequantize(x: np.ndarray) -> np.ndarray:
    return x.astype(np.float32) / 255.0


def write_bank(
    out_dir: Path,
    manifest: dict,
    cases: list[dict],
    signals: np.ndarray,
    lead_importance: np.ndarray,
    temporal: np.ndarray,
    heatmap: np.ndarray,
) -> None:
    """Write a bank. Arrays are indexed in the same order as `cases`."""
    n = len(cases)
    sizes = {a.shape[0] for a in (signals, lead_importance, temporal, heatmap)}
    assert sizes == {n}, f"array lengths {sizes} don't match {n} cases"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "manifest.json").write_text(
        json.dumps({**manifest, "schema_version": SCHEMA_VERSION, "n_cases": n}, indent=2)
    )
    (out_dir / "cases.json").write_text(json.dumps(cases, indent=1))
    np.savez_compressed(out_dir / "signals.npz", signals=signals.astype(np.float16))
    np.savez_compressed(
        out_dir / "explanations.npz",
        lead_importance=lead_importance.astype(np.float16),
        temporal=quantize(temporal),
        heatmap=quantize(heatmap),
    )


@dataclass
class CaseBank:
    manifest: dict
    cases: list[dict]
    signals: np.ndarray
    lead_importance: np.ndarray
    temporal: np.ndarray
    heatmap: np.ndarray

    @classmethod
    def load(cls, bank_dir: Path, expected_model_version: str | None = None) -> "CaseBank":
        """
        Load a bank, refusing one built for different weights.

        Raises:
            ValueError: unknown schema, or model_version mismatch (the bank's
                        predictions and explanations would not match the served model)
        """
        manifest = json.loads((bank_dir / "manifest.json").read_text())
        if manifest.get("schema_version") != SCHEMA_VERSION:
            raise ValueError(f"Unsupported case bank schema {manifest.get('schema_version')}")
        if expected_model_version and manifest["model_version"] != expected_model_version:
            raise ValueError(
                f"Case bank was built for {manifest['model_version']}, "
                f"but the served model is {expected_model_version}. Rebuild it: make case-bank"
            )
        cases = json.loads((bank_dir / "cases.json").read_text())
        sig = np.load(bank_dir / "signals.npz")
        exp = np.load(bank_dir / "explanations.npz")
        return cls(
            manifest=manifest,
            cases=cases,
            signals=sig["signals"],
            lead_importance=exp["lead_importance"],
            temporal=exp["temporal"],
            heatmap=exp["heatmap"],
        )

    def index_of(self, case_id: str) -> int:
        for i, c in enumerate(self.cases):
            if c["case_id"] == case_id:
                return i
        raise KeyError(case_id)
