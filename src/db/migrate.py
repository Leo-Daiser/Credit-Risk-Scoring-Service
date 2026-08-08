"""Apply Alembic migrations, including a safe bridge from the legacy schema."""

from __future__ import annotations

from collections.abc import Collection

from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect

from src.core.config import settings

ALEMBIC_REVISION_TABLE = "alembic_version"
LEGACY_BASE_REVISION = "20260806_01"
LEGACY_TABLES = {
    "model_registry",
    "scoring_requests",
    "scoring_predictions",
    "feature_stats",
}


def classify_schema(table_names: Collection[str]) -> str:
    """Classify a database as empty, Alembic-managed or complete legacy."""
    tables = set(table_names)
    if ALEMBIC_REVISION_TABLE in tables:
        return "managed"
    present_legacy = tables & LEGACY_TABLES
    if not present_legacy:
        return "empty"
    if present_legacy == LEGACY_TABLES:
        return "legacy"
    missing = sorted(LEGACY_TABLES - present_legacy)
    raise RuntimeError(
        "Database contains a partial legacy schema; refusing automatic migration. "
        f"Missing tables: {missing}."
    )


def run_migrations() -> str:
    """Stamp a complete legacy schema when needed, then upgrade to head."""
    engine = create_engine(settings.resolved_database_url, pool_pre_ping=True)
    try:
        state = classify_schema(inspect(engine).get_table_names())
    finally:
        engine.dispose()

    config = Config("alembic.ini")
    if state == "legacy":
        command.stamp(config, LEGACY_BASE_REVISION)
    command.upgrade(config, "head")
    return state


def migrations_are_current(database_url: str | None = None) -> bool:
    """Return whether the database revision matches the configured Alembic head."""
    config = Config("alembic.ini")
    expected = ScriptDirectory.from_config(config).get_current_head()
    engine = create_engine(database_url or settings.resolved_database_url, pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            actual = MigrationContext.configure(connection).get_current_revision()
    finally:
        engine.dispose()
    return actual == expected


def main() -> None:
    previous_state = run_migrations()
    print(f"Database migrations applied (previous_state={previous_state}).")


if __name__ == "__main__":
    main()
