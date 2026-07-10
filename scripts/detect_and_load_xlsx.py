"""
Routes a .xlsx file dropped in data/ to the loader that actually understands
its columns, instead of assuming every .xlsx is a fretes_colheita export.

Root cause this fixes: setup.sh used to run load_fretes_xlsx.py on every
.xlsx in data/ unconditionally. When a third export type (the equipment
usage report) landed there, it crashed -- the columns didn't match. The fix
at the time (load_equipamentos_xlsx.py) was never wired back into setup.sh,
so the same crash would repeat verbatim for a fourth file type. This script
closes that gap generically: it reads only the header row, compares it
against each known loader's own COLUMN_MAP (single source of truth per
loader -- not duplicated here), and dispatches to whichever loader's
expected columns are a subset of what's actually in the file. If zero or
more than one loader matches, it warns and skips the file rather than
guessing -- a loud skip is recoverable, a silent wrong-loader run is not.
"""

import argparse
import subprocess
import sys
from pathlib import Path

import pandas as pd

from load_fretes_xlsx import COLUMN_MAP as FRETES_COLUMN_MAP
from load_equipamentos_xlsx import COLUMN_MAP as EQUIPAMENTOS_COLUMN_MAP
from logging_setup import get_logger

SCRIPT_DIR = Path(__file__).resolve().parent

logger = get_logger("detect_and_load_xlsx")

# Loader name -> (COLUMN_MAP whose keys must all be present in the file's
# header, script filename to dispatch to). Order doesn't matter -- every
# candidate is checked, and more than one match is treated as ambiguous.
LOADERS = {
    "fretes_colheita": (FRETES_COLUMN_MAP, "load_fretes_xlsx.py"),
    "uso_equipamentos": (EQUIPAMENTOS_COLUMN_MAP, "load_equipamentos_xlsx.py"),
}


def detect_loader(xlsx_path: Path) -> list[str]:
    """Return the names of every loader whose expected columns are all
    present in the file's header row. Reads only the header (nrows=0) --
    no need to load the full file just to route it."""
    header = set(pd.read_excel(xlsx_path, nrows=0).columns)
    matches = []
    for name, (column_map, _script) in LOADERS.items():
        if set(column_map.keys()).issubset(header):
            matches.append(name)
    return matches


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("xlsx_path", type=Path)
    parser.add_argument("--db-url", default=None)
    args = parser.parse_args()

    if not args.xlsx_path.exists():
        logger.error(f"File not found: {args.xlsx_path}")
        sys.exit(f"File not found: {args.xlsx_path}")

    matches = detect_loader(args.xlsx_path)

    if len(matches) != 1:
        if not matches:
            logger.warning(
                f"Skipped {args.xlsx_path.name}: no known loader's columns match this "
                "file's header. This looks like a new export type -- write a dedicated "
                "loader for it (see load_equipamentos_xlsx.py's docstring for the "
                "pattern), then add it to LOADERS in this script."
            )
        else:
            logger.warning(
                f"Skipped {args.xlsx_path.name}: more than one loader's columns match "
                f"this file's header ({matches}) -- ambiguous, refusing to guess."
            )
        return 1

    loader_name, (_column_map, script) = matches[0], LOADERS[matches[0]]
    logger.info(f"Detected {args.xlsx_path.name} as a {loader_name!r} export -- dispatching to {script}")

    cmd = [sys.executable, str(SCRIPT_DIR / script), str(args.xlsx_path)]
    if args.db_url:
        cmd += ["--db-url", args.db_url]
    result = subprocess.run(cmd)
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
