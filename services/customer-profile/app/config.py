"""
Customer Profile Config
"""

from pydantic_settings import BaseSettings
from pydantic import Field


class ProfileSettings(BaseSettings):
    service_name: str = Field(default="customer-profile")
    service_version: str = Field(default="1.0.0")

    database_url: str = Field(default="postgresql+asyncpg://fraud_user:fraud_pass@postgres:5432/fraud_transactions")
    redis_url: str = Field(default="redis://redis:6379/0")

    kafka_bootstrap_servers: str = Field(default="kafka:29092")
    kafka_consumer_group_id: str = Field(default="customer-profile-group")

    # Topics to consume for dashboard metrics
    transaction_enriched_topic: str = Field(default="transaction.enriched")
    fraud_scored_topic: str = Field(default="fraud.scored")
    velocity_updated_topic: str = Field(default="velocity.updated")
    alert_created_topic: str = Field(default="alert.created")

    model_config = {
        "env_prefix": "PROFILE_",
        "case_sensitive": False,
        "extra": "ignore",
    }


settings = ProfileSettings()
