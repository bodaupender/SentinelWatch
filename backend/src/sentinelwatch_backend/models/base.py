"""Shared SQLAlchemy declarative base for all SentinelWatch models."""

# Keep every model in the metadata registry used by database.init_database().
# Defining a second DeclarativeBase here silently left telemetry tables out of
# development schema creation.
from ..database import Base

__all__ = ["Base"]
