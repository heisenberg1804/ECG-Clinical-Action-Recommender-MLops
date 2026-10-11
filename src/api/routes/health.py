# ============================================================
# FILE: src/api/routes/health.py
# ============================================================
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from src.ml.inference import predictor as predictor_module

router = APIRouter()


@router.get("/health")
async def health_check():
    """Liveness probe - is the process running?"""
    return {"status": "healthy"}


@router.get("/ready")
async def readiness_check():
    """
    Readiness probe - can this pod serve predictions?

    Only the model gates readiness. Prediction logging to Postgres is
    best-effort, so a database outage must not pull pods out of rotation.
    """
    instance = predictor_module._predictor_instance
    if instance is None:
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "checks": {"model": "not_loaded"}},
        )
    return {
        "status": "ready",
        "checks": {"model": "loaded"},
        "model_version": instance.model_version,
    }
