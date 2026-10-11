# ============================================================
# FILE: src/api/routes/predict.py (COMPLETE WITH LOGGING)
# ============================================================
import json
import time
import uuid
from typing import Any

import asyncpg
import numpy as np
from fastapi import APIRouter, HTTPException
from prometheus_client import Counter, Gauge, Histogram
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from src.db import ensure_schema, postgres_dsn
from src.ml.inference.predictor import get_predictor

router = APIRouter()

# Prometheus metrics
PREDICTIONS_TOTAL = Counter(
    'ecg_predictions_total',
    'Total number of predictions made',
    ['diagnosis', 'urgency']
)

PREDICTION_LATENCY = Histogram(
    'ecg_prediction_latency_seconds',
    'Time spent processing predictions',
    buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 2.0, 5.0]
)

PREDICTION_CONFIDENCE = Histogram(
    'ecg_prediction_confidence',
    'Confidence scores of predictions',
    ['diagnosis'],
    buckets=[0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
)

MODEL_LOADED = Gauge(
    'ecg_model_loaded',
    'Whether the model is loaded (1) or not (0)'
)

# Database connection pool
DB_POOL = None


async def get_db_pool():
    """Get database connection pool (lazy initialization)."""
    global DB_POOL
    if DB_POOL is None:
        DB_POOL = await asyncpg.create_pool(
            dsn=postgres_dsn(),
            min_size=2,
            max_size=10,
            timeout=5,  # Fail fast: logging must never stall a prediction
        )
        async with DB_POOL.acquire() as conn:
            await ensure_schema(conn)
    return DB_POOL


class ECGInput(BaseModel):
    """Input schema for ECG prediction."""

    ecg_signal: list[list[float]] = Field(
        ...,
        description="12-lead ECG signal, shape (12, num_samples)",
        min_length=12,
        max_length=12,
    )
    patient_age: int | None = Field(None, ge=0, le=120)
    patient_sex: str | None = Field(None, pattern="^(M|F)$")
    sampling_rate: int = Field(
        default=500, ge=100, le=2000,
        description="Sampling rate in Hz. Signals are resampled to 500 Hz; at least 10 s required.",
    )
    explain: bool = Field(default=False, description="Generate explanation for prediction")
    use_llm: bool = Field(default=False,
                           description="Use medical LLM for clinical explanation (slower)")


class ClinicalAction(BaseModel):
    """A recommended clinical action."""

    action: str
    confidence: float = Field(ge=0.0, le=1.0)
    urgency: str = Field(pattern="^(immediate|urgent|routine)$")
    reasoning: str


class Diagnosis(BaseModel):
    """A predicted diagnosis."""

    diagnosis: str
    confidence: float = Field(ge=0.0, le=1.0)


class PredictionResponse(BaseModel):
    """Response schema for ECG prediction."""

    ecg_id: str
    probabilities: dict[str, float] = Field(
        description="Model probability for every diagnostic class"
    )
    diagnoses: list[Diagnosis]
    recommendations: list[ClinicalAction]
    model_version: str
    processing_time_ms: float
    explanation: dict[str, Any] | None = Field(
        None,
        description="Explanation for the prediction (if explain=True)"
    )


@router.post("/predict", response_model=PredictionResponse)
async def predict_clinical_actions(ecg_input: ECGInput) -> PredictionResponse:
    """
    Predict clinical actions based on ECG signal.

    This endpoint accepts a 12-lead ECG signal and returns
    recommended clinical actions ranked by confidence.

    The model classifies the ECG into diagnostic categories:
    - NORM: Normal ECG
    - MI: Myocardial Infarction
    - STTC: ST/T Changes
    - CD: Conduction Disturbance
    - HYP: Hypertrophy

    Then maps diagnoses to clinical actions via a rule table (action_mapping.json).
    """
    start_time = time.time()
    ecg_id = str(uuid.uuid4())

    try:
        signal = np.array(ecg_input.ecg_signal, dtype=np.float32)
    except ValueError:
        raise HTTPException(status_code=400, detail="All 12 leads must have the same length")

    try:
        predictor = get_predictor()
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Model unavailable: {e}")

    try:
        # Inference is CPU-bound: run it off the event loop so the API stays responsive
        with PREDICTION_LATENCY.time():
            result = await run_in_threadpool(
                predictor.predict,
                signal,
                sampling_rate=ecg_input.sampling_rate,
                explain=ecg_input.explain,
                use_llm=ecg_input.use_llm,
                patient_age=ecg_input.patient_age,
                patient_sex=ecg_input.patient_sex,
            )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Prediction failed: {e}")

    diagnoses = [
        Diagnosis(diagnosis=d['diagnosis'], confidence=d['confidence'])
        for d in result['diagnoses']
    ]
    recommendations = [
        ClinicalAction(
            action=r['action'],
            confidence=r['confidence'],
            urgency=r['urgency'],
            reasoning=r['reasoning'],
        )
        for r in result['recommendations']
    ]

    # Record Prometheus metrics
    for dx in diagnoses:
        PREDICTION_CONFIDENCE.labels(diagnosis=dx.diagnosis).observe(dx.confidence)
    primary = diagnoses[0].diagnosis if diagnoses else 'NONE'
    for rec in recommendations:
        PREDICTIONS_TOTAL.labels(diagnosis=primary, urgency=rec.urgency).inc()

    processing_time = (time.time() - start_time) * 1000

    # Log prediction to PostgreSQL database
    try:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO predictions (
                    ecg_id, patient_age, patient_sex, model_version,
                    processing_time_ms, diagnoses, recommendations
                ) VALUES ($1, $2, $3, $4, $5, $6, $7)
                """,
                uuid.UUID(ecg_id),
                ecg_input.patient_age,
                ecg_input.patient_sex,
                predictor.model_version,
                processing_time,
                json.dumps([d.model_dump() for d in diagnoses]),
                json.dumps([r.model_dump() for r in recommendations])
            )
    except Exception as e:
        # Log error but don't fail the request
        print(f"⚠️  Failed to log prediction to database: {e}")

    return PredictionResponse(
        ecg_id=ecg_id,
        probabilities=result['probabilities'],
        diagnoses=diagnoses,
        recommendations=recommendations,
        model_version=predictor.model_version,
        processing_time_ms=round(processing_time, 2),
        explanation=result.get('explanation'),
    )


@router.get("/model/info")
async def get_model_info():
    """Get information about the loaded model."""
    try:
        predictor = get_predictor()
        return {
            "model_type": "ResNet-18 1D",
            "model_version": predictor.model_version,
            "classes": predictor.superclasses,
            "device": str(predictor.device),
            "model_path": str(predictor.model_path),
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to load model info: {str(e)}"
        )
