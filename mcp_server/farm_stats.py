"""MCP server exposing aggregate/superlative queries over the farm Postgres
tables (pesagens, fretes_colheita) that gbrain's search/query tools cannot
answer reliably (counts, sums, averages, min/max) — see CLAUDE.md.

Every table/field/op/group-by the caller can select comes from a fixed
Python mapping below, never from a raw string the caller supplies directly
as SQL — this is a deliberate, narrow tool, not a general SQL escape hatch.
"""

import os
from typing import Literal, Optional

import psycopg2
import psycopg2.extras
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("farm-stats")

DSN = os.environ.get("FARM_STATS_DSN", "dbname=gbrain_dev")

PESAGEM_FIELDS = {
    "peso_bruto_kg": "peso_bruto_kg",
    "peso_tara_kg": "peso_tara_kg",
    "peso_liquido_umido_kg": "peso_liquido_umido_kg",
    "peso_liquido_seco_kg": "peso_liquido_seco_kg",
    "umidade_pct": "(parametros_qualidade->>'UMIDADE')::numeric",
    "impureza_pct": "(parametros_qualidade->>'IMPUREZA')::numeric",
}
PesagemField = Literal[
    "peso_bruto_kg",
    "peso_tara_kg",
    "peso_liquido_umido_kg",
    "peso_liquido_seco_kg",
    "umidade_pct",
    "impureza_pct",
]

FRETE_FIELDS = {
    "area_ha": "area_ha",
    "frete_reais_saca": "frete_reais_saca",
    "colheita_reais_ha": "colheita_reais_ha",
}
FreteField = Literal["area_ha", "frete_reais_saca", "colheita_reais_ha"]

AggOp = Literal["sum", "avg", "min", "max", "count"]
OP_SQL = {"sum": "SUM", "avg": "AVG", "min": "MIN", "max": "MAX", "count": "COUNT"}


def _connect():
    return psycopg2.connect(DSN)


def _pesagem_filters(
    nome_motorista: Optional[str],
    placa: Optional[str],
    since: Optional[str],
    until: Optional[str],
):
    conditions = []
    params: list = []
    if nome_motorista:
        conditions.append("nome_motorista = %s")
        params.append(nome_motorista)
    if placa:
        conditions.append("placa = %s")
        params.append(placa)
    if since:
        conditions.append("data_chegada >= %s")
        params.append(since)
    if until:
        conditions.append("data_chegada <= %s")
        params.append(until)
    where = (" WHERE " + " AND ".join(conditions)) if conditions else ""
    return where, params


@mcp.tool()
def pesagens_count(
    nome_motorista: Optional[str] = None,
    placa: Optional[str] = None,
    since: Optional[str] = None,
    until: Optional[str] = None,
) -> int:
    """Exact row count in pesagens, optionally filtered by exact driver name,
    exact plate, and/or date range (since/until as YYYY-MM-DD). Use this for
    any "how many loads/records" question — gbrain's search tools cannot
    count reliably (capped result lists, not a real count)."""
    where, params = _pesagem_filters(nome_motorista, placa, since, until)
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(f"SELECT COUNT(*) FROM pesagens{where}", params)
        return cur.fetchone()[0]


@mcp.tool()
def pesagens_aggregate(
    field: PesagemField,
    op: AggOp,
    nome_motorista: Optional[str] = None,
    placa: Optional[str] = None,
    since: Optional[str] = None,
    until: Optional[str] = None,
) -> Optional[float]:
    """Exact sum/avg/min/max/count of a numeric pesagens field (weight in kg,
    or umidade_pct / impureza_pct), optionally filtered by exact driver name,
    exact plate, and/or date range (since/until as YYYY-MM-DD). Use this for
    any total/average/highest/lowest question — gbrain's query/search tools
    rank by text similarity, not numeric value, and cannot answer these
    reliably."""
    col = PESAGEM_FIELDS[field]
    where, params = _pesagem_filters(nome_motorista, placa, since, until)
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(f"SELECT {OP_SQL[op]}({col}) FROM pesagens{where}", params)
        result = cur.fetchone()[0]
        return float(result) if result is not None else None


@mcp.tool()
def pesagens_extremes(
    field: PesagemField,
    direction: Literal["max", "min"],
    n: int = 1,
    nome_motorista: Optional[str] = None,
    placa: Optional[str] = None,
    since: Optional[str] = None,
    until: Optional[str] = None,
) -> dict:
    """The N records with the highest/lowest value of a numeric pesagens
    field, with full context (romaneio, driver, plate, date, value) so the
    answer is independently checkable. Use this for "which load had the
    highest/lowest X" — gbrain's search tools were found wrong 4 times out
    of 5 on this exact question shape (they rank by semantic similarity,
    not numeric value). Returns {"match_found": false, "message": ...} if
    the driver/plate/date filter matches no rows, instead of a bare empty
    list that could be mistaken for "still loading" rather than "no such
    record"."""
    col = PESAGEM_FIELDS[field]
    where, params = _pesagem_filters(nome_motorista, placa, since, until)
    where = where + (" AND " if where else " WHERE ") + f"{col} IS NOT NULL"
    order = "DESC" if direction == "max" else "ASC"
    sql = (
        f"SELECT numero_romaneio, nome_motorista, placa, data_chegada, {col} AS value "
        f"FROM pesagens{where} ORDER BY {col} {order} LIMIT %s"
    )
    with _connect() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, params + [n])
        rows = cur.fetchall()
        if not rows:
            return {
                "match_found": False,
                "message": "No pesagens records match nome_motorista="
                f"{nome_motorista!r}, placa={placa!r}, since={since!r}, until={until!r}.",
            }
        return {"match_found": True, "results": [dict(r) for r in rows]}


@mcp.tool()
def pesagens_date_range() -> dict:
    """Earliest and latest data_chegada (arrival date) across all pesagens
    records. Use this for "what date range does the data cover"."""
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT MIN(data_chegada), MAX(data_chegada) FROM pesagens")
        min_d, max_d = cur.fetchone()
        return {"earliest": str(min_d), "latest": str(max_d)}


@mcp.tool()
def pesagens_group_counts(
    group_by: Literal["nome_motorista", "placa"],
    limit: int = 20,
    since: Optional[str] = None,
    until: Optional[str] = None,
) -> dict:
    """Load counts grouped by driver or plate, ordered highest first. Use
    this for "who made the most loads" or "which plate was used most" —
    gbrain's search tools cannot rank/count across the full corpus. Returns
    {"match_found": false, "message": ...} if the date range matches no
    rows, instead of a bare empty list."""
    where, params = _pesagem_filters(None, None, since, until)
    sql = (
        f"SELECT {group_by} AS value, COUNT(*) AS n FROM pesagens{where} "
        f"GROUP BY {group_by} ORDER BY n DESC LIMIT %s"
    )
    with _connect() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, params + [limit])
        rows = cur.fetchall()
        if not rows:
            return {
                "match_found": False,
                "message": f"No pesagens records match since={since!r}, until={until!r}.",
            }
        return {"match_found": True, "results": [dict(r) for r in rows]}


@mcp.tool()
def pesagens_distinct_count(field: Literal["placa", "nome_motorista"]) -> int:
    """Count of distinct plates or drivers in the pesagens dataset."""
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(f"SELECT COUNT(DISTINCT {field}) FROM pesagens")
        return cur.fetchone()[0]


@mcp.tool()
def fretes_aggregate(
    field: FreteField,
    op: AggOp,
    municipio: Optional[str] = None,
) -> Optional[float]:
    """Exact sum/avg/min/max/count of a numeric fretes_colheita field (area,
    freight rate, or harvest cost), optionally filtered by exact municipio."""
    col = FRETE_FIELDS[field]
    where, params = "", []
    if municipio:
        where = " WHERE municipio = %s"
        params = [municipio]
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(f"SELECT {OP_SQL[op]}({col}) FROM fretes_colheita{where}", params)
        result = cur.fetchone()[0]
        return float(result) if result is not None else None


if __name__ == "__main__":
    mcp.run()
