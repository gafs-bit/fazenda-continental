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

`mcp_server/farm_stats.py` reads the same `gbrain_dev` Postgres tables
directly (not via gbrain) to answer count/sum/average/min/max questions
gbrain's search can't answer reliably — registered as the `farm-stats` MCP
server; see CLAUDE.md for when to use which.

## Structure

- `data/` — raw farm exports (gitignored — see `.gitignore`; same PII
  sensitivity as the generated pages: driver names, plates, client/document
  numbers)
- `scripts/` — the pipeline scripts, plus `db_upsert.py` (shared upsert
  helper) and `logging_setup.py` (shared logging config)
- `mcp_server/` — `farm_stats.py`, the `farm-stats` MCP server (aggregate
  queries direct from Postgres), plus `gbrain_search_safe.py`, the
  `gbrain-search-safe` MCP server (wraps gbrain keyword search with an
  explicit no-match message — see CLAUDE.md). Each has its own `serve*.sh`
  launch wrapper (resolves paths from its own location so cwd doesn't
  matter)
- `telegram_bot/` — `bot.py`, a Telegram front-end that answers each
  message by running `claude -p` from the repo root (so CLAUDE.md's rules
  and the MCP tools above apply automatically); allowlisted Telegram user
  IDs only, since the data is PII-sensitive. `run.sh` is the launcher;
  copy `.env.example` to `.env` (gitignored) and fill in the bot token —
  see CLAUDE.md for how to get one
- `logs/` — `pipeline.log`, a chronological record of every script run
  (gitignored — same PII sensitivity as `data/`)
- `docs/` — extended documentation: `docs/USAGE.md` (how to phrase
  questions so gbrain reliably gets used) and `docs/SETUP.md` (getting a
  fresh clone working end to end on a new machine)
- `notes/` — internship journal carried over from the original repo
- `requirements.txt` — pinned Python deps for `scripts/` (Python 3.9 venv)
- `.mcp.json` — registers the `farm-stats` and `gbrain-search-safe` MCP
  servers for this project
- `CLAUDE.md` — behavior rules for Claude Code sessions in this repo (no
  ad-hoc SQL fallback; gbrain-search-safe/gbrain-query for content,
  farm-stats for aggregates)

## Setup

```
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

The `farm-stats` MCP server needs Python >=3.10 (the pipeline's own `.venv`
is 3.9), so it runs in a separate venv:

```
python3.12 -m venv .venv-mcp
source .venv-mcp/bin/activate
pip install -r mcp_server/requirements.txt
```

## Re-running the pipeline

All three scripts are safe to re-run against the same or updated data. The
loaders (`load_pesagem_csv.py`, `load_fretes_xlsx.py`) upsert on a natural
key (`numero_romaneio` for pesagens, `local` for fretes_colheita) via
`db_upsert.py` — re-running against a file with rows already in Postgres
updates them in place instead of duplicating. `generate_gbrain_pages.py` is
always safe to re-run (overwrites by filename). Follow up with
`gbrain import ~/gbrain-farm-pages` to re-embed anything new/changed.

See `CLAUDE.md` for the rule on always using the gbrain MCP tool (never raw
SQL) to answer questions about this data, and `docs/USAGE.md` for how an
answer actually gets made and how to phrase questions so gbrain reliably
gets used.

## Logging

All three pipeline scripts log to both the console and `logs/pipeline.log`
(via `scripts/logging_setup.py`), so a run's state — rows parsed/upserted,
warnings (e.g. an unparseable date), errors, row counts at each stage — is
recorded chronologically across scripts, not just visible while watching the
terminal live.
