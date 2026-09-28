"""Migrations run as the OWNER role (MIGRATION_DATABASE_URL) — the app role holds no DDL (§6.6)."""
import os
import sys
from pathlib import Path

# backend/ for config/models, alembic/ for the shared vb_ops helpers
sys.path[:0] = [str(Path(__file__).resolve().parents[1]), str(Path(__file__).resolve().parent)]

from alembic import context
from sqlalchemy import create_engine, pool

import models  # noqa: F401  — registers every model on Base.metadata
from config import get_settings
from models.base import Base

target_metadata = Base.metadata


def _url() -> str:
    return os.environ.get("VB_ALEMBIC_URL") or get_settings().migration_database_url


def run_migrations_online() -> None:
    engine = create_engine(_url(), poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata,
                          compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


run_migrations_online()
