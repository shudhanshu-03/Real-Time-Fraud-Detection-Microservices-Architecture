"""
Transaction Service – Application Configuration.

Centralises every tuneable knob via environment variables using
``pydantic-settings``.  Default values are development-friendly; override
them through environment variables or a ``.env`` file in production.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings


class TransactionServiceSettings(BaseSettings):
    """Settings for the Transaction Service."""

    # ── General ─────────────────────────────────────────────────────────
    service_name: str = "transaction-service"
    service_version: str = "1.0.0"
    debug: bool = False

    # ── Database ────────────────────────────────────────────────────────
    pg_host: str = "postgres"
    pg_user: str = "fraud_user"
    pg_password: str = "fraud_pass"

    @property
    def database_url(self) -> str:
        return f"postgresql+asyncpg://{self.pg_user}:{self.pg_password}@{self.pg_host}:5432/fraud_transactions"

    # ── Kafka ───────────────────────────────────────────────────────────
    kafka_bootstrap_servers: str = "kafka:29092"

    # ── Redis ───────────────────────────────────────────────────────────
    redis_url: str = "redis://localhost:6379/0"

    # ── Batch processing ────────────────────────────────────────────────
    batch_max_size: int = 1000

    model_config = {
        "env_prefix": "TXN_",
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
    }


# Module-level singleton – import this everywhere.
settings = TransactionServiceSettings()
