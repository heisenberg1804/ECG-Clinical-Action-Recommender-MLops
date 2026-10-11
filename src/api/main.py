# ============================================================
# FILE: src/api/main.py
# ============================================================
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator

from src.api.routes import bias, drift, health, predict
from src.ml.inference.predictor import get_predictor


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Load the model at startup so /ready reflects reality and the first
    # request doesn't pay the load cost. A failure keeps /health up (so the
    # pod can be inspected) while /ready reports not-ready.
    try:
        get_predictor()
        predict.MODEL_LOADED.set(1)
    except Exception as e:
        predict.MODEL_LOADED.set(0)
        print(f"❌ Model failed to load at startup: {e}")
    yield


app = FastAPI(
    title="ECG Clinical Action Recommender",
    description="Recommends clinical actions based on 12-lead ECG signals",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Public, unauthenticated API: no cookies/credentials
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Prometheus metrics instrumentation
Instrumentator().instrument(app).expose(app, endpoint="/metrics")

# Include routers
app.include_router(health.router, tags=["Health"])
app.include_router(predict.router, tags=["Predictions"])
app.include_router(drift.router, prefix="/monitoring", tags=["Monitoring"])
app.include_router(bias.router, prefix="/monitoring", tags=["Monitoring"])
