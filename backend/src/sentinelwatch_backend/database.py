"""
SentinelWatch Backend Database Layer.

SQLAlchemy 2.0 async ORM setup with session management,
connection pooling, and migration support.
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional

from sqlalchemy import MetaData, event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from .config import get_config
from .logging import get_logger


logger = get_logger(__name__)

# Global engine and session factory
_engine = None
_session_factory: Optional[async_sessionmaker[AsyncSession]] = None


class Base(DeclarativeBase):
    """Base class for all ORM models."""

    metadata = MetaData(
        naming_convention={
            "ix": "ix_%(column_0_label)s",
            "uq": "uq_%(table_name)s_%(column_0_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        }
    )


def get_engine():
    """Get or create the async database engine."""
    global _engine
    if _engine is None:
        config = get_config()
        is_sqlite = "sqlite" in config.database.url
        engine_kwargs: dict = {}
        if not is_sqlite:
            engine_kwargs["pool_size"] = config.database.pool_size
            engine_kwargs["max_overflow"] = config.database.max_overflow
            engine_kwargs["pool_timeout"] = config.database.pool_timeout
            engine_kwargs["pool_recycle"] = config.database.pool_recycle

        _engine = create_async_engine(
            config.database.url,
            echo=config.database.echo,
            connect_args={"check_same_thread": False} if is_sqlite else {},
            **engine_kwargs,
        )

        # Enable foreign keys for SQLite
        if is_sqlite:

            @event.listens_for(_engine.sync_engine, "connect")
            def set_sqlite_pragma(dbapi_connection, connection_record):
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.close()

    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Get or create the async session factory."""
    global _session_factory
    if _session_factory is None:
        engine = get_engine()
        _session_factory = async_sessionmaker(
            engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )
    return _session_factory


async def init_database() -> None:
    """Initialize database connection and create tables."""
    global _engine, _session_factory

    config = get_config()
    logger.info("database_initializing", url=config.database.url)

    is_sqlite = "sqlite" in config.database.url
    engine_kwargs: dict = {}
    if not is_sqlite:
        engine_kwargs["pool_size"] = config.database.pool_size
        engine_kwargs["max_overflow"] = config.database.max_overflow
        engine_kwargs["pool_timeout"] = config.database.pool_timeout
        engine_kwargs["pool_recycle"] = config.database.pool_recycle

    _engine = create_async_engine(
        config.database.url,
        echo=config.database.echo,
        connect_args={"check_same_thread": False} if is_sqlite else {},
        **engine_kwargs,
    )

    if is_sqlite:

        @event.listens_for(_engine.sync_engine, "connect")
        def set_sqlite_pragma(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    _session_factory = async_sessionmaker(
        _engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )

    # Import all models to register them
    from .models import (  # noqa: F401
        Agent,
        Alert,
        AuditLog,
        Evidence,
        ProcessTelemetry,
        Rule,
        ServiceTelemetry,
        StartupInventory,
        User,
    )

    # Create tables (in development; production uses migrations)
    if config.server.debug:
        async with _engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("database_tables_created")

    logger.info("database_initialized")


async def close_database() -> None:
    """Close database connections."""
    global _engine, _session_factory
    if _engine:
        await _engine.dispose()
        _engine = None
        _session_factory = None
        logger.info("database_closed")


@asynccontextmanager
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Get a database session for dependency injection."""
    session_factory = get_session_factory()
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# FastAPI dependency
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency for database session."""
    async with get_db_session() as session:
        yield session


# For use in background tasks
async def get_background_session() -> AsyncSession:
    """Get a session for background tasks (caller must close)."""
    session_factory = get_session_factory()
    return session_factory()


# Database health check
async def check_database_connection() -> bool:
    """Check if database is accessible."""
    try:
        from sqlalchemy import text

        async with get_db_session() as session:
            await session.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.error("database_health_check_failed", error=str(e))
        return False
