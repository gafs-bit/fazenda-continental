# Fazenda Continental — Farm Data Pipeline

Raw farm data + the load/adapter pipeline that feeds the real `gbrain` brain
(`~/gbrain`, connected as an MCP server). Successor to the original
`fazenda-continental-internship` repo — this one carries forward only the
load-bearing pieces (raw data, loaders, adapter); the deprecated local search
prototype (fastembed/sentence-transformers, separate `documentos` table) was
not carried over.

## Pipeline

```
data/*.csv, *.xlsx  (raw farm exports)
        ↓  scripts/load_pesagem_csv.py, load_fretes_xlsx.py
gbrain_dev Postgres: pesagens, fretes_colheita tables
        ↓  scripts/generate_gbrain_pages.py
~/gbrain-farm-pages/  (one gbrain-format markdown page per row)
        ↓  gbrain import ~/gbrain-farm-pages
gbrain (query via the gbrain MCP tool)
```

## Structure

- `data/` — raw farm exports (gitignored — see `.gitignore`; same PII
  sensitivity as the generated pages: driver names, plates, client/document
  numbers)
- `scripts/` — the three pipeline scripts above
- `notes/` — internship journal carried over from the original repo

## Re-running the pipeline

The load scripts (`load_pesagem_csv.py`, `load_fretes_xlsx.py`) use
`if_exists="append"` — do NOT re-run them against data already loaded into
`gbrain_dev`, or rows will duplicate. `generate_gbrain_pages.py` is safe to
re-run any time (overwrites by filename) and should be followed by
`gbrain import ~/gbrain-farm-pages` to re-embed anything new.

See `CLAUDE.md` for the rule on always using the gbrain MCP tool (never raw
SQL) to answer questions about this data.
