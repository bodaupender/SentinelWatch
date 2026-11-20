"""
SentinelWatch Backend - Main FastAPI Application.

Entry point for the backend API server.
"""

import argparse
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import BackendConfig, get_config, set_config
from .database import close_database
from .db_init import initialize_database_safe, verify_database_schema
from .health import router as health_router
from .api.v1 import agents, telemetry, alerts, rules, auth, audit, reports, suppression
from .api.v1.agent_communication import router as agent_comm_router
from .api.v1.ai_investigation import ai_status_router, router as ai_investigation_router
from .api.v1.enrollment_tokens import router as enrollment_tokens_router
from .api.v1.organizations import router as organizations_router
from .api.v1.events import router as events_router
from .logging import get_logger, setup_logging, setup_audit_logging
from .security.rate_limit import RateLimitMiddleware


logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    config = get_config()

    # Setup logging
    setup_logging(config)
    setup_audit_logging(config)

    logger.info("application_starting", version="0.1.0")

    # Initialize database safely (preserves existing data)
    await initialize_database_safe()

    # Verify schema
    schema_info = await verify_database_schema()
    if not schema_info["schema_ok"]:
        logger.warning("schema_verification_issues", **schema_info)
    else:
        logger.info("schema_verified", tables=schema_info["tables_found"])

    logger.info("application_started")

    yield

    # Shutdown
    logger.info("application_stopping")
    await close_database()
    logger.info("application_stopped")


def create_app(config: Optional[BackendConfig] = None) -> FastAPI:
    """Create FastAPI application."""
    if config is None:
        config = get_config()

    set_config(config)

    app = FastAPI(
        title="SentinelWatch API",
        description="SentinelWatch Windows Endpoint Monitoring Platform API",
        version="0.1.0",
        docs_url="/docs" if config.server.debug else None,
        redoc_url="/redoc" if config.server.debug else None,
        openapi_url="/openapi.json" if config.server.debug else None,
        lifespan=lifespan,
    )

    # Added before CORS so rate-limit responses retain CORS and security headers.
    # Counters are process-local; multi-worker deployments must enforce limits at
    # a shared reverse proxy or API gateway as well.
    app.add_middleware(RateLimitMiddleware, config=config.rate_limiting)

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.cors.allowed_origins_list,
        allow_credentials=config.cors.allow_credentials,
        allow_methods=config.cors.allowed_methods_list,
        allow_headers=config.cors.allowed_headers_list,
    )

    # Security headers middleware
    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        if config.tls.enabled:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains; preload"
        return response

    # Request ID middleware
    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        import uuid
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        request.state.request_id = request_id

        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

    # Global exception handler
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        logger.error(
            "unhandled_exception",
            path=request.url.path,
            method=request.method,
            error=str(exc),
            request_id=getattr(request.state, "request_id", None),
            exc_info=True,
        )
        return JSONResponse(
            status_code=500,
            content={
                "error": "Internal server error",
                "request_id": getattr(request.state, "request_id", None),
            },
        )

    # Include routers
    app.include_router(health_router)

    # API v1 routers
    app.include_router(auth.router, prefix="/api/v1")
    app.include_router(agents.router, prefix="/api/v1")
    app.include_router(telemetry.router, prefix="/api/v1")
    app.include_router(alerts.router, prefix="/api/v1")
    app.include_router(rules.router, prefix="/api/v1")
    app.include_router(reports.router, prefix="/api/v1")
    app.include_router(audit.router, prefix="/api/v1")
    app.include_router(suppression.router, prefix="/api/v1")
    app.include_router(enrollment_tokens_router, prefix="/api/v1")
    app.include_router(organizations_router, prefix="/api/v1")
    app.include_router(events_router, prefix="/api/v1")

    # Agent communication router (prefix is already /agent/v1 in router definition)
    app.include_router(agent_comm_router)
    app.include_router(ai_investigation_router, prefix="/api/v1")
    app.include_router(ai_status_router, prefix="/api/v1")

    # Metrics endpoint
    if config.metrics.enabled:
        from prometheus_client import make_asgi_app
        metrics_app = make_asgi_app()
        app.mount(config.metrics.path, metrics_app)

    return app


def create_argument_parser() -> argparse.ArgumentParser:
    """Create command-line argument parser."""
    parser = argparse.ArgumentParser(
        prog="sentinelwatch-backend",
        description="SentinelWatch Backend API Server",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "-c", "--config",
        type=Path,
        help="Path to configuration file (default: config/backend.yaml)",
    )

    parser.add_argument(
        "--host",
        type=str,
        help="Host to bind to (overrides config)",
    )

    parser.add_argument(
        "--port",
        type=int,
        help="Port to listen on (overrides config)",
    )

    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable auto-reload (development)",
    )

    parser.add_argument(
        "--validate-config",
        action="store_true",
        help="Validate configuration and exit",
    )

    parser.add_argument(
        "--version",
        action="version",
        version="%(prog)s 0.1.0",
    )

    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # Database migration commands
    migrate_parser = subparsers.add_parser("migrate", help="Run database migrations")
    migrate_parser.add_argument("revision", nargs="?", default="head", help="Target revision")

    migrate_create_parser = subparsers.add_parser("migrate-create", help="Create new migration")
    migrate_create_parser.add_argument("message", help="Migration message")

    subparsers.add_parser("migrate-history", help="Show migration history")

    # Database lifecycle commands
    db_reset_parser = subparsers.add_parser("db-reset", help="Reset database (drops all data)")
    db_reset_parser.add_argument("--confirm", action="store_true", help="Confirm destructive operation")
    db_reset_parser.add_argument("--force", action="store_true", help="Force reset without prompts (CI)")
    db_reset_parser.add_argument("--environment", choices=["development", "test", "production"], help="Target environment")

    db_backup_parser = subparsers.add_parser("db-backup", help="Create database backup")
    db_backup_parser.add_argument("--suffix", default="backup", help="Backup file suffix")

    db_restore_parser = subparsers.add_parser("db-restore", help="Restore database from backup")
    db_restore_parser.add_argument("backup_path", help="Path to backup file")
    db_restore_parser.add_argument("--confirm", action="store_true", help="Confirm destructive operation")

    db_verify_parser = subparsers.add_parser("db-verify", help="Verify database integrity")

    db_info_parser = subparsers.add_parser("db-info", help="Show database information")

    db_fresh_parser = subparsers.add_parser("db-fresh", help="Create fresh database for environment")
    db_fresh_parser.add_argument("--environment", choices=["development", "test", "production"], default="development", help="Target environment")

    return parser


def run_migrations(config: BackendConfig, revision: str = "head") -> int:
    """Run database migrations."""
    from alembic import command
    from alembic.config import Config as AlembicConfig

    alembic_cfg = AlembicConfig("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", config.database.url)

    try:
        command.upgrade(alembic_cfg, revision)
        print(f"Migrations applied successfully to {revision}")
        return 0
    except Exception as e:
        print(f"Migration failed: {e}", file=sys.stderr)
        return 1


def create_migration(config: BackendConfig, message: str) -> int:
    """Create a new migration."""
    from alembic import command
    from alembic.config import Config as AlembicConfig

    alembic_cfg = AlembicConfig("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", config.database.url)

    try:
        command.revision(alembic_cfg, message=message, autogenerate=True)
        print(f"Migration created: {message}")
        return 0
    except Exception as e:
        print(f"Migration creation failed: {e}", file=sys.stderr)
        return 1


def show_migration_history(config: BackendConfig) -> int:
    """Show migration history."""
    from alembic import command
    from alembic.config import Config as AlembicConfig

    alembic_cfg = AlembicConfig("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", config.database.url)

    try:
        command.history(alembic_cfg)
        return 0
    except Exception as e:
        print(f"Failed to show history: {e}", file=sys.stderr)
        return 1


def reset_database_cli(config: BackendConfig, confirm: bool, force: bool, environment: Optional[str]) -> int:
    """Reset database via CLI."""
    import asyncio
    from .db_init import reset_database

    if not confirm and not force:
        print("ERROR: Database reset requires --confirm or --force flag", file=sys.stderr)
        print("WARNING: This will destroy ALL data in the database!", file=sys.stderr)
        return 1

    try:
        result = asyncio.run(reset_database(confirm=confirm, force=force, environment=environment))
        if result:
            print("Database reset completed successfully")
            return 0
        else:
            print("Database reset failed", file=sys.stderr)
            return 1
    except Exception as e:
        print(f"Database reset failed: {e}", file=sys.stderr)
        return 1


def backup_database_cli(config: BackendConfig, suffix: str) -> int:
    """Create database backup via CLI."""
    import asyncio
    from .db_init import backup_database

    try:
        backup_path = asyncio.run(backup_database(suffix))
        if backup_path:
            print(f"Backup created: {backup_path}")
            return 0
        else:
            print("Backup failed or not supported for this database type", file=sys.stderr)
            return 1
    except Exception as e:
        print(f"Backup failed: {e}", file=sys.stderr)
        return 1


def restore_database_cli(config: BackendConfig, backup_path: str, confirm: bool) -> int:
    """Restore database from backup via CLI."""
    import asyncio
    from pathlib import Path
    from .db_init import restore_database

    if not confirm:
        print("ERROR: Database restore requires --confirm flag", file=sys.stderr)
        print("WARNING: This will overwrite the current database!", file=sys.stderr)
        return 1

    try:
        result = asyncio.run(restore_database(Path(backup_path), confirm=True))
        if result:
            print("Database restored successfully")
            return 0
        else:
            print("Database restore failed", file=sys.stderr)
            return 1
    except Exception as e:
        print(f"Database restore failed: {e}", file=sys.stderr)
        return 1


def verify_database_cli(config: BackendConfig) -> int:
    """Verify database integrity via CLI."""
    import asyncio
    from .db_init import verify_database_integrity

    try:
        result = asyncio.run(verify_database_integrity())
        print(f"Foreign keys OK: {result.get('foreign_keys_ok', False)}")
        print(f"Checks passed: {result.get('checks_passed', False)}")

        if result.get('foreign_key_violations'):
            print(f"Foreign key violations: {result['foreign_key_violations']}")

        if result.get('orphaned_records'):
            print(f"Orphaned records: {result['orphaned_records']}")

        if result.get('checks_passed'):
            print("All integrity checks passed")
            return 0
        else:
            print("Integrity checks FAILED", file=sys.stderr)
            return 1
    except Exception as e:
        print(f"Verification failed: {e}", file=sys.stderr)
        return 1


def database_info_cli(config: BackendConfig) -> int:
    """Show database information via CLI."""
    import asyncio
    from .db_init import get_database_info

    try:
        info = asyncio.run(get_database_info())
        for key, value in info.items():
            print(f"{key}: {value}")
        return 0
    except Exception as e:
        print(f"Failed to get database info: {e}", file=sys.stderr)
        return 1


def fresh_database_cli(config: BackendConfig, environment: str) -> int:
    """Create fresh database for environment via CLI."""
    from .db_init import create_fresh_database

    try:
        result = create_fresh_database(environment)
        if result:
            print(f"Fresh {environment} database created successfully")
            return 0
        else:
            print("Fresh database creation failed", file=sys.stderr)
            return 1
    except Exception as e:
        print(f"Fresh database creation failed: {e}", file=sys.stderr)
        return 1


def main() -> int:
    """Main entry point."""
    parser = create_argument_parser()
    args = parser.parse_args()

    # Load configuration
    try:
        config = BackendConfig.load(args.config)
    except Exception as e:
        print(f"Failed to load configuration: {e}", file=sys.stderr)
        return 1

    # Override config with CLI args
    if args.host:
        config.server.host = args.host
    if args.port:
        config.server.port = args.port
    if args.reload:
        config.server.debug = True

    # Validate config
    if args.validate_config:
        print("Configuration valid!")
        print(f"Server: {config.server.host}:{config.server.port}")
        print(f"Database: {config.database.url}")
        print(f"Debug: {config.server.debug}")
        return 0

    # Handle migration commands
    if args.command == "migrate":
        return run_migrations(config, args.revision)
    elif args.command == "migrate-create":
        return create_migration(config, args.message)
    elif args.command == "migrate-history":
        return show_migration_history(config)
    elif args.command == "db-reset":
        return reset_database_cli(config, args.confirm, args.force, args.environment)
    elif args.command == "db-backup":
        return backup_database_cli(config, args.suffix)
    elif args.command == "db-restore":
        return restore_database_cli(config, args.backup_path, args.confirm)
    elif args.command == "db-verify":
        return verify_database_cli(config)
    elif args.command == "db-info":
        return database_info_cli(config)
    elif args.command == "db-fresh":
        return fresh_database_cli(config, args.environment)

    # Run server
    import uvicorn

    uvicorn.run(
        "sentinelwatch_backend.main:create_app",
        factory=True,
        host=config.server.host,
        port=config.server.port,
        reload=config.server.debug,
        workers=config.server.workers if not config.server.debug else 1,
        log_config=None,  # We use structlog
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
