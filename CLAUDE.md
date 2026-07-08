# CLAUDE.md

This repo has real farm data (weighing/freight records from Fazenda
Continental) — the pipeline that feeds the real `gbrain` brain (`~/gbrain`).
See README.md for the pipeline diagram.

## No ad-hoc SQL/psql fallback — ever

**Never query `pesagens` or `fretes_colheita` directly via raw SQL, `psql`,
or any other freeform database path, for any question about the farm
data.** Always go through the `gbrain` MCP tool (content/lookup questions)
or the `farm-stats` MCP tool (count/sum/average/min/max questions — see
below), full stop. This is a hard rule, not a default-with-exceptions.

If gbrain's search results seem capped or incomplete (e.g. conservative search
mode's default result limit), the correct move is to push harder on gbrain
itself — raise the search mode/limit (`gbrain config set search.mode balanced`
or pass a higher `--limit`), issue multiple targeted queries, or use gbrain's
keyword `search` command instead of vector `query` — NOT to reach for direct
SQL as a workaround. If gbrain genuinely cannot answer after that, say so
explicitly rather than silently falling back to the database.

Two things are legitimate exceptions to "no raw SQL," and only these two:
- `scripts/load_pesagem_csv.py`, `scripts/load_fretes_xlsx.py`, and
  `scripts/generate_gbrain_pages.py` — the data-loading/adapter pipeline
  itself (raw files → Postgres → gbrain markdown pages), not a way to
  answer content questions. Running them to (re)load or regenerate data is
  fine — but see README.md's caution about the loaders being append-only
  (don't re-run against already-loaded data).
- `mcp_server/farm_stats.py` (the `farm-stats` MCP tool) — a fixed,
  narrow set of parametrized aggregate queries (see below), not a general
  SQL executor. It exists precisely so nobody needs to improvise raw SQL
  for aggregate questions; reach for it, don't reinvent it.

## Exact-ID / specific-record questions: use `search`, not `query`

For any question naming a specific identifier — a Romaneio number, a placa,
a Talhão/field code (BL.xxx, P.xx) — use gbrain's keyword `search` command,
not the vector `query` command. A 20-question audit (2026-07-08) found
`query`'s semantic ranking can bury the exact match under unrelated
records with similar wording (e.g. querying for "Romaneio 15064" returned
other romaneios in the top results, not 15064 itself), while `search`'s
BM25 ranking puts the exact ID match first with a wide score gap
(~0.83+ vs ~0.47 for everything else). Reserve `query` for genuinely fuzzy/
semantic questions ("which field is near Frutal", "loads with high
moisture").

## Verify before answering — never present the closest hit as the answer

Before stating a result as the answer to a question about a specific
ID/name, confirm the result's own romaneio/placa/talhão field literally
matches what was asked. If nothing matches, say so explicitly ("no record
found for Romaneio X") — do not answer with the closest-ranked hit anyway.

This matters most for superlative questions (highest/lowest/most/least) and
count/sum/average questions: gbrain's `search`/`query` rank by textual/
semantic similarity, not by numeric value or corpus-wide aggregation, so
they were found wrong 4 times out of 5 on max/min questions and cannot
answer count/sum/average at all (audit, 2026-07-08).

## Aggregate/superlative questions: use the `farm-stats` MCP tool

For any count, sum, average, min, or max question about `pesagens` or
`fretes_colheita` — "how many loads", "average moisture", "highest dry
weight and which romaneio", "who delivered the most", "total area in
Frutal-MG" — use the `farm-stats` MCP tool
(`mcp_server/farm_stats.py`, registered project-scoped), not gbrain.
It runs exact, parametrized SQL aggregates directly against Postgres, so
answers are always exact rather than inferred from a capped, similarity-
ranked result list. Tools: `pesagens_count`, `pesagens_aggregate`,
`pesagens_extremes`, `pesagens_date_range`, `pesagens_group_counts`,
`pesagens_distinct_count`, `fretes_aggregate`. All field/op/group-by
arguments are fixed enums the tool defines — there is no way to pass
arbitrary SQL through it, so using it is not the same thing as the banned
ad-hoc SQL fallback above.

Rule of thumb: gbrain answers "what/which/tell me about" questions about
specific records or fuzzy topics; farm-stats answers "how many/what's the
total/what's the average/what's the highest" questions. If a question is
genuinely both (e.g. "which driver had the highest average moisture"),
use farm-stats for the numeric part and gbrain only if a record's narrative
detail (Observação field, etc.) is also needed.

Runs on Python 3.12 in its own venv (`.venv-mcp/`) — separate from the
pipeline scripts' `.venv` (Python 3.9), since the `mcp` SDK requires
Python >=3.10.
