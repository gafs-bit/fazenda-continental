#!/bin/bash
# Wrapper so the MCP client's cwd doesn't matter — always run from the repo
# root with the dedicated Python 3.12 venv (the mcp SDK needs >=3.10; the
# pipeline's own .venv is 3.9 and stays untouched).
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$DIR" || exit 1
exec "$DIR/.venv-mcp/bin/python3" "$DIR/mcp_server/farm_stats.py"
