"""Incremental multi-source update engine (V1.2).

For every enabled series in data_sources.yaml the updater walks the provider
chain (primary -> fallback), merges freshly fetched rows into the canonical
parquet (latest import wins, so overlaps never duplicate data), records the
fetch state per series, and emits:

    data/local/data_status.csv             - per-series status report
    data/local/manual_fetch_required.csv   - series needing manual action

Failure isolation: any exception inside one series' update is caught and
converted into a FAILED outcome; the remaining series keep updating.

Canonical metadata (series_name / unit / frequency / category) comes from
``config/indicators.yaml`` - the single source of truth. Adapters only
produce (series_id, date, value) plus source provenance.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from macro_compass import paths
from macro_compass.config import IndicatorConfig, load_indicator_config
from macro_compass.data_sources.base import (
    DataSourceError,
    FetchStatus,
    ManualFetchRequired,
    ProviderUnavailable,
)
from macro_compass.data_sources.registry import AdapterRegistry, DataSourcesConfig, load_data_sources_config
from macro_compass.ingestion.validator import validate_canonical
from macro_compass.logging import get_logger
from macro_compass.storage.canonical_store import (
    append_canonical,
    replace_series,
    replace_window,
)
from macro_compass.storage.duckdb_store import DuckDBStore

logger = get_logger(__name__)

STATE_KEYS = ("last_observation_date", "last_successful_fetch", "last_provider", "fetch_status")

STATUS_CSV_COLUMNS = [
    "series_id",
    "series_name",
    "fetch_status",
    "provider_used",
    "last_observation_date",
    "last_successful_fetch",
    "rows_fetched",
    "stale_days",
    "max_staleness_days",
    "message",
]
MANUAL_CSV_COLUMNS = ["series_id", "series_name", "fetch_status", "message"]


@dataclass
class FetchOutcome:
    series_id: str
    series_name: str
    status: str
    provider_used: str = ""
    rows_fetched: int = 0
    last_observation_date: str | None = None
    last_successful_fetch: str | None = None
    stale_days: int | None = None
    max_staleness_days: int | None = None
    message: str = ""
    frame: pd.DataFrame | None = None  # enriched canonical rows (success only)


@dataclass
class UpdateReport:
    outcomes: list[FetchOutcome] = field(default_factory=list)
    dry_run: bool = False

    @property
    def ok(self) -> bool:
        return all(o.status not in (FetchStatus.FAILED.value,) for o in self.outcomes)

    def summary(self) -> str:
        lines = [f"Update {'(dry run)' if self.dry_run else ''}: {len(self.outcomes)} series"]
        for o in self.outcomes:
            lines.append(
                f"  [{o.status:>15}] {o.series_id} ({o.provider_used or '-'}): "
                f"rows={o.rows_fetched} last={o.last_observation_date or '-'} "
                f"{('- ' + o.message) if o.message else ''}"
            )
        return "\n".join(lines)

    def to_status_frame(self) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "series_id": o.series_id,
                    "series_name": o.series_name,
                    "fetch_status": o.status,
                    "provider_used": o.provider_used,
                    "last_observation_date": o.last_observation_date or "",
                    "last_successful_fetch": o.last_successful_fetch or "",
                    "rows_fetched": o.rows_fetched,
                    "stale_days": o.stale_days if o.stale_days is not None else "",
                    "max_staleness_days": o.max_staleness_days if o.max_staleness_days is not None else "",
                    "message": o.message,
                }
                for o in self.outcomes
            ],
            columns=STATUS_CSV_COLUMNS,
        )

    def to_manual_frame(self) -> pd.DataFrame:
        rows = [
            {
                "series_id": o.series_id,
                "series_name": o.series_name,
                "fetch_status": o.status,
                "message": o.message,
            }
            for o in self.outcomes
            if o.status in (FetchStatus.MANUAL_REQUIRED.value, FetchStatus.FAILED.value)
        ]
        return pd.DataFrame(rows, columns=MANUAL_CSV_COLUMNS)


def load_fetch_state(path: Path | None = None) -> dict:
    path = Path(path) if path else paths.FETCH_STATE_PATH
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except (json.JSONDecodeError, OSError):
        logger.warning("fetch state file unreadable, starting fresh: %s", path)
        return {}


def save_fetch_state(state: dict, path: Path | None = None) -> None:
    path = Path(path) if path else paths.FETCH_STATE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(state, fh, ensure_ascii=False, indent=2, sort_keys=True)


def _incremental_start(series_id: str, state: dict, overlap_days: int):
    """New-fetch window start: last observation minus a revision overlap."""
    if series_id not in state:
        return None
    last_obs = state[series_id].get("last_observation_date")
    if not last_obs:
        return None
    return pd.Timestamp(last_obs) - pd.Timedelta(days=overlap_days)


def _enrich_with_indicator_metadata(
    frame: pd.DataFrame, series_id: str, indicators: dict[str, IndicatorConfig]
) -> pd.DataFrame:
    cfg = indicators.get(series_id)
    if cfg is None or frame.empty:
        return frame
    frame = frame.copy()
    frame["series_name"] = cfg.name
    frame["unit"] = cfg.unit
    frame["frequency"] = cfg.frequency
    frame["category"] = cfg.category
    return frame


def _save_vintage_snapshot(frame: pd.DataFrame, series_id: str, provider: str) -> Path:
    """Persist the raw fetched frame as a vintage snapshot (V1.2C section 11).

    Snapshots accumulate under data/local/vintage/<series_id>/ so revised
    sources (GSCPI, OECD) build up a local vintage history; the canonical
    store keeps only the latest values.
    """
    stamp = pd.Timestamp.now().strftime("%Y%m%dT%H%M%S")
    directory = paths.VINTAGE_DIR / series_id
    directory.mkdir(parents=True, exist_ok=True)
    snapshot = frame.copy()
    snapshot["asof_date"] = pd.Timestamp.now().date()
    snapshot["fetched_provider"] = provider.upper()
    target = directory / f"{stamp}.parquet"
    snapshot.to_parquet(target, index=False)
    return target


def _record_success(state: dict, outcome: FetchOutcome, now: pd.Timestamp) -> None:
    state[outcome.series_id] = {
        "last_observation_date": outcome.last_observation_date,
        "last_successful_fetch": outcome.last_successful_fetch,
        "last_provider": outcome.provider_used,
        "fetch_status": outcome.status,
    }


def _record_failure(state: dict, series_id: str, status: str) -> None:
    entry = state.setdefault(series_id, {})
    entry["fetch_status"] = status


def update_series(
    series_id: str,
    config: DataSourcesConfig,
    indicators: dict[str, IndicatorConfig],
    adapters: AdapterRegistry,
    state: dict,
    *,
    dry_run: bool = False,
    backfill: bool = False,
) -> FetchOutcome:
    """Update one series through its provider chain. Never raises."""
    spec = config.series[series_id]
    indicator_cfg = indicators.get(series_id)
    outcome = FetchOutcome(
        series_id=series_id,
        series_name=indicator_cfg.name if indicator_cfg else series_id,
        status=FetchStatus.FAILED.value,
        max_staleness_days=spec.max_staleness_days,
    )

    start_date = None
    if not backfill:
        start_date = _incremental_start(series_id, state, config.overlap_days)

    fetched_frame = None
    provider_used = ""
    errors: list[str] = []
    manual_only = True

    for provider_id in config.chain_for(series_id):
        provider_spec = config.providers[provider_id]
        if not provider_spec.enabled:
            errors.append(f"{provider_id}: provider disabled")
            continue
        attempts = 2  # one immediate retry: several endpoints (FRED, NBS)
        for attempt in range(1, attempts + 1):  # fail intermittently
            try:
                frame = adapters.get(provider_id).fetch(
                    series_id, start_date=start_date, end_date=None
                )
                fetched_frame = frame
                provider_used = provider_id
                break
            except ManualFetchRequired as exc:
                errors.append(f"{provider_id}: {exc}")
                break
            except ProviderUnavailable as exc:
                errors.append(f"{provider_id}: {exc}")
                break
            except DataSourceError as exc:
                errors.append(f"{provider_id}: {exc}")
                manual_only = False
            except Exception as exc:  # failure isolation inside the chain, too
                errors.append(f"{provider_id}: unexpected {type(exc).__name__}: {exc}")
                manual_only = False
            if attempt < attempts:
                time.sleep(5)  # backoff, then retry the same provider
        if fetched_frame is not None:
            break

    if fetched_frame is None:
        outcome.status = (
            FetchStatus.MANUAL_REQUIRED.value if manual_only
            else FetchStatus.FAILED.value
        )
        outcome.message = " | ".join(errors) or "no provider attempted"
        _record_failure(state, series_id, outcome.status)
        return outcome

    frame = _enrich_with_indicator_metadata(fetched_frame, series_id, indicators)
    validation = validate_canonical(frame, indicators)
    if not validation.passed:
        outcome.status = FetchStatus.FAILED.value
        outcome.rows_fetched = len(frame)
        outcome.provider_used = provider_used
        outcome.message = "validation failed: " + "; ".join(validation.errors)
        _record_failure(state, series_id, FetchStatus.FAILED.value)
        return outcome

    last_obs = max(frame["date"])
    now = pd.Timestamp.now()
    stale_days = int((now.normalize() - pd.Timestamp(last_obs)).days)
    used_fallback = provider_id == spec.fallback and spec.fallback is not None

    status = FetchStatus.FALLBACK_USED if used_fallback else FetchStatus.OK
    if stale_days > spec.max_staleness_days:
        status = FetchStatus.STALE

    if not dry_run:
        policy = spec.update_policy.mode
        if policy == "full_refresh":
            _save_vintage_snapshot(frame, series_id, provider_used)
            replace_series(frame)
        elif policy == "replace_window":
            replace_window(frame)
        else:
            append_canonical(frame)

    outcome.status = status.value
    outcome.provider_used = provider_used
    outcome.rows_fetched = len(frame)
    outcome.last_observation_date = pd.Timestamp(last_obs).date().isoformat()
    outcome.last_successful_fetch = now.isoformat(timespec="seconds")
    outcome.stale_days = stale_days
    policy = spec.update_policy.mode
    outcome.message = "; ".join(
        ([f"policy={policy}"] if policy != "append" else []) + list(validation.warnings)
    )
    outcome.frame = frame
    _record_success(state, outcome, now)
    return outcome


def run_update(
    series_ids: list[str] | None = None,
    *,
    dry_run: bool = False,
    backfill: bool = False,
    indicators_path=None,
    config_path=None,
    state_path: Path | None = None,
) -> UpdateReport:
    """Run a full (or subset) multi-source update and write status outputs."""
    indicators = load_indicator_config(indicators_path or paths.INDICATORS_YAML)
    config = load_data_sources_config(config_path or paths.DATA_SOURCES_YAML, indicators)
    adapters = AdapterRegistry(config)
    state = load_fetch_state(state_path)

    requested = series_ids if series_ids else adapters.enabled_series()
    unknown = [sid for sid in requested if sid not in config.series]
    if unknown:
        raise ValueError(f"unknown series id(s) in data_sources.yaml: {unknown}")

    report = UpdateReport(dry_run=dry_run)
    written_frames: list[pd.DataFrame] = []

    for series_id in requested:
        try:
            outcome = update_series(
                series_id,
                config,
                indicators,
                adapters,
                state,
                dry_run=dry_run,
                backfill=backfill,
            )
        except Exception as exc:  # failure isolation across series
            logger.exception("unexpected error updating %s", series_id)
            cfg = config.series[series_id]
            indicator_cfg = indicators.get(series_id)
            outcome = FetchOutcome(
                series_id=series_id,
                series_name=indicator_cfg.name if indicator_cfg else series_id,
                status=FetchStatus.FAILED.value,
                max_staleness_days=cfg.max_staleness_days,
                message=f"unexpected {type(exc).__name__}: {exc}",
            )
        report.outcomes.append(outcome)
        if not dry_run and outcome.frame is not None:
            written_frames.append(outcome.frame)

    if not dry_run:
        save_fetch_state(state, state_path)
        if written_frames:
            with DuckDBStore() as store:
                store.refresh_series_data(pd.concat(written_frames, ignore_index=True))
                store.refresh_series_metadata(indicators)

    status_df = report.to_status_frame()
    manual_df = report.to_manual_frame()
    paths.DATA_STATUS_CSV.parent.mkdir(parents=True, exist_ok=True)
    status_df.to_csv(paths.DATA_STATUS_CSV, index=False, encoding="utf-8-sig")
    manual_df.to_csv(paths.MANUAL_FETCH_CSV, index=False, encoding="utf-8-sig")

    return report
