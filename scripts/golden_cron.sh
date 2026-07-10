#!/usr/bin/env bash
# Cron wrapper for the Fazenda Continental golden-answer harness.
# Exits 0 on all-pass (no output -> no alert). On any failure, prints a
# compact report so the scheduling system delivers it to the owner.
set -u
cd "/Users/giacomosantos/R.P. fazenda continetal/fazenda-continental-data" || exit 2
OUT=$(./.venv-bot/bin/python3 scripts/golden_check.py 2>&1)
RC=$?
if [ "$RC" -ne 0 ]; then
  echo "FARMACAO GOLDEN HARNESS FAILED ($(date)):"
  echo "$OUT" | grep -E '\[FAIL\]|passed ===' 
  exit 1
fi
# Success: emit nothing so the alert channel stays silent.
exit 0
