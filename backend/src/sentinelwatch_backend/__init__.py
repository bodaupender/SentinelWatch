"""
SentinelWatch Backend - FastAPI Application.

Main entry point for the SentinelWatch backend API server.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import BackendConfig, get_config, set_config
from .database import init_database, close_database, Base
from .health import router as health_router
from .logging import setup_logging, setup_audit_logging

# Import all models to register them with SQLAlchemy Base
from .models import (  # noqa: F401
    Agent,
    Alert,
    AuditLog,
    Evidence,
    ProcessTelemetry,
    ServiceTelemetry,
    StartupInventory,
    EventLogEntry,
    User,
    SuppressionRule,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    config = get_config()

    # Setup logging
    setup_logging(config)
    setup_audit_logging(config)

    logger.info("application_starting", version="0.1.0")

    # Initialize database
    await init_database()

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

    from fastapi.middleware.cors import CORSMiddleware

    app = FastAPI(
        title="SentinelWatch API",
        description="SentinelWatch Windows Endpoint Monitoring Platform API",
        version="0.1.0",
        docs_url="/docs" if config.server.debug else None,
        redoc_url="/redoc" if config.server.debug else None,
        openapi_url="/openapi.json" if config.server.debug else None,
        lifespan=lifespan,
    )

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

    # TODO: Include API routers
    # app.include_router(agents_router, prefix="/api/v1/agents", tags=["agents"])
    # app.include_router(telemetry_router, prefix="/api/v1/telemetry", tags=["telemetry"])
    # app.include_router(alerts_router, prefix="/api/v1/alerts", tags=["alerts"])
    # app.include_router(rules_router, prefix="/api/v1/rules", tags=["rules"])
    # app.include_router(auth_router, prefix="/api/v1/auth", tags=["auth"])
    # app.include_router(audit_router, prefix="/api/v1/audit", tags=["audit"])

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

    subparsers.add_parser("migrate-create", help="Create new migration")
    migrate_parser.add_argument("message", help="Migration message")

    subparsers.add_parser("migrate-history", help="Show migration history")

    return parser


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
    if args.command in ("migrate", "migrate-create", "migrate-history"):
        print(f"Migration command '{args.command}' not yet implemented")
        return 1

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
