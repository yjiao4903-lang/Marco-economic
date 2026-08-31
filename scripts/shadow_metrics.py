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
from macro_compass.shadow import (  # noqa: E402
    content_hash, decision_snapshot_frame, outcome_observation_frame,
    append_unique, maturity_counts, runtime_metadata, git_hash, replay_gate,
)


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
    parser.add_argument("--snapshot-out", default=str(paths.LOCAL_DIR / "shadow" / "decision_snapshots.csv"),
                        help="append-only decision snapshot CSV")
    parser.add_argument("--out", default=str(paths.LOCAL_DIR / "shadow" / "outcome_observations.csv"),
                        help="append-only outcome observation CSV")
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

    decisions = decision_snapshot_frame(
        sample.asset_scores, sample.asset_coverage, threshold=threshold, as_of=today,
        config_hash=content_hash(assets_config), data_hash=content_hash(sample.asset_scores),
        git_hash_value=git_hash(PROJECT_ROOT), runtime_metadata_value=runtime_metadata(),
    )
    if decisions.empty:
        print("no scored (date, asset) rows - nothing to record")
        return

    outcomes = outcome_observation_frame(decisions, sample.forward_returns, observed_as_of=today)
    snapshot_path = Path(args.snapshot_out)
    outcome_path = Path(args.out)
    # Fail closed before any write: existing files are treated as persisted
    # evidence, and a malformed/entangled file must be repaired manually.
    existing_decisions = (pd.read_csv(snapshot_path)
                          if snapshot_path.exists()
                          else pd.DataFrame(columns=decisions.columns))
    existing_outcomes = (pd.read_csv(outcome_path)
                         if outcome_path.exists()
                         else pd.DataFrame(columns=outcomes.columns))
    preflight = replay_gate(existing_decisions, existing_outcomes)
    if not preflight["valid"]:
        raise RuntimeError(f"Shadow replay gate failed before write: {preflight}")
    candidate_gate = replay_gate(
        pd.concat([existing_decisions, decisions], ignore_index=True),
        pd.concat([existing_outcomes, outcomes], ignore_index=True),
    )
    if not candidate_gate["valid"]:
        raise RuntimeError(f"Shadow replay gate failed for candidate run: {candidate_gate}")
    merged_decisions = append_unique(snapshot_path, decisions, "snapshot_id")
    merged_outcomes = append_unique(outcome_path, outcomes, "outcome_id")

    # trailing-window subset for the summary (keyed on scoring date)
    lo = today.normalize() - pd.DateOffset(months=int(args.window))
    print(f"=== Shadow Operation metrics - generated {today.date()} ===")
    print("isolation: reads frozen V2/V1.5 outputs + canonical; no modification;")
    print("no synthetic; no tuning; threshold read from assets.yaml = "
          f"{threshold:g}; no Core change (decisions only via decision_journal).")
    print(f"\npanel: {sample.factor_panel.index.min().date()} -> "
          f"{sample.factor_panel.index.max().date()} (month-ends, PIT); "
          f"decision snapshots this run = {len(decisions)}; "
          f"summary window = trailing {args.window}m (>= {lo.date()})")
    counts = maturity_counts(merged_decisions, merged_outcomes)
    gate = replay_gate(merged_decisions, merged_outcomes)
    print(f"Replay gate: {'PASS' if gate['valid'] else 'FAIL'}")
    print(f"\nGovernance counts: snapshot_count={counts['snapshot_count']}; "
          f"matured_1m_count={counts['matured_1m_count']}; matured_3m_count={counts['matured_3m_count']}")
    print(f"Written decisions: {snapshot_path} (append-only, total {len(merged_decisions)})")
    print(f"Written outcomes: {outcome_path} (append-only, total {len(merged_outcomes)})")
    print("\nRead-only monitor - canonical / asset outputs were not modified.")


if __name__ == "__main__":
    main()
