"""Central logging setup for macro_compass.

All entry-point scripts should call setup_logging() once; library modules
just use ``logging.getLogger(__name__)``.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

LOG_DIR_NAME = "logs"

_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
_DATEFMT = "%Y-%m-%d %H:%M:%S"


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def setup_logging(level: int = logging.INFO, log_dir: Path | None = None) -> None:
    """Configure root logging with console output, optionally a log file."""
    root = logging.getLogger()
    if root.handlers:
        # Already configured in this process; just raise level if requested.
        root.setLevel(level)
        return

    root.setLevel(level)
    formatter = logging.Formatter(_FORMAT, _DATEFMT)

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)
    root.addHandler(console)

    if log_dir is not None:
        log_dir = Path(log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(
            log_dir / "macro_compass.log", encoding="utf-8"
        )
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)
