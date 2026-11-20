"""Database initialization utilities for SentinelWatch Backend.

Provides safe database initialization that preserves existing data
and supports migration-based schema management.
"""

import asyncio
import os
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from alembic.config import Config as AlembicConfig
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from .config import get_config
from .database import Base
from .logging import get_logger

logger = get_logger(__name__)

# Resolve the project root (backend/) so all paths are stable regardless of cwd.
_PACKAGE_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _PACKAGE_DIR.parent.parent  # src/sentinelwatch_backend -> backend/


def _resolve_sqlite_path(db_url: str) -> Path:
    """Extract and resolve the SQLite file path from a database URL."""
    if "///" in db_url:
        db_path = db_url.split("///")[1]
    else:
        db_path = db_url.replace("sqlite+aiosqlite:///", "").replace("sqlite:///", "")

    if not os.path.isabs(db_path):
        # Anchor relative to the backend/ directory, not the caller's cwd.
        db_path = (_PROJECT_ROOT / db_path).resolve()

    return Path(db_path)


def _ensure_data_dir(path: Path) -> None:
    """Create the parent directory of *path* if it does not exist."""
    parent = path.parent
    if not parent.exists():
        parent.mkdir(parents=True, exist_ok=True)
        logger.info("created_data_directory", path=str(parent))


def _build_alembic_cfg(database_url: str) -> AlembicConfig:
    """Build an Alembic config with the given database URL, anchored at
    ``_PROJECT_ROOT`` so that scripts_location resolves correctly."""
    cfg = AlembicConfig(_PROJECT_ROOT / "alembic.ini")
    cfg.set_main_option("sqlalchemy.url", database_url)
    return cfg


async def _run_migrations_via_subprocess(database_url: str) -> bool:
    """Run ``alembic upgrade head`` in a child process to avoid event-loop
    conflicts while uvicorn is already running.  Returns True on success."""
    cfg = _build_alembic_cfg(database_url)
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=str(_PROJECT_ROOT),
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode == 0:
        logger.info("database_initialized")
        return True
    logger.error(
        "migration_failed",
        error=result.stderr,
        stdout=result.stdout,
    )
    return False


def get_environment_database_path(config) -> Path:
    """Get environment-specific database path."""
    env = config.server.debug and "development" or os.getenv("ENVIRONMENT", "production").lower()

    db_file = _resolve_sqlite_path(config.database.url)

    if "sqlite" in config.database.url and env in ("development", "test", "testing"):
        env_suffix = "_dev" if env == "development" else "_test"
        return db_file.with_name(f"{db_file.stem}{env_suffix}{db_file.suffix}")

    return db_file


async def check_database_exists() -> bool:
    """Check if database file exists and has tables."""
    config = get_config()
    db_file = _resolve_sqlite_path(config.database.url)

    if "sqlite" not in config.database.url:
        return True

    if not db_file.exists():
        return False

    if db_file.stat().st_size == 0:
        return False

    try:
        conn = sqlite3.connect(str(db_file))
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = cursor.fetchall()
        conn.close()
        return len(tables) > 0
    except Exception:
        return False


async def backup_database(backup_suffix: str = "backup") -> Optional[Path]:
    """Create a backup of the existing database."""
    config = get_config()

    if "sqlite" not in config.database.url:
        logger.warning("backup_not_supported", database_type=config.database.url.split("+")[0])
        return None

    db_file = _resolve_sqlite_path(config.database.url)

    if not db_file.exists():
        return None

    backup_path = db_file.with_name(f"{db_file.stem}_{backup_suffix}{db_file.suffix}")

    try:
        shutil.copy2(db_file, backup_path)
        logger.info("database_backed_up", source=str(db_file), backup=str(backup_path))
        return backup_path
    except Exception as e:
        logger.error("database_backup_failed", error=str(e))
        return None


async def initialize_database_safe(
    force_migrate: bool = False,
    skip_backup: bool = False,
) -> bool:
    """Initialize database safely, preserving existing data."""
    config = get_config()

    db_exists = await check_database_exists()

    if db_exists and not force_migrate:
        logger.info("database_exists_skip_init", message="Database already initialized.")
        return True

    if db_exists:
        logger.info("database_exists_running_migrations", message="Database exists, running migrations...")
        if not skip_backup:
            await backup_database("pre_migration")
    else:
        logger.info("database_not_found_creating", message="No existing database found, creating new schema...")

    # Ensure the data directory exists before attempting any operation.
    db_file = _resolve_sqlite_path(config.database.url)
    _ensure_data_dir(db_file)

    return await _run_migrations_via_subprocess(config.database.url)


async def verify_database_schema() -> dict:
    """Verify that the connected database contains the expected tables."""
    config = get_config()
    db_url = config.database.url
    # Derive expected table names from the ORM metadata so it stays in sync.
    expected_tables = set(Base.metadata.tables.keys())

    result = {
        "schema_ok": False,
        "tables_found": 0,
        "missing_tables": [],
        "extra_tables": [],
        "timestamp": datetime.utcnow().isoformat(),
    }

    if "sqlite" not in db_url:
        # Non-SQLite databases are checked via Alembic history instead.
        result["schema_ok"] = True
        result["note"] = "non-sqlite-database"
        return result

    db_file = _resolve_sqlite_path(db_url)
    if not db_file.exists():
        result["missing_tables"] = sorted(expected_tables)
        return result

    try:
        import aiosqlite

        async with aiosqlite.connect(str(db_file)) as conn:
            async with conn.execute("SELECT name FROM sqlite_master WHERE type='table'") as cur:
                rows = await cur.fetchall()
                existing_tables = {row[0] for row in rows}

        result["tables_found"] = len(existing_tables)
        result["missing_tables"] = sorted(expected_tables - existing_tables)
        result["extra_tables"] = sorted(existing_tables - expected_tables)
        result["schema_ok"] = len(result["missing_tables"]) == 0

        logger.info(
            "schema_verification_complete",
            tables_found=result["tables_found"],
            missing=len(result["missing_tables"]),
            extra=len(result["extra_tables"]),
        )
    except Exception as e:
        logger.error("schema_verification_error", error=str(e))
        result["error"] = str(e)

    return result


async def reset_database(
    confirm: bool = False,
    force: bool = False,
    environment: Optional[str] = None,
) -> bool:
    """Reset the database, dropping all data. Requires confirmation."""
    config = get_config()

    if not confirm and not force:
        logger.error("database_reset_requires_confirmation")
        return False

    db_file = _resolve_sqlite_path(config.database.url)
    if db_file.exists():
        if "sqlite" in config.database.url and environment and environment != "production":
            # Use environment-specific path when resetting for dev/test.
            db_file = get_environment_database_path(config)
        db_file.unlink()
        logger.info("database_reset", path=str(db_file))

    return await _run_migrations_via_subprocess(config.database.url)


async def restore_database(backup_path: Path, confirm: bool = False) -> bool:
    """Restore the database from a backup file."""
    if not confirm:
        logger.error("database_restore_requires_confirmation")
        return False

    if not backup_path.exists():
        logger.error("backup_file_not_found", path=str(backup_path))
        return False

    config = get_config()
    db_file = _resolve_sqlite_path(config.database.url)
    _ensure_data_dir(db_file)

    try:
        shutil.copy2(backup_path, db_file)
        logger.info("database_restored", source=str(backup_path), target=str(db_file))
        return True
    except Exception as e:
        logger.error("database_restore_failed", error=str(e))
        return False


async def verify_database_integrity() -> dict:
    """Run integrity checks against the SQLite database."""
    config = get_config()
    result = {"foreign_keys_ok": False, "checks_passed": False, "errors": []}

    if "sqlite" not in config.database.url:
        result["note"] = "only-applies-to-sqlite"
        return result

    db_file = _resolve_sqlite_path(config.database.url)
    if not db_file.exists():
        result["errors"].append("database-file-missing")
        return result

    try:
        conn = sqlite3.connect(str(db_file))
        cursor = conn.cursor()

        # Check foreign keys are enforced.
        cursor.execute("PRAGMA foreign_keys")
        fk_enabled = cursor.fetchone()[0]

        cursor.execute("PRAGMA foreign_key_check")
        violations = cursor.fetchall()

        cursor.execute("PRAGMA integrity_check")
        integrity = cursor.fetchall()

        conn.close()

        result["foreign_keys_ok"] = fk_enabled == 1 and len(violations) == 0
        all_clean = all(row[0] == "ok" for row in integrity)
        result["checks_passed"] = result["foreign_keys_ok"] and all_clean

        if violations:
            result["foreign_key_violations"] = violations
        clean_integrity = [row for row in integrity if row[0] != "ok"]
        if clean_integrity:
            result["integrity_errors"] = clean_integrity

    except Exception as e:
        result["errors"].append(str(e))

    return result


def get_database_info() -> dict:
    """Return metadata about the configured database."""
    config = get_config()
    info = {
        "url": config.database.url,
        "driver": "aiosqlite" if "sqlite" in config.database.url else "unknown",
        "debug_mode": config.server.debug,
    }

    if "sqlite" in config.database.url:
        db_file = _resolve_sqlite_path(config.database.url)
        info["path"] = str(db_file)
        info["exists"] = db_file.exists()
        if db_file.exists():
            stat = db_file.stat()
            info["size_bytes"] = stat.st_size
            info["size_mb"] = round(stat.st_size / (1024 * 1024), 2)

    return info


def create_fresh_database(environment: str = "development") -> bool:
    """Create a fresh database for the specified environment."""
    config = get_config()

    if "sqlite" not in config.database.url:
        logger.error("fresh_database_only_for_sqlite")
        return False

    db_file = _resolve_sqlite_path(config.database.url)

    if db_file.exists():
        db_file.unlink()
        logger.info("removed_existing_database", path=str(db_file))

    _ensure_data_dir(db_file)

    try:
        return asyncio.run(_run_migrations_via_subprocess(config.database.url))
    except Exception as e:
        logger.error("fresh_database_exception", error=str(e))
        return False
