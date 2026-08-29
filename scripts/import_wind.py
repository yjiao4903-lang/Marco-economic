"""Import a Wind-exported Excel/CSV file into the macro compass data layer.

Pipeline: fingerprint -> dedup check -> parse -> validate ->
[archive raw -> canonical parquet -> DuckDB -> manifest] (unless --dry-run).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from macro_compass import paths  # noqa: E402
from macro_compass.config import ConfigError, WindMapping, load_indicator_config  # noqa: E402
from macro_compass.logging import setup_logging  # noqa: E402
from macro_compass.pipeline import (  # noqa: E402
    STATUS_DRY_RUN,
    STATUS_FAILED_VALIDATION,
    STATUS_SKIPPED,
    import_wind_file,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", type=Path, help="Wind export file (.xlsx or .csv)")
    parser.add_argument(
        "--mapping",
        type=Path,
        default=paths.WIND_MAPPING_YAML,
        help="Wind column mapping YAML (default: config/wind_mapping.yaml)",
    )
    parser.add_argument(
        "--source",
        default="WIND",
        help="Value for the 'source' contract field (default: WIND)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and validate only; write nothing",
    )
    args = parser.parse_args(argv)

    setup_logging()

    try:
        mapping = WindMapping.from_file(args.mapping)
        registry = load_indicator_config(paths.INDICATORS_YAML)
    except ConfigError as exc:
        print(f"ERROR: {exc}")
        return 2

    try:
        result = import_wind_file(
            args.file, mapping, registry, source=args.source, dry_run=args.dry_run
        )
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}")
        return 2
    except (ValueError, KeyError) as exc:
        print(f"ERROR: {exc}")
        return 2

    if result.status == STATUS_SKIPPED:
        print(f"{result.file_name}: {result.message}")
        print("Status: SKIPPED_ALREADY_IMPORTED")
        return 0

    if result.status == STATUS_FAILED_VALIDATION:
        print(f"{result.file_name}: validation FAILED, nothing written")
        for e in result.validation_errors:
            print(f"  ERROR: {e}")
        for w in result.validation_warnings:
            print(f"  WARN:  {w}")
        return 1

    print("File parsed successfully")
    print(f"Series: {result.canonical['series_id'].nunique()}")
    print(f"Rows: {result.rows}")
    if not result.canonical.empty:
        print(f"Date range: {result.canonical['date'].min()} .. {result.canonical['date'].max()}")
    for w in result.validation_warnings:
        print(f"  WARN: {w}")
    if result.status == STATUS_DRY_RUN:
        print("Dry run: nothing written.")
    else:
        print(f"Archived to: {result.archive_path}")
        print(result.message)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
