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
