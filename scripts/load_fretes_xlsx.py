"""
Loads the sorghum harvest freight/cost table (per field/lot) into gbrain_dev.
"""

import argparse
import sys
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text

DEFAULT_DB_URL = "postgresql+psycopg2://localhost/gbrain_dev"

COLUMN_MAP = {
    "Local": "local",
    "Área (ha)": "area_ha",
    "Município": "municipio",
    "Frete R$/saca Peso Liquido Umido": "frete_reais_saca",
    "Colheita  R$/ha ": "colheita_reais_ha",
}

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS fretes_colheita (
    id SERIAL PRIMARY KEY,
    local TEXT,
    area_ha NUMERIC,
    municipio TEXT,
    frete_reais_saca NUMERIC,
    colheita_reais_ha NUMERIC,
    source_file TEXT,
    loaded_at TIMESTAMP DEFAULT now()
);
"""


def load_xlsx(xlsx_path: Path) -> pd.DataFrame:
    raw = pd.read_excel(xlsx_path)
    df = raw.rename(columns=COLUMN_MAP)[list(COLUMN_MAP.values())].copy()
    df["source_file"] = xlsx_path.name
    return df


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("xlsx_path", type=Path)
    parser.add_argument("--db-url", default=DEFAULT_DB_URL)
    args = parser.parse_args()

    if not args.xlsx_path.exists():
        sys.exit(f"File not found: {args.xlsx_path}")

    df = load_xlsx(args.xlsx_path)
    print(f"Parsed {len(df)} rows from {args.xlsx_path.name}")

    engine = create_engine(args.db_url)
    with engine.begin() as conn:
        conn.execute(text(CREATE_TABLE_SQL))

    df.to_sql("fretes_colheita", engine, if_exists="append", index=False, method="multi")
    print(f"Loaded {len(df)} rows into 'fretes_colheita' in {args.db_url}")


if __name__ == "__main__":
    main()
