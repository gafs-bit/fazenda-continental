"""MCP server exposing direct, deterministic queries over the farm Postgres
tables (pesagens, fretes_colheita, uso_equipamentos) — replaces gbrain as
the storage/retrieval layer for these three tables entirely (see CLAUDE.md
and docs/AUDIT.md for why: gbrain's search/query tools were audited and
found unreliable for exact-ID lookups and cannot aggregate at all).

Four tool shapes, per table where it applies:
  - exact-key lookup (*_get)            — pesagem_get, frete_get
  - filtered search (0..N rows)         — uso_equipamentos_search
  - aggregate/superlative               — *_count, *_aggregate, *_extremes,
                                           *_group_counts, *_distinct_count
  - free-text substring search          — *_search_observacao

Every table/field/op/group-by the caller can select comes from a fixed
Python mapping below, never from a raw string the caller supplies directly
as SQL — this is a deliberate, narrow tool, not a general SQL escape hatch.

Every tool that returns a dict carries a "match_found" key, including the
exact-key lookups on success (not just on failure) — one invariant to
remember ("always check match_found") instead of a special case per tool.
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

USO_FIELDS = {
    "horas_trabalhadas": "horas_trabalhadas",
    "valor_horas": "valor_horas",
    "ha_por_hora": "ha_por_hora",
    "frete_por_hectare": "frete_por_hectare",
}
UsoField = Literal["horas_trabalhadas", "valor_horas", "ha_por_hora", "frete_por_hectare"]

AggOp = Literal["sum", "avg", "min", "max", "count"]
OP_SQL = {"sum": "SUM", "avg": "AVG", "min": "MIN", "max": "MAX", "count": "COUNT"}


def _connect():
    return psycopg2.connect(DSN)


def _row_or_not_found(row, not_found_message: str) -> dict:
    """Shared success/failure envelope for single-row exact-key lookups —
    same {"match_found": ...} invariant as every other dict-returning tool
    in this file, so a caller never has to remember a special case."""
    if row is None:
        return {"match_found": False, "message": not_found_message}
    return {"match_found": True, "record": dict(row)}


POSSUI_ROMANEIO_TEXT = {
    True: "A Pesagem possui Romaneio",
    False: "A Pesagem não possui Romaneio",
}


def _pesagem_filters(
    nome_motorista: Optional[str],
    placa: Optional[str],
    since: Optional[str],
    until: Optional[str],
    produto: Optional[str] = None,
    possui_romaneio: Optional[bool] = None,
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
    if produto:
        conditions.append("produto = %s")
        params.append(produto)
    if possui_romaneio is not None:
        conditions.append("possui_romaneio = %s")
        params.append(POSSUI_ROMANEIO_TEXT[possui_romaneio])
    where = (" WHERE " + " AND ".join(conditions)) if conditions else ""
    return where, params


@mcp.tool()
def pesagem_get(numero_romaneio: str) -> dict:
    """Full pesagens row (all columns) for an exact numero_romaneio — the
    table's natural key (UNIQUE constraint pesagens_numero_romaneio_key).
    Use this for any exact-Romaneio lookup instead of gbrain search: a
    direct indexed WHERE either finds the row or doesn't, with none of the
    ranking/fabrication failure modes gbrain's search tools were audited to
    have for nonexistent IDs (see docs/AUDIT.md). Returns
    {"match_found": false, "message": ...} if no row has that
    numero_romaneio, and {"match_found": true, "record": {...}} otherwise —
    check match_found, not whether the dict happens to be non-empty."""
    with _connect() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT * FROM pesagens WHERE numero_romaneio = %s", [numero_romaneio])
        row = cur.fetchone()
        return _row_or_not_found(
            row, f"No pesagens record found for numero_romaneio={numero_romaneio!r}."
        )


@mcp.tool()
def pesagens_count(
    nome_motorista: Optional[str] = None,
    placa: Optional[str] = None,
    since: Optional[str] = None,
    until: Optional[str] = None,
    produto: Optional[str] = None,
    possui_romaneio: Optional[bool] = None,
) -> int:
    """Exact row count in pesagens, optionally filtered by exact driver name,
    exact plate, date range (since/until as YYYY-MM-DD), exact crop/product
    name (produto), and/or whether the weighing has a romaneio (possui_
    romaneio). Use this for any "how many loads/records" question —
    gbrain's search tools cannot count reliably (capped result lists, not a
    real count)."""
    where, params = _pesagem_filters(
        nome_motorista, placa, since, until, produto, possui_romaneio
    )
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
    produto: Optional[str] = None,
    possui_romaneio: Optional[bool] = None,
) -> Optional[float]:
    """Exact sum/avg/min/max/count of a numeric pesagens field (weight in kg,
    or umidade_pct / impureza_pct), optionally filtered by exact driver name,
    exact plate, date range (since/until as YYYY-MM-DD), exact crop/product
    name (produto), and/or whether the weighing has a romaneio (possui_
    romaneio). Use this for any total/average/highest/lowest question —
    gbrain's query/search tools rank by text similarity, not numeric value,
    and cannot answer these reliably."""
    col = PESAGEM_FIELDS[field]
    where, params = _pesagem_filters(
        nome_motorista, placa, since, until, produto, possui_romaneio
    )
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
    produto: Optional[str] = None,
    possui_romaneio: Optional[bool] = None,
) -> dict:
    """The N records with the highest/lowest value of a numeric pesagens
    field, with full context (romaneio, driver, plate, date, value) so the
    answer is independently checkable. Optionally filtered by exact driver
    name, exact plate, date range, exact crop/product name (produto), and/or
    whether the weighing has a romaneio (possui_romaneio). Use this for
    "which load had the highest/lowest X" — gbrain's search tools were found
    wrong 4 times out of 5 on this exact question shape (they rank by
    semantic similarity, not numeric value). Returns {"match_found": false,
    "message": ...} if the filter matches no rows, instead of a bare empty
    list that could be mistaken for "still loading" rather than "no such
    record"."""
    col = PESAGEM_FIELDS[field]
    where, params = _pesagem_filters(
        nome_motorista, placa, since, until, produto, possui_romaneio
    )
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
def frete_get(local: str) -> dict:
    """Full fretes_colheita row (all columns) for an exact local — the
    table's natural key (UNIQUE constraint fretes_colheita_local_key). Use
    this for any exact-Talhão lookup instead of gbrain search. Same
    {"match_found": ...} envelope as pesagem_get."""
    with _connect() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT * FROM fretes_colheita WHERE local = %s", [local])
        row = cur.fetchone()
        return _row_or_not_found(row, f"No fretes_colheita record found for local={local!r}.")


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


def _uso_filters(
    numero_equipamento: Optional[str] = None,
    funcionario: Optional[str] = None,
    servico: Optional[str] = None,
    descricao_fase: Optional[str] = None,
    since: Optional[str] = None,
    until: Optional[str] = None,
):
    conditions = []
    params: list = []
    if numero_equipamento:
        conditions.append("numero_equipamento = %s")
        params.append(numero_equipamento)
    if funcionario:
        conditions.append("funcionario = %s")
        params.append(funcionario)
    if servico:
        conditions.append("servico = %s")
        params.append(servico)
    if descricao_fase:
        conditions.append("descricao_fase = %s")
        params.append(descricao_fase)
    if since:
        conditions.append("data >= %s")
        params.append(since)
    if until:
        conditions.append("data <= %s")
        params.append(until)
    where = (" WHERE " + " AND ".join(conditions)) if conditions else ""
    return where, params


@mcp.tool()
def uso_equipamentos_search(
    numero_equipamento: Optional[str] = None,
    funcionario: Optional[str] = None,
    servico: Optional[str] = None,
    descricao_fase: Optional[str] = None,
    since: Optional[str] = None,
    until: Optional[str] = None,
    limit: int = 20,
) -> dict:
    """Matching uso_equipamentos rows (the equipment/machinery usage
    journal — one row per equipment/day/phase/service entry; no single-row
    natural key, row_hash is dedup-only, not a lookup key), filtered by any
    combination of exact numero_equipamento, exact funcionario, exact
    servico, exact descricao_fase, and/or date range (since/until as
    YYYY-MM-DD on the `data` column). Ordered by data DESC, capped at
    `limit` (default 20) — a loose filter like just funcionario can match
    thousands of the 22,575 total rows; use uso_equipamentos_count /
    uso_equipamentos_aggregate instead if you want a total, not a row list.
    Returns {"match_found": false, "message": ...} if nothing matches,
    {"match_found": true, "results": [...]} otherwise."""
    where, params = _uso_filters(
        numero_equipamento, funcionario, servico, descricao_fase, since, until
    )
    sql = (
        "SELECT numero_equipamento, equipamento, data, funcionario, servico, "
        "descricao_fase, horas_trabalhadas, valor_horas, observacao, row_hash "
        f"FROM uso_equipamentos{where} ORDER BY data DESC LIMIT %s"
    )
    with _connect() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, params + [limit])
        rows = cur.fetchall()
        if not rows:
            return {
                "match_found": False,
                "message": "No uso_equipamentos records match numero_equipamento="
                f"{numero_equipamento!r}, funcionario={funcionario!r}, servico={servico!r}, "
                f"descricao_fase={descricao_fase!r}, since={since!r}, until={until!r}.",
            }
        return {"match_found": True, "results": [dict(r) for r in rows]}


@mcp.tool()
def uso_equipamentos_count(
    numero_equipamento: Optional[str] = None,
    funcionario: Optional[str] = None,
    servico: Optional[str] = None,
    descricao_fase: Optional[str] = None,
    since: Optional[str] = None,
    until: Optional[str] = None,
) -> int:
    """Exact row count in uso_equipamentos, optionally filtered — same
    filter set as uso_equipamentos_search. Use for "how many entries/days"
    questions."""
    where, params = _uso_filters(
        numero_equipamento, funcionario, servico, descricao_fase, since, until
    )
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(f"SELECT COUNT(*) FROM uso_equipamentos{where}", params)
        return cur.fetchone()[0]


@mcp.tool()
def uso_equipamentos_aggregate(
    field: UsoField,
    op: AggOp,
    numero_equipamento: Optional[str] = None,
    funcionario: Optional[str] = None,
    servico: Optional[str] = None,
    descricao_fase: Optional[str] = None,
    since: Optional[str] = None,
    until: Optional[str] = None,
) -> Optional[float]:
    """Exact sum/avg/min/max/count of a numeric uso_equipamentos field
    (hours worked, R$ value of hours, hectares/hour, or R$ freight/
    hectare), optionally filtered — same filter set as
    uso_equipamentos_search. Note: horas_trabalhadas/horimetro readings are
    NULL for maintenance/workshop-only entries (roughly half the rows, per
    load_equipamentos_xlsx.py's docstring) — SQL sum/avg skip NULLs
    silently, same behavior pesagens_aggregate already has for partially-
    populated fields (umidade_pct/impureza_pct)."""
    col = USO_FIELDS[field]
    where, params = _uso_filters(
        numero_equipamento, funcionario, servico, descricao_fase, since, until
    )
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(f"SELECT {OP_SQL[op]}({col}) FROM uso_equipamentos{where}", params)
        result = cur.fetchone()[0]
        return float(result) if result is not None else None


@mcp.tool()
def uso_equipamentos_extremes(
    field: UsoField,
    direction: Literal["max", "min"],
    n: int = 1,
    numero_equipamento: Optional[str] = None,
    funcionario: Optional[str] = None,
    servico: Optional[str] = None,
    descricao_fase: Optional[str] = None,
    since: Optional[str] = None,
    until: Optional[str] = None,
) -> dict:
    """The N uso_equipamentos entries with the highest/lowest value of a
    numeric field, with full context (equipment, date, employee, service,
    value) for an independently-checkable answer. Same
    {"match_found": ...} contract as pesagens_extremes."""
    col = USO_FIELDS[field]
    where, params = _uso_filters(
        numero_equipamento, funcionario, servico, descricao_fase, since, until
    )
    where = where + (" AND " if where else " WHERE ") + f"{col} IS NOT NULL"
    order = "DESC" if direction == "max" else "ASC"
    sql = (
        "SELECT numero_equipamento, equipamento, data, funcionario, servico, "
        f"descricao_fase, {col} AS value FROM uso_equipamentos{where} "
        f"ORDER BY {col} {order} LIMIT %s"
    )
    with _connect() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, params + [n])
        rows = cur.fetchall()
        if not rows:
            return {
                "match_found": False,
                "message": "No uso_equipamentos records match the given filters "
                f"(numero_equipamento={numero_equipamento!r}, funcionario={funcionario!r}).",
            }
        return {"match_found": True, "results": [dict(r) for r in rows]}


@mcp.tool()
def uso_equipamentos_group_counts(
    group_by: Literal["numero_equipamento", "funcionario", "servico", "descricao_fase"],
    limit: int = 20,
    since: Optional[str] = None,
    until: Optional[str] = None,
) -> dict:
    """Entry counts grouped by equipment/employee/service/phase, ordered
    highest first. Use for "which equipment/employee has the most entries"
    — same {"match_found": ...} contract as pesagens_group_counts."""
    where, params = _uso_filters(None, None, None, None, since, until)
    sql = (
        f"SELECT {group_by} AS value, COUNT(*) AS n FROM uso_equipamentos{where} "
        f"GROUP BY {group_by} ORDER BY n DESC LIMIT %s"
    )
    with _connect() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, params + [limit])
        rows = cur.fetchall()
        if not rows:
            return {
                "match_found": False,
                "message": f"No uso_equipamentos records match since={since!r}, until={until!r}.",
            }
        return {"match_found": True, "results": [dict(r) for r in rows]}


@mcp.tool()
def uso_equipamentos_distinct_count(
    field: Literal["numero_equipamento", "funcionario", "servico"],
) -> int:
    """Count of distinct equipment numbers / employees / service types in
    the uso_equipamentos dataset (355 distinct numero_equipamento values as
    of the last load)."""
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(f"SELECT COUNT(DISTINCT {field}) FROM uso_equipamentos")
        return cur.fetchone()[0]


def _ilike_pattern(texto: str) -> str:
    """Escape LIKE/ILIKE metacharacters in free user text before wrapping
    in %...% -- otherwise a literal '%' or '_' typed by the user (e.g.
    searching for "50%") silently becomes a wildcard instead of a literal
    match. Parametrized via %s either way, so this is a correctness fix,
    not a SQL-injection concern."""
    escaped = texto.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


@mcp.tool()
def pesagens_search_observacao(texto: str, limit: int = 10) -> dict:
    """Case-insensitive substring search (SQL ILIKE, not semantic) over the
    free-text observacao field in pesagens. Use for narrative questions the
    fixed enum-based tools above can't express (e.g. "which loads mention
    'chuva' in the notes") -- deliberately simple, no pg_trgm/embeddings:
    this field/dataset is small enough that a plain substring scan is both
    sufficient and fully predictable. Returns {"match_found": false,
    "message": ...} if no row's observacao contains texto
    (case-insensitive)."""
    sql = (
        "SELECT numero_romaneio, nome_motorista, placa, data_chegada, observacao "
        "FROM pesagens WHERE observacao ILIKE %s ORDER BY data_chegada DESC LIMIT %s"
    )
    with _connect() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, [_ilike_pattern(texto), limit])
        rows = cur.fetchall()
        if not rows:
            return {"match_found": False, "message": f'No pesagens.observacao contains "{texto}".'}
        return {"match_found": True, "results": [dict(r) for r in rows]}


@mcp.tool()
def uso_equipamentos_search_observacao(texto: str, limit: int = 10) -> dict:
    """Same ILIKE substring search as pesagens_search_observacao, over
    uso_equipamentos.observacao instead (e.g. equipment breakdown/incident
    notes)."""
    sql = (
        "SELECT numero_equipamento, equipamento, data, funcionario, servico, observacao "
        "FROM uso_equipamentos WHERE observacao ILIKE %s ORDER BY data DESC LIMIT %s"
    )
    with _connect() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, [_ilike_pattern(texto), limit])
        rows = cur.fetchall()
        if not rows:
            return {
                "match_found": False,
                "message": f'No uso_equipamentos.observacao contains "{texto}".',
            }
        return {"match_found": True, "results": [dict(r) for r in rows]}


if __name__ == "__main__":
    mcp.run()
