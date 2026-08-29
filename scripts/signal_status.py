"""V1.3 signal registry status: coverage + per-signal input availability.

Validates config/signals.yaml against config/indicators.yaml (unknown
series_id aborts with a clear error), assesses every signal's input
availability against canonical parquet, and writes the missing-series manifest
for later acquisition (data/local/missing_series.csv). Read-only except for
that manifest.

Usage:
    python scripts/signal_status.py
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from macro_compass import paths  # noqa: E402
from macro_compass.config import load_indicator_config  # noqa: E402
from macro_compass.signals import (  # noqa: E402
    assess_availability,
    load_signal_registry,
)
from macro_compass.storage import canonical_store  # noqa: E402


def main() -> None:
    indicators = load_indicator_config(paths.INDICATORS_YAML)
    registry = load_signal_registry(paths.SIGNALS_YAML, indicators_registry=indicators)

    available: set[str] = set()
    for category in ("macro", "market"):
        frame = canonical_store.read_canonical(category)
        if not frame.empty:
            available.update(frame["series_id"].unique())

    availability = assess_availability(registry, available)

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
                f"{state.status:<13} missing: {missing}"
            )

    core_ids = list(registry.core)
    ready = sum(1 for s in core_ids if availability[s].status == "READY")
    partial = sum(1 for s in core_ids if availability[s].status == "PARTIAL")
    print(f"\nCore signals READY: {ready}/15, PARTIAL: {partial}")

    missing = registry.missing_series(available)
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
