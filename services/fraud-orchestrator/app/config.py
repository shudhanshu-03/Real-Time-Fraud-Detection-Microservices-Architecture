"""
Fraud Orchestrator - Application Configuration.

Centralized configuration management using pydantic-settings.
All settings are loaded from environment variables with sensible defaults
for local development and container deployment.
"""

from pydantic_settings import BaseSettings
from pydantic import Field


class OrchestratorSettings(BaseSettings):
    """Configuration settings for the Fraud Scoring Orchestrator service.

    Settings are loaded from environment variables (case-insensitive).
    Prefix: ORCHESTRATOR_ can be used to namespace env vars.
    """

    # -------------------------------------------------------------------------
    # Service Metadata
    # -------------------------------------------------------------------------
    service_name: str = Field(
        default="fraud-orchestrator",
        description="Name of this microservice",
    )
    service_version: str = Field(
        default="1.0.0",
        description="Semantic version of the service",
    )

    # -------------------------------------------------------------------------
    # Scoring Weights (must sum to ~1.0)
    # -------------------------------------------------------------------------
    w_rule: float = Field(
        default=0.30,
        ge=0.0,
        le=1.0,
        description="Weight for the rule-engine score",
    )
    w_ml: float = Field(
        default=0.35,
        ge=0.0,
        le=1.0,
        description="Weight for the ML scoring model",
    )
    w_graph: float = Field(
        default=0.20,
        ge=0.0,
        le=1.0,
        description="Weight for the graph-analysis score",
    )
    w_history: float = Field(
        default=0.15,
        ge=0.0,
        le=1.0,
        description="Weight for the historical velocity score",
    )

    # -------------------------------------------------------------------------
    # Decision Thresholds
    # -------------------------------------------------------------------------
    approve_threshold: float = Field(
        default=0.30,
        ge=0.0,
        le=1.0,
        description="Maximum score to auto-approve a transaction",
    )
    review_threshold: float = Field(
        default=0.60,
        ge=0.0,
        le=1.0,
        description="Maximum score to flag for manual review",
    )
    high_risk_threshold: float = Field(
        default=0.85,
        ge=0.0,
        le=1.0,
        description="Minimum score to block a transaction",
    )

    # -------------------------------------------------------------------------
    # Scoring Timeouts
    # -------------------------------------------------------------------------
    scoring_timeout_ms: int = Field(
        default=2000,
        gt=0,
        description="Per-engine gRPC call timeout in milliseconds",
    )
    total_timeout_ms: int = Field(
        default=5000,
        gt=0,
        description="Total orchestration timeout in milliseconds",
    )

    # -------------------------------------------------------------------------
    # gRPC Targets
    # -------------------------------------------------------------------------
    rule_engine_grpc_target: str = Field(
        default="rule-engine:50051",
        description="gRPC target address for the Rule Engine service",
    )
    ml_scoring_grpc_target: str = Field(
        default="ml-scoring:50052",
        description="gRPC target address for the ML Scoring service",
    )
    graph_analysis_grpc_target: str = Field(
        default="graph-analysis:50053",
        description="gRPC target address for the Graph Analysis service",
    )

    # -------------------------------------------------------------------------
    # Kafka
    # -------------------------------------------------------------------------
    kafka_bootstrap_servers: str = Field(
        default="kafka:29092",
        description="Comma-separated list of Kafka bootstrap servers",
    )
    input_topic: str = Field(
        default="transactions",
        description="Kafka topic to consume incoming transactions from"
    )
    output_topic: str = Field(
        default="fraud.evaluated.transactions",
        description="Kafka topic to publish evaluated transactions to"
    )

    # -------------------------------------------------------------------------
    # Redis
    # -------------------------------------------------------------------------
    redis_url: str = Field(
        default="redis://redis:6379/0",
        description="Redis connection URL",
    )

    # -------------------------------------------------------------------------
    # Operational
    # -------------------------------------------------------------------------
    redis_score_cache_ttl: int = Field(
        default=3600,
        gt=0,
        description="TTL in seconds for cached scoring results in Redis",
    )
    kafka_consumer_group_id: str = Field(
        default="fraud-orchestrator-group",
        description="Kafka consumer group identifier",
    )
    dlq_max_retries: int = Field(
        default=3,
        ge=1,
        description="Max retries before sending a message to the DLQ",
    )

    model_config = {
        "env_prefix": "ORCHESTRATOR_",
        "case_sensitive": False,
        "extra": "ignore",
    }


# Singleton instance for the application
settings = OrchestratorSettings()
