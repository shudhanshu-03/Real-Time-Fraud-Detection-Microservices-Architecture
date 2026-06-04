"""
Configuration module for the Fraud Detection Platform.

Provides Pydantic BaseSettings-based configuration classes for all
infrastructure components used across microservices. Each settings class
supports environment variable loading with a dedicated prefix, enabling
12-factor-style configuration management.

Usage:
    from fraud_common.config import get_settings

    settings = get_settings()
    kafka_brokers = settings.kafka.bootstrap_servers
    redis_host = settings.redis.host
"""

from __future__ import annotations

from enum import Enum
from functools import lru_cache
from typing import List, Optional

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings


class Environment(str, Enum):
    """Supported deployment environments."""

    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class KafkaSettings(BaseSettings):
    """Configuration for Apache Kafka connectivity.

    Attributes:
        bootstrap_servers: Comma-separated list of Kafka broker addresses.
        schema_registry_url: URL of the Confluent Schema Registry.
        consumer_group_prefix: Prefix applied to all consumer group IDs
            to avoid cross-service collisions.
        max_retries: Maximum number of retry attempts for transient failures.
        retry_backoff_ms: Backoff interval in milliseconds between retries.
    """

    model_config = {"env_prefix": "KAFKA_"}

    bootstrap_servers: str = Field(
        default="localhost:9092",
        description="Comma-separated list of Kafka broker addresses.",
    )
    schema_registry_url: str = Field(
        default="http://localhost:8081",
        description="URL of the Confluent Schema Registry.",
    )
    consumer_group_prefix: str = Field(
        default="fraud-platform",
        description="Prefix for consumer group IDs.",
    )
    max_retries: int = Field(
        default=3,
        ge=0,
        description="Maximum number of retry attempts for transient failures.",
    )
    retry_backoff_ms: int = Field(
        default=1000,
        ge=100,
        description="Backoff interval in milliseconds between retries.",
    )


class RedisSettings(BaseSettings):
    """Configuration for Redis connectivity.

    Attributes:
        host: Redis server hostname.
        port: Redis server port.
        password: Optional authentication password.
        db: Redis database index.
        max_connections: Maximum number of connections in the pool.
        socket_timeout: Socket timeout in seconds for blocking operations.
    """

    model_config = {"env_prefix": "REDIS_"}

    host: str = Field(
        default="localhost",
        description="Redis server hostname.",
    )
    port: int = Field(
        default=6379,
        ge=1,
        le=65535,
        description="Redis server port.",
    )
    password: Optional[str] = Field(
        default=None,
        description="Optional authentication password.",
    )
    db: int = Field(
        default=0,
        ge=0,
        description="Redis database index.",
    )
    max_connections: int = Field(
        default=20,
        ge=1,
        description="Maximum number of connections in the pool.",
    )
    socket_timeout: float = Field(
        default=5.0,
        gt=0,
        description="Socket timeout in seconds for blocking operations.",
    )


class PostgresSettings(BaseSettings):
    """Configuration for PostgreSQL connectivity.

    Provides connection parameters for asyncpg-based database access,
    including connection pooling settings.

    Attributes:
        host: PostgreSQL server hostname.
        port: PostgreSQL server port.
        user: Database user for authentication.
        password: Database password for authentication.
        database: Target database name.
        min_pool_size: Minimum number of connections in the pool.
        max_pool_size: Maximum number of connections in the pool.
        echo: Whether to echo SQL statements for debugging.
    """

    model_config = {"env_prefix": "PG_"}

    host: str = Field(
        default="localhost",
        description="PostgreSQL server hostname.",
    )
    port: int = Field(
        default=5432,
        ge=1,
        le=65535,
        description="PostgreSQL server port.",
    )
    user: str = Field(
        default="postgres",
        description="Database user for authentication.",
    )
    password: str = Field(
        default="postgres",
        description="Database password for authentication.",
    )
    database: str = Field(
        default="fraud_detection",
        description="Target database name.",
    )
    min_pool_size: int = Field(
        default=5,
        ge=1,
        description="Minimum number of connections in the pool.",
    )
    max_pool_size: int = Field(
        default=20,
        ge=1,
        description="Maximum number of connections in the pool.",
    )
    echo: bool = Field(
        default=False,
        description="Whether to echo SQL statements for debugging.",
    )

    @computed_field  # type: ignore[misc]
    @property
    def dsn(self) -> str:
        """Build an asyncpg-compatible PostgreSQL DSN.

        Returns:
            A connection string in the format
            ``postgresql+asyncpg://user:password@host:port/database``.
        """
        return (
            f"postgresql+asyncpg://{self.user}:{self.password}"
            f"@{self.host}:{self.port}/{self.database}"
        )


class Neo4jSettings(BaseSettings):
    """Configuration for Neo4j graph database connectivity.

    Attributes:
        uri: Bolt protocol URI for Neo4j.
        user: Authentication username.
        password: Authentication password.
        database: Target Neo4j database name.
        max_connection_pool_size: Maximum number of connections in the pool.
    """

    model_config = {"env_prefix": "NEO4J_"}

    uri: str = Field(
        default="bolt://localhost:7687",
        description="Bolt protocol URI for Neo4j.",
    )
    user: str = Field(
        default="neo4j",
        description="Authentication username.",
    )
    password: str = Field(
        default="neo4j",
        description="Authentication password.",
    )
    database: str = Field(
        default="neo4j",
        description="Target Neo4j database name.",
    )
    max_connection_pool_size: int = Field(
        default=50,
        ge=1,
        description="Maximum number of connections in the pool.",
    )


class ElasticsearchSettings(BaseSettings):
    """Configuration for Elasticsearch connectivity.

    Attributes:
        hosts: List of Elasticsearch node URLs.
        username: Optional authentication username.
        password: Optional authentication password.
        index_prefix: Prefix applied to all index names for namespace isolation.
    """

    model_config = {"env_prefix": "ES_"}

    hosts: List[str] = Field(
        default=["http://localhost:9200"],
        description="List of Elasticsearch node URLs.",
    )
    username: Optional[str] = Field(
        default=None,
        description="Optional authentication username.",
    )
    password: Optional[str] = Field(
        default=None,
        description="Optional authentication password.",
    )
    index_prefix: str = Field(
        default="fraud-platform",
        description="Prefix applied to all index names for namespace isolation.",
    )


class ServiceSettings(BaseSettings):
    """Configuration for the running microservice instance.

    Attributes:
        name: Human-readable service name (used in logging and health checks).
        version: Semantic version of the service.
        host: Bind address for the HTTP server.
        port: Bind port for the HTTP server.
        debug: Whether to enable debug mode.
        log_level: Logging verbosity level.
        environment: Deployment environment (development, staging, production).
    """

    model_config = {"env_prefix": "SERVICE_"}

    name: str = Field(
        default="fraud-service",
        description="Human-readable service name.",
    )
    version: str = Field(
        default="0.1.0",
        description="Semantic version of the service.",
    )
    host: str = Field(
        default="0.0.0.0",
        description="Bind address for the HTTP server.",
    )
    port: int = Field(
        default=8000,
        ge=1,
        le=65535,
        description="Bind port for the HTTP server.",
    )
    debug: bool = Field(
        default=False,
        description="Whether to enable debug mode.",
    )
    log_level: str = Field(
        default="INFO",
        description="Logging verbosity level.",
    )
    environment: Environment = Field(
        default=Environment.DEVELOPMENT,
        description="Deployment environment.",
    )


class Settings(BaseSettings):
    """Root configuration composing all subsystem settings.

    Each subsystem pulls its values from environment variables using a
    dedicated prefix (e.g. ``KAFKA_BOOTSTRAP_SERVERS``, ``REDIS_HOST``).
    Instantiate via :func:`get_settings` for caching.

    Example::

        settings = get_settings()
        print(settings.kafka.bootstrap_servers)
        print(settings.postgres.dsn)
    """

    kafka: KafkaSettings = Field(default_factory=KafkaSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    postgres: PostgresSettings = Field(default_factory=PostgresSettings)
    neo4j: Neo4jSettings = Field(default_factory=Neo4jSettings)
    elasticsearch: ElasticsearchSettings = Field(
        default_factory=ElasticsearchSettings,
    )
    service: ServiceSettings = Field(default_factory=ServiceSettings)


@lru_cache()
def get_settings() -> Settings:
    """Create and cache the application settings singleton.

    Returns:
        A fully resolved :class:`Settings` instance populated from
        environment variables and defaults.

    Note:
        The result is cached via :func:`functools.lru_cache`.  To force
        re-creation (e.g. in tests), call ``get_settings.cache_clear()``.
    """
    return Settings()
