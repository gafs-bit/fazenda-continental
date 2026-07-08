# Setting up this repo on a new machine

Cloning this repo gets you the code. It does **not** get you a working
system — several things it depends on live outside git on purpose (real farm
data is PII-sensitive; databases, venvs, and secrets don't belong in version
control). This doc is the checklist for going from a fresh clone to a working
answer.

## What has to exist before any of this is useful

- **Postgres**, running, reachable at `postgresql+psycopg2://localhost/gbrain_dev`
  (or set `FARM_STATS_DSN` / edit the loader scripts' `DEFAULT_DB_URL` to point
  elsewhere). The `gbrain_dev` database itself must already exist
  (`createdb gbrain_dev`) — the loader scripts create their own tables inside
  it (`CREATE TABLE IF NOT EXISTS`), but not the database.
- **`gbrain`**, installed and initialized separately — this repo only
  *connects* to it (`~/gbrain`), it doesn't install or configure it. See
  gbrain's own docs for `gbrain init` against the same `gbrain_dev` Postgres.
- **The `claude` CLI**, installed and logged in — needed both for interactive
  use and because the Telegram bot shells out to `claude -p`.
- **Python 3.9+ and 3.12+** available (`python3` and `python3.12` on PATH) —
  the pipeline scripts and the two MCP servers/bot use different venvs on
  purpose (see below).
- **Real GSB/farm export files** (`data/*.csv`, `*.xlsx`) — gitignored, not
  in the repo. You need your own copies; nothing to load ships with the code.

## Steps

```bash
git clone git@gitlab.com:guac-co-group/fazenda-continental.git
cd fazenda-continental
```

**1. Pipeline venv** (Python 3.9, for the loader/adapter scripts):
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

**2. MCP server venv** (Python 3.12 — the `mcp` SDK needs >=3.10):
```bash
python3.12 -m venv .venv-mcp
.venv-mcp/bin/pip install -r mcp_server/requirements.txt
```

**3. Telegram bot venv** (only if you're running the bot):
```bash
python3.12 -m venv .venv-bot
.venv-bot/bin/pip install -r telegram_bot/requirements.txt
```

**4. Load real data.** Drop your GSB exports into `data/`, then, with the
pipeline venv active:
```bash
python scripts/load_pesagem_csv.py data/your_pesagem_export.csv
python scripts/load_fretes_xlsx.py data/your_fretes_export.xlsx
python scripts/generate_gbrain_pages.py
gbrain import ~/gbrain-farm-pages
```
The loaders upsert on a natural key, so re-running them against the same
file is safe — but see the main `README.md`'s note on this before re-running
against partially-overlapping exports.

**5. Register the MCP servers.** `.mcp.json` is checked in and already
points at the right scripts using `${CLAUDE_PROJECT_DIR}`, so this works
regardless of where you cloned the repo — nothing to edit. Start a Claude
Code session in the repo root and run `/mcp` to confirm `farm-stats` and
`gbrain-search-safe` both show as connected.

**6. Telegram bot** (optional — only if you want the bot, not just
interactive Claude Code access):
```bash
cd telegram_bot
cp .env.example .env
```
Fill in `.env` yourself (don't paste secrets into a chat with an AI
assistant, including this one):
- `TELEGRAM_BOT_TOKEN` — from `@BotFather` on Telegram (`/newbot`)
- `ALLOWED_TELEGRAM_USER_IDS` — leave empty at first, run `./run.sh`,
  message the bot, and its rejection reply will include your numeric
  Telegram user id. Add it here and restart.

```bash
./run.sh
```

## Verifying it actually works

Ask a question you can independently check against the raw export, e.g. a
specific Romaneio number's weight — and check the answer against the source
file directly. Also try an ID that doesn't exist (e.g. a Romaneio number way
outside the real range) — it should come back with an explicit "no match,"
not a fabricated-looking answer. See `CLAUDE.md` for why that check matters
and `docs/USAGE.md` for how to phrase questions so they reliably hit gbrain.
