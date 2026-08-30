"""Validation report assembly + CSV persistence (task 60 section 6)."""

from __future__ import annotations

import pandas as pd

from macro_compass import paths


def _out(name: str):
    return paths.LOCAL_DIR / name


def coverage_matrix_rows(coverage) -> list[dict]:
    rows = []
    for sig in coverage:
        for sr in sig.inputs:
            rows.append({
                "signal_id": sig.signal_id,
                "name": sig.name,
                "factor": sig.factor,
                "input_series": sr.series_id,
                "role": sr.role,
                "earliest_observation": (
                    sr.earliest_observation.date().isoformat()
                    if sr.earliest_observation is not None else ""
                ),
                "provider": sr.provider,
                "update_policy": sr.update_policy_mode,
                "revision_risk": sr.revision_risk,
                "breakpoints": sr.note,
            })
        rows.append({
            "signal_id": sig.signal_id,
            "name": sig.name,
            "factor": sig.factor,
            "input_series": "== signal ==",
            "role": "comparable_history_start",
            "earliest_observation": (
                sig.comparable_history_start.date().isoformat()
                if sig.comparable_history_start is not None else ""
            ),
            "provider": "",
            "update_policy": "",
            "revision_risk": "minimum_validation_start=" + (
                sig.minimum_validation_start.date().isoformat()
                if sig.minimum_validation_start is not None else "n/a"
            ),
            "breakpoints": "; ".join(sig.breakpoints),
        })
    return rows


def write_all(
    coverage,
    backfill_gaps,
    methods,
    lomo,
    regime_checks,
    factor_panel,
    asset_scores,
    asset_coverage,
    today,
) -> list[str]:
    paths.LOCAL_DIR.mkdir(parents=True, exist_ok=True)
    written = []
    pd.DataFrame(coverage_matrix_rows(coverage)).to_csv(
        _out("validation_coverage_matrix.csv"), index=False, encoding="utf-8-sig"
    )
    written.append("validation_coverage_matrix.csv")
    pd.DataFrame(backfill_gaps).to_csv(
        _out("validation_backfill_gaps.csv"), index=False, encoding="utf-8-sig"
    )
    written.append("validation_backfill_gaps.csv")
    pd.DataFrame(methods).to_csv(
        _out("validation_methods.csv"), index=False, encoding="utf-8-sig"
    )
    written.append("validation_methods.csv")
    pd.DataFrame([r.__dict__ for r in lomo]).to_csv(
        _out("validation_lomo.csv"), index=False, encoding="utf-8-sig"
    )
    written.append("validation_lomo.csv")
    pd.DataFrame([r.__dict__ for r in regime_checks]).to_csv(
        _out("validation_regime_checks.csv"), index=False, encoding="utf-8-sig"
    )
    written.append("validation_regime_checks.csv")
    factor_panel.reset_index().to_csv(
        _out("validation_factor_panel.csv"), index=False, encoding="utf-8-sig"
    )
    asset_scores.reset_index().to_csv(
        _out("validation_asset_scores.csv"), index=False, encoding="utf-8-sig"
    )
    asset_coverage.reset_index().to_csv(
        _out("validation_asset_coverage.csv"), index=False, encoding="utf-8-sig"
    )
    written += ["validation_factor_panel.csv", "validation_asset_scores.csv",
                "validation_asset_coverage.csv"]
    return ["data/local/" + w for w in written]


def summary_tables(methods, lomo, regime_checks, coverage):
    """Human-facing summaries used by the printed report."""
    method_table = pd.DataFrame(methods)[
        ["method", "asset", "horizon", "metric", "statistic", "n", "conclusion"]
    ]
    lomo_table = pd.DataFrame([
        {
            "factor": r.factor, "mechanism": r.mechanism,
            "factor_stability": r.factor_stability,
            "min_asset_stability": r.min_asset_stability,
            "max_sep_delta": r.max_separation_delta,
            "candidate": r.candidate, "sample_ok": r.sample_ok,
        }
        for r in lomo
    ])
    regime_table = pd.DataFrame([
        {"check": r.check_id, "conclusion": r.conclusion, "statistic": r.statistic,
         "n": r.n, "detail": r.detail}
        for r in regime_checks
    ])
    return method_table, lomo_table, regime_table