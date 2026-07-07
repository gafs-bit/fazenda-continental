"""
Shared logging setup for the pipeline scripts.

Logs to both the console and a persistent file (logs/pipeline.log, gitignored
-- same PII sensitivity as data/, since messages can include driver names and
romaneio numbers) so a run's state (rows parsed/upserted/skipped, warnings,
errors) can be reviewed after the fact, not just watched live in the
terminal. All three pipeline scripts write to the same file, so a full
load -> adapt -> import sequence reads as one chronological history.
"""

import logging
import sys
from pathlib import Path

LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
LOG_FILE = LOG_DIR / "pipeline.log"


def get_logger(name: str) -> logging.Logger:
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger(name)
    if logger.handlers:
        return logger  # already configured -- avoid duplicate handlers on reimport

    logger.setLevel(logging.INFO)
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )

    file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    return logger
