"""
SentinelWatch Backend Health Checks.

Provides health and readiness endpoints for Kubernetes probes
and load balancer checks.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .config import get_config
from .database import get_db
from .logging import get_logger


logger = get_logger(__name__)

router = APIRouter(tags=["health"])


@dataclass
class HealthStatus:
    """Health check result."""

    healthy: bool
    component: str
    details: dict[str, Any]
    timestamp: datetime = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now(timezone.utc)

    def to_dict(self) -> dict[str, Any]:
        return {
            "healthy": self.healthy,
            "component": self.component,
            "details": self.details,
            "timestamp": self.timestamp.isoformat(),
        }


class HealthChecker:
    """Performs health checks on system components."""

    def __init__(self):
        self.config = get_config()

    async def check_database(self, db: AsyncSession) -> HealthStatus:
        """Check database connectivity."""
        try:
            # Simple query to verify connection
            result = await db.execute(text("SELECT 1"))
            result.scalar()

            # Check if we can run a transaction
            await db.execute(text("SELECT 1"))
            await db.commit()

            return HealthStatus(
                healthy=True,
                component="database",
                details={"status": "connected", "driver": str(db.bind.dialect)},
            )
        except Exception as e:
            logger.error("health_check_database_failed", error=str(e))
            return HealthStatus(
                healthy=False,
                component="database",
                details={"status": "disconnected", "error": str(e)},
            )

    async def check_database_migrations(self, db: AsyncSession) -> HealthStatus:
        """Check if database migrations are up to date."""
        try:
            # Check alembic_version table
            result = await db.execute(text("SELECT version_num FROM alembic_version"))
            version = result.scalar()

            return HealthStatus(
                healthy=True,
                component="migrations",
                details={"status": "up_to_date", "version": version},
            )
        except Exception as e:
            # Development startup creates the schema from SQLAlchemy metadata and
            # does not maintain an Alembic revision table.
            if self.config.server.debug:
                return HealthStatus(
                    healthy=True,
                    component="migrations",
                    details={
                        "status": "not_applicable",
                        "schema_management": "SQLAlchemy create_all (development)",
                    },
                )
            logger.warning("health_check_migrations_failed", error=str(e))
            return HealthStatus(
                healthy=False,
                component="migrations",
                details={"status": "unknown", "error": str(e)},
            )

    def check_config(self) -> HealthStatus:
        """Check configuration validity."""
        try:
            # Validate critical config
            issues = []

            if self.config.auth.jwt_secret == "CHANGE_ME_IN_PRODUCTION_USE_STRONG_RANDOM_KEY":
                issues.append("Default JWT secret in use")

            if self.config.database.url.startswith("sqlite") and not self.config.server.debug:
                issues.append("SQLite database in production")

            if not self.config.tls.enabled and not self.config.server.debug:
                issues.append("TLS disabled in production")

            healthy = len(issues) == 0

            return HealthStatus(
                healthy=healthy,
                component="configuration",
                details={
                    "status": "valid" if healthy else "issues_found",
                    "issues": issues,
                    "environment": "production" if not self.config.server.debug else "development",
                },
            )
        except Exception as e:
            logger.error("health_check_config_failed", error=str(e))
            return HealthStatus(
                healthy=False,
                component="configuration",
                details={"status": "error", "error": str(e)},
            )

    def check_disk_space(self) -> HealthStatus:
        """Check available disk space."""
        import shutil

        try:
            # Check data directory
            data_path = Path(self.config.database.url.replace("sqlite+aiosqlite:///", "")).parent
            if not data_path.exists():
                data_path = Path(".")

            usage = shutil.disk_usage(data_path)
            free_gb = usage.free / (1024**3)
            total_gb = usage.total / (1024**3)
            percent_free = (usage.free / usage.total) * 100

            # Alert if less than 1GB or 5% free
            healthy = free_gb > 1.0 and percent_free > 5.0

            return HealthStatus(
                healthy=healthy,
                component="disk",
                details={
                    "free_gb": round(free_gb, 2),
                    "total_gb": round(total_gb, 2),
                    "percent_free": round(percent_free, 2),
                    "path": str(data_path),
                },
            )
        except Exception as e:
            logger.error("health_check_disk_failed", error=str(e))
            return HealthStatus(
                healthy=False,
                component="disk",
                details={"status": "error", "error": str(e)},
            )

    def check_memory(self) -> HealthStatus:
        """Check memory usage."""
        import psutil

        try:
            memory = psutil.virtual_memory()
            process = psutil.Process()

            healthy = memory.percent < 90.0

            return HealthStatus(
                healthy=healthy,
                component="memory",
                details={
                    "system_percent": memory.percent,
                    "system_available_gb": round(memory.available / (1024**3), 2),
                    "process_mb": round(process.memory_info().rss / (1024**2), 2),
                },
            )
        except Exception as e:
            logger.error("health_check_memory_failed", error=str(e))
            return HealthStatus(
                healthy=False,
                component="memory",
                details={"status": "error", "error": str(e)},
            )


# Global health checker instance
_health_checker: Optional[HealthChecker] = None


def get_health_checker() -> HealthChecker:
    """Get global health checker instance."""
    global _health_checker
    if _health_checker is None:
        _health_checker = HealthChecker()
    return _health_checker


@router.get("/health")
async def health_check() -> dict[str, Any]:
    """
    Liveness probe endpoint.

    Returns 200 if the application is running.
    Does not check dependencies.
    """
    return {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "version": "0.1.0",
    }


@router.get("/ready")
async def readiness_check(db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """
    Readiness probe endpoint.

    Returns 200 if the application is ready to serve traffic.
    Checks database connectivity and configuration.
    """
    checker = get_health_checker()

    # Run all checks
    checks = [
        await checker.check_database(db),
        checker.check_config(),
        checker.check_disk_space(),
        checker.check_memory(),
    ]

    # Overall readiness
    all_healthy = all(check.healthy for check in checks)

    response = {
        "status": "ready" if all_healthy else "not_ready",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "version": "0.1.0",
        "checks": [check.to_dict() for check in checks],
    }

    if not all_healthy:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=response,
        )

    return response


@router.get("/health/detailed")
async def detailed_health_check(db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """
    Detailed health check endpoint.

    Returns comprehensive health information for all components.
    """
    checker = get_health_checker()

    checks = [
        await checker.check_database(db),
        await checker.check_database_migrations(db),
        checker.check_config(),
        checker.check_disk_space(),
        checker.check_memory(),
    ]

    all_healthy = all(check.healthy for check in checks)

    return {
        "status": "healthy" if all_healthy else "degraded",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "version": "0.1.0",
        "checks": [check.to_dict() for check in checks],
    }
