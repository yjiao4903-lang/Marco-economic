"""V1.3/V1.5E signal registry status: per-signal availability + engine status.

Loads the production data pipeline ONCE via the shared runtime
(``signals.status.load_core_computations``) and reports the resolved status
(READY / WARMUP / PARTIAL / MISSING_INPUT / DECLARED) for every signal -
identical to macro_report and signal_quality by construction. Also writes the
missing-series manifest for later acquisition (data/local/missing_series.csv).

Usage:
    python scripts/signal_status.py [--allow-synthetic]
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from macro_compass import paths  # noqa: E402
from macro_compass.config import load_indicator_config  # noqa: E402
from macro_compass.macro import load_macro_config  # noqa: E402
from macro_compass.market import compute_market_metrics, load_market_config  # noqa: E402
from macro_compass.signals import (  # noqa: E402
    load_core_computations,
    load_signal_registry,
    resolve_signal_status,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--allow-synthetic",
        action="store_true",
        help="test-only: include synthetic fixture rows (production excludes them)",
    )
    args = parser.parse_args()

    indicators = load_indicator_config(paths.INDICATORS_YAML)
    registry = load_signal_registry(paths.SIGNALS_YAML, indicators_registry=indicators)
    macro_config = load_macro_config(paths.MACRO_YAML)
    market_config = load_market_config(paths.MARKET_YAML)

    snapshot = load_core_computations(
        registry, macro_config, allow_synthetic=args.allow_synthetic
    )
    availability = snapshot.availability
    # V1.6A: market-layer statuses come from the market engine (READY /
    # WARMUP / MISSING_INPUT), not the registry placeholders
    market_metrics = compute_market_metrics(
        registry, market_config, snapshot.series, snapshot.today
    )
    resolved = resolve_signal_status(
        registry, availability, snapshot.computations, market_metrics
    )

    layers = (("core", "Core Fundamental"), ("market", "Market Confirmation"),
              ("structural", "Structural Risk"))
    for layer, title in layers:
        signals = registry.by_layer(layer)
        print(f"\n=== {title} signals ({len(signals)}) ===")
        for signal_id, spec in signals.items():
            state = availability[signal_id]
            missing = ", ".join(state.missing) if state.missing else "-"
            print(
                f"  {signal_id:>3} {spec.name:<40} factor={spec.factor or '-':<20} "
                f"{resolved[signal_id]:<13} missing: {missing}"
            )

    core_ids = list(registry.core)
    ready = sum(1 for s in core_ids if resolved[s] == "READY")
    warmup = sum(1 for s in core_ids if resolved[s] == "WARMUP")
    partial = sum(1 for s in core_ids if resolved[s] == "PARTIAL")
    print(f"\nCore signals READY: {ready}/15, WARMUP: {warmup}, PARTIAL: {partial}")

    missing = registry.missing_series(snapshot.available_series)
    paths.LOCAL_DIR.mkdir(parents=True, exist_ok=True)
    with paths.MISSING_SERIES_CSV.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["series_id", "referenced_by", "registered_in_indicators"])
        for series_id in missing:
            referencing = [
                sid
                for sid, spec in registry.signals.items()
                if series_id in {i.series_id for i in spec.inputs}
            ]
            writer.writerow([series_id, " ".join(referencing), series_id in indicators])
    print(f"Missing-series manifest written: {paths.MISSING_SERIES_CSV} ({len(missing)} series)")


if __name__ == "__main__":
    main()
