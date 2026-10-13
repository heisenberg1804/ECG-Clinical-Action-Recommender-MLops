# ============================================================
# FILE: tests/unit/test_casebank.py
# ============================================================
"""Case bank selection logic and on-disk format (synthetic data; no PTB-XL needed)."""
import numpy as np
import pytest

from src.casebank.build import display_age, primary_class, select_cases, superclass_likelihoods
from src.casebank.store import CaseBank, dequantize, quantize, write_bank
from src.ml.training.data import SUPERCLASSES


@pytest.fixture
def population():
    rng = np.random.default_rng(0)
    primary = np.array(rng.choice(SUPERCLASSES, size=2000))
    correct = rng.random(2000) > 0.3
    return primary, correct


class TestSelection:
    def test_stratified_with_error_share(self, population):
        primary, correct = population
        idx = select_cases(primary, correct, per_class=20, error_share=0.25, seed=0)
        assert len(idx) == len(set(idx)) == 100
        for cls in SUPERCLASSES:
            mine = idx[primary[idx] == cls]
            assert len(mine) == 20
            assert (~correct[mine]).sum() == 5

    def test_deterministic_and_interleaved(self, population):
        primary, correct = population
        a = select_cases(primary, correct, 20, 0.25, seed=0)
        b = select_cases(primary, correct, 20, 0.25, seed=0)
        np.testing.assert_array_equal(a, b)
        assert len(set(primary[a[:10]])) > 1  # Shuffled, not grouped by class

    def test_error_share_rounds_half_up(self, population):
        primary, correct = population
        idx = select_cases(primary, correct, per_class=2, error_share=0.25, seed=0)
        assert all((~correct[idx[primary[idx] == c]]).sum() == 1 for c in SUPERCLASSES)

    def test_takes_all_errors_when_there_are_too_few(self):
        primary = np.array(["NORM"] * 30 + ["MI"] * 30 + ["STTC"] * 30 + ["CD"] * 30 + ["HYP"] * 30)
        correct = np.ones(150, bool)
        correct[[0, 1]] = False  # Only 2 NORM errors exist
        idx = select_cases(primary, correct, per_class=20, error_share=0.25, seed=0)
        norm = idx[primary[idx] == "NORM"]
        assert len(norm) == 20 and (~correct[norm]).sum() == 2


def test_superclass_likelihoods_and_primary():
    code_to_class = {"IMI": "MI", "LVH": "HYP", "NORM": "NORM"}
    lk = superclass_likelihoods("{'IMI': 80.0, 'LVH': 100.0, 'SR': 0.0}", code_to_class)
    assert lk == {"MI": 80.0, "HYP": 100.0}
    assert primary_class(lk) == "HYP"
    assert primary_class({"MI": 50.0, "STTC": 50.0}) == "MI"  # Ties go to the earlier class


def test_display_age():
    assert display_age(300) == ">89"
    assert display_age(61.0) == "61"
    assert display_age(float("nan")) is None


class TestStore:
    def make(self, tmp_path, n=3):
        rng = np.random.default_rng(0)
        cases = [{"case_id": f"case-{i + 1:03d}", "labels": ["NORM"]} for i in range(n)]
        args = dict(
            signals=rng.normal(size=(n, 12, 2500)),
            lead_importance=rng.uniform(size=(n, 5, 12)),
            temporal=rng.uniform(size=(n, 5, 500)),
            heatmap=rng.uniform(size=(n, 5, 12, 500)),
        )
        write_bank(tmp_path, {"model_version": "resnet18-abc"}, cases, **args)
        return args

    def test_roundtrip(self, tmp_path):
        args = self.make(tmp_path)
        bank = CaseBank.load(tmp_path, expected_model_version="resnet18-abc")
        assert bank.manifest["n_cases"] == 3 and bank.index_of("case-002") == 1
        np.testing.assert_allclose(bank.signals, args["signals"], atol=1e-2)
        np.testing.assert_allclose(dequantize(bank.heatmap), args["heatmap"], atol=1 / 255)

    def test_refuses_bank_for_other_weights(self, tmp_path):
        self.make(tmp_path)
        with pytest.raises(ValueError, match="make case-bank"):
            CaseBank.load(tmp_path, expected_model_version="resnet18-other")

    def test_quantize_clips(self):
        assert quantize(np.array([-0.5, 0.0, 0.5, 1.0, 2.0])).tolist() == [0, 0, 128, 255, 255]
