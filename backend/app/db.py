from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import text
from sqlmodel import Session, SQLModel, create_engine

from app.config import settings

# check_same_thread=False so the engine can be used from FastAPI's threadpool
# and from the background import worker.
engine = create_engine(
    settings.db_url,
    connect_args={"check_same_thread": False},
)


def init_db() -> None:
    Path(settings.data_dir).mkdir(parents=True, exist_ok=True)
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    # Import models so SQLModel.metadata is populated before create_all.
    import app.models  # noqa: F401

    SQLModel.metadata.create_all(engine)
    _migrate(engine)


def _migrate(eng) -> None:
    """Apply additive schema changes that create_all cannot handle."""
    with eng.connect() as conn:
        _migrate_table(conn, "recipe", [
            ("import_job_id",       "INTEGER REFERENCES importjob(id)"),
            ("verification_status", "VARCHAR"),
            ("verification_notes",  "VARCHAR"),
            ("source_pages",        "VARCHAR"),
            ("raw_source_text",     "VARCHAR"),
            ("course",              "VARCHAR"),
            ("calories_per_person", "REAL"),
            ("protein_per_person",  "REAL"),
            ("is_vegetarian",       "BOOLEAN DEFAULT 0"),
            ("is_vegan",            "BOOLEAN DEFAULT 0"),
            ("is_favourite",        "BOOLEAN DEFAULT 0"),
        ])
        _migrate_table(conn, "importjob", [
            ("progress_current", "INTEGER DEFAULT 0"),
            ("progress_total",   "INTEGER DEFAULT 0"),
            ("phase",            "VARCHAR"),
        ])
        conn.commit()


def _migrate_table(conn, table: str, columns: list[tuple[str, str]]) -> None:
    existing = {row[1] for row in conn.execute(text(f"PRAGMA table_info({table})"))}
    for col, col_def in columns:
        if col not in existing:
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {col_def}"))


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session
