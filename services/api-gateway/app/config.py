"""
Configuration module for the API Gateway service.

Uses pydantic-settings to load configuration from environment variables
with sensible defaults for local development.
"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Gateway-specific settings loaded from environment variables."""

    # ── Service identity ────────────────────────────────────────────────
    service_name: str = "api-gateway"
    service_version: str = "1.0.0"
    debug: bool = False

    # ── JWT configuration ───────────────────────────────────────────────
    jwt_secret_key: str = "dev-secret-key-change-in-production-a1b2c3d4e5f6"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7

    # ── Rate limiting ───────────────────────────────────────────────────
    rate_limit_per_minute: int = 100
    rate_limit_burst: int = 20

    # ── Upstream service URLs ───────────────────────────────────────────
    transaction_service_url: str = "http://transaction-service:8001"
    alert_service_url: str = "http://alert-service:8087"
    case_service_url: str = "http://case-management:8088"
    rule_engine_url: str = "http://rule-engine:8003"
    monitoring_service_url: str = "http://monitoring-service:8010"

    # ── Redis ───────────────────────────────────────────────────────────
    redis_host: str = "redis"
    redis_port: int = 6379
    redis_db: int = 0
    kafka_bootstrap_servers: str = "kafka:29092"

    # Optional services ──────────────────────────────────────────────────
    proxy_timeout_seconds: float = 30.0
    circuit_breaker_failure_threshold: int = 5
    circuit_breaker_recovery_timeout: int = 30

    model_config = {
        "env_prefix": "GATEWAY_",
        "case_sensitive": False,
    }


# Module-level singleton
settings = Settings()
