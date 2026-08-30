"""V2 Asset Compass snapshot report - the human acceptance entry point.

One run prints the latest picture of the whole Asset Compass layer:

* the seven-asset table: Score / View / 1M & 3M change / confirmation /
  confidence;
* per-asset Factor decomposition (additive contribution of each core factor
  to the score, with the declared prior beta and its normalised weight);
* per-asset Signal decomposition (additive contribution of each contributing
  signal, with its factor and series -> provider trace);
* the parallel Market Confirmation observation per asset (never merged into
  the Score).

ISOLATION: this report READS the fundamental factor outputs and the market
confirmation outputs; it has no path that modifies them (ARCHITECTURE 10/11).
Views are tailwind / headwind / neutral only - never buy/sell/position advice.
Asset Score != expected return != trading signal != portfolio weight.

Read-only except for the snapshot CSV (data/local/asset_scores.csv).

Usage:
    python scripts/asset_report.py
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
from macro_compass.market import compute_market_confirmations, load_market_config  # noqa: E402
from macro_compass.assets import compute_assets, load_asset_config  # noqa: E402
from macro_compass.signals import load_core_computations, load_signal_registry  # noqa: E402

FACTORS = ("growth", "inflation", "domestic_financial", "global_financial")


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
    assets_config = load_asset_config(paths.ASSETS_YAML, registry=registry)
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

    factor_signal_ids = {
        factor: [sid for sid, spec in registry.core.items() if spec.factor == factor]
        for factor in FACTORS
    }
    factor_results = {
        factor: compute_factor(
            factor, factor_signal_ids[factor], snapshot.computations, macro_config,
            staleness, today,
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

    results = compute_assets(
        assets_config,
        factor_results,
        snapshot.computations,
        macro_config,
        staleness,
        today,
        factor_signal_ids=factor_signal_ids,
        market_confirmations=confirmations,
    )

    print(f"=== Asset Compass snapshot - generated {today.date()} ===")
    print(
        "isolation: the asset layer reads factor outputs + a parallel market "
        "confirmation observation; nothing here modifies Growth/Inflation or "
        "any market state. Asset Score != expected return != trading signal."
    )

    _print_overview(assets_config, results)
    _print_factor_breakdown(results)
    _print_signal_breakdown(assets_config, results)
    _write_snapshot(assets_config, results)

    print("\nRead-only report - canonical data was not modified.")
    print(f"Asset snapshot written: {paths.ASSET_SCORES_CSV}")


def _print_overview(assets_config, results) -> None:
    print("\n--- Assets (Score / View / 1M / 3M change) ---")
    header = (
        f"{'asset':<20}{'status':<8}{'score':>8} {'view':<8}"
        f"{'1M chg':>8} {'3M chg':>9}  confirmation"
    )
    print(header)
    for asset_id, asset_cfg in assets_config["assets"].items():
        r = results[asset_id]
        conf = r.market_confirmation
        conf_s = (
            f"{conf.state} ({conf.status})" if conf is not None else "n/a"
        )
        print(
            f"{asset_id:<20}{r.status:<8}{_fmt(r.score):>8} {str(r.view or '-'):<8}"
            f"{_fmt(r.change_1m, '+.3f'):>8} {_fmt(r.change_3m, '+.3f'):>9}  {conf_s}"
        )


def _print_factor_breakdown(results) -> None:
    print("\n--- Factor contribution (additive asset-score points) ---")
    for asset_id, r in results.items():
        if r.status != "READY":
            print(f"\n  {asset_id:<20} status={r.status} (not enough scored factors)")
            continue
        parts = [
            f"{f}={_fmt(r.factor_contributions[f], '+.3f')}"
            f"[beta {_fmt(r.beta[f], '.1f')}, w {_fmt(r.beta_normalized[f], '+.2f')}]"
            for f in FACTORS
            if _fmt(r.factor_contributions[f]) != "  n/a"
        ]
        print(f"\n  {asset_id:<20} score={_fmt(r.score):<8} " + "  ".join(parts))


def _print_signal_breakdown(assets_config, results) -> None:
    print("\n--- Signal contribution (asset -> factor -> signal -> series/source) ---")
    for asset_id, asset_cfg in assets_config["assets"].items():
        r = results[asset_id]
        print(f"\n  {asset_id} ({asset_cfg.get('name')})")
        if r.status != "READY":
            print(f"    status={r.status}")
            continue
        for sid in sorted(r.signal_contributions):
            sc = r.signal_contributions[sid]
            trace = "; ".join(f"{sid2}={src}" for sid2, src in sc.inputs.items())
            print(
                f"    {sid:<4} contribution={_fmt(sc.contribution, '+.4f'):<10} "
                f"score={_fmt(sc.score):<8} factor={sc.factor:<18} series/source: {trace}"
            )


def _write_snapshot(assets_config, results) -> None:
    rows = []
    for asset_id, asset_cfg in assets_config["assets"].items():
        r = results[asset_id]
        conf = r.market_confirmation
        for f in FACTORS:
            rows.append(
                {
                    "asset": asset_id,
                    "asset_name": asset_cfg.get("name"),
                    "status": r.status,
                    "score": r.score,
                    "view": r.view,
                    "change_1m": r.change_1m,
                    "change_3m": r.change_3m,
                    "factor": f,
                    "beta": r.beta.get(f),
                    "beta_normalized": r.beta_normalized.get(f),
                    "factor_contribution": r.factor_contributions.get(f),
                    "confidence_coverage": r.confidence.get("coverage"),
                    "confidence_freshness": r.confidence.get("freshness"),
                    "confidence_source_quality": r.confidence.get("source_quality"),
                    "confidence_composite": r.confidence.get("composite"),
                    "market_signal": asset_cfg.get("market_signal") or "",
                    "market_state": conf.state if conf else "",
                    "market_status": conf.status if conf else "",
                    "market_agreement": conf.agreement if conf else "",
                    "as_of": r.asof.date().isoformat() if r.asof is not None else "",
                }
            )
    paths.LOCAL_DIR.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(paths.ASSET_SCORES_CSV, index=False, encoding="utf-8-sig")


if __name__ == "__main__":
    main()