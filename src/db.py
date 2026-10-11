# ============================================================
# FILE: src/db.py
# ============================================================
"""
Postgres connection settings, shared by the API, monitoring jobs and Airflow DAGs.

Credentials come from environment variables only. The defaults match the local
docker-compose dev database; staging/prod inject real values from k8s Secrets.
"""
import os


def postgres_dsn(prefix: str = "POSTGRES_") -> str:
    """
    Build a postgresql:// DSN from environment variables.

    Args:
        prefix: Env var prefix. The API uses POSTGRES_*; the Airflow containers
                use ECG_POSTGRES_* to avoid clashing with Airflow's own database.
    """
    user = os.getenv(f"{prefix}USER", "ecg_user")
    password = os.getenv(f"{prefix}PASSWORD", "ecg_password_dev")
    host = os.getenv(f"{prefix}HOST", "localhost")
    port = os.getenv(f"{prefix}PORT", "5432")
    db = os.getenv(f"{prefix}DB", "ecg_predictions")
    return f"postgresql://{user}:{password}@{host}:{port}/{db}"


# Idempotent: safe to run on every startup, so a fresh database (local compose,
# a new Cloud SQL instance) needs no manual migration step.
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS predictions (
    id SERIAL PRIMARY KEY,
    ecg_id UUID NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    -- Patient info
    patient_age INTEGER,
    patient_sex VARCHAR(1),

    -- Model info
    model_version VARCHAR(50) NOT NULL,
    processing_time_ms FLOAT,

    -- Predictions (stored as JSONB for flexibility)
    diagnoses JSONB NOT NULL,
    recommendations JSONB NOT NULL,

    -- Metadata
    request_ip VARCHAR(50),

    -- Indexes
    CONSTRAINT ecg_id_unique UNIQUE (ecg_id)
);

CREATE INDEX IF NOT EXISTS idx_predictions_created_at ON predictions(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_predictions_model_version ON predictions(model_version);
CREATE INDEX IF NOT EXISTS idx_predictions_diagnoses ON predictions USING GIN (diagnoses);

-- View for easy querying
CREATE OR REPLACE VIEW prediction_summary AS
SELECT
    date_trunc('hour', created_at) as hour,
    model_version,
    COUNT(*) as total_predictions,
    AVG(processing_time_ms) as avg_latency_ms,
    AVG(jsonb_array_length(diagnoses)) as avg_diagnoses_count
FROM predictions
GROUP BY hour, model_version
ORDER BY hour DESC;
"""


async def ensure_schema(conn) -> None:
    """Create the prediction log table, indexes and summary view if missing."""
    await conn.execute(SCHEMA_SQL)
