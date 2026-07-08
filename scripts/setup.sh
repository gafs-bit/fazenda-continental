#!/bin/bash
# Chains the deterministic parts of getting this repo running on a new
# machine. See docs/SETUP.md for the full picture, including the parts
# this script deliberately does NOT do (and why):
#
#   - `gbrain init` is not run for you: it's an interactive wizard that
#     asks for personal API keys (ZeroEntropy/Anthropic/etc). Scripting
#     blind execution of a step that needs someone's secrets is the same
#     mistake as hardcoding a token -- run it yourself, once.
#   - Real GSB export files are not fetched or fabricated. They're
#     gitignored on purpose (PII); this script only proceeds to the load
#     step if it finds files already sitting in data/.
#   - gbrain itself is not installed or vendored. It's a separate,
#     full application by design (see its own docs on multi-project
#     "company brain" deployments) -- this script only checks it's on
#     PATH and already initialized against Postgres (not PGLite: farm-stats
#     needs a real Postgres connection to gbrain's own database).
#
# Safe to re-run: every step below is idempotent.

set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$DIR"

ok()   { printf "  [ok] %s\n" "$1"; }
warn() { printf "  [!!] %s\n" "$1"; }
step() { printf "\n== %s ==\n" "$1"; }

step "Checking prerequisites on PATH"
missing=0
for bin in python3 python3.12 psql gbrain claude; do
    if command -v "$bin" >/dev/null 2>&1; then
        ok "$bin found"
    else
        warn "$bin not found -- install it before continuing"
        missing=1
    fi
done
if [ "$missing" = 1 ]; then
    echo ""
    echo "Missing prerequisites above. Install them, then re-run this script."
    exit 1
fi

step "Postgres: gbrain_dev database"
if psql -lqt 2>/dev/null | cut -d '|' -f 1 | grep -qw gbrain_dev; then
    ok "gbrain_dev already exists"
else
    warn "gbrain_dev does not exist yet"
    if [ -t 0 ]; then
        read -rp "  Create it now with 'createdb gbrain_dev'? [y/N] " reply
    else
        reply="n"
    fi
    if [[ "$reply" =~ ^[Yy]$ ]]; then
        createdb gbrain_dev
        ok "created gbrain_dev"
    else
        echo "  Skipping -- create it yourself before loading data (createdb gbrain_dev)."
    fi
fi

step "gbrain: initialized against Postgres?"
if gbrain config get search.mode >/dev/null 2>&1; then
    ok "gbrain already initialized"
else
    warn "gbrain is not initialized yet (or not pointed at a brain)"
    echo "  Run this yourself -- it needs your own API keys, so this script won't do it:"
    echo "    gbrain init --url postgresql://localhost/gbrain_dev"
    echo "  (NOT --pglite: farm-stats connects to this same Postgres database directly,"
    echo "   which only works in Postgres/Supabase mode, not gbrain's embedded PGLite.)"
fi

step "Python virtualenvs"
if [ ! -d .venv ]; then
    python3 -m venv .venv
    .venv/bin/pip install -q -r requirements.txt
    ok "created .venv and installed pipeline deps"
else
    ok ".venv already exists"
fi
if [ ! -d .venv-mcp ]; then
    python3.12 -m venv .venv-mcp
    .venv-mcp/bin/pip install -q -r mcp_server/requirements.txt
    ok "created .venv-mcp and installed MCP server deps"
else
    ok ".venv-mcp already exists"
fi
if [ ! -d .venv-bot ]; then
    python3.12 -m venv .venv-bot
    .venv-bot/bin/pip install -q -r telegram_bot/requirements.txt
    ok "created .venv-bot and installed bot deps"
else
    ok ".venv-bot already exists"
fi

step "Loading real farm data"
csv_files=(data/*.csv)
xlsx_files=(data/*.xlsx)
if [ -e "${csv_files[0]}" ] || [ -e "${xlsx_files[0]}" ]; then
    for f in data/*.csv; do
        [ -e "$f" ] || continue
        echo "  loading $f ..."
        .venv/bin/python scripts/load_pesagem_csv.py "$f"
    done
    for f in data/*.xlsx; do
        [ -e "$f" ] || continue
        echo "  loading $f ..."
        .venv/bin/python scripts/load_fretes_xlsx.py "$f"
    done
    echo "  generating gbrain pages..."
    .venv/bin/python scripts/generate_gbrain_pages.py
    echo "  importing into gbrain..."
    gbrain import ~/gbrain-farm-pages
    ok "data loaded and imported"
else
    warn "no files in data/*.csv or data/*.xlsx yet"
    echo "  Drop your real GSB exports into data/, then re-run this script"
    echo "  (or just this step -- see docs/SETUP.md)."
fi

step "Done"
echo "Next: start a Claude Code session in this directory and run /mcp to"
echo "confirm farm-stats and gbrain-search-safe are connected. See"
echo "docs/SETUP.md for the Telegram bot's separate .env setup."
