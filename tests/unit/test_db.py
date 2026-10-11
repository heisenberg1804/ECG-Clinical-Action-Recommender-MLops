# ============================================================
# FILE: tests/unit/test_db.py
# ============================================================
import re

from src.db import SCHEMA_SQL, postgres_dsn


def test_dsn_reads_prefixed_env(monkeypatch):
    for key, value in {"HOST": "127.0.0.1", "PORT": "6543", "USER": "u", "PASSWORD": "p",
                       "DB": "d"}.items():
        monkeypatch.setenv(f"ECG_POSTGRES_{key}", value)
    assert postgres_dsn(prefix="ECG_POSTGRES_") == "postgresql://u:p@127.0.0.1:6543/d"


def test_dsn_defaults_to_local_dev(monkeypatch):
    for key in ("HOST", "PORT", "USER", "PASSWORD", "DB"):
        monkeypatch.delenv(f"POSTGRES_{key}", raising=False)
    assert postgres_dsn().endswith("@localhost:5432/ecg_predictions")


def test_schema_is_idempotent():
    """It runs on every API start, so every statement must be safe to repeat."""
    statements = [s.strip() for s in SCHEMA_SQL.split(";") if s.strip()]
    creates = [s for s in statements if s.upper().startswith("CREATE")]
    assert creates, "schema should create the predictions table"
    for stmt in creates:
        assert re.match(r"CREATE (TABLE|INDEX) IF NOT EXISTS|CREATE OR REPLACE VIEW", stmt,
                        re.IGNORECASE), stmt
