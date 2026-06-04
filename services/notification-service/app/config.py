"""
Notification Service Config
"""

from pydantic_settings import BaseSettings
from pydantic import Field


class NotificationSettings(BaseSettings):
    service_name: str = Field(default="notification-service")
    service_version: str = Field(default="1.0.0")

    # DB & Kafka
    database_url: str = Field(default="postgresql+asyncpg://fraud_user:fraud_pass@postgres:5432/fraud_transactions")
    kafka_bootstrap_servers: str = Field(default="kafka:29092")
    kafka_consumer_group_id: str = Field(default="notification-service-group")
    notify_request_topic: str = Field(default="notification.requested")
    notify_delivery_topic: str = Field(default="notification.delivered")
    redis_url: str = Field(default="redis://redis:6379/0")

    # SMTP Settings
    smtp_host: str = Field(default="smtp.example.com")
    smtp_port: int = Field(default=587)
    smtp_user: str = Field(default="notify@example.com")
    smtp_pass: str = Field(default="secret")
    smtp_from: str = Field(default="alerts@fraudplatform.com")

    # Twilio
    twilio_account_sid: str = Field(default="AC_dummy")
    twilio_auth_token: str = Field(default="dummy")
    twilio_from: str = Field(default="+1234567890")

    # Slack
    slack_webhook_url: str = Field(default="https://hooks.slack.com/services/dummy/dummy")

    model_config = {
        "env_prefix": "NOTIFY_",
        "case_sensitive": False,
        "extra": "ignore",
    }


settings = NotificationSettings()
