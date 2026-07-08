# Search/tool accuracy audit

Evidence behind the tool-choice rules in `CLAUDE.md`. Findings from testing
gbrain's search/query tools and the `farm-stats` MCP tool against the raw
`data/*.csv`/`*.xlsx` exports, most recently 2026-07-08.

## gbrain `query` buries exact matches under semantic near-matches

A 20-question audit (2026-07-08) found `query`'s semantic ranking can bury
the exact match under unrelated records with similar wording — e.g.
querying for "Romaneio 15064" returned other romaneios in the top results,
not 15064 itself.

## gbrain `search`, called directly, fabricates matches for nonexistent IDs

Testing the same day found gbrain's raw `search` tool is worse than the
`query` audit above suggested: for an ID that doesn't exist anywhere in the
data (e.g. "Romaneio 99999", a nonexistent placa "ZZZ9999"), it still
returns several results tagged `"evidence": "keyword_exact"` with high
scores (~0.80+) and no signal that nothing actually matched.

This is reproducible, and confirmed *not* a gbrain search-engine bug:
`gbrain call search` (the same underlying tool, invoked locally via the
CLI) correctly returns `[]` for the identical query. The fault is in the
MCP tool wiring for this session specifically — `gbrain-search-safe`
(`mcp_server/gbrain_search_safe.py`) routes through the reliable CLI path
instead and returns an explicit `{"match_found": false, ...}`.

Also found: even when the exact match *is* somewhere in the result set,
raw `search`'s top-ranked hit isn't always the actual match — about 29% of
tested exact-ID lookups (2/7 in one round) had the true match ranked #2 or
lower behind an unrelated record with a higher score.

## gbrain search/query can't answer numeric or aggregate questions reliably

Superlative questions (highest/lowest/most/least) and count/sum/average
questions: gbrain's `search`/`query` rank by textual/semantic similarity,
not by numeric value or corpus-wide aggregation, so they were found wrong 4
times out of 5 on max/min questions (audit, 2026-07-08) and cannot answer
count/sum/average at all. `farm-stats` (`mcp_server/farm_stats.py`) runs
exact, parametrized SQL aggregates directly against Postgres instead.

## farm-stats accuracy

Cross-checked every `farm-stats` tool's output against an independent
pandas computation on the raw CSV/XLSX (not through the loaded Postgres
tables) — 13/13 exact matches across counts, aggregates (sum/avg/min/max),
extremes, group counts, distinct counts, and date range, including edge
cases (a field with only 179/400 non-null readings, a filter matching zero
rows). Also verified the `produto`/`possui_romaneio` filters added later
(avg peso_liquido_seco_kg where possui_romaneio=false: 12895.377358490567,
exact match against an independent pandas computation).
