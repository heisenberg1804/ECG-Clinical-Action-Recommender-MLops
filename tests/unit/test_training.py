# ============================================================
# FILE: tests/unit/test_training.py
# ============================================================
"""Training data pipeline and metrics, on small synthetic fixtures (no PTB-XL needed)."""
import numpy as np
import pandas as pd
import pytest

from src.ml.training import metrics as m
from src.ml.training.data import SUPERCLASSES, load_metadata, split_by_fold


@pytest.fixture
def ptbxl_dir(tmp_path):
    pd.DataFrame({
        "ecg_id": [1, 2, 3, 4, 5],
        "patient_id": [10, 10, 11, 12, 13],
        "scp_codes": [
            "{'NORM': 100.0, 'SR': 0.0}",      # NORM (SR is a rhythm code, ignored)
            "{'IMI': 50.0, 'LVH': 100.0}",     # MI + HYP
            "{'NDT': 100.0}",                  # STTC
            "{'SR': 0.0}",                     # no diagnostic class -> dropped
            "{'CLBBB': 100.0, 'ISCAL': 80.0}",  # CD + STTC
        ],
        "strat_fold": [1, 1, 9, 5, 10],
    }).to_csv(tmp_path / "ptbxl_database.csv", index=False)
    pd.DataFrame({
        "code": ["NORM", "IMI", "LVH", "NDT", "CLBBB", "ISCAL", "SR"],
        "diagnostic": [1, 1, 1, 1, 1, 1, None],
        "diagnostic_class": ["NORM", "MI", "HYP", "STTC", "CD", "STTC", None],
    }).to_csv(tmp_path / "scp_statements.csv", index=False)
    return tmp_path


class TestData:
    def test_official_superclass_aggregation(self, ptbxl_dir):
        df = load_metadata(ptbxl_dir)
        assert list(df.index) == [1, 2, 3, 5]  # record 4 has no diagnostic class
        assert df.loc[2, "superclasses"] == ["HYP", "MI"]
        assert df.loc[5, "labels"] == [0, 0, 1, 1, 0]
        assert all(len(lbl) == len(SUPERCLASSES) for lbl in df.labels)

    def test_split_uses_strat_fold(self, ptbxl_dir):
        splits = split_by_fold(load_metadata(ptbxl_dir))
        assert list(splits["train"].index) == [1, 2]
        assert list(splits["val"].index) == [3]
        assert list(splits["test"].index) == [5]

    def test_patients_do_not_cross_splits(self, ptbxl_dir):
        splits = split_by_fold(load_metadata(ptbxl_dir))
        patients = [set(s.patient_id) for s in splits.values()]
        assert not (patients[0] & patients[1] or patients[0] & patients[2]
                    or patients[1] & patients[2])


class TestMetrics:
    classes = ["A", "B"]

    def test_tune_thresholds_separates_perfect_scores(self):
        y = np.array([[0, 1], [0, 1], [1, 0], [1, 0]])
        p = np.array([[0.1, 0.8], [0.2, 0.9], [0.7, 0.3], [0.9, 0.2]])
        th = m.tune_thresholds(y, p, self.classes)
        assert 0.2 < th["A"] <= 0.7 and 0.3 < th["B"] <= 0.8
        metrics = m.threshold_metrics(y, p, self.classes, th)
        assert metrics["A"] == {"f1": 1.0, "sensitivity": 1.0, "specificity": 1.0}

    def test_ece_is_zero_when_calibrated(self):
        y = np.array([0] * 8 + [1] * 2)
        p = np.full(10, 0.2)
        assert m.expected_calibration_error(y, p) == pytest.approx(0.0)

    def test_ece_detects_overconfidence(self):
        y = np.array([0] * 5 + [1] * 5)
        assert m.expected_calibration_error(y, np.full(10, 0.95)) == pytest.approx(0.45)

    def test_subgroup_auc_handles_ptbxl_age_encoding(self):
        rng = np.random.default_rng(0)
        y = rng.integers(0, 2, size=(40, 2))
        p = np.clip(y + rng.normal(0, 0.4, size=y.shape), 0, 1)
        meta = pd.DataFrame({"sex": [0, 1] * 20, "age": [30, 50, 70, 300] * 10})
        groups = m.subgroup_auc(y, p, meta, self.classes)
        assert set(groups) == {"sex_male", "sex_female", "age_lt40", "age_40to65", "age_gt65"}
        assert all(0.5 < v <= 1.0 for v in groups.values())


def test_evaluate_and_flat_metrics_names():
    """Metric names are a contract with every past MLflow run and the promotion gates."""
    rng = np.random.default_rng(1)
    classes = ["A", "B"]
    y = rng.integers(0, 2, size=(60, 2))
    p = np.clip(y * 0.6 + rng.uniform(0, 0.4, size=y.shape), 0, 1)
    meta = pd.DataFrame({"sex": [0, 1] * 30, "age": [30, 50, 70] * 20})
    flat = m.flat_metrics(m.evaluate(y, p, y, p, meta, classes))
    expected = {"test_macro_auc", "test_auc_A", "test_f1_A", "test_sensitivity_A",
                "test_specificity_A", "test_ece_A", "test_auc_sex_male", "test_auc_sex_female",
                "test_auc_age_lt40", "test_auc_age_40to65", "test_auc_age_gt65"}
    assert expected <= set(flat)
