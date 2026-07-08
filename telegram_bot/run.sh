#!/bin/bash
# Wrapper so the bot always runs from the repo root with its own venv,
# regardless of the caller's cwd.
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$DIR" || exit 1
exec "$DIR/.venv-bot/bin/python3" "$DIR/telegram_bot/bot.py"
