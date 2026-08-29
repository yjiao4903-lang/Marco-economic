"""Run data quality checks against the canonical parquet data layer."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import pandas as pd  # noqa: E402

from macro_compass import paths  # noqa: E402
from macro_compass.config import ConfigError, load_indicator_config  # noqa: E402
from macro_compass.ingestion.quality import check_quality  # noqa: E402
from macro_compass.logging import setup_logging  # noqa: E402
from macro_compass.storage.canonical_store import read_canonical  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)

    setup_logging()
    try:
        registry = load_indicator_config(paths.INDICATORS_YAML)
    except ConfigError as exc:
        print(f"ERROR: {exc}")
        return 2

    canonical = pd.concat(
        [read_canonical("macro"), read_canonical("market")], ignore_index=True
    )
    if canonical.empty:
        print("Quality: no canonical data found. Import a file first.")
        return 0

    report = check_quality(canonical, registry)
    print(report.summary())
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
