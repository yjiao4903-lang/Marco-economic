"""Two-source overlap check (v0.4c Task 2, hard acceptance item).

Compares the latest N observations of one series fetched from two different
providers and reports max/median absolute difference plus missing dates.
Required before US_REAL_YIELD_10Y treats Treasury as its canonical primary
with FRED DFII10 as validation/fallback: the check needs >= 60 common trading
days. The check itself never writes data.

Usage:
    python scripts/overlap_check.py --series US_REAL_YIELD_10Y \
        --left treasury --right fred --min-days 60
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from macro_compass.config import load_indicator_config  # noqa: E402
from macro_compass.data_sources.base import DataSourceError  # noqa: E402
from macro_compass.data_sources.registry import (  # noqa: E402
    AdapterRegistry,
    load_data_sources_config,
)
from macro_compass import paths  # noqa: E402


def compare_frames(
    left: pd.DataFrame, right: pd.DataFrame
) -> dict[str, float | int | None]:
    """Statistics over the common observation dates of two canonical frames."""
    l = left.set_index("date")["value"].astype(float)
    r = right.set_index("date")["value"].astype(float)
    common = l.index.intersection(r.index)
    result: dict[str, float | int | None] = {
        "common_days": int(len(common)),
        "left_only_days": int(len(l.index.difference(r.index))),
        "right_only_days": int(len(r.index.difference(l.index))),
    }
    if common.empty:
        result["max_abs_diff"] = None
        result["median_abs_diff"] = None
        return result
    diff = (l[common] - r[common]).abs()
    result["max_abs_diff"] = float(diff.max())
    result["median_abs_diff"] = float(diff.median())
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--series", required=True)
    parser.add_argument("--left", required=True, help="provider id (candidate primary)")
    parser.add_argument("--right", required=True, help="provider id (reference)")
    parser.add_argument("--min-days", type=int, default=60)
    parser.add_argument("--start", default=None, help="ISO start date for both fetches")
    args = parser.parse_args()

    indicators = load_indicator_config(paths.INDICATORS_YAML)
    config = load_data_sources_config(paths.DATA_SOURCES_YAML, indicators)
    adapters = AdapterRegistry(config)

    frames: dict[str, pd.DataFrame] = {}
    errors: dict[str, str] = {}
    for provider in (args.left, args.right):
        try:
            frames[provider] = adapters.get(provider).fetch(
                args.series, start_date=args.start, end_date=None
            )
        except DataSourceError as exc:
            errors[provider] = str(exc)

    if errors:
        for provider, message in errors.items():
            print(f"[UNAVAILABLE] {provider}: {message}")
        if len(frames) < 2:
            print(
                "\nOVERLAP CHECK: BLOCKED - both sources are required. "
                "This is a hard acceptance gate before switching the series' "
                "canonical primary; rerun when the failing source is reachable."
            )
            sys.exit(2)

    stats = compare_frames(frames[args.left], frames[args.right])
    print(f"overlap check for {args.series}: {args.left} vs {args.right}")
    for key, value in stats.items():
        print(f"  {key}: {value if value is not None else 'n/a'}")
    if stats["common_days"] >= args.min_days:
        passed = (stats["max_abs_diff"] or 0.0) <= 0.05  # rounding tolerance
        verdict = "PASS" if passed else "PASS-WITH-DIFFS (definition drift - do NOT merge series)"
        print(f"\nOVERLAP CHECK: {verdict} (>= {args.min_days} common days)")
        sys.exit(0 if passed else 1)
    print(f"\nOVERLAP CHECK: FAIL - only {stats['common_days']} common days (< {args.min_days})")
    sys.exit(1)


if __name__ == "__main__":
    main()
