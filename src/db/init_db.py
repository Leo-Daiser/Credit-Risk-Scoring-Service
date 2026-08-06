from src.db.migrate import run_migrations


def init_db() -> None:
    """Apply all database migrations (kept as a backward-compatible CLI name)."""
    run_migrations()
