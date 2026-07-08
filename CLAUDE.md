# CLAUDE.md

This repo has real farm data (weighing/freight records from Fazenda
Continental) — the pipeline that feeds the real `gbrain` brain (`~/gbrain`).
See README.md for the pipeline diagram.

## Rules

- **Never query `pesagens`/`fretes_colheita` via raw SQL, `psql`, or any
  other freeform database path**, for any question about the farm data.
  Use `gbrain-search-safe` / gbrain's `query` (content questions) or
  `farm-stats` (count/sum/average/min/max questions) instead — full stop,
  not a default-with-exceptions. Raw `psql` is also blocked at the
  permission level (`.claude/settings.json`) as a backstop. The only two
  legitimate exceptions: `scripts/load_*.py` + `generate_gbrain_pages.py`
  (the loader pipeline itself, not a way to answer content questions —
  see README.md before re-running against already-loaded data) and
  `mcp_server/farm_stats.py` (fixed enum-based aggregates, not a SQL
  escape hatch).
- **Exact-ID questions** (a Romaneio number, a placa, a Talhão/field code
  like BL.xxx or P.xx) → the `gbrain-search-safe` MCP tool's
  `search_with_fallback`, not gbrain's own `search`/`query` directly. Raw
  `gbrain search` is denied at the permission level — it fabricates
  confident-looking matches for IDs that don't exist (see `docs/AUDIT.md`).
- **Fuzzy/semantic questions with no exact identifier** ("which field is
  near Frutal", "loads with high moisture") → gbrain's `query` tool.
  Same verify-before-answering caution applies (below).
- **Count/sum/average/min/max questions** about `pesagens` or
  `fretes_colheita` → the `farm-stats` MCP tool, never gbrain (it ranks by
  text/semantic similarity, not numeric value, and can't aggregate at
  all — see `docs/AUDIT.md`). Tools: `pesagens_count`, `pesagens_aggregate`,
  `pesagens_extremes`, `pesagens_date_range`, `pesagens_group_counts`,
  `pesagens_distinct_count`, `fretes_aggregate`.
- **Verify before answering.** Before stating a result as the answer to a
  specific ID/name question, confirm the result's own romaneio/placa/talhão
  field literally matches what was asked. If nothing matches, say so
  explicitly ("no record found for Romaneio X") — never answer with the
  closest-ranked hit anyway.
- **Check `match_found`, not emptiness.** `pesagens_extremes` and
  `pesagens_group_counts` return `{"match_found": true, "results": [...]}`
  or `{"match_found": false, "message": ...}` — check that field rather
  than treating an empty list as ambiguous. `pesagens_count` /
  `pesagens_aggregate` / `fretes_aggregate` are unchanged (`0`/`None` are
  already unambiguous for those).

## Rule of thumb

gbrain answers "what/which/tell me about" questions about specific records
or fuzzy topics; farm-stats answers "how many/what's the total/what's the
average/what's the highest" questions. If a question is genuinely both
(e.g. "which driver had the highest average moisture"), use farm-stats for
the numeric part and gbrain only if narrative detail (Observação field,
etc.) is also needed.

See `docs/AUDIT.md` for the testing behind these rules and `docs/SETUP.md`
for getting a fresh clone running.
