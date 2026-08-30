"""V3 Local Dashboard - read-only snapshot loader and validation helpers.

This is the ONLY data-access layer used by the Streamlit app. It reads:

* the snapshot CSVs already produced by the four report scripts
  (`macr_report / market_report / asset_report / structural_report`),
* the static config YAML (signals / indicators / data_sources / assets),

and rebuilds a small, display-ready model. It deliberately does NOT import any
engine module and never triggers an update or a recomputation: every value
shown by the dashboard comes from an already-written snapshot file.

The module is unit-testable without Streamlit (pure ``pandas`` / ``yaml``), so
the acceptance checks - as-of same-day alignment, no synthetic leakage, and the
no-buy/sell/position vocabulary rule - can be asserted in ``pytest``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd
import yaml

from macro_compass import paths

# Display names for the four MASTER SPEC core factors.
FACTOR_NAMES = {
    "growth": "增长",
    "inflation": "通胀",
    "domestic_financial": "国内金融",
    "global_financial": "全球金融",
}

# Red-line vocabulary: the dashboard must contain no buy/sell/position advice.
# Asset views are only 顺风 / 逆风 / 中性 and the panel names never advise a
# trade. Scanned over every display string produced by this module.
FORBIDDEN_VOCAB = (
    "BUY", "SELL", "LONG", "SHORT", "POSITION",
    "买入", "卖出", "加仓", "减仓", "做多", "做空", "看多", "看空",
    "仓位", "持仓", "交易信号", "止损", "止盈",
)

# Every snapshot that carries a shared reference day -> used for the as-of
# same-day alignment check. ``_resolve_override`` lets tests point these at
# tmp_path fixtures (data/local is git-ignored).
_SNAPSHOT_DATE_SOURCES: tuple[tuple[str, Path], ...] = (
    ("macro_raw", paths.MACRO_DASHBOARD_CSV),
    ("asset_signal", paths.ASSET_SIGNAL_CSV),
    ("market", paths.MARKET_CONFIRMATION_CSV),
    ("structural", paths.STRUCTURAL_RISK_CSV),
)


def _overridden(path: Path, key: str, paths_override: dict | None) -> Path:
    if paths_override and key in paths_override:
        return Path(paths_override[key])
    return path


def _read_csv(path: Path) -> pd.DataFrame:
    """Read a snapshot CSV (an empty frame if missing)."""
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


def _load_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    return data or {}


@dataclass
class DashboardState:
    """Display-ready model assembled purely from snapshots + static config."""

    snapshot_date: str = ""
    regime: str = ""
    regime_rationale: list[str] = field(default_factory=list)

    factors: list[dict] = field(default_factory=list)          # four factors
    signals: list[dict] = field(default_factory=list)          # 15 core latest
    market: list[dict] = field(default_factory=list)           # 6 market signals
    assets: list[dict] = field(default_factory=list)           # asset overview rows
    asset_factors: dict[str, list[dict]] = field(default_factory=dict)
    asset_signals: dict[str, list[dict]] = field(default_factory=dict)
    structural: list[dict] = field(default_factory=list)       # S1/S2/S3

    series_meta: dict[str, dict] = field(default_factory=dict)  # series -> metadata
    signal_meta: dict[str, dict] = field(default_factory=dict)  # signal -> metadata


def _build_series_and_signal_meta(config_dir: Path) -> tuple[dict, dict]:
    indicators = _load_yaml(config_dir / "indicators.yaml").get("indicators", {})
    if not indicators:
        # indicators.yaml is a flat mapping series_id -> metadata.
        indicators = _load_yaml(config_dir / "indicators.yaml")

    routes = _load_yaml(config_dir / "data_sources.yaml").get("series", {})
    signals_cfg = _load_yaml(config_dir / "signals.yaml").get("signals", {})

    def _provider_default(r: dict) -> str:
        return str(r.get("fallback") or r.get("primary") or "n/a")

    series_meta: dict[str, dict] = {}
    for series_id, meta in (indicators or {}).items():
        if not isinstance(meta, dict):
            continue
        route = routes.get(series_id, {})
        provider = route.get("primary") or _provider_default(route)
        series_meta[series_id] = {
            "name": meta.get("name", series_id),
            "unit": meta.get("unit", ""),
            "frequency": meta.get("frequency", ""),
            "provider": str(provider),
            "fallback": str(route.get("fallback") or ""),
            "original_source": str(route.get("original_source") or ""),
        }

    signal_meta: dict[str, dict] = {}
    for signal_id, spec in (signals_cfg or {}).items():
        if not isinstance(spec, dict):
            continue
        signal_meta[signal_id] = {
            "name": spec.get("name", signal_id),
            "factor": spec.get("factor", ""),
            "layer": spec.get("layer", ""),
            "mechanism": (spec.get("mechanism") or "").strip(),
        }
    return series_meta, signal_meta


def load_dashboard(config_dir: Path | None = None, paths_override: dict | None = None) -> DashboardState:
    """Assemble the dashboard state from the on-disk snapshots and config.

    ``paths_override`` maps snapshot keys (macro_dashboard / macro_factors /
    market / asset / asset_signal / structural and optionally ``config_dir``)
    to alternate paths - used by tests to point at tmp_path fixtures.

    Raises FileNotFoundError if the required snapshots are absent - the
    operator must run the four report scripts (with the same ``--today``) first.
    """
    if config_dir is None and paths_override and "config_dir" in paths_override:
        config_dir = Path(paths_override["config_dir"])
    config_dir = Path(config_dir) if config_dir else paths.CONFIG_DIR

    p_macro_dash = _overridden(paths.MACRO_DASHBOARD_CSV, "macro_dashboard", paths_override)
    p_macro_factors = _overridden(paths.MACRO_FACTORS_CSV, "macro_factors", paths_override)
    p_market = _overridden(paths.MARKET_CONFIRMATION_CSV, "market", paths_override)
    p_asset = _overridden(paths.ASSET_SCORES_CSV, "asset", paths_override)
    p_asset_sig = _overridden(paths.ASSET_SIGNAL_CSV, "asset_signal", paths_override)
    p_struct = _overridden(paths.STRUCTURAL_RISK_CSV, "structural", paths_override)

    macro_raw = _read_csv(p_macro_dash)
    factor_raw = _read_csv(p_macro_factors)
    market_raw = _read_csv(p_market)
    asset_raw = _read_csv(p_asset)
    asset_sig_raw = _read_csv(p_asset_sig)
    struct_raw = _read_csv(p_struct)

    missing = [name for name, path in (
        ("宏观快照", p_macro_dash),
        ("因子/Regime", p_macro_factors),
        ("市场确认", p_market),
        ("资产分数", p_asset),
        ("资产信号追踪", p_asset_sig),
        ("结构风险", p_struct),
    ) if not path.exists()]
    if missing:
        raise FileNotFoundError(
            "Dashboard needs the report snapshots first. Missing: "
            + ", ".join(missing)
            + ".\nRun: python scripts/macro_report.py; market_report.py; "
            "asset_report.py; structural_report.py (same --today for aligned as-of)."
        )

    series_meta, signal_meta = _build_series_and_signal_meta(config_dir)

    # ---- reference snapshot day: shared across the four report runs ----
    snapshot_date = ""
    if not macro_raw.empty:
        snapshot_date = str(macro_raw["snapshot_date"].iloc[-1])

    # ---- factors + regime ----
    factors = []
    regime_rationale: list[str] = []
    regime = ""
    if not factor_raw.empty:
        for _, row in factor_raw.iterrows():
            if row["kind"] == "regime":
                regime = str(row["confidence_composite"] or "")
                rationale = str(row["breadth_detail"] or "")
                regime_rationale = [line for line in rationale.splitlines() if line.strip()]
            else:
                factors.append(_row_to_plain(row))

    # ---- signals (15 core latest) ----
    signals = [_row_to_plain(r) for _, r in macro_raw.iterrows()]

    # ---- market ----
    market = [_row_to_plain(r) for _, r in market_raw.iterrows()]

    # ---- structural ----
    structural = [_row_to_plain(r) for _, r in struct_raw.iterrows()]

    # ---- assets: one overview row per asset + factor rows ----
    assets: list[dict] = []
    asset_factors: dict[str, list[dict]] = {}
    if not asset_raw.empty:
        overview_cols = [
            "asset", "asset_name", "status", "score", "view",
            "change_1m", "change_3m", "market_signal", "market_state",
            "market_status", "market_agreement",
            "confidence_coverage", "confidence_freshness",
            "confidence_source_quality", "confidence_composite", "as_of",
        ]
        for asset_id, group in asset_raw.groupby("asset", sort=False):
            first = group.iloc[0]
            row = {col: first.get(col) for col in overview_cols if col in first}
            asset_factors[asset_id] = [
                _row_to_plain(r) for _, r in group.iterrows()
            ]
            assets.append(row)

    # ---- asset -> signal trace (empty dict if a previous run left none) ----
    asset_signals: dict[str, list[dict]] = {}
    if not asset_sig_raw.empty:
        for asset_id, group in asset_sig_raw.groupby("asset", sort=False):
            asset_signals[asset_id] = [
                _row_to_plain(r) for _, r in group.iterrows()
            ]

    return DashboardState(
        snapshot_date=snapshot_date,
        regime=regime,
        regime_rationale=regime_rationale,
        factors=factors,
        signals=signals,
        market=market,
        assets=assets,
        asset_factors=asset_factors,
        asset_signals=asset_signals,
        structural=structural,
        series_meta=series_meta,
        signal_meta=signal_meta,
    )


def _row_to_plain(row: pd.Series) -> dict:
    """Convert a pandas row to a plain dict with json-ish scalar handling."""
    out = {}
    for key, value in row.items():
        if pd.isna(value):
            out[key] = None
        elif hasattr(value, "item"):
            out[key] = value.item()
        else:
            out[key] = value
    return out


# --------------------------------------------------------------------------
# Validation helpers (pure, unit-tested)
# --------------------------------------------------------------------------

def same_day_alignment(
    state: DashboardState,
    snapshot_sources: tuple[tuple[str, Path], ...] | None = None,
) -> tuple[bool, list[str], set[str]]:
    """Return (aligned, gaps, distinct_snapshot_dates).

    ``aligned`` is True only when every snapshot that records a reference
    snapshot day shares the same value (i.e. all four reports were generated in
    the same run / same ``--today``). Snapshot files with no recorded date are
    reported as gaps, never silently ignored. ``snapshot_sources`` may point at
    tmp fixtures in tests.
    """
    sources = snapshot_sources or _SNAPSHOT_DATE_SOURCES
    dates: set[str] = set()
    gaps: list[str] = []
    for name, path in sources:
        col = pd.Series(dtype=str)
        if path.exists():
            col = pd.read_csv(path, nrows=1).get("snapshot_date", pd.Series(dtype=str))
        if col is None or col.empty or not str(col.iloc[0]).strip():
            gaps.append(name)
        else:
            dates.add(str(col.iloc[0]).strip())
    aligned = (len(dates) == 1) and not gaps
    return aligned, gaps, dates


def synthetic_rows(state: DashboardState) -> list[str]:
    """Signal ids whose displayed data is not real (synthetic / mixed / unknown).

    Production runs exclude synthetic rows, so this is normally empty; the app
    still renders a visible marker (never silently real) whenever it is not.
    """
    leaked: list[str] = []
    for sig in state.signals:
        prov = str(sig.get("provenance") or "").lower()
        if sig.get("score") is not None and prov not in ("real",):
            leaked.append(str(sig.get("signal_id")))
    return leaked


def forbidden_words(state: DashboardState) -> list[str]:
    """Display strings that contain red-line buy/sell/position vocabulary."""
    hits: list[str] = []
    candidates: list[str] = []
    for sig in state.signals:
        candidates.append(str(sig.get("name") or ""))
    for a in state.assets:
        candidates.append(str(a.get("asset_name") or ""))
        candidates.append(str(a.get("view") or ""))
    for m in state.market:
        candidates.append(str(m.get("signal_name") or ""))
        candidates.append(str(m.get("state") or ""))
    for s in state.structural:
        candidates.append(str(s.get("signal_name") or ""))
        candidates.append(str(s.get("diagnostic") or ""))
    candidates.append(state.regime)
    for c in candidates:
        upper = c.upper()
        for word in FORBIDDEN_VOCAB:
            if word in upper:
                hits.append(c)
                break
    return hits


def asset_chain(state: DashboardState, asset_id: str) -> list[str]:
    """Return the full Asset -> Factor -> Signal -> series/provider trace as a
    flat list of trace strings, proving every asset display is traceable."""
    traces: list[str] = []
    for row in state.asset_signals.get(asset_id, []):
        trace = (
            f"{asset_id} -> {row.get('factor')} -> {row.get('signal_id')} -> "
            f"{row.get('series_source')}"
        )
        traces.append(trace)
    return traces