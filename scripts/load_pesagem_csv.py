"""
Loads a truck weighing ("pesagem") CSV export into the gbrain_dev Postgres database.

Source format notes (as exported by the farm's system):
- Latin-1 encoded, semicolon-delimited, CRLF line endings
- Numbers use Brazilian formatting (comma as decimal separator)
- Dates are dd/mm/yyyy HH:MM
- Quality readings (e.g. UMIDADE, IMPUREZA) are stored in repeated generic
  "Desconto"/"Porcentagem" column pairs rather than named columns, and not
  every row uses all of the pairs -- these are collapsed into a single
  JSONB column here.
"""

import argparse
import json
import sys
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text

DEFAULT_DB_URL = "postgresql+psycopg2://localhost/gbrain_dev"

COLUMN_MAP = {
    "Lote": "lote",
    "Nº Viagem": "numero_viagem",
    "Produto": "produto",
    "ID Placa": "id_placa",
    "Placa": "placa",
    "ID Motorista": "id_motorista",
    "Nome Motorista": "nome_motorista",
    "Tipo Rodado": "tipo_rodado",
    "Tipo Carroceria": "tipo_carroceria",
    "Nº Romaneio": "numero_romaneio",
    "Data Chegada": "data_chegada",
    "Data Aprovação": "data_aprovacao",
    "Data Peso1": "data_peso1",
    "Data Peso2": "data_peso2",
    "Peso Bruto": "peso_bruto_kg",
    "Peso Tara": "peso_tara_kg",
    "Peso Liquido Umido": "peso_liquido_umido_kg",
    "Peso Liquido Seco": "peso_liquido_seco_kg",
    "Chapa": "chapa",
    "Observação": "observacao",
    "Tipo Pesagem": "tipo_pesagem",
    "Proprietário": "proprietario",
    "Cliente": "cliente",
    "Documento": "documento",
    "Local Entrega": "local_entrega",
    "Possui Romaneio": "possui_romaneio",
    "Transgenia": "transgenia",
}

QUALITY_PAIR_COLUMNS = [
    ("Desconto", "Porcentagem"),
    ("Desconto.1", "Porcentagem.1"),
    ("Desconto.2", "Porcentagem.2"),
    ("Desconto.3", "Porcentagem.3"),
]

DATE_COLUMNS = ["data_chegada", "data_aprovacao", "data_peso1", "data_peso2"]
WEIGHT_COLUMNS = [
    "peso_bruto_kg",
    "peso_tara_kg",
    "peso_liquido_umido_kg",
    "peso_liquido_seco_kg",
]

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS pesagens (
    id SERIAL PRIMARY KEY,
    lote NUMERIC,
    numero_viagem TEXT,
    produto TEXT,
    id_placa TEXT,
    placa TEXT,
    id_motorista TEXT,
    nome_motorista TEXT,
    tipo_rodado TEXT,
    tipo_carroceria TEXT,
    numero_romaneio TEXT,
    data_chegada TIMESTAMP,
    data_aprovacao TIMESTAMP,
    data_peso1 TIMESTAMP,
    data_peso2 TIMESTAMP,
    peso_bruto_kg NUMERIC,
    peso_tara_kg NUMERIC,
    peso_liquido_umido_kg NUMERIC,
    peso_liquido_seco_kg NUMERIC,
    chapa TEXT,
    observacao TEXT,
    tipo_pesagem TEXT,
    proprietario TEXT,
    cliente TEXT,
    documento TEXT,
    local_entrega TEXT,
    possui_romaneio TEXT,
    transgenia TEXT,
    parametros_qualidade JSONB,
    source_file TEXT,
    loaded_at TIMESTAMP DEFAULT now()
);
"""


def parse_br_number(value):
    if pd.isna(value):
        return None
    return float(str(value).replace(".", "").replace(",", "."))


def build_quality_params(row):
    params = {}
    for name_col, value_col in QUALITY_PAIR_COLUMNS:
        name = row.get(name_col)
        value = row.get(value_col)
        if pd.notna(name) and pd.notna(value):
            params[str(name).strip()] = parse_br_number(value)
    return params


def load_csv(csv_path: Path) -> pd.DataFrame:
    raw = pd.read_csv(csv_path, sep=";", encoding="latin-1")

    quality_params = raw.apply(build_quality_params, axis=1)

    df = raw.rename(columns=COLUMN_MAP)[list(COLUMN_MAP.values())].copy()
    df["parametros_qualidade"] = quality_params.apply(lambda d: json.dumps(d, ensure_ascii=False))

    for col in WEIGHT_COLUMNS:
        df[col] = df[col].apply(parse_br_number)

    for col in DATE_COLUMNS:
        parsed = pd.to_datetime(df[col], format="%d/%m/%Y %H:%M", errors="coerce")
        bad = parsed.isna() & df[col].notna()
        if bad.any():
            romaneios = df.loc[bad, "numero_romaneio"].tolist()
            print(
                f"WARNING: {bad.sum()} row(s) had an unparseable '{col}' value "
                f"(expected dd/mm/yyyy HH:MM) and were set to null. "
                f"Affected numero_romaneio: {romaneios}",
                file=sys.stderr,
            )
        df[col] = parsed

    df["source_file"] = csv_path.name
    return df


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_path", type=Path, help="Path to the pesagem CSV export")
    parser.add_argument("--db-url", default=DEFAULT_DB_URL, help="SQLAlchemy DB URL")
    args = parser.parse_args()

    if not args.csv_path.exists():
        sys.exit(f"File not found: {args.csv_path}")

    df = load_csv(args.csv_path)
    print(f"Parsed {len(df)} rows from {args.csv_path.name}")

    engine = create_engine(args.db_url)
    with engine.begin() as conn:
        conn.execute(text(CREATE_TABLE_SQL))

    df.to_sql("pesagens", engine, if_exists="append", index=False, method="multi", chunksize=200)
    print(f"Loaded {len(df)} rows into 'pesagens' in {args.db_url}")


if __name__ == "__main__":
    main()
