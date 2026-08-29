"""V1.5C macro snapshot report - the human acceptance entry point.

One run prints the latest picture of the whole macro engine:

* all 15 core signals (status / provenance / level & momentum scores /
  composite score / freshness / coverage, plus composite contribution
  breakdowns and the missing-input manifest entries);
* the four MASTER SPEC factors (score, breadth, confidence decomposition);
* the current growth x inflation regime with its full rationale.

Provenance is visible throughout: every signal and factor input is labelled
synthetic / real / mixed by matching its canonical ``source_file`` against
the synthetic markers declared in ``config/macro.yaml``.

Read-only except for the snapshot CSV (data/local/signal_scores.csv).

Usage:
    python scripts/macro_report.py
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
from macro_compass.macro import (  # noqa: E402
    classify_provenance,
    classify_regime,
    compute_factor,
    load_macro_config,
)
from macro_compass.signals import (  # noqa: E402
    assess_availability,
    compute_core_signals,
    load_signal_registry,
)
from macro_compass.signals.engine import SignalComputation  # noqa: E402
from macro_compass.synthetic_guard import filter_synthetic  # noqa: E402
from macro_compass.storage import canonical_store  # noqa: E402

FACTORS = ("growth", "inflation", "domestic_financial", "global_financial")


def _load_canonical() -> pd.DataFrame:
    frames = [canonical_store.read_canonical(category) for category in ("macro", "market")]
    frames = [f for f in frames if not f.empty]
    if not frames:
        raise SystemExit(
            "canonical parquet is empty - run scripts/update_sources.py or "
            "scripts/import_wind.py first"
        )
    return pd.concat(frames, ignore_index=True)


def _series_from_canonical(canonical: pd.DataFrame) -> dict[str, pd.Series]:
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
    return series


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
    sources_cfg = load_data_sources_config(paths.DATA_SOURCES_YAML, indicator_registry=indicators)

    canonical = _load_canonical()
    canonical = filter_synthetic(
        canonical, macro_config.get("synthetic_markers") or [],
        allow_synthetic=args.allow_synthetic,
    )
    series = _series_from_canonical(canonical)
    availability = assess_availability(registry, set(series))

    markers = macro_config.get("synthetic_markers") or []
    provenance_by_series = classify_provenance(
        canonical.groupby("series_id")["source_file"].agg(lambda s: list(s.dropna().unique())).to_dict(),
        markers,
    )
    source_by_series = (
        canonical.sort_values("import_time")
        .groupby("series_id")["source"]
        .last()
        .to_dict()
    )
    staleness = {
        series_id: spec.max_staleness_days for series_id, spec in sources_cfg.series.items()
    }

    computations = compute_core_signals(
        registry,
        series,
        macro_config,
        today,
        input_provenance=provenance_by_series,
        input_sources=source_by_series,
    )

    print(f"=== Macro Engine snapshot - generated {today.date()} ===")
    print(
        "provenance markers (config/macro.yaml): "
        + ", ".join(markers)
        + " -> canonical rows matching them are labelled SYNTHETIC"
    )

    _print_signal_table(registry, computations, availability, staleness, macro_config, today)
    factors = _print_factors(registry, computations, macro_config, staleness, today)
    _print_regime(factors, macro_config)
    _write_snapshot(registry, computations)

    print("\nRead-only report - canonical data was not modified.")
    print(f"Signal snapshot written: {paths.SIGNAL_SCORES_CSV}")


def _print_signal_table(
    registry, computations, availability, staleness, macro_config, today
) -> None:
    print("\n--- Core signals (15) ---")
    header = (
        f"{'ID':<4}{'signal':<30}{'factor':<20}{'status':<14}{'data':<10}"
        f"{'score':>7} {'lvl_sc':>7} {'mom_sc':>7} {'fresh(d)':>9} {'cov':>5}"
    )
    print(header)
    for signal_id, spec in registry.core.items():
        comp = computations[signal_id]
        latest = comp.latest()
        missing = ", ".join(availability[signal_id].missing) or "-"
        name = spec.name[:28]
        factor = spec.factor or "-"
        if latest is None:
            print(
                f"{signal_id:<4}{name:<30}{factor:<20}{comp.status:<14}{comp.provenance:<10}"
                f"{'n/a':>7} {'n/a':>7} {'n/a':>7} {'n/a':>9} {'n/a':>5}  missing: {missing}"
            )
            continue
        default_budget = int(
            macro_config["confidence"].get("default_max_staleness_days", 90)
        )
        budget = min(
            (staleness.get(sid, default_budget) for sid in comp.input_series_ids),
            default=default_budget,
        )
        fresh = int(latest["freshness"])
        stale_flag = "STALE" if fresh > budget else "ok"
        print(
            f"{signal_id:<4}{name:<30}{factor:<20}{comp.status:<14}{comp.provenance:<10}"
            f"{_fmt(latest['score'], '+.3f'):>7} {_fmt(latest['level_score'], '+.3f'):>7} "
            f"{_fmt(latest['momentum_score'], '+.3f'):>7} {fresh:>5} {stale_flag:<3} "
            f"{latest['coverage']:>5.2f}  missing: {missing}"
        )
        _print_breakdown(signal_id, comp)


def _print_breakdown(signal_id: str, comp: SignalComputation) -> None:
    if comp.contributions is None or comp.contributions.empty:
        return
    latest_row = comp.contributions.iloc[-1]
    parts = []
    for column in comp.contributions.columns:
        value = latest_row[column]
        if pd.isna(value):
            parts.append(f"{column}: n/a")
        else:
            parts.append(f"{column}: {value:+.3f}")
    unit = (
        "signed share of raw composite" if comp.combination == "difference"
        else "additive score points"
    )
    print(f"     combination={comp.combination} breakdown ({unit}): " + "; ".join(parts))


def _print_factors(registry, computations, macro_config, staleness, today) -> dict:
    print("\n--- Macro factors ---")
    factors = {}
    for factor in FACTORS:
        declared = [sid for sid, spec in registry.core.items() if spec.factor == factor]
        result = compute_factor(
            factor, declared, computations, macro_config, staleness, today
        )
        factors[factor] = result
        conf = result.confidence
        score = "n/a" if result.score is None else f"{result.score:+.3f}"
        print(
            f"{factor:<20} score {score:>7}  breadth {result.breadth} "
            f"{result.breadth_detail}  confidence {conf['composite']:.2f} "
            f"(coverage {conf['coverage']:.2f}, freshness {conf['freshness']:.2f}, "
            f"source_quality {conf['source_quality']:.2f})"
        )
        for signal_id, contribution in result.signals.items():
            inputs = ", ".join(f"{sid}={src}" for sid, src in contribution.inputs.items()) or "-"
            if contribution.freshness_days is None:
                fresh_text = "  n/a"
            else:
                fresh_text = f"{contribution.freshness_days}d"
            stale = "STALE" if contribution.stale else (
                "ok" if contribution.freshness_days is not None else "-"
            )
            print(
                f"    {signal_id:<4} score {_fmt(contribution.score, '+.3f'):>7} "
                f"w {contribution.weight:.1f}  contribution {_fmt(contribution.contribution, '+.3f'):>7} "
                f"cov {contribution.coverage:.2f}  fresh {fresh_text:>5} {stale:<5} "
                f"data {contribution.provenance:<9} inputs: {inputs}"
            )
        if not result.signals:
            print("    (no declared signal has output)")
    return factors


def _print_regime(factors: dict, macro_config: dict) -> None:
    result = classify_regime(factors, macro_config)
    print("\n--- Regime ---")
    print(f"REGIME: {result.regime}")
    for line in result.rationale:
        print(f"  - {line}")


def _write_snapshot(registry, computations) -> None:
    frames = []
    for signal_id, comp in computations.items():
        if comp.frame.empty:
            continue
        factor = registry.core[signal_id].factor or ""
        frames.append(comp.frame.assign(factor=factor, data_provenance=comp.provenance))
    paths.LOCAL_DIR.mkdir(parents=True, exist_ok=True)
    if frames:
        pd.concat(frames, ignore_index=True).to_csv(paths.SIGNAL_SCORES_CSV, index=False)
    else:
        paths.SIGNAL_SCORES_CSV.write_text("", encoding="utf-8")


if __name__ == "__main__":
    main()
