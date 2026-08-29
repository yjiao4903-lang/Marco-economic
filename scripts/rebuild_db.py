"""Rebuild the local DuckDB cache entirely from canonical parquet files.

Safe to run at any time: canonical parquet is the source of truth, so
deleting data/local/macro.duckdb and running this script loses nothing.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from macro_compass import paths  # noqa: E402
from macro_compass.config import ConfigError, load_indicator_config  # noqa: E402
from macro_compass.logging import setup_logging  # noqa: E402
from macro_compass.storage.duckdb_store import rebuild_duckdb_from_canonical  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--db",
        type=Path,
        default=paths.DUCKDB_PATH,
        help="Target DuckDB file (default: data/local/macro.duckdb)",
    )
    args = parser.parse_args(argv)

    setup_logging()
    try:
        registry = load_indicator_config(paths.INDICATORS_YAML)
    except ConfigError as exc:
        print(f"ERROR: {exc}")
        return 2

    counts = rebuild_duckdb_from_canonical(registry, db_path=args.db)
    print(f"DuckDB rebuilt at: {args.db}")
    print(f"  series_data rows:     {counts['series_data']}")
    print(f"  series_metadata rows: {counts['series_metadata']}")
    print(f"  import_manifest rows: {counts['import_manifest']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
