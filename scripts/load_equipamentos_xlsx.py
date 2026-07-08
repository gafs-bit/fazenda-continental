"""
Loads the equipment/machinery usage log ("Relatório de Equipamentos") into
gbrain_dev.

Unlike pesagens (numero_romaneio) or fretes_colheita (local), this report
has no column that uniquely identifies a row: it's a usage journal, not a
row-per-real-world-entity export. The equipment number repeats across every
day it was used; the hour-meter readings (the next-best candidate) are
entirely absent for ~half the rows (workshop/maintenance entries log hours
worked but no start/end reading).

So the natural key here is a hash of the entire row instead of a real
business column. This makes an exact re-run of the same file safe (no
duplicates), but is a best-effort compromise, not a guarantee: two genuinely
different real-world log entries that happen to match on all 24 columns
would collapse into one row on upsert. If GSB's underlying system has a real
line/entry ID that isn't included in this particular report view, that
would be a strictly better natural key -- worth checking for.

Column note: `porcentagem` here means percent of an hour allocated to this
task/phase -- NOT a quality reading like pesagens' UMIDADE/IMPUREZA
percentages, despite the identical column name in the source exports. This
is exactly the kind of same-name-different-meaning trap a generic/automatic
loader can't catch on its own.
"""

import argparse
import hashlib
import sys
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text

from db_upsert import ensure_unique_constraint, upsert_dataframe
from logging_setup import get_logger

DEFAULT_DB_URL = "postgresql+psycopg2://localhost/gbrain_dev"

logger = get_logger("load_equipamentos_xlsx")

COLUMN_MAP = {
    "Numero": "numero_equipamento",
    "Equipamento": "equipamento",
    "Data": "data",
    "Dia": "dia_semana",
    "Terceiro": "terceiro",
    "Proprietário": "proprietario",
    "Filial": "filial",
    "Área": "area",
    "Sub Área": "sub_area",
    "Ano": "ano",
    "Fase": "fase",
    "Descrição Fase": "descricao_fase",
    "Serviço": "servico",
    "Horímetro Início": "horimetro_inicio",
    "Horímetro Fim": "horimetro_fim",
    "Hora Início": "hora_inicio",
    "Hora Fim": "hora_fim",
    "Horas Trabalhadas": "horas_trabalhadas",
    "Porcentagem": "porcentagem",
    "Valor Horas": "valor_horas",
    "Funcionário": "funcionario",
    "Observação": "observacao",
    "Frete/Hect.": "frete_por_hectare",
    "Ha/Hrs": "ha_por_hora",
}

# Order matters for the hash -- must stay stable across runs.
HASH_COLUMNS = list(COLUMN_MAP.values())

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS uso_equipamentos (
    id SERIAL PRIMARY KEY,
    numero_equipamento TEXT,
    equipamento TEXT,
    data DATE,
    dia_semana TEXT,
    terceiro TEXT,
    proprietario TEXT,
    filial TEXT,
    area TEXT,
    sub_area TEXT,
    ano TEXT,
    fase NUMERIC,
    descricao_fase TEXT,
    servico TEXT,
    horimetro_inicio NUMERIC,
    horimetro_fim NUMERIC,
    hora_inicio TEXT,
    hora_fim TEXT,
    horas_trabalhadas NUMERIC,
    porcentagem NUMERIC,
    valor_horas NUMERIC,
    funcionario TEXT,
    observacao TEXT,
    frete_por_hectare NUMERIC,
    ha_por_hora NUMERIC,
    row_hash TEXT,
    source_file TEXT,
    loaded_at TIMESTAMP DEFAULT now()
);
"""


def _canonical(v) -> str:
    """Stable string form of a cell value for hashing (NaN/None collapse to
    the same sentinel, so a row's hash doesn't depend on how pandas
    happened to represent a missing value)."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "\x00"
    return str(v)


def row_hash(row: pd.Series) -> str:
    canonical = "\x1f".join(_canonical(row[col]) for col in HASH_COLUMNS)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def load_xlsx(xlsx_path: Path) -> pd.DataFrame:
    raw = pd.read_excel(xlsx_path)
    df = raw.rename(columns=COLUMN_MAP)[HASH_COLUMNS].copy()
    df["row_hash"] = df.apply(row_hash, axis=1)
    df["source_file"] = xlsx_path.name

    n_before = len(df)
    df = df.drop_duplicates(subset="row_hash", keep="first")
    n_dropped = n_before - len(df)
    if n_dropped:
        logger.warning(
            f"Dropped {n_dropped} row(s) that share a hash with another row in the "
            "same file (all 24 columns identical) -- Postgres can't upsert the same "
            "conflict key twice in one statement, and by our hash definition they're "
            "the same row anyway. See module docstring."
        )
    return df


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("xlsx_path", type=Path)
    parser.add_argument("--db-url", default=DEFAULT_DB_URL)
    args = parser.parse_args()

    logger.info(f"Starting load: {args.xlsx_path}")

    if not args.xlsx_path.exists():
        logger.error(f"File not found: {args.xlsx_path}")
        sys.exit(f"File not found: {args.xlsx_path}")

    try:
        df = load_xlsx(args.xlsx_path)
        logger.info(f"Parsed {len(df)} unique rows from {args.xlsx_path.name}")

        engine = create_engine(args.db_url)
        with engine.begin() as conn:
            conn.execute(text(CREATE_TABLE_SQL))
            ensure_unique_constraint(
                conn, "uso_equipamentos", "row_hash", "uso_equipamentos_row_hash_key"
            )

        n = upsert_dataframe(engine, "uso_equipamentos", df, conflict_column="row_hash")
        logger.info(f"Upserted {n} rows into 'uso_equipamentos' (matched on row_hash) in {args.db_url}")
    except Exception:
        logger.exception(f"Load failed for {args.xlsx_path}")
        raise


if __name__ == "__main__":
    main()
