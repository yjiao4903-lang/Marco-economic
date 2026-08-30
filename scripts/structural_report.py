"""V2.6 Structural Risk snapshot report - the human acceptance entry point.

One run prints the latest picture of the whole Structural Risk layer:

* per signal (S1 credit-to-GDP gap / S2 debt service ratio / S3 property
  vulnerability): resolved display status, latest observation date, latest
  raw value, rolling percentile against its own history, the trend over the
  declared quarters and the diagnostic read;
* explicit NO_SIGNAL when there is no canonical data OR the latest quarterly
  observation is older than its staleness budget - never a silent fallback,
  never a synthetic placeholder.

ISOLATION (MASTER SPEC section 7): Structural Risk is a medium/long-term
fragility diagnostic that NEVER enters the short-term Asset Score. The asset
engine only reads the four core factor outputs and never imports this package.

Read-only except for the snapshot CSV (data/local/structural_risk.csv).

Usage:
    python scripts/structural_report.py [--today YYYY-MM-DD]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from macro_compass import paths  # noqa: E402
from macro_compass.config import load_indicator_config  # noqa: E402
from macro_compass.data_sources.registry import (  # noqa: E402
    load_data_sources_config,
)
from macro_compass.macro import classify_provenance, load_macro_config  # noqa: E402
from macro_compass.structural import (  # noqa: E402
    compute_structural_readings,
    load_structural_config,
)
from macro_compass.signals import load_core_computations, load_signal_registry  # noqa: E402

NO_SIGNAL = "NO_SIGNAL"  # explicit report-level state: no data or stale latest


def _fmt(value, spec: str = ".3f") -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "  n/a"
    return format(value, spec)


def _display_status(reading) -> str:
    """Report-level status: NO_SIGNAL when there is no data OR the latest
    quarterly observation is stale (beyond its declared staleness budget)."""
    if reading.status == "MISSING_INPUT" or reading.stale:
        return NO_SIGNAL
    return reading.status


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--today",
        default=None,
        help="reference date for freshness (ISO, default: today)",
    )
    parser.add_argument(
        "--allow-synthetic",
        action="store_true",
        help="test-only: include synthetic fixture rows in the calculation "
        "(production default: synthetic rows are excluded)",
    )
    args = parser.parse_args()
    today = pd.Timestamp(args.today) if args.today else pd.Timestamp.today()

    indicators = load_indicator_config(paths.INDICATORS_YAML)
    registry = load_signal_registry(paths.SIGNALS_YAML, indicators_registry=indicators)
    macro_config = load_macro_config(paths.MACRO_YAML)
    structural_config = load_structural_config(paths.STRUCTURAL_YAML)
    sources_cfg = load_data_sources_config(paths.DATA_SOURCES_YAML, indicator_registry=indicators)

    snapshot = load_core_computations(
        registry, macro_config, allow_synthetic=args.allow_synthetic, today=today
    )
    canonical = snapshot.canonical
    series = snapshot.series

    provenance_by_series = classify_provenance(
        canonical.groupby("series_id")["source_file"]
        .agg(lambda s: list(s.dropna().unique()))
        .to_dict(),
        macro_config.get("synthetic_markers") or [],
    )
    source_by_series = (
        canonical.sort_values("import_time").groupby("series_id")["source"].last().to_dict()
    )
    staleness = {
        series_id: spec.max_staleness_days for series_id, spec in sources_cfg.series.items()
    }

    readings = compute_structural_readings(
        registry,
        structural_config,
        series,
        today,
        staleness=staleness,
        provenance_by_series=provenance_by_series,
        sources_by_series=source_by_series,
    )

    print(f"=== Structural Risk snapshot - generated {today.date()} ===")
    print(
        "diagnostic layer: S1/S2 on BIS quarterly long series; S3 proxy pool "
        "pending B-package. Structural risk NEVER enters the short-term Asset Score."
    )

    _print_readings(registry, readings, staleness, structural_config)
    _write_snapshot(registry, readings)

    print("\nRead-only report - canonical data was not modified.")
    print(f"Structural risk snapshot written: {paths.STRUCTURAL_RISK_CSV}")


def _print_readings(registry, readings, staleness, structural_config) -> None:
    print("\n--- Structural Risk signals (fragility diagnostics) ---")
    for signal_id, spec in registry.by_layer("structural").items():
        r = readings[signal_id]
        display = _display_status(r)
        print(f"\n  {signal_id} {spec.name}")
        if display == NO_SIGNAL:
            print(f"      status: NO_SIGNAL  ({r.message or '无数据'})")
            continue
        as_of = r.as_of.date().isoformat() if r.as_of is not None else "-"
        source = r.source or r.series_id
        print(
            f"      status: {display:<10} series={r.series_id:<22} as_of={as_of}"
            f"  source={source} ({r.provenance})"
        )
        print(
            f"      level={_fmt(r.level):>8}  percentile({r.percentile_window}q)={_fmt(r.percentile, '.3f'):>8}"
            f"  trend({r.trend_quarters}q)={_fmt(r.trend, '+.3f'):>9}pp"
            f"  diagnostic={r.diagnostic or '-'}"
        )
        if r.message:
            print(f"      note: {r.message}")
        print(
            f"      direction convention: {r.direction} (rising = more fragile); "
            f"history {r.history_length} obs, freshness {r.freshness_days}d "
            f"(budget {staleness.get(r.series_id, 260)}d)"
        )


def _write_snapshot(registry, readings) -> None:
    rows = []
    for signal_id, spec in registry.by_layer("structural").items():
        r = readings[signal_id]
        rows.append(
            {
                "signal_id": signal_id,
                "signal_name": spec.name,
                "series_id": r.series_id,
                "engine_status": r.status,
                "display_status": _display_status(r),
                "direction_convention": r.direction,
                "as_of": r.as_of.date().isoformat() if r.as_of is not None else "",
                "history_start": r.history_start.date().isoformat() if r.history_start is not None else "",
                "history_length": r.history_length,
                "level": r.level,
                "percentile": r.percentile,
                "trend": r.trend,
                "trend_quarters": r.trend_quarters,
                "diagnostic": r.diagnostic or "",
                "freshness_days": r.freshness_days,
                "stale": r.stale,
                "message": r.message,
                "provenance": r.provenance,
                "source": r.source,
            }
        )
    paths.LOCAL_DIR.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(paths.STRUCTURAL_RISK_CSV, index=False, encoding="utf-8-sig")


if __name__ == "__main__":
    main()
