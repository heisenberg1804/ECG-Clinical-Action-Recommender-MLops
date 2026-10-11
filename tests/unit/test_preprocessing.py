# ============================================================
# FILE: tests/unit/test_preprocessing.py
# ============================================================
import numpy as np
import pytest

from src.ml.preprocessing.signal import normalize_signal, prepare_ecg


@pytest.fixture
def signal():
    return np.random.default_rng(0).normal(size=(12, 5000)) * 10 + 5


class TestNormalize:
    def test_zero_mean_unit_variance(self, signal):
        x = normalize_signal(signal)
        np.testing.assert_allclose(x.mean(axis=1), 0, atol=1e-5)
        np.testing.assert_allclose(x.std(axis=1), 1, atol=1e-4)

    def test_flat_lead_is_finite(self):
        assert np.isfinite(normalize_signal(np.ones((12, 5000)))).all()


class TestPrepareEcg:
    def test_output_contract(self, signal):
        x = prepare_ecg(signal)
        assert x.shape == (12, 5000)
        assert x.dtype == np.float32

    def test_accepts_samples_by_leads(self, signal):
        np.testing.assert_allclose(prepare_ecg(signal.T), prepare_ecg(signal))

    def test_resamples_by_duration(self):
        ten_s_at_250 = np.random.default_rng(0).normal(size=(12, 2500))
        assert prepare_ecg(ten_s_at_250, sampling_rate=250).shape == (12, 5000)

    def test_crops_to_first_10s(self, signal):
        twenty_s = np.concatenate([signal, signal * 0], axis=1)
        np.testing.assert_allclose(prepare_ecg(twenty_s), prepare_ecg(signal))

    def test_rejects_short(self):
        with pytest.raises(ValueError, match="at least 10 s"):
            prepare_ecg(np.zeros((12, 4999)))

    def test_rejects_wrong_lead_count(self):
        with pytest.raises(ValueError, match="12-lead"):
            prepare_ecg(np.zeros((8, 5000)))
