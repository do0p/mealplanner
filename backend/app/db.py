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
    _enable_wal(engine)


def _enable_wal(eng) -> None:
    with eng.connect() as conn:
        conn.execute(text("PRAGMA journal_mode=WAL"))
        conn.execute(text("PRAGMA busy_timeout=5000"))
        conn.commit()


def _drop_verification_columns(conn) -> None:
    """Remove verification_status / verification_notes from the recipe table.

    SQLite cannot ALTER COLUMN, so we use the standard table-rebuild technique.
    This is a one-shot migration: if neither column is present the function is a no-op.
    """
    rows = conn.execute(text("PRAGMA table_info(recipe)")).fetchall()
    # rows: (cid, name, type, notnull, dflt_value, pk)
    if not any(r[1] in ("verification_status", "verification_notes") for r in rows):
        return

    REMOVE = {"verification_status", "verification_notes"}
    keep = [r for r in rows if r[1] not in REMOVE]

    def _col_sql(r: tuple) -> str:
        _, name, typ, notnull, dflt, pk = r
        parts = [f'"{name}"', typ or "TEXT"]
        if pk == 1:
            parts.append("PRIMARY KEY")
        else:
            if notnull:
                parts.append("NOT NULL")
            if dflt is not None:
                parts.append(f"DEFAULT {dflt}")
        return " ".join(parts)

    col_defs   = ", ".join(_col_sql(r) for r in keep)
    keep_names = ", ".join(f'"{r[1]}"' for r in keep)

    conn.execute(text("PRAGMA foreign_keys=OFF"))
    conn.execute(text("DROP TABLE IF EXISTS recipe_v2"))
    conn.execute(text(f"CREATE TABLE recipe_v2 ({col_defs})"))
    conn.execute(text(f"INSERT INTO recipe_v2 ({keep_names}) SELECT {keep_names} FROM recipe"))
    conn.execute(text("DROP TABLE recipe"))
    conn.execute(text("ALTER TABLE recipe_v2 RENAME TO recipe"))
    conn.execute(text("PRAGMA foreign_keys=ON"))


def _migrate(eng) -> None:
    """Apply additive schema changes that create_all cannot handle."""
    with eng.connect() as conn:
        _drop_verification_columns(conn)
        _migrate_table(conn, "recipe", [
            ("import_job_id",       "INTEGER REFERENCES importjob(id)"),
            ("source_pages",        "VARCHAR"),
            ("raw_source_text",     "VARCHAR"),
            ("course",              "VARCHAR"),
            ("calories_per_person", "REAL"),
            ("protein_per_person",  "REAL"),
            ("fat_per_person",      "REAL"),
            ("carbs_per_person",    "REAL"),
            ("is_vegetarian",       "BOOLEAN DEFAULT 0"),
            ("is_vegan",            "BOOLEAN DEFAULT 0"),
            ("is_favourite",        "BOOLEAN DEFAULT 0"),
            ("is_want_to_try",     "BOOLEAN DEFAULT 0"),
        ])
        _migrate_table(conn, "importjob", [
            ("progress_current", "INTEGER DEFAULT 0"),
            ("progress_total",   "INTEGER DEFAULT 0"),
            ("phase",            "VARCHAR"),
        ])
        _normalize_recipe_titles(conn)
        conn.commit()


def _normalize_recipe_titles(conn) -> None:
    """Title-case any recipe whose title is stored in ALL CAPS (PDF extraction artifact)."""
    rows = conn.execute(text("SELECT id, title FROM recipe")).fetchall()
    for recipe_id, title in rows:
        if not title:
            continue
        if title == title.upper() and any(c.isalpha() for c in title):
            conn.execute(
                text("UPDATE recipe SET title = :t WHERE id = :id"),
                {"t": title.strip().title(), "id": recipe_id},
            )


def _migrate_table(conn, table: str, columns: list[tuple[str, str]]) -> None:
    existing = {row[1] for row in conn.execute(text(f"PRAGMA table_info({table})"))}
    for col, col_def in columns:
        if col not in existing:
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {col_def}"))


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session
