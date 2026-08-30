"""Shadow Operation metrics snapshot - read-only observation monitor.

Usage:
  python scripts/shadow_metrics.py [--today YYYY-MM-DD] [--window 24]
      [--horizon 3m] [--out data/local/shadow/shadow_metrics.csv]

Builds the PIT asset-score panel + realized forward-return proxies with the
SAME frozen machinery as validation_report.py (allow_synthetic=False), derives
the declared per-asset View from the frozen 0.15 threshold in assets.yaml, and
upserts one row per (date x asset) into an append-only CSV under data/local/
shadow/. It then prints a per-asset directional hit-rate summary over the
trailing ``--window`` month-ends.

Shadow discipline (V4.6 handoff -> Shadow Operation, MASTER SPEC section 15):
NEVER modifies canonical / weights / thresholds / signals. If the shadow phase
finds a proposed change (downgrade, threshold, new signal), log it to
docs/shadow/decision_journal.md - do NOT apply it here.
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
from macro_compass.data_sources.registry import load_data_sources_config  # noqa: E402
from macro_compass.macro import load_macro_config  # noqa: E402
from macro_compass.assets import load_asset_config  # noqa: E402
from macro_compass.signals import load_core_computations, load_signal_registry  # noqa: E402
from macro_compass.macro.config import CORE_FACTORS  # noqa: E402
from macro_compass.validation import assemble  # noqa: E402
from macro_compass.shadow import hit_summary, realized_frame, upsert_snapshot  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--today", default=None, help="reference date (ISO, default: today)")
    parser.add_argument(
        "--window", type=int, default=24,
        help="trailing month-ends included in the summary (default: 24)",
    )
    parser.add_argument(
        "--horizon", default="3m", choices=["1m", "3m"],
        help="forward horizon for the hit summary (default: 3m)",
    )
    parser.add_argument(
        "--out", default=str(paths.LOCAL_DIR / "shadow" / "shadow_metrics.csv"),
        help="append-only snapshot CSV path (default: data/local/shadow/shadow_metrics.csv)",
    )
    args = parser.parse_args()
    today = pd.Timestamp(args.today) if args.today else pd.Timestamp.today()
    threshold = float(load_asset_config(paths.ASSETS_YAML)["defaults"]["view_threshold"])

    indicators = load_indicator_config(paths.INDICATORS_YAML)
    registry = load_signal_registry(paths.SIGNALS_YAML, indicators_registry=indicators)
    macro_config = load_macro_config(paths.MACRO_YAML)
    assets_config = load_asset_config(paths.ASSETS_YAML, registry=registry)
    sources_cfg = load_data_sources_config(paths.DATA_SOURCES_YAML, indicator_registry=indicators)

    # allow_synthetic is always False - synthetic never enters the observation panel.
    snapshot = load_core_computations(
        registry, macro_config, allow_synthetic=False, today=today
    )
    staleness = {sid: spec.max_staleness_days for sid, spec in sources_cfg.series.items()}
    factor_signal_ids = {
        f: [sid for sid, spec in registry.core.items() if spec.factor == f]
        for f in CORE_FACTORS
    }
    sample = assemble(
        snapshot.computations, factor_signal_ids, macro_config, staleness,
        assets_config, snapshot.series, today,
    )

    frame = realized_frame(
        sample.asset_scores, sample.forward_returns, sample.asset_coverage,
        threshold=threshold,
    )
    if frame.empty:
        print("no scored (date, asset) rows - nothing to record")
        return

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    merged = upsert_snapshot(out_path, frame, today)
    merged.to_csv(out_path, index=False, encoding="utf-8-sig")

    # trailing-window subset for the summary (keyed on scoring date)
    lo = today.normalize() - pd.DateOffset(months=int(args.window))
    recent = frame[pd.to_datetime(frame["date"]) >= lo]
    summary = hit_summary(recent, horizon=args.horizon)

    print(f"=== Shadow Operation metrics - generated {today.date()} ===")
    print("isolation: reads frozen V2/V1.5 outputs + canonical; no modification;")
    print("no synthetic; no tuning; threshold read from assets.yaml = "
          f"{threshold:g}; no Core change (decisions only via decision_journal).")
    print(f"\npanel: {sample.factor_panel.index.min().date()} -> "
          f"{sample.factor_panel.index.max().date()} (month-ends, PIT); "
          f"scored (date x asset) rows this run = {len(frame)}; "
          f"summary window = trailing {args.window}m (>= {lo.date()})")

    print(f"\n--- Directional hit-rate vs realized {args.horizon} fwd "
          "(non-neutral views only) ---")
    if summary.empty:
        print("  (no non-neutral view with a realized forward return yet - "
              "normal early in the observation phase)")
    else:
        print(summary.to_string(index=False))

    n_rec = len(merged)
    print(f"\nWritten: {out_path} (total rows {n_rec}, keyed date x asset; "
          "existing rows refreshed when fwd becomes available)")
    print("\nRead-only monitor - canonical / asset outputs were not modified.")


if __name__ == "__main__":
    main()
