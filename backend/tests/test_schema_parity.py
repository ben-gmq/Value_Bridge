"""Migrations and models describe the same schema (sara M2). Autogenerate misses partial and
expression indexes, so index and unique-constraint names are compared from pg_indexes too."""
import os

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import UniqueConstraint, create_engine, text

from models import Base


def test_models_match_the_migrated_database():
    eng = create_engine(os.environ["MIGRATION_DATABASE_URL"])
    with eng.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
        rows = conn.execute(text("SELECT tablename, indexname FROM pg_indexes "
                                 "WHERE schemaname = 'public' AND indexname NOT LIKE '%_pkey' "
                                 "AND tablename <> 'alembic_version'")).all()
    eng.dispose()
    assert diff == []
    in_db = {(t, i) for t, i in rows}
    in_models = {(t.name, ix.name) for t in Base.metadata.tables.values() for ix in t.indexes} | {
        (t.name, c.name) for t in Base.metadata.tables.values() for c in t.constraints
        if isinstance(c, UniqueConstraint) and c.name} | {
        (t.name, f"{t.name}_{col.name}_key") for t in Base.metadata.tables.values()   # column unique=True
        for col in t.columns if col.unique}
    assert sorted(in_db - in_models) == [], "index in a migration but not its model"
    assert sorted(in_models - in_db) == [], "index in a model but not its migration"
