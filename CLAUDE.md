# CLAUDE.md

This repo has real farm data (weighing/freight records from Fazenda
Continental) — the pipeline that feeds the real `gbrain` brain (`~/gbrain`).
See README.md for the pipeline diagram.

## No SQL/psql fallback — ever

**Never query `pesagens` or `fretes_colheita` directly via SQL, `psql`, or any
other raw-database path, for any question about the farm data — including
counts, totals, averages, date ranges, or exhaustive "find every X" searches.**
Always use the `gbrain` MCP tool, full stop. This is a hard rule, not a
default-with-exceptions.

If gbrain's search results seem capped or incomplete (e.g. conservative search
mode's default result limit), the correct move is to push harder on gbrain
itself — raise the search mode/limit (`gbrain config set search.mode balanced`
or pass a higher `--limit`), issue multiple targeted queries, or use gbrain's
keyword `search` command instead of vector `query` — NOT to reach for direct
SQL as a workaround. If gbrain genuinely cannot answer after that, say so
explicitly rather than silently falling back to the database.

`scripts/load_pesagem_csv.py`, `scripts/load_fretes_xlsx.py`, and
`scripts/generate_gbrain_pages.py` are the one legitimate exception: they're
the data-loading/adapter pipeline itself (raw files → Postgres → gbrain
markdown pages), not a way to answer content questions. Running them to
(re)load or regenerate data is fine — but see README.md's caution about the
loaders being append-only (don't re-run against already-loaded data).
