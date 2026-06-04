"""
Stream Processor Configuration
"""

from pydantic_settings import BaseSettings
from pydantic import Field


class StreamProcessorSettings(BaseSettings):
    service_name: str = Field(default="stream-processor")
    service_version: str = Field(default="1.0.0")

    # Kafka
    kafka_bootstrap_servers: str = Field(default="kafka:29092")
    kafka_consumer_group_id: str = Field(default="stream-processor-group")
    transaction_topic: str = Field(default="transaction.created")
    velocity_updated_topic: str = Field(default="velocity.updated")
    velocity_breach_topic: str = Field(default="velocity.threshold.breach")
    fraud_pattern_topic: str = Field(default="fraud.pattern.detected")

    # Redis
    redis_url: str = Field(default="redis://redis:6379/0")

    # Velocity Thresholds (1-min)
    t1m_txn_count: int = Field(default=5)
    t1m_txn_sum: float = Field(default=5000.0)
    t1m_distinct_merchants: int = Field(default=3)
    t1m_distinct_countries: int = Field(default=1)
    t1m_max_amount: float = Field(default=2500.0)

    # Velocity Thresholds (5-min)
    t5m_txn_count: int = Field(default=15)
    t5m_txn_sum: float = Field(default=10000.0)
    t5m_distinct_merchants: int = Field(default=8)
    t5m_distinct_countries: int = Field(default=2)
    t5m_max_amount: float = Field(default=5000.0)

    # Velocity Thresholds (1-hr)
    t1h_txn_count: int = Field(default=50)
    t1h_txn_sum: float = Field(default=25000.0)
    t1h_distinct_merchants: int = Field(default=20)
    t1h_distinct_countries: int = Field(default=3)
    t1h_max_amount: float = Field(default=10000.0)

    # Velocity Thresholds (24-hr)
    t24h_txn_count: int = Field(default=200)
    t24h_txn_sum: float = Field(default=100000.0)
    t24h_distinct_merchants: int = Field(default=50)
    t24h_distinct_countries: int = Field(default=5)
    t24h_max_amount: float = Field(default=25000.0)

    model_config = {
        "env_prefix": "STREAM_",
        "case_sensitive": False,
        "extra": "ignore",
    }


settings = StreamProcessorSettings()
