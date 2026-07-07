"""
Shared upsert helper for the loader scripts.

Makes re-running a loader against a cumulative export safe: rows are matched
on a natural key (e.g. numero_romaneio, local) and updated in place instead
of being duplicated the way a plain `df.to_sql(if_exists="append")` would.

Note on JSONB columns: pass the raw Python dict/list in the DataFrame, never
a pre-`json.dumps`'d string. SQLAlchemy's JSONB type serializes the bind value
itself -- handing it an already-serialized string causes it to be serialized
AGAIN (wrapping the JSON text in a JSON string literal), corrupting the
column. Same double-encoding class of bug as gbrain's own JSONB guard.
"""

import math

import pandas as pd
from sqlalchemy import MetaData, Table, text
from sqlalchemy.dialects.postgresql import insert as pg_insert


def clean_value(v):
    """Convert pandas NaN/NaT to None so they bind as SQL NULL."""
    if v is None:
        return None
    if isinstance(v, float) and math.isnan(v):
        return None
    if v is pd.NaT:
        return None
    return v


def ensure_unique_constraint(conn, table_name: str, column: str, constraint_name: str) -> None:
    """Idempotently add a UNIQUE constraint if it doesn't already exist."""
    conn.execute(text(f"""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = '{constraint_name}'
            ) THEN
                ALTER TABLE {table_name} ADD CONSTRAINT {constraint_name} UNIQUE ({column});
            END IF;
        END $$;
    """))


def upsert_dataframe(engine, table_name: str, df: pd.DataFrame, conflict_column: str, chunksize: int = 200) -> int:
    """Insert df into table_name; rows matching an existing conflict_column
    value are updated in place instead of duplicated. Returns rows upserted."""
    metadata = MetaData()
    table = Table(table_name, metadata, autoload_with=engine)

    records = [
        {k: clean_value(v) for k, v in record.items()}
        for record in df.to_dict(orient="records")
    ]

    update_cols = [c.name for c in table.columns if c.name not in ("id", conflict_column, "loaded_at")]

    total = 0
    with engine.begin() as conn:
        for i in range(0, len(records), chunksize):
            chunk = records[i:i + chunksize]
            stmt = pg_insert(table).values(chunk)
            stmt = stmt.on_conflict_do_update(
                index_elements=[conflict_column],
                set_={col: stmt.excluded[col] for col in update_cols},
            )
            conn.execute(stmt)
            total += len(chunk)
    return total
