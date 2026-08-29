"""V1.5D Signal Quality Gate report.

Diagnostics for every core signal, computed from the SAME production signal
tables as ``macro_report`` (synthetic rows excluded unless
``--allow-synthetic``):

- status (READY / PARTIAL / WARMUP / MISSING_INPUT, registry-consistent)
- history length (scored observations), freshness vs the declared budget
- composite completeness: available / required inputs and coverage
- saturation: share of |score| >= 0.95 over the last 24 / 60 scored
  observations (SCALE_SATURATED warning when the 24-month share exceeds the
  configured threshold)
- normalization: the declared score-mapping rule for the signal (percentile /
  robust z-score / scale from config/macro.yaml)
- as-of note: expected release lag from data_sources.yaml freshness metadata;
  a snapshot observation whose (observation_date + lag) is in the future
  would NOT have been knowable - the report warns when data looks
  not-yet-released and never assumes same-day availability.

Read-only except for the quality CSV snapshot (data/local/signal_quality.csv).

Usage:
    python scripts/signal_quality.py [--allow-synthetic] [--today YYYY-MM-DD]
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from macro_compass import paths  # noqa: E402
from macro_compass.config import load_indicator_config  # noqa: E402
from macro_compass.data_sources.registry import load_data_sources_config  # noqa: E402
from macro_compass.macro import load_macro_config  # noqa: E402
from macro_compass.signals import (  # noqa: E402
    assess_availability,
    compute_core_signals,
    load_signal_registry,
)
from macro_compass.signals.engine import (  # noqa: E402
    _basis_type,
    _basis_scale,
    _zscore_clip,
)
from macro_compass.storage import canonical_store  # noqa: E402
from macro_compass.synthetic_guard import filter_synthetic  # noqa: E402

SATURATION_THRESHOLD = 0.4  # documented diagnostic constant, not a score input
WINDOW_24M = 24
WINDOW_60M = 60


def _saturation(scores: pd.Series, window: int) -> float:
    scored = scores.dropna()
    if scored.empty:
        return float("nan")
    recent = scored.tail(window)
    return float((recent.abs() >= 0.95).mean())


def _normalization_label(spec, macro_config) -> str:
    level_type = _basis_type(spec)
    if level_type == "rolling_percentile":
        return f"percentile -> 2*(basis-{spec.neutral})"
    if level_type == "robust_zscore":
        return f"robust_zscore -> clip(+/-{_zscore_clip(macro_config)})/{_zscore_clip(macro_config)}"
    scale = _basis_scale(macro_config, spec.signal_id, "level")
    return f"scale {level_type}/{scale:g} -> clip(+/-1)"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--today", default=None, help="ISO reference date")
    parser.add_argument(
        "--allow-synthetic",
        action="store_true",
        help="test-only: include synthetic fixture rows (production excludes them)",
    )
    args = parser.parse_args()
    today = pd.Timestamp(args.today) if args.today else pd.Timestamp.today()

    indicators = load_indicator_config(paths.INDICATORS_YAML)
    registry = load_signal_registry(paths.SIGNALS_YAML, indicators_registry=indicators)
    macro_config = load_macro_config(paths.MACRO_YAML)
    sources_cfg = load_data_sources_config(
        paths.DATA_SOURCES_YAML, indicator_registry=indicators
    )
    markers = macro_config.get("synthetic_markers") or []

    frames = [canonical_store.read_canonical(c) for c in ("macro", "market")]
    frames = [f for f in frames if not f.empty]
    canonical = filter_synthetic(
        pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(),
        markers,
        allow_synthetic=args.allow_synthetic,
    )
    series: dict[str, pd.Series] = {}
    for series_id, rows in canonical.groupby("series_id"):
        series[series_id] = (
            rows.assign(date=pd.to_datetime(rows["date"]))
            .drop_duplicates(subset="date", keep="last")
            .sort_values("date")
            .set_index("date")["value"]
            .astype(float)
            .rename(series_id)
        )
    availability = assess_availability(registry, set(series))

    computations = compute_core_signals(
        registry, series, macro_config, today,
        input_sources=canonical.sort_values("import_time").groupby("series_id")["source"].last().to_dict(),
    )

    print(f"=== Signal quality report - generated {today.date()} ===")
    header = (
        f"{'ID':<4}{'status':<14}{'hist':>5} {'fresh(d)':>9} {'cov':>5} "
        f"{'sat24':>6} {'sat60':>6} {'normalization':<28}warnings"
    )
    print(header)
    rows_out = []
    for signal_id, spec in registry.core.items():
        comp = computations[signal_id]
        warnings: list[str] = []
        scored = comp.frame["score"].dropna() if not comp.frame.empty else pd.Series(dtype=float)
        sat24 = _saturation(comp.frame["score"], WINDOW_24M)
        sat60 = _saturation(comp.frame["score"], WINDOW_60M)
        missing = availability[signal_id].missing
        label = _normalization_label(spec, macro_config)
        history = len(scored)

        freshness_text = "-"
        if not comp.frame.empty:
            freshness_days = int((today.normalize() - comp.frame["date"].max()).days)
            budgets = [
                sources_cfg.series[sid].max_staleness_days
                for sid in comp.input_series_ids if sid in sources_cfg.series
            ]
            budget = min(budgets) if budgets else 90
            freshness_text = f"{freshness_days}"
            if freshness_days > budget:
                warnings.append("STALE")
        if comp.status == "WARMUP":
            warnings.append("WARMUP")
        if comp.status == "PARTIAL":
            warnings.append(f"missing:{','.join(missing)}")
        if comp.status == "MISSING_INPUT":
            warnings.append(f"missing:{','.join(missing)}")
        if sat24 == sat24 and sat24 > SATURATION_THRESHOLD:
            warnings.append("SCALE_SATURATED")
        if history and history < _required_minimum(spec):
            warnings.append("SHORT_HISTORY")

        cov = comp.frame["coverage"].iloc[-1] if not comp.frame.empty else float("nan")
        print(
            f"{signal_id:<4}{comp.status:<14}{history:>5} {freshness_text:>9} "
            f"{cov if cov == cov else float('nan'):>5.2f} "
            f"{sat24:>6.0%} {sat60:>6.0%} {label:<28}"
            f"{';'.join(warnings) or '-'}"
        )
        rows_out.append(
            {
                "signal_id": signal_id,
                "status": comp.status,
                "history_scored": history,
                "freshness_days": freshness_text,
                "coverage_latest": cov,
                "saturation_24m": round(sat24, 4) if sat24 == sat24 else "",
                "saturation_60m": round(sat60, 4) if sat60 == sat60 else "",
                "normalization": label,
                "warnings": ";".join(warnings),
            }
        )

    print("\n--- Saturation detail (v0.4c Task 8) ---")
    print("Review trigger: 24M saturation > 25% OR 60M saturation > 15%.")
    print(
        f"{'ID':<5}{'pre-clip p50':>13} {'p95 |pre|':>11} {'max |pre|':>11} "
        f"{'clip rate':>10}   verdict"
    )
    for signal_id, spec in registry.core.items():
        comp = computations[signal_id]
        if comp.frame.empty:
            continue
        pre = _pre_clip_scores(spec, series, macro_config)
        if pre is None or pre.dropna().empty:
            continue
        abs_pre = pre.dropna().abs()
        p50 = float(pre.dropna().median())
        p95 = float(abs_pre.quantile(0.95))
        clip_rate = float((abs_pre >= 0.95).mean())
        verdict = "REVIEW" if clip_rate > 0.25 else "ok"
        print(
            f"{signal_id:<5}{p50:>13.3f} {p95:>11.3f} {abs_pre.max():>11.3f} "
            f"{clip_rate:>10.1%}   {verdict}"
        )
    print(
        "\nSaturation = share of |score| >= 0.95 among the last N scored rows; "
        f"SCALE_SATURATED when the 24-row share exceeds {SATURATION_THRESHOLD:.0%}."
    )
    print(
        "As-of semantics: release lag metadata (data_sources.yaml) documents the "
        "publication delay per series; no snapshot assumes same-day availability."
    )
    paths.LOCAL_DIR.mkdir(parents=True, exist_ok=True)
    with paths.LOCAL_DIR.joinpath("signal_quality.csv").open(
        "w", newline="", encoding="utf-8"
    ) as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows_out[0].keys()))
        writer.writeheader()
        writer.writerows(rows_out)
    print(f"Quality snapshot written: {paths.LOCAL_DIR / 'signal_quality.csv'}")


def _pre_clip_scores(spec, series: dict, macro_config) -> pd.Series | None:
    """Diagnostic: the level score mapping WITHOUT the +/-1 clip (v0.4c Task 8).

    Mirrors the documented map_score rules on the LEVEL basis only, purely
    for distribution review - the production engine is untouched.
    """
    from macro_compass.signals.engine import _basis_scale, _basis_type, _level_basis, _zscore_clip
    from macro_compass.transforms.pipeline import apply_chain

    available = [i.series_id for i in spec.inputs if i.series_id in series]
    if not available:
        return None
    basis_type = _basis_type(spec)
    scale = _basis_scale(macro_config, spec.signal_id, "level")
    neutral = float(spec.neutral or 0.0)
    direction = 1.0 if (spec.direction or "positive") == "positive" else -1.0
    zsc = _zscore_clip(macro_config)

    def _map(basis: pd.Series) -> pd.Series:
        if basis_type == "rolling_percentile":
            return 2.0 * (basis - neutral)
        if basis_type == "robust_zscore":
            return basis / zsc  # no clip: distribution review
        return basis / scale

    from macro_compass.signals.engine import resolve_combination

    if resolve_combination(spec) == "difference":
        # difference composites chain the RAW composite - mirror that here
        legs = pd.concat(
            [series[i.series_id] for i in spec.inputs], axis=1, join="inner"
        ).dropna()
        composite = legs.iloc[:, 0]
        for column in legs.columns[1:]:
            composite = composite - legs[column]
        return _map(apply_chain(composite, [dict(step) for step in spec.transforms])) * direction

    frames = []
    for sid in available:
        level = apply_chain(series[sid], [dict(step) for step in spec.transforms])
        frames.append(_map(level) * direction)
    combined = pd.concat(frames, axis=1).mean(axis=1)
    return combined


def _required_minimum(spec) -> int:
    """Minimum scored history for a healthy signal (declared-chain derived)."""
    from macro_compass.signals.engine import _required_history

    return min(_required_history(spec), 13)


if __name__ == "__main__":
    main()
