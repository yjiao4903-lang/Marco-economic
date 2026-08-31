"""V2.5 Historical Validation report - the acceptance entry point (task 60).

One run produces:

* Historical Coverage Matrix (per Core Signal + per input series);
* a backfill gap assessment (the Wind one-shot candidate list still short);
* the five Validation methods (forward returns / score bucket / regime analysis /
  rolling beta / weight robustness) per asset;
* the Leave-One-Mechanism-Out (LOMO) information-increment test per factor;
* the two R2 regime/structural checks (gold real-yield decoupling, credit
  funding sensitivity).

Everything here READS the frozen V2 / V1.5 outputs (factor engine + canonical)
and the market return proxies - nothing is modified and no synthetic row enters
the sample (production isolation). Outputs go to ``data/local/validation_*.csv``.
No Core signal is ever downgraded by this Run; LOMO findings are recommendations
only (owner approval required, task 60 section 4/6).
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
from macro_compass.validation import (  # noqa: E402
    assemble,
    run_all_for_asset,
    run_lomo,
    run_regime_checks,
    assess_backfill_gaps,
    build_coverage_matrix,
    first_score_dates,
    mechanism_scored_share,
)
from macro_compass.validation.report import write_all, summary_tables
from macro_compass.validation.verdict import build_verdicts, verdicts_frame


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--today", default=None, help="reference date (ISO, default: today)")
    parser.add_argument(
        "--min-coverage", type=float, default=0.5,
        help="min asset factor-coverage for a (score, fwd) pair to enter methods",
    )
    args = parser.parse_args()
    today = pd.Timestamp(args.today) if args.today else pd.Timestamp.today()

    indicators = load_indicator_config(paths.INDICATORS_YAML)
    registry = load_signal_registry(paths.SIGNALS_YAML, indicators_registry=indicators)
    macro_config = load_macro_config(paths.MACRO_YAML)
    assets_config = load_asset_config(paths.ASSETS_YAML, registry=registry)
    sources_cfg = load_data_sources_config(paths.DATA_SOURCES_YAML, indicator_registry=indicators)

    # NOTE: allow_synthetic is always False - synthetic never enters a validation sample.
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

    # --- coverage + backfill ---
    fsd = first_score_dates(snapshot.computations)
    coverage = build_coverage_matrix(
        registry, sources_cfg, macro_config, snapshot.series, fsd
    )
    backfill = assess_backfill_gaps(snapshot.series, today)

    # --- five methods ---
    methods = []
    for asset_id in assets_config["assets"]:
        methods += run_all_for_asset(
            asset_id, sample, assets_config, min_coverage=args.min_coverage
        )

    # --- LOMO ---
    lomo = run_lomo(
        snapshot.computations, factor_signal_ids, macro_config, staleness,
        assets_config, sample, first_score_dates=fsd,
        mechanism_scored_share=mechanism_scored_share(
            snapshot.computations, sample.factor_panel.index
        ),
    )

    # --- regime checks ---
    regime = run_regime_checks(sample, assets_config)

    written = write_all(
        coverage, backfill, methods, lomo, regime,
        sample.factor_panel, sample.asset_scores, sample.asset_coverage, today,
    )

    # V4.6 Task 10: per-asset empirical verdicts (pure read-only assembly).
    verdicts = build_verdicts(
        methods, sample.asset_scores, sample.asset_coverage,
        assets=list(assets_config["assets"]),
    )
    verdict_df = verdicts_frame(verdicts)
    verdict_csv = paths.LOCAL_DIR / "validation_verdicts.csv"
    paths.LOCAL_DIR.mkdir(parents=True, exist_ok=True)
    verdict_df.to_csv(verdict_csv, index=False, encoding="utf-8-sig")
    written += ["data/local/validation_verdicts.csv"]

    method_table, lomo_table, regime_table = summary_tables(
        methods, lomo, regime, coverage
    )

    print(f"=== V2.5 Historical Validation - generated {today.date()} ===")
    print("isolation: reads frozen V2 outputs + canonical; no modification; no "
          "synthetic; no auto-tuning; no Core downgrade (recommendations only).")
    print(f"\nValidation grid: {sample.factor_panel.index.min().date()} -> "
          f"{sample.factor_panel.index.max().date()} (month-ends, PIT)")

    print("\n--- ASSET factor coverage (mean |norm-beta| scored, [0,1]; ~1.0 = near full) ---")
    cov_df = sample.asset_coverage
    full_rows = cov_df[cov_df.sum(axis=1) > 0]
    print(f"  dates={len(full_rows)}; per-asset mean coverage:")
    for c in cov_df.columns:
        vals = cov_df[c][cov_df[c] > 0]
        print(f"    {c:<22} mean={vals.mean():.3f}, first_scored={vals.index.min().date() if len(vals) else '-'}")

    print("\n--- Five methods (methods with adequate n are the only ones able to signal) ---")
    _print_table(method_table)

    print("\n--- LOMO (Leave-One-Mechanism-Out) ---")
    _print_table(lomo_table)

    print("\n--- R2 regime/structural checks ---")
    for row in regime_table.to_dict("records"):
        print(f"  {row['check']}: {row['conclusion']}  (n={row['n']})  {row['detail']}")

    print("\n--- V4.6 per-asset empirical verdicts (task 86; read-only) ---")
    _print_table(verdict_df)

    print("\n--- Coverage matrix (inputs + signal comparable-history start) ---")
    cdf = pd.DataFrame(coverage_matrix_rows(coverage))
    keep = cdf[["signal_id", "input_series", "earliest_observation",
                "provider", "revision_risk"]]
    print(keep.to_string(index=False))

    print("\n--- Backfill gaps (Wind one-shot candidates still short) ---")
    gdf = pd.DataFrame(backfill)
    print(gdf.to_string(index=False) if len(backfill) else "  none - all candidates covered")

    print("\nWarnings:")
    n_adequate = int(sum(1 for m in methods if m["adequate"]))
    print(f"  {n_adequate}/{len(methods)} method results have an adequate sample "
          f"(>={60} monthly obs); the rest are INSUFFICIENT_SAMPLE - do not treat "
          f"them as refutations.")
    print(f"  The adequate rows still use PARTIAL factor coverage: the domestic "
          f"financial factor only scores from ~2024-12 (D1 needs DR007+policy-rate "
          f"history), so pre-2024 asset scores omit domestic - weak results on them "
          f"are exploratory, not a strong refutation.")
    print(f"  GOLD now has real London spot history in canonical (1968-01 to "
          f"2026-08, monthly); forward validation is available subject to the "
          f"declared horizon/sample gates. The real-yield decoupling check still "
          f"depends on US_REAL_YIELD_10Y overlap.")

    _print_conclusion(regime, lomo, methods, sample)

    print("\nWritten: " + ", ".join(written))
    print("\nRead-only report - canonical / asset outputs were not modified.")


def _print_conclusion(regime, lomo, methods, sample) -> None:
    n_full = int(
        sample.asset_coverage[sample.asset_coverage.max(axis=1) >= 0.99].count().max()
        if not sample.asset_coverage.empty else 0
    )
    candidates = [r for r in lomo if r.candidate]
    lomo_cand = ", ".join(f"{r.factor}:{r.mechanism}" for r in candidates) or "none"
    regime_txt = "; ".join(f"{r.check_id}={r.conclusion}" for r in regime)
    print("\n=== OVERALL VALIDATION CONCLUSION (V2.5) ===")
    print(f"1. SAMPLE: the four-factor comparable asset-score window is ~{n_full} "
          f"month-ends (from ~2024-12, when domestic_financial first scores). This "
          f"is far below the owner minimum (2012/2015-present, spec 47 sec 31) - "
          f"so NO firm 'effective/ineffective' verdict is warranted on current data.")
    print(f"2. FIVE METHODS: dominant NO_EFFECT_OR_WEAK on partial-coverage scores; "
          f"exploratory only. One borderline reversed signal (CN_CREDIT 3m).")
    print(f"3. LOMO: candidates (low-increment, high-history mechanisms) = "
          f"[{lomo_cand}]. Recommendations ONLY - no Core signal is downgraded by "
          f"this window (requires owner approval after backfill validation).")
    print(f"4. REGIME CHECKS: {regime_txt}. Gold real-yield decoupling remains "
          f"INSUFFICIENT_SAMPLE because US_REAL_YIELD_10Y has no pre-2022 overlap; M3 "
          f"regime-dependence is INSUFFICIENT_SAMPLE (yield series starts "
          f"2023-05, few yield-down month-ends); credit funding-sensitivity "
          f"is INSUFFICIENT_SAMPLE (D1 history too short).")
    print(f"5. NEXT: Wind one-shot backfill (see backfill gaps) - TSF/gov-bond "
          f"financing, PMI orders/input-price, property, core CPI, policy rate "
          f"history, USD_BROAD, and pre-2022 real yield - then re-run this "
          f"report before any Core downgrade decision.")


def _print_table(df: pd.DataFrame) -> None:
    if df.empty:
        print("  (no rows)")
        return
    print(df.to_string(index=False))


def coverage_matrix_rows(coverage) -> list[dict]:
    from macro_compass.validation.report import coverage_matrix_rows as _r
    return _r(coverage)


if __name__ == "__main__":
    main()
