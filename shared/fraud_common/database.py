"""
Asynchronous Database Utilities for the Real-Time Fraud Detection Platform.

This module provides a centralised :class:`DatabaseManager` that wraps
SQLAlchemy 2.0 async support backed by the ``asyncpg`` driver.  Every
microservice in the fraud detection ecosystem should obtain its database
sessions through this manager to ensure consistent connection-pool sizing,
health-check semantics, and graceful shutdown behaviour.

Key components:

* :class:`DatabaseManager` – owns the async engine and session factory.
* :data:`Base` – the shared declarative base from which all ORM models
  should inherit.
* :func:`get_db_manager` – a convenience factory that constructs a
  ``DatabaseManager`` from a settings / config object.

Usage::

    from fraud_common.database import get_db_manager, Base

    db = get_db_manager(settings)
    await db.create_engine("postgresql+asyncpg://user:pass@host/db")

    async with db.get_session() as session:
        result = await session.execute(select(Transaction))
        ...

    await db.close()
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, Protocol, runtime_checkable

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

# ═══════════════════════════════════════════════════════════════════════════
# Declarative Base
# ═══════════════════════════════════════════════════════════════════════════


class Base(DeclarativeBase):
    """Shared SQLAlchemy declarative base for all fraud-platform ORM models.

    All domain models (``Transaction``, ``FraudAlert``, ``Rule``, etc.)
    should inherit from this base so they share a single metadata registry
    and can be discovered by Alembic for migration auto-generation.

    Example
    -------
    ::

        from fraud_common.database import Base
        from sqlalchemy import Column, String, Float
        from sqlalchemy.dialects.postgresql import UUID

        class Transaction(Base):
            __tablename__ = "transactions"
            id = Column(UUID(as_uuid=True), primary_key=True)
            amount = Column(Float, nullable=False)
            currency = Column(String(3), nullable=False)
    """

    pass


# ═══════════════════════════════════════════════════════════════════════════
# Settings Protocol
# ═══════════════════════════════════════════════════════════════════════════


@runtime_checkable
class DatabaseSettings(Protocol):
    """Structural protocol describing the settings attributes that
    :func:`get_db_manager` expects.

    Any object (Pydantic ``BaseSettings``, dataclass, plain class, etc.)
    that exposes these attributes will satisfy the protocol without
    needing to inherit from it.

    Attributes
    ----------
    database_dsn : str
        The full async DSN, e.g.
        ``"postgresql+asyncpg://user:pass@localhost:5432/fraud_db"``.
    database_pool_size : int
        Maximum number of connections to keep in the pool.
    database_pool_overflow : int
        Number of connections allowed beyond ``pool_size`` during bursts.
    database_echo_sql : bool
        Whether to echo generated SQL to the log (debug only).
    """

    database_dsn: str
    database_pool_size: int
    database_pool_overflow: int
    database_echo_sql: bool


# ═══════════════════════════════════════════════════════════════════════════
# DatabaseManager
# ═══════════════════════════════════════════════════════════════════════════


class DatabaseManager:
    """Manage an async SQLAlchemy engine, session factory, and lifecycle.

    This class is the single owner of the database connection pool for a
    microservice.  It should be instantiated **once** at application startup
    (typically inside a FastAPI ``lifespan`` context manager) and shared via
    dependency injection.

    Attributes
    ----------
    _engine : AsyncEngine | None
        The underlying async engine; ``None`` until :meth:`create_engine`
        is called.
    _session_factory : async_sessionmaker[AsyncSession] | None
        A session factory bound to the engine; ``None`` until
        :meth:`create_engine` is called.

    Example
    -------
    ::

        db = DatabaseManager()
        await db.create_engine("postgresql+asyncpg://…", pool_size=20)

        async with db.get_session() as session:
            await session.execute(select(Transaction))

        healthy = await db.health_check()
        await db.close()
    """

    def __init__(self) -> None:
        """Initialise the manager in an *unconfigured* state.

        Call :meth:`create_engine` before using :meth:`get_session`.
        """
        self._engine: AsyncEngine | None = None
        self._session_factory: async_sessionmaker[AsyncSession] | None = None

    # ------------------------------------------------------------------
    # Engine creation
    # ------------------------------------------------------------------

    async def create_engine(
        self,
        dsn: str,
        *,
        pool_size: int = 20,
        max_overflow: int = 10,
        pool_pre_ping: bool = True,
        pool_recycle: int = 3600,
        echo: bool = False,
        connect_args: dict[str, Any] | None = None,
    ) -> None:
        """Create the async engine and bind a session factory to it.

        This method is **idempotent** — calling it when an engine already
        exists will first close the old engine before creating a new one.

        Parameters
        ----------
        dsn : str
            An async-compatible DSN string.  Must use the ``asyncpg``
            dialect, e.g.
            ``"postgresql+asyncpg://user:pass@host:5432/fraud_db"``.
        pool_size : int
            Number of persistent connections in the pool.  Tune according
            to the service's expected concurrency and the PostgreSQL
            ``max_connections`` setting.
        max_overflow : int
            Temporary connections allowed above *pool_size* during traffic
            spikes.  These connections are reaped when idle.
        pool_pre_ping : bool
            If ``True``, each connection is tested with a lightweight
            ``SELECT 1`` before being handed to application code.
            Recommended for long-lived pools.
        pool_recycle : int
            Maximum age (seconds) of a connection before it is recycled.
            Helps avoid stale connections behind PgBouncer or cloud proxies.
        echo : bool
            If ``True``, all emitted SQL is logged.  **Never** enable in
            production.
        connect_args : dict[str, Any] | None
            Extra keyword arguments forwarded to the underlying ``asyncpg``
            ``connect()`` call (e.g. ``statement_cache_size``).

        Raises
        ------
        ValueError
            If *dsn* does not use an async-compatible dialect.
        """
        if "asyncpg" not in dsn and "+aiosqlite" not in dsn:
            raise ValueError(
                f"DSN must use an async dialect (e.g. asyncpg). Got: {dsn!r}"
            )

        # Tear down any pre-existing engine.
        if self._engine is not None:
            logger.warning("database_engine_replaced", old_dsn=str(self._engine.url))
            await self.close()

        self._engine = create_async_engine(
            dsn,
            pool_size=pool_size,
            max_overflow=max_overflow,
            pool_pre_ping=pool_pre_ping,
            pool_recycle=pool_recycle,
            echo=echo,
            connect_args=connect_args or {},
        )

        self._session_factory = async_sessionmaker(
            bind=self._engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

        logger.info(
            "database_engine_created",
            dsn=_sanitise_dsn(dsn),
            pool_size=pool_size,
            max_overflow=max_overflow,
            pool_pre_ping=pool_pre_ping,
        )

    # ------------------------------------------------------------------
    # Session management
    # ------------------------------------------------------------------

    @asynccontextmanager
    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        """Yield an async session with automatic commit / rollback semantics.

        The session is committed on a clean exit and rolled back if an
        exception propagates.  The session is always closed afterwards.

        Yields
        ------
        AsyncSession
            A scoped async session bound to the managed engine.

        Raises
        ------
        RuntimeError
            If the engine has not been initialised via :meth:`create_engine`.

        Example
        -------
        ::

            async with db.get_session() as session:
                session.add(Transaction(amount=100.0))
                # auto-committed on exit
        """
        if self._session_factory is None:
            raise RuntimeError(
                "DatabaseManager is not initialised. "
                "Call create_engine() before requesting sessions."
            )

        session: AsyncSession = self._session_factory()
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------

    async def health_check(self) -> bool:
        """Execute a lightweight query to verify database connectivity.

        Returns
        -------
        bool
            ``True`` if the database responded successfully, ``False``
            otherwise.  This method **never** raises — all exceptions are
            caught and logged so it can be used safely inside Kubernetes
            liveness / readiness probes.
        """
        if self._engine is None:
            logger.warning("health_check_failed", reason="engine_not_initialised")
            return False

        try:
            async with self._engine.connect() as conn:
                result = await conn.execute(text("SELECT 1"))
                row = result.scalar_one_or_none()
                healthy = row == 1

            if healthy:
                logger.debug("database_health_check", status="healthy")
            else:
                logger.warning(
                    "database_health_check",
                    status="unhealthy",
                    reason="unexpected_result",
                    result=row,
                )
            return healthy

        except Exception as exc:
            logger.error(
                "database_health_check",
                status="unhealthy",
                reason=str(exc),
                exc_type=type(exc).__name__,
            )
            return False

    # ------------------------------------------------------------------
    # Shutdown
    # ------------------------------------------------------------------

    async def close(self) -> None:
        """Gracefully dispose of the engine and release all pooled connections.

        This method is safe to call multiple times; subsequent calls are
        no-ops.  It should be invoked during application shutdown (e.g.
        inside a FastAPI ``lifespan`` context manager's teardown phase).
        """
        if self._engine is not None:
            await self._engine.dispose()
            logger.info("database_engine_closed")
            self._engine = None
            self._session_factory = None

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def engine(self) -> AsyncEngine | None:
        """Return the underlying async engine, or ``None`` if not initialised."""
        return self._engine

    @property
    def is_initialised(self) -> bool:
        """Return ``True`` if the engine has been created and is ready."""
        return self._engine is not None


# ═══════════════════════════════════════════════════════════════════════════
# Factory function
# ═══════════════════════════════════════════════════════════════════════════


def get_db_manager(settings: DatabaseSettings) -> DatabaseManager:
    """Create and **partially** initialise a :class:`DatabaseManager`.

    .. note::

        This function instantiates the manager and stores the settings for
        deferred engine creation.  You **must** still call
        :meth:`DatabaseManager.create_engine` (which is async) during
        application startup::

            db = get_db_manager(settings)
            await db.create_engine(
                settings.database_dsn,
                pool_size=settings.database_pool_size,
                max_overflow=settings.database_pool_overflow,
                echo=settings.database_echo_sql,
            )

    Parameters
    ----------
    settings : DatabaseSettings
        Any object satisfying the :class:`DatabaseSettings` protocol.

    Returns
    -------
    DatabaseManager
        A new, uninitialised manager instance.  The caller is responsible
        for calling ``await manager.create_engine(…)`` at startup and
        ``await manager.close()`` at shutdown.

    Raises
    ------
    TypeError
        If *settings* does not satisfy the :class:`DatabaseSettings`
        protocol.
    """
    if not isinstance(settings, DatabaseSettings):
        raise TypeError(
            f"Expected an object satisfying DatabaseSettings protocol, "
            f"got {type(settings).__name__!r}."
        )

    manager = DatabaseManager()

    logger.info(
        "database_manager_created",
        dsn=_sanitise_dsn(settings.database_dsn),
        pool_size=settings.database_pool_size,
        pool_overflow=settings.database_pool_overflow,
    )

    return manager


# ═══════════════════════════════════════════════════════════════════════════
# Internal helpers
# ═══════════════════════════════════════════════════════════════════════════


def _sanitise_dsn(dsn: str) -> str:
    """Mask the password component of a DSN for safe logging.

    Parameters
    ----------
    dsn : str
        A database connection string that may contain credentials.

    Returns
    -------
    str
        The DSN with any password replaced by ``***``.

    Examples
    --------
    >>> _sanitise_dsn("postgresql+asyncpg://user:s3cret@host/db")
    'postgresql+asyncpg://user:***@host/db'
    >>> _sanitise_dsn("postgresql+asyncpg://host/db")
    'postgresql+asyncpg://host/db'
    """
    try:
        # Handle the common pattern: scheme://user:password@host/db
        if "@" in dsn and ":" in dsn.split("@")[0]:
            scheme_user, rest = dsn.rsplit("@", 1)
            # Find the password portion (after last ':' in scheme_user)
            prefix, _ = scheme_user.rsplit(":", 1)
            return f"{prefix}:***@{rest}"
    except (ValueError, IndexError):
        pass
    return dsn
