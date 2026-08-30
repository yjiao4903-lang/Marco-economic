"""Historical score reconstruction + forward-return proxies (V2.5).

V2.5 reads the V2 Asset Composer's *outputs* - the frozen ``macro.factors``
and ``assets.engine`` - and never modifies them. Everything here is a pure,
read-only consumer:

* ``build_factor_panel`` reconstructs each core factor's point-in-time (PIT)
  score on a monthly grid by truncating the already-computed signal frames to
  each date and re-aggregating through the frozen ``compute_factor``. This is
  PIT-correct because every declared transform step is backward-looking
  (rolling windows / yoy / deltas; no centred statistics) - the value at date
  ``t`` uses only observations <= ``t``, so truncation reveals the score as it
  stood then. It is exactly the method the frozen asset engine already uses
  for its own 1M/3M change (``assets/engine._factor_scores_at``).
* ``build_asset_panel`` turns the factor scores into per-asset scores using the
  declared (frozen) prior betas and their L1 normalisation - the same formula
  as ``assets.engine.compute_asset``. Per-date factor coverage is retained so
  the reader always sees *which* factors were scored on each date.
* ``forward_returns`` builds a per-asset return proxy from the canonical market
  series and computes forward total/price returns (1M / 3M horizons) aligned to
  each scoring date. Return proxies are EXPLICITLY approximations - noted per
  asset - and never synthetic.

No file under this module is imported by production Asset/Macro/Market code, and
nothing here writes to canonical. Outputs are plain DataFrames.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Optional

import pandas as pd

from macro_compass.macro.config import CORE_FACTORS
from macro_compass.macro.factors import compute_factor

# Return-proxy kind per market series: how a move maps to an asset return.
#   price  - pct_change of an index/FX/commodity
#   yield  - -(modified_duration / 100) * delta(yield)  (bond price proxy)
#   spread - -(modified_duration / 100) * delta(spread) (credit proxy, weak)
#   gold   - pct_change of the (sparse) spot series
# The kind + declared duration are set per asset, never fitted (MASTER SPEC 2).
RETURN_PROXY: dict[str, dict] = {
    "CN_EQUITY": {"series": "CSI300", "kind": "price", "note": "CSI300 index"},
    "HK_EQUITY": {"series": "HSI", "kind": "price", "note": "HSI PRICE index (no total return)"},
    "CN_GOV_BOND": {
        "series": "CN_GOV_YIELD_10Y", "kind": "yield", "mod_duration": 8.0,
        "note": "10Y CGB yield; price proxy = -ModDur*dyield (8y)",
    },
    "CN_CREDIT": {
        "series": "CN_AAA_CREDIT_SPREAD", "kind": "spread", "mod_duration": 3.5,
        "note": "AAA 3Y spread; return proxy = -ModDur*dspread (no benchmark yield; weak)",
    },
    "GOLD": {"series": "GOLD", "kind": "gold", "note": "spot gold, sparse history"},
    "INDUSTRIAL_COMMODITY": {
        "series": "COPPER_PRICE", "kind": "price",
        "note": "LME 3M copper (USD net price; FX embedded)",
    },
    "CNY": {"series": "USD_CNY", "kind": "price", "sign": -1, "note": "CNY apprec = -USDCNY ret"},
}

# Forward horizons in BUSINESS days, aligned with the frozen market windows.
FORWARD_WINDOWS = {"1m": 22, "3m": 63}

# Declared sanity bar below which we refuse a directional conclusion
# (task 60 / spec 47 section 31: ideal 2012-present, min 2015-present).
MIN_N_FOR_DIRECTIONAL = 60


def factor_scores_on_grid(
    computations: Mapping[str, object],
    factor_signal_ids: Mapping[str, list[str]],
    macro_config: Mapping,
    staleness: Mapping[str, int],
    grid: pd.DatetimeIndex,
) -> pd.DataFrame:
    """PIT factor-score panel over an explicit ``grid`` (month-ends usually).
    ``factor_signal_ids`` may be reduced (LOMO) - handled identity is allowed."""
    from dataclasses import replace

    rows = []
    for d in grid:
        truncated = {}
        for sid, comp in computations.items():
            frame = comp.frame
            if not frame.empty:
                frame = frame[frame["date"] <= d]
            truncated[sid] = replace(comp, frame=frame)
        row = {"date": d}
        for f in factor_signal_ids:
            if not factor_signal_ids[f]:
                row[f] = None
                continue
            row[f] = compute_factor(
                f, factor_signal_ids[f], truncated, macro_config, staleness, d
            ).score
        rows.append(row)
    return pd.DataFrame(rows).set_index("date")


def build_factor_panel(
    computations: Mapping[str, object],
    factor_signal_ids: Mapping[str, list[str]],
    macro_config: Mapping,
    staleness: Mapping[str, int],
    today: pd.Timestamp,
    grid_start: str = "2006-01-01",
) -> pd.DataFrame:
    """Monthly PIT factor-score panel: index=month-end dates, cols=factors.

    A ``NaN`` at a (date, factor) cell means that factor had no computable
    signal on that date (insufficient / misaligned history, never zero-filled).
    """
    today = pd.Timestamp(today)
    grid = pd.date_range(grid_start, today, freq="MS") + pd.offsets.MonthEnd(0)
    return factor_scores_on_grid(
        computations, factor_signal_ids, macro_config, staleness, grid
    )


def _normalize_betas(asset_cfg: Mapping) -> dict[str, float]:
    beta = {f: float(asset_cfg["factors"][f]["beta"]) for f in CORE_FACTORS}
    total = sum(abs(b) for b in beta.values())
    if total <= 0:
        return {f: 0.0 for f in CORE_FACTORS}
    return {f: beta[f] / total for f in CORE_FACTORS}


def build_asset_panel(
    assets_config: Mapping,
    factor_panel: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Per-asset PIT scores + per-date factor-coverage (fraction of the asset's
    non-zero-beta factors that were scored).

    ``scores`` has cols = asset ids; ``coverage`` has cols = asset ids with a
    value in [0,1] = share of the asset's |norm beta| that was scored that date.
    A score is emitted whenever >=1 of the asset's non-zero-beta factors scored
    (faithful to ``assets.engine.compute_asset`` with ``min_scored_factors=1``).
    """
    scores, coverage = {}, {}
    for asset_id, asset_cfg in assets_config["assets"].items():
        norm = _normalize_betas(asset_cfg)
        used = {f for f in CORE_FACTORS if abs(norm[f]) > 0}
        denom = sum(abs(norm[f]) for f in used) if used else 1.0
        s = pd.Series(index=factor_panel.index, dtype=float)
        c = pd.Series(index=factor_panel.index, dtype=float)
        for d, r in factor_panel.iterrows():
            scored = {f for f in used if pd.notna(r[f])}
            if not scored:
                s[d] = None
                c[d] = 0.0
            else:
                s[d] = float(sum(norm[f] * r[f] for f in scored))
                c[d] = sum(abs(norm[f]) for f in scored) / denom
        scores[asset_id] = s
        coverage[asset_id] = c
    return pd.DataFrame(scores), pd.DataFrame(coverage)


def build_return_proxies(
    series: Mapping[str, pd.Series],
    assets_config: Mapping,
) -> dict[str, tuple[str, str, pd.Series]]:
    """Per-asset daily return-basis series (proxy kind -> series). No data is
    synthesised: assets whose market series is missing yield an empty basis."""
    out: dict[str, tuple[str, str, pd.Series]] = {}
    for asset_id in assets_config["assets"]:
        spec = RETURN_PROXY.get(asset_id)
        if not spec:
            continue
        sid = spec["series"]
        if sid not in series:
            out[asset_id] = (spec["kind"], spec["note"], pd.Series(dtype=float))
            continue
        raw = series[sid].dropna().sort_index()
        out[asset_id] = (spec["kind"], spec["note"], raw)
    return out


def _basis_to_daily_return(basis: pd.Series, kind: str, mod_duration: float, sign: int) -> pd.Series:
    """1-step daily 'return' proxy series. For price/gold it is the log move;
    for yield/spread it is -(ModDur/100)*delta."""
    if kind == "price":
        r = basis.pct_change()
    elif kind == "gold":
        r = basis.pct_change()
    elif kind == "yield":
        r = -(mod_duration / 100.0) * basis.diff()
    elif kind == "spread":
        r = -(mod_duration / 100.0) * basis.diff()
    else:  # pragma: no cover - defensive
        r = basis.pct_change()
    return (sign * r).rename("ret")


def forward_return_at(
    daily_ret: pd.Series,
    d: pd.Timestamp,
    horizon_bdays: int,
) -> Optional[float]:
    """Cumulative (sum) 1-step return-proxy over ``horizon_bdays`` trading days
    starting at ``d``. ``None`` when either endpoint is unavailable."""
    idx = daily_ret.dropna().index
    pos_start = idx.searchsorted(d, side="left")
    if pos_start >= len(idx):
        return None
    poss = idx.values
    start_idx = poss[pos_start]
    j = pos_start
    # walk forward horizon_bdays distinct observations
    j_end = pos_start + horizon_bdays
    if j_end > len(idx) - 1:
        return None
    return float(daily_ret.iloc[pos_start + 1: j_end + 1].sum())


def build_forward_returns(
    scores: pd.DataFrame,
    return_proxies: dict[str, tuple[str, str, pd.Series]],
    windows: Optional[Mapping[str, int]] = None,
) -> dict[str, pd.DataFrame]:
    """Per asset: DataFrame indexed by scoring date with one fwd-return column
    per horizon (1m / 3m). Alignment: forward return is attributed to the score
    at its START date."""
    windows = windows or FORWARD_WINDOWS
    out: dict[str, pd.DataFrame] = {}
    for asset_id in scores.columns:
        if asset_id not in return_proxies:
            out[asset_id] = pd.DataFrame(index=scores.index)
            continue
        kind, note, basis = return_proxies[asset_id]
        if basis.empty:
            out[asset_id] = pd.DataFrame(index=scores.index)
            continue
        spec = RETURN_PROXY[asset_id]
        mod_dur = float(spec.get("mod_duration", 0.0))
        sign = int(spec.get("sign", 1))
        daily = _basis_to_daily_return(basis, kind, mod_dur, sign)
        cols = {}
        for hname, hb in windows.items():
            cols[f"fwd_{hname}"] = pd.Series(
                {d: forward_return_at(daily, d, int(hb)) for d in scores.index},
                dtype="float64",
            )
        out[asset_id] = pd.DataFrame(cols, index=scores.index)
    return out


@dataclass
class ValidationSample:
    """Everything a method needs, keyed by asset and pre-aligned by start date."""

    factor_panel: pd.DataFrame
    asset_scores: pd.DataFrame          # index=date, cols=asset
    asset_coverage: pd.DataFrame
    forward_returns: dict[str, pd.DataFrame]  # asset -> {fwd_1m, fwd_3m}
    series: Mapping[str, pd.Series] = None     # raw canonical (real-only) series


def assemble(
    computations,
    factor_signal_ids,
    macro_config,
    staleness,
    assets_config,
    series,
    today,
    **kw,
) -> ValidationSample:
    """Convenience: build the full PIT sample in one call (used by the report).
    ``allow_synthetic`` is deliberately NOT accepted here - synthetic rows never
    enter a validation sample (task 60 section 6)."""
    fp = build_factor_panel(computations, factor_signal_ids, macro_config, staleness, today)
    scores, cov = build_asset_panel(assets_config, fp)
    proxies = build_return_proxies(series, assets_config)
    fwd = build_forward_returns(scores, proxies)
    return ValidationSample(fp, scores, cov, fwd, series=series)


def mechanism_scored_share(
    computations: Mapping[str, object],
    grid: pd.DatetimeIndex,
) -> dict[str, float]:
    """Share of ``grid`` dates on which each signal produced a PIT score
    (its own compatible-history presence). Used to stop LOMO flagging a
    mechanism as low-increment when it simply arrived late."""
    out = {}
    for sid, comp in computations.items():
        frame = comp.frame
        if frame is None or frame.empty:
            out[sid] = 0.0
            continue
        scored_dates = set(pd.DatetimeIndex(frame.loc[frame["score"].notna(), "date"]))
        out[sid] = sum(1 for d in grid if d in scored_dates) / max(1, len(grid))
    return out


def aligned(asset_id: str, horizon: str, sample: ValidationSample, min_coverage: float = 0.5):
    """Rows (score, forward_return) for one asset/horizon where the fwd return
    exists and the score's factor coverage clears ``min_coverage``."""
    s = sample.asset_scores[asset_id].dropna()
    fdf = sample.forward_returns.get(asset_id)
    col = f"fwd_{horizon}"
    if fdf is None or col not in fdf:
        return pd.DataFrame(columns=["score", "fwd"])
    fwd = fdf[col]
    cov = sample.asset_coverage[asset_id]
    rows = []
    for d in s.index:
        v = fwd.get(d)
        if pd.isna(v) or pd.isna(s[d]):
            continue
        if cov.get(d, 0.0) < min_coverage:
            continue
        rows.append({"date": d, "score": float(s[d]), "fwd": float(v)})
    return pd.DataFrame(rows).set_index("date") if rows else pd.DataFrame(columns=["score", "fwd"])