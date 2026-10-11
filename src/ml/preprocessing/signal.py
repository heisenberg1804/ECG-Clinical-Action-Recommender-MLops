# ============================================================
# FILE: src/ml/preprocessing/signal.py
# ============================================================
"""
ECG preprocessing shared by training and serving.

Both the training dataset and the inference predictor call prepare_ecg(),
so there is exactly one definition of what the model sees (no train/serve skew).
"""
import numpy as np
from scipy.signal import resample

TARGET_FS = 500  # Hz the model is trained on
TARGET_SAMPLES = 5000  # 10 s at 500 Hz
N_LEADS = 12


def normalize_signal(ecg_signal: np.ndarray) -> np.ndarray:
    """
    Z-score each lead independently.

    Args:
        ecg_signal: ECG signal array, shape (n_leads, n_samples)

    Returns:
        Normalized float32 signal; flat leads become all zeros
    """
    mean = ecg_signal.mean(axis=1, keepdims=True)
    std = ecg_signal.std(axis=1, keepdims=True)
    return ((ecg_signal - mean) / (std + 1e-8)).astype(np.float32)


def prepare_ecg(ecg_signal: np.ndarray, sampling_rate: int = TARGET_FS) -> np.ndarray:
    """
    Convert a raw 12-lead ECG into the model's input format.

    Steps: orient to (12, n) -> resample to 500 Hz by duration -> take the
    first 10 s -> per-lead z-score.

    Args:
        ecg_signal: Raw ECG, shape (12, n_samples) or (n_samples, 12)
        sampling_rate: Sampling rate of ecg_signal in Hz

    Returns:
        float32 array of shape (12, 5000)

    Raises:
        ValueError: If the signal is not 12-lead, contains NaN/inf,
                    or is shorter than 10 seconds
    """
    ecg_signal = np.asarray(ecg_signal, dtype=np.float32)
    if ecg_signal.ndim != 2 or N_LEADS not in ecg_signal.shape:
        raise ValueError(f"Expected a 12-lead signal, got shape {ecg_signal.shape}")
    if not np.isfinite(ecg_signal).all():
        raise ValueError("ECG signal contains NaN or infinite values")

    if ecg_signal.shape[0] != N_LEADS:
        ecg_signal = ecg_signal.T

    if sampling_rate != TARGET_FS:
        n_out = round(ecg_signal.shape[1] * TARGET_FS / sampling_rate)
        ecg_signal = resample(ecg_signal, n_out, axis=1)

    if ecg_signal.shape[1] < TARGET_SAMPLES:
        duration_s = ecg_signal.shape[1] / TARGET_FS
        raise ValueError(
            f"ECG must be at least 10 s long; got {duration_s:.2f} s "
            f"({ecg_signal.shape[1]} samples at {TARGET_FS} Hz after resampling)"
        )

    return normalize_signal(ecg_signal[:, :TARGET_SAMPLES])
