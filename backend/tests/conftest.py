"""
Pytest configuration for SentinelWatch Backend tests.
"""

import sys
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from sentinelwatch_backend.config import BackendConfig, set_config
from sentinelwatch_backend.database import Base, get_engine, init_database
from sentinelwatch_backend.main import create_app
# Import models to register them with SQLAlchemy Base
from sentinelwatch_backend.models.agent import Agent  # noqa: F401
from sentinelwatch_backend.models.alert import Alert, Evidence  # noqa: F401
from sentinelwatch_backend.models.audit import AuditLog  # noqa: F401
from sentinelwatch_backend.models.detection_rule import Rule  # noqa: F401
from sentinelwatch_backend.models.telemetry import ProcessTelemetry, ServiceTelemetry, StartupInventory, EventLogEntry  # noqa: F401
from sentinelwatch_backend.models.user import User  # noqa: F401


@pytest_asyncio.fixture
async def test_config() -> BackendConfig:
    """Create test configuration with in-memory SQLite."""
    config = BackendConfig(
        database={"url": "sqlite+aiosqlite:///:memory:"},
        server={"debug": True},
        auth={"jwt_secret": "test-secret-key-for-testing-only"},
    )
    set_config(config)
    return config


@pytest_asyncio.fixture
async def test_engine(test_config: BackendConfig):
    """Create test database engine."""
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(
        test_config.database.url,
        connect_args={"check_same_thread": False},
    )

    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(test_engine):
    """Create a database session for each test."""
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    session_factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def app(test_config: BackendConfig):
    """Create FastAPI test application."""
    return create_app(test_config)


@pytest_asyncio.fixture
async def client(app):
    """Create async test client."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


@pytest.fixture(autouse=True)
def reset_config(monkeypatch: pytest.MonkeyPatch):
    """Reset global config before each test.

    Tests must run in an explicit test environment so the production JWT
    secret guard never fires on the placeholder. The environment variable
    is set per-test via monkeypatch so it cannot leak into production runs.
    """
    monkeypatch.setenv("SW_BACKEND_ENVIRONMENT", "test")
    monkeypatch.setenv("ENVIRONMENT", "test")
    set_config(None)
    yield
    set_config(None)
