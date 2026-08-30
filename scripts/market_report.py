"""V1.6A market confirmation snapshot report - the human acceptance entry point.

One run prints the latest picture of the whole Market Confirmation layer:

* the Market Data Matrix - per market signal: provider chain, canonical
  history start, frequency, freshness and resolved data status;
* the six market signals' 1M / 3M / 6M moves (direction-adjusted), the
  rolling percentile (oriented so >0.5 = supportive) and the market
  direction call;
* the divergence classification per signal: macro direction (from the
  fundamental factor outputs), market direction, agreement, confidence and
  the five-state divergence state.

ISOLATION: this report READS the fundamental factor outputs; it has no path
that modifies them (ARCHITECTURE section 10). Divergence states are
confirmation observations, never buy/sell signals.

Read-only except for the snapshot CSV (data/local/market_confirmation.csv).

Usage:
    python scripts/market_report.py
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
from macro_compass.macro import classify_provenance, compute_factor, load_macro_config  # noqa: E402
from macro_compass.market import (  # noqa: E402
    compute_market_confirmations,
    load_market_config,
)
from macro_compass.signals import load_core_computations, load_signal_registry  # noqa: E402

FACTORS = ("growth", "inflation", "domestic_financial", "global_financial")

DIRECTION_LABEL = {1: "+1 (up)", 0: " 0 (flat)", -1: "-1 (down)"}


def _fmt(value, spec: str = ".3f") -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "  n/a"
    return format(value, spec)


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
    market_config = load_market_config(paths.MARKET_YAML)
    sources_cfg = load_data_sources_config(paths.DATA_SOURCES_YAML, indicator_registry=indicators)

    snapshot = load_core_computations(
        registry, macro_config, allow_synthetic=args.allow_synthetic, today=today
    )
    canonical = snapshot.canonical
    series = snapshot.series

    markers = macro_config.get("synthetic_markers") or []
    provenance_by_series = classify_provenance(
        canonical.groupby("series_id")["source_file"]
        .agg(lambda s: list(s.dropna().unique()))
        .to_dict(),
        markers,
    )
    source_by_series = (
        canonical.sort_values("import_time").groupby("series_id")["source"].last().to_dict()
    )
    staleness = {
        series_id: spec.max_staleness_days for series_id, spec in sources_cfg.series.items()
    }

    # fundamental factor outputs (read-only inputs to the divergence engine)
    factor_results = {
        factor: compute_factor(
            factor,
            [sid for sid, spec in registry.core.items() if spec.factor == factor],
            snapshot.computations,
            macro_config,
            staleness,
            today,
        )
        for factor in FACTORS
    }

    confirmations = compute_market_confirmations(
        registry,
        market_config,
        series,
        factor_results,
        staleness,
        macro_config,
        today,
        provenance_by_series=provenance_by_series,
        sources_by_series=source_by_series,
    )

    print(f"=== Market Confirmation snapshot - generated {today.date()} ===")
    print(
        "direction conventions: config/market.yaml (positive = rising series "
        "supports the read; the percentile is oriented to match)"
    )
    print(
        "isolation: the market layer reads factor outputs only - no fundamental "
        "module reads market results and nothing here modifies Growth/Inflation"
    )

    _print_matrix(registry, sources_cfg, confirmations, staleness)
    _print_signals(registry, confirmations, market_config)
    _print_divergence(registry, confirmations, factor_results, market_config)
    _write_snapshot(registry, confirmations, today.date().isoformat())

    print("\nRead-only report - canonical data was not modified.")
    print(f"Market confirmation snapshot written: {paths.MARKET_CONFIRMATION_CSV}")


def _print_matrix(registry, sources_cfg, confirmations, staleness) -> None:
    print("\n--- Market Data Matrix ---")
    header = (
        f"{'ID':<4}{'signal':<30}{'series':<22}{'primary/fallback':<24}"
        f"{'freq':<8}{'start':<12}{'obs':>6} {'fresh(d)':>9}  status"
    )
    print(header)
    for signal_id, spec in registry.by_layer("market").items():
        result = confirmations[signal_id]
        series_spec = sources_cfg.series.get(result.series_id)
        chain = f"{series_spec.primary}/{series_spec.fallback or '-'}" if series_spec else "-"
        start = (
            result.history_start.date().isoformat() if result.history_start is not None else "-"
        )
        fresh = "-" if result.freshness_days is None else str(result.freshness_days)
        if result.freshness_days is not None:
            budget = staleness.get(result.series_id, 90)
            fresh = f"{result.freshness_days} {'STALE' if result.freshness_days > budget else 'ok'}"
        print(
            f"{signal_id:<4}{spec.name[:28]:<30}{result.series_id:<22}{chain:<24}"
            f"{series_spec.frequency if series_spec else '-':<8}{start:<12}"
            f"{result.history_length:>6} {fresh:>9}  {result.status}"
        )


def _print_signals(registry, confirmations, market_config) -> None:
    print("\n--- Market signals (1M/3M/6M = direction-adjusted) ---")
    header = (
        f"{'ID':<4}{'signal':<30}{'as_of':<12}{'1M':>8} {'3M':>8} {'6M':>8} "
        f"{'pct(adj)':>8} {'dir':>10}"
    )
    print(header)
    for signal_id, spec in registry.by_layer("market").items():
        result = confirmations[signal_id]
        name = spec.name[:28]
        as_of = result.as_of.date().isoformat() if result.as_of is not None else "-"
        if result.status == "MISSING_INPUT":
            print(
                f"{signal_id:<4}{name:<30}{as_of:<12}{'n/a':>8} {'n/a':>8} {'n/a':>8} "
                f"{'n/a':>8} {'n/a':>10}  missing: {result.series_id}"
            )
            continue
        print(
            f"{signal_id:<4}{name:<30}{as_of:<12}"
            f"{_fmt(result.adj_move_1m, '+.3f'):>8} {_fmt(result.adj_move_3m, '+.3f'):>8} "
            f"{_fmt(result.adj_trend_6m, '+.3f'):>8} {_fmt(result.adj_percentile, '.2f'):>8} "
            f"{DIRECTION_LABEL[result.market_direction]:>10}"
        )
        print(
            f"     basis={market_config['signals'][signal_id]['move']} "
            f"trend_6m threshold={result.threshold_trend_6m} "
            f"history={result.history_length} obs  raw 6M={_fmt(result.trend_6m, '+.3f')} "
            f"raw pct={_fmt(result.percentile, '.2f')}"
        )


def _print_divergence(registry, confirmations, factor_results, market_config) -> None:
    print("\n--- Divergence (macro direction x market direction) ---")
    for signal_id, spec in registry.by_layer("market").items():
        result = confirmations[signal_id]
        refs = ", ".join(
            f"{factor}({_fmt(factor_results[factor].score, '+.3f')})"
            for factor in result.macro_reference
        )
        conf = result.confidence or {}
        print(
            f"  {signal_id} {spec.name[:28]:<30} state={result.state}"
        )
        print(
            f"      macro refs [{refs}] -> macro_direction {result.macro_direction:+d} "
            f"(score {_fmt(result.macro_score, '+.3f')}, threshold "
            f"{market_config['thresholds']['macro_score']}); "
            f"market_direction {result.market_direction:+d}; agreement: {result.agreement or 'n/a'}"
        )
        print(
            f"      confidence {conf.get('composite', 0):.2f} (coverage "
            f"{conf.get('coverage', 0):.2f}, freshness {conf.get('freshness', 0):.2f}, "
            f"source_quality {conf.get('source_quality', 0):.2f}) - data quality "
            f"description, not a forecast probability"
        )


def _write_snapshot(registry, confirmations, snapshot_date=None) -> None:
    rows = []
    for signal_id, result in confirmations.items():
        factor = registry.by_layer("market")[signal_id]
        rows.append(
            {
                "signal_id": signal_id,
                "signal_name": factor.name,
                "series_id": result.series_id,
                "status": result.status,
                "direction_convention": result.direction,
                "as_of": result.as_of.date().isoformat() if result.as_of is not None else "",
                "snapshot_date": snapshot_date or "",
                "history_length": result.history_length,
                "move_1m": result.move_1m,
                "move_3m": result.move_3m,
                "trend_6m": result.trend_6m,
                "adj_move_1m": result.adj_move_1m,
                "adj_move_3m": result.adj_move_3m,
                "adj_trend_6m": result.adj_trend_6m,
                "percentile": result.percentile,
                "adj_percentile": result.adj_percentile,
                "market_direction": result.market_direction,
                "macro_score": result.macro_score,
                "macro_direction": result.macro_direction,
                "agreement": result.agreement or "",
                "state": result.state or "",
                "confidence_composite": (result.confidence or {}).get("composite"),
                "provenance": result.provenance,
                "source": result.source,
            }
        )
    paths.LOCAL_DIR.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(paths.MARKET_CONFIRMATION_CSV, index=False, encoding="utf-8-sig")


if __name__ == "__main__":
    main()
