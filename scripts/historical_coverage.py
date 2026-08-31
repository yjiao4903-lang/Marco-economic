"""V4.5 Historical Completion - Task 3 (P0-2) Historical Coverage Matrix.

For every Core / Market / Structural signal and every one of its input
series, this read-only report records:

    signal_id / layer / factor / input_series / role /
    earliest_observation / comparable_history_start /
    minimum_validation_start / current_source / historical_source /
    frequency / revision_risk / breakpoints / status / blocker

plus a Source-Transition table (Task 4, P0 discipline): for each series and
signal that carries (or may later carry) a history+live splice, record the
canonical definition, historical source, live source, transition date,
overlap window, unit, frequency, methodology notes and any declared
breakpoint. The hard rule: if the definitions are not comparable, prefer a
shorter comparable history over fabricating a continuous series - no silent
splicing, no synthetic production.

Outputs:
    data/historical_coverage_matrix.csv  (one row per (signal, input series))
    docs/HISTORICAL_COVERAGE_MATRIX.md   (human-readable matrix + transitions)

Everything here reads the frozen V1-V4 pipeline (signals.status shared
loader + resolve_signal_status, market engine, structural engine). Nothing is
modified, no weight/threshold/signal declaration changes, no synthetic rows.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from macro_compass import paths  # noqa: E402
from macro_compass.config import load_indicator_config  # noqa: E402
from macro_compass.data_sources.registry import load_data_sources_config  # noqa: E402
from macro_compass.macro import load_macro_config  # noqa: E402
from macro_compass.market import compute_market_metrics, load_market_config  # noqa: E402
from macro_compass.structural import (  # noqa: E402
    compute_structural_readings,
    load_structural_config,
)
from macro_compass.signals import (  # noqa: E402
    load_core_computations,
    load_signal_registry,
    resolve_signal_status,
)


# ---- Declared Source-Transition metadata (Task 4, owner-maintained) ---------
# For each series that has (or may later carry) a history+live splice. Rules:
#   - canonical_definition: what the series numerically means today.
#   - historical_source / live_source: the two legs. If both are the same
#     definition, a splice is acceptable; if not, comparable history is
#     shortened rather than fabricated.
#   - transition_date / overlap / unit / frequency / notes.
# These are DECLARED prior/records, not derived numbers - they are the
# human-maintained source-of-truth that the coverage matrix prints.
SOURCE_TRANSITIONS: dict[str, dict] = {
    "CN_TSF_TOTAL": {
        "canonical_definition": "Total TSF monthly flow (cumulative increment differenced)",
        "historical_source": "Wind one-shot backfill wind_backfill_tsf.csv (PENDING file)",
        "live_source": "PBOC monthly financial report (replace_window) / AKShare fallback",
        "transition_date": "TBD once backfill imported",
        "overlap": "TBD (overlap_check-style diff on shared months after import)",
        "unit": "CNY bn monthly flow",
        "frequency": "monthly",
        "notes": (
            "Same definition expected (both PBOC-sourced monthly flow), so a splice "
            "is acceptable AFTER cross-validation with the live leg; do NOT splice "
            "before overlap passes. Used by D2."
        ),
        "breakpoint": "none declared yet; validate before merging",
    },
    "CN_GOV_BOND_FINANCING": {
        "canonical_definition": "Government bond net financing monthly flow",
        "historical_source": "Wind one-shot backfill wind_backfill_tsf.csv (PENDING file)",
        "live_source": "PBOC monthly financial report (replace_window)",
        "transition_date": "TBD once backfill imported",
        "overlap": "TBD after import",
        "unit": "CNY bn monthly flow",
        "frequency": "monthly",
        "notes": "Used by D2 and D4. Validate overlap with live leg before merging.",
        "breakpoint": "none declared yet; validate before merging",
    },
    "US_REAL_YIELD_10Y": {
        "canonical_definition": "US 10Y real yield (Treasury Daily Par Real Yield Curve)",
        "historical_source": "FRED DFII10 (fallback; NOT merged - overlap BLOCKED by FRED network)",
        "live_source": "Treasury Daily Par Real Yield Curve (primary, v0.4c)",
        "transition_date": "not switching until overlap_check PASS (>=60 common days)",
        "overlap": "overlap_check.py BLOCKED (2026-08-30, FRED timeout)",
        "unit": "percent",
        "frequency": "daily",
        "notes": (
            "DFII10 IS a redistribution of the Treasury curve - same underlying "
            "data/definition. Merge gated on overlap_check PASS. Currently NO "
            "FRED rows in canonical; earlier history relies on eventual FRED reach."
        ),
        "breakpoint": "source-switch gate documented in data_sources.yaml",
    },
    "USD_BROAD": {
        "canonical_definition": "Fed broad trade-weighted USD index (Jan2006=100)",
        "historical_source": "FRED DTWEXBGS (network BLOCKED; only H.10 fallback live so far)",
        "live_source": "Fed H.10 weekly release page (fallback; only recent weeks)",
        "transition_date": "FRED restoration required to backfill longer history",
        "overlap": "n/a until FRED reachable",
        "unit": "index (Jan 2006 = 100)",
        "frequency": "daily",
        "notes": (
            "Same definition both legs. X2 stays WARMUP until history accumulates. "
            "FRED backfill is automatic on update - do NOT splice synthetic rows."
        ),
        "breakpoint": "none declared; explicit WARMUP blocker",
    },
    "CN_POLICY_RATE_7D": {
        "canonical_definition": "PBOC 7-day reverse-repo operation rate (step series)",
        "historical_source": "Committed step file data/manual_series/ (MANUAL provenance bootstrap)",
        "live_source": "PBOC OMO transaction announcement (replace_window)",
        "transition_date": "2024 (canonical history starts there)",
        "overlap": "same official announcements in both legs - low risk",
        "unit": "percent",
        "frequency": "daily (step)",
        "notes": "Both legs transcribed from the same official announcements - comparable by construction.",
        "breakpoint": "event/step series, flat between cuts (non-continuous but defined)",
    },
    "CN_CORE_CPI_YOY": {
        "canonical_definition": "Core CPI YoY (NBS, excludes food & energy)",
        "historical_source": "NBS CPI release historical (via update pipeline)",
        "live_source": "NBS official CPI release page (I1 preferred leg)",
        "transition_date": "n/a - same source/definition",
        "overlap": "n/a",
        "unit": "percent",
        "frequency": "monthly",
        "notes": "I1 preferred leg; headline CN_CPI_YOY is a declared FALLBACK only (never written into core id).",
        "breakpoint": "I1 fallback semantics fixed (core/headline kept as separate series_id)",
    },
    "G3": {
        "canonical_definition": "Hard activity composite (industrial output + retail, YoY %)",
        "historical_source": "OECD volume indices (declared fallback only post-switch)",
        "live_source": "NBS YoY growth (CN_IND_PROD_YOY / CN_RETAIL_SALES_YOY), v1.6A G0",
        "transition_date": "2026-08 (owner-approved G3 switch)",
        "overlap": "unit differs (index vs %) - NOT numerically continuous",
        "unit": "percent (live) / index (historical fallback)",
        "frequency": "monthly",
        "notes": (
            "Unit change index->% means pre/post are NOT numerically continuous; "
            "OECD entries kept ONLY as fallback when NBS legs are absent. Do NOT "
            "splice indices with growth percentages."
        ),
        "breakpoint": "declared breakpoint (signals.yaml G3 commentary)",
    },
}


# ---- Declared per-signal blockers (owner-maintained, honest) ----------------
BACKFILL_BLOCKERS: dict[str, str] = {
    "D2": "wind_backfill_tsf.csv NOT yet provided by user (P0-1) - WARMUP, no splice",
    "D4": "wind_backfill_tsf.csv NOT yet provided by user (P0-1) - WARMUP, no splice",
    "X1": "FRED DFII10 unreachable (overlap BLOCKED 2026-08-30) - no FRED rows merged yet",
    "X2": "FRED DTWEXBGS unreachable - only H.10 fallback weeks, history insufficient (WARMUP)",
    "S3": "Property Vulnerability proxy pool pending B-package research - NO_SIGNAL (honest, no fabricated proxy)",
}


def _refresh_usd_broad_state(canonical: pd.DataFrame) -> tuple[dict[str, dict], dict[str, str]]:
    """Derive USD_BROAD transition/blocker text from the current canonical.

    The matrix is a generated report, so a previous network failure must not
    remain visible after a later canonical import succeeds.  Keep the
    conservative readiness thresholds aligned with the market engine: 250
    observations and 120 months of history.  This helper only changes report
    metadata; it never writes or alters canonical data.
    """
    transitions = {key: dict(value) for key, value in SOURCE_TRANSITIONS.items()}
    blockers = dict(BACKFILL_BLOCKERS)
    rows = canonical[canonical["series_id"].eq("USD_BROAD")].copy() if (
        not canonical.empty and "series_id" in canonical.columns
    ) else pd.DataFrame()
    if rows.empty:
        return transitions, blockers

    dates = pd.to_datetime(rows["date"], errors="coerce").dropna()
    n = int(rows.loc[rows["value"].notna(), "date"].nunique())
    start = dates.min().date().isoformat() if not dates.empty else ""
    end = dates.max().date().isoformat() if not dates.empty else ""
    months = ((dates.max().year - dates.min().year) * 12
              + dates.max().month - dates.min().month + 1) if not dates.empty else 0
    ready = n >= 250 and months >= 120

    meta = transitions["USD_BROAD"]
    meta["historical_source"] = "FRED DTWEXBGS (canonical)"
    meta["live_source"] = "FRED DTWEXBGS / Fed H.10 fallback (route)"
    meta["transition_date"] = "n/a - canonical history is definition-equivalent"
    meta["overlap"] = "n/a - single canonical definition"
    meta["notes"] = (
        f"Canonical contains {n} observations from {start} through {end}. "
        "FRED DTWEXBGS and H.10 use the same Jan 2006=100 definition; no "
        "synthetic splice is permitted."
    )
    meta["breakpoint"] = "none declared"
    if ready:
        blockers.pop("X2", None)
    else:
        blockers["X2"] = (
            f"USD_BROAD canonical history has {n} observations over {months} months "
            "(<250 observations or <120 months) - WARMUP"
        )
    return transitions, blockers


_MODE_TO_RISK = {"full_refresh": "HIGH", "replace_window": "MEDIUM", "append": "LOW"}


@dataclass
class Row:
    signal_id: str
    layer: str
    name: str
    factor: str
    input_series: str
    role: str
    earliest_observation: str
    comparable_history_start: str
    minimum_validation_start: str
    current_source: str
    historical_source: str
    frequency: str
    revision_risk: str
    breakpoints: str
    status: str
    blocker: str = ""


def _series_source_label(routes, series_id: str) -> str:
    r = routes.series.get(series_id)
    if r is None:
        return "no-route"
    prim = str(r.primary or "")
    fb = str(r.fallback or "")
    return prim + (f"+{fb}" if fb else "")


def _series_frequency(routes, indicators, series_id: str) -> str:
    r = routes.series.get(series_id)
    if r is not None and getattr(r, "frequency", None):
        return str(r.frequency)
    ind = indicators.get(series_id)
    if ind is not None:
        f = (ind if isinstance(ind, dict) else getattr(ind, "frequency", None))
        if f:
            return str(f)
    return "n/a"


def _series_revision_risk(routes, series_id: str) -> str:
    r = routes.series.get(series_id)
    if r is None:
        return "n/a"
    up = getattr(r, "update_policy", None)
    mode = None
    if hasattr(up, "mode"):
        mode = up.mode
    elif isinstance(up, dict):
        mode = up.get("mode")
    if mode is None:
        return "n/a"
    return _MODE_TO_RISK.get(mode, "MEDIUM")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--today", default=None, help="reference date (ISO, default: today)")
    args = parser.parse_args()
    today = pd.Timestamp(args.today) if args.today else pd.Timestamp.today()

    indicators = load_indicator_config(paths.INDICATORS_YAML)
    registry = load_signal_registry(paths.SIGNALS_YAML, indicators_registry=indicators)
    macro_config = load_macro_config(paths.MACRO_YAML)
    market_config = load_market_config(paths.MARKET_YAML)
    structural_config = load_structural_config(paths.STRUCTURAL_YAML)
    sources_cfg = load_data_sources_config(paths.DATA_SOURCES_YAML, indicator_registry=indicators)

    snapshot = load_core_computations(
        registry, macro_config, allow_synthetic=False, today=today
    )
    market_metrics = compute_market_metrics(
        registry, market_config, snapshot.series, snapshot.today
    )
    structural_readings = compute_structural_readings(
        registry, structural_config, snapshot.series, snapshot.today
    )
    resolved = resolve_signal_status(
        registry, snapshot.availability, snapshot.computations,
        market_metrics, structural_readings,
    )
    transitions, blockers = _refresh_usd_broad_state(snapshot.canonical)

    rows: list[Row] = []
    for signal_id, spec in registry.signals.items():
        status = resolved.get(signal_id, "n/a")
        blocker = blockers.get(signal_id, "")
        comp = snapshot.computations.get(signal_id)
        sig_frame = comp.frame if comp is not None else None
        if sig_frame is not None and not sig_frame.empty:
            scored = sig_frame[sig_frame["score"].notna()]
            comparable_start = (
                str(pd.Timestamp(scored["date"].min()).date()) if not scored.empty else ""
            )
        else:
            comparable_start = ""
        # minimum_validation_start is PIT first stated computable day == comparable start
        min_val_start = comparable_start

        for inp in spec.inputs:
            sid = inp.series_id
            ser = snapshot.series.get(sid)
            earliest = (
                str(pd.Timestamp(ser.index.min()).date())
                if ser is not None and len(ser) else ""
            )
            hist = transitions.get(sid, {}).get("historical_source", "same as current / n/a")
            bp = transitions.get(sid, {}).get("breakpoint", "")
            rows.append(Row(
                signal_id=signal_id,
                layer=spec.layer,
                name=spec.name,
                factor=spec.factor or "-",
                input_series=sid,
                role=str(inp.role),
                earliest_observation=earliest,
                comparable_history_start=comparable_start,
                minimum_validation_start=min_val_start,
                current_source=_series_source_label(sources_cfg, sid),
                historical_source=hist,
                frequency=_series_frequency(sources_cfg, indicators, sid),
                revision_risk=_series_revision_risk(sources_cfg, sid),
                breakpoints=bp,
                status=status,
                blocker=blocker,
            ))

    # --- flatten ---
    df = pd.DataFrame([r.__dict__ for r in rows])
    paths.DATA_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = paths.DATA_DIR / "historical_coverage_matrix.csv"
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    print(f"Wrote {csv_path} ({len(df)} rows)")

    # --- markdown ---
    md = _render_markdown(df, today, transitions=transitions)
    docs_path = paths.PROJECT_ROOT / "docs" / "HISTORICAL_COVERAGE_MATRIX.md"
    docs_path.write_text(md, encoding="utf-8")
    print(f"Wrote {docs_path}")

    # short console summary
    for layer in ("core", "market", "structural"):
        sub = df[df["layer"] == layer]
        n = sub["status"].nunique()
        summary = "; ".join(f"{s}:{int((sub['status']==s).sum())}" for s in sorted(sub["status"].unique()))
        print(f"{layer}: {len(sub)} series rows | status distribution: {summary}")


def _render_markdown(
    df: pd.DataFrame, today: pd.Timestamp, *, transitions: dict[str, dict] | None = None
) -> str:
    transitions = transitions or SOURCE_TRANSITIONS
    lines: list[str] = []
    lines.append("# Historical Coverage Matrix (V4.5 Historical Completion)")
    lines.append("")
    lines.append(
        f"> Generated {today.date()} by `python scripts/historical_coverage.py` from live "
        "canonical data + declared source-transition metadata. Read-only: nothing modified, "
        "no weights/thresholds/signal declarations touched, no synthetic rows. "
        "Target: 2012-present (minimum priority 2015-present); never splice incomparable "
        "data to hit a date target."
    )
    lines.append("")
    lines.append("## Legend")
    lines.append("")
    lines.append("- **earliest_observation**: first real canonical observation for the input series.")
    lines.append("- **comparable_history_start / minimum_validation_start**: PIT first day the signal scored. "
                 "Comparable history is shortened rather than fabricated if a splice is not definition-equivalent.")
    lines.append("- **current_source**: route primary+fallback from data_sources.yaml.")
    lines.append("- **historical_source**: declared historical/backfill leg (Wind one-shot, FRED, etc.).")
    lines.append("- **revision_risk**: HIGH=full_refresh / MEDIUM=replace_window / LOW=append.")
    lines.append("- **breakpoints**: declared structural breaks.")
    lines.append("- **status**: shared resolved status (READY/WARMUP/PARTIAL/MISSING_INPUT).")
    lines.append("- **blocker**: declared honest blocker (empty = none).")
    lines.append("")

    order = {"core": 0, "market": 1, "structural": 2}
    for layer in ("core", "market", "structural"):
        sub = df[df["layer"] == layer]
        if sub.empty:
            continue
        lines.append(f"## {layer.title()} signals")
        lines.append("")
        show = sub[[
            "signal_id", "name", "input_series", "role", "earliest_observation",
            "current_source", "historical_source", "frequency", "revision_risk",
            "status", "comparable_history_start", "blocker",
        ]]
        lines.append(_dataframe_to_markdown(show))
        lines.append("")

    lines.append("## Source-Transition notes (Task 4)")
    lines.append("")
    for sid, meta in transitions.items():
        lines.append(f"### {sid}")
        lines.append("")
        for k, v in meta.items():
            lines.append(f"- **{k}**: {v}")
        lines.append("")

    lines.append("")
    lines.append("## Summary")
    lines.append("")
    core = df[df["layer"] == "core"]
    lines.append(
        f"- Core signals whose inputs are all live-and-comparable to 2012+: "
        f"see per-signal `comparable_history_start` above."
    )
    lines.append(
        "- Domestic target (>=3/4 READY) currently D1+D3 READY; D2/D4 held WARMUP "
        "until `wind_backfill_tsf.csv` is imported (no splice, no synthetic)."
    )
    x2 = df[df["signal_id"].eq("X2")]
    x2_status = x2["status"].iloc[0] if not x2.empty else "n/a"
    x2_blocker = x2["blocker"].iloc[0] if not x2.empty else ""
    x2_summary = f"X2 = {x2_status}" + (f" ({x2_blocker})" if x2_blocker else " (canonical history ready)")
    lines.append(f"- X1 overlap check remains governed by its own gate; {x2_summary}.")
    return "\n".join(lines)


def _dataframe_to_markdown(df: pd.DataFrame) -> str:
    """Render a dataframe as a Markdown table without requiring ``tabulate``.

    ``DataFrame.to_markdown`` is a convenience wrapper around the optional
    ``tabulate`` package.  This report is part of the normal local pipeline,
    so an optional presentation dependency must not prevent CSV/Markdown
    generation.  Keep the renderer deliberately small and deterministic: the
    report tables contain scalar values and do not need tabulate's alignment or
    numeric-formatting features.
    """
    columns = [str(column) for column in df.columns]

    def cell(value: object) -> str:
        if pd.isna(value):
            return ""
        # Markdown tables use | as a delimiter; preserve the value while
        # preventing a free-text field from creating additional columns.
        return str(value).replace("|", r"\|").replace("\r\n", "<br>").replace("\n", "<br>")

    header = "| " + " | ".join(cell(column) for column in columns) + " |"
    separator = "| " + " | ".join("---" for _ in columns) + " |"
    body = [
        "| " + " | ".join(cell(value) for value in row) + " |"
        for row in df.itertuples(index=False, name=None)
    ]
    return "\n".join([header, separator, *body])


if __name__ == "__main__":
    main()
