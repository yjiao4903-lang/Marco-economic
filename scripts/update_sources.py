"""Incremental update of all public data sources (V1.2).

Fetches every enabled series declared in config/data_sources.yaml through its
provider chain, merges results into canonical parquet, refreshes the DuckDB
cache, records per-series fetch state and writes the status outputs:

    data/local/data_status.csv
    data/local/manual_fetch_required.csv

Examples:
    python scripts/update_sources.py               # incremental update, all series
    python scripts/update_sources.py --dry-run     # fetch only, write nothing
    python scripts/update_sources.py --series USD_CNY --series CHN_CLI
    python scripts/update_sources.py --backfill    # full history, ignore state
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from macro_compass.data_sources import run_update  # noqa: E402
from macro_compass.logging import setup_logging  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--series",
        action="append",
        default=[],
        help="update only these series ids (repeatable)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="fetch and report, but write nothing to canonical/DuckDB/state",
    )
    parser.add_argument(
        "--backfill",
        action="store_true",
        help="fetch full history for the selected series, ignoring fetch state",
    )
    args = parser.parse_args(argv)

    setup_logging()
    try:
        report = run_update(
            series_ids=args.series or None,
            dry_run=args.dry_run,
            backfill=args.backfill,
        )
    except Exception as exc:
        print(f"ERROR: {exc}")
        return 2

    print(report.summary())
    print(f"status report:      {__import__('macro_compass').paths.DATA_STATUS_CSV}")
    print(f"manual fetch list:  {__import__('macro_compass').paths.MANUAL_FETCH_CSV}")
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
