"""Deterministic updater tests using fake adapters (no network access).

Covers: canonical writes, repeat-update dedup, fallback status, manual
required, failure isolation, staleness, dry-run, and the status CSV outputs.
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from macro_compass.data_sources.base import (
    DataSourceAdapter,
    FetchError,
    FetchStatus,
    ManualFetchRequired,
    ProviderUnavailable,
    build_canonical_frame,
)
from macro_compass.data_sources.registry import (
    AdapterRegistry,
    DataSourcesConfig,
    ProviderSpec,
    SeriesSource,
)
from macro_compass.data_sources.updater import update_series
from macro_compass.storage.canonical_store import read_canonical


def _frame(series_id: str, category: str, days: list[date], values: list[float]):
    return build_canonical_frame(
        series_id,
        days,
        values,
        provider="fake",
        source_file="fake://test",
        series_name=series_id,
        unit="",
        frequency="monthly" if category == "macro" else "daily",
        category=category,
    )


class FakeAdapter(DataSourceAdapter):
    """Scriptable adapter: returns pre-built frames or raises per series."""

    def __init__(self, provider_spec, series_specs, results):
        super().__init__(provider_spec, series_specs)
        self.results = results
        self.calls: list[tuple[str, object]] = []

    def fetch(self, series_id: str, start_date=None, end_date=None) -> pd.DataFrame:
        self.calls.append((series_id, start_date))
        outcome = self.results[series_id]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _build_config(series_defs: dict[str, dict], enabled=True) -> DataSourcesConfig:
    return DataSourcesConfig(
        providers={
            "fake_a": ProviderSpec(module="fred", adapter_class="FredAdapter", enabled=enabled),
            "fake_b": ProviderSpec(module="fred", adapter_class="FredAdapter", enabled=enabled),
        },
        series=series_defs,
        overlap_days=10,
    )


def _wire(config: DataSourcesConfig, adapters: dict[str, DataSourceAdapter]) -> AdapterRegistry:
    registry = AdapterRegistry(config)
    for provider_id, adapter in adapters.items():
        adapter.provider_spec = config.providers[provider_id]
        specs = {}
        for sid, spec in config.series.items():
            chain = [spec.primary] + ([spec.fallback] if spec.fallback else [])
            if provider_id not in chain:
                continue
            if provider_id == spec.fallback and spec.fallback_code:
                spec = spec.model_copy(update={"provider_code": spec.fallback_code})
            specs[sid] = spec
        adapter.series_specs = specs
        registry._adapters[provider_id] = adapter
    return registry


RECENT = [date(2026, 8, 1), date(2026, 8, 2), date(2026, 8, 3)]


def _one_series(primary="fake_a", fallback=None, **spec_kwargs) -> dict:
    return {
        "CHN_CLI": SeriesSource(
            primary=primary,
            fallback=fallback,
            provider_code="KEY",
            frequency="monthly",
            category="macro",
            **{"max_staleness_days": 90, **spec_kwargs},
        )
    }


def test_success_writes_canonical_state_and_status(data_env, indicators, status_paths, tmp_path):
    config = _build_config(_one_series())
    adapters = _wire(config, {
        "fake_a": FakeAdapter(None, {}, {"CHN_CLI": _frame("CHN_CLI", "macro", RECENT, [98.5, 98.6, 98.7])}),
    })
    state_path = tmp_path / "state.json"

    state = {}
    outcome = update_series("CHN_CLI", config, indicators, adapters, state)

    assert outcome.status == FetchStatus.OK.value
    assert outcome.provider_used == "fake_a"
    assert outcome.rows_fetched == 3
    assert outcome.last_observation_date == "2026-08-03"
    assert state["CHN_CLI"]["last_observation_date"] == "2026-08-03"
    assert state["CHN_CLI"]["last_provider"] == "fake_a"
    assert state["CHN_CLI"]["fetch_status"] == "OK"

    canonical = read_canonical("macro")
    assert list(canonical["series_id"].unique()) == ["CHN_CLI"]
    assert len(canonical) == 3
    # indicator metadata enriched from the registry
    assert (canonical["series_name"] == "中国CLI领先指标").all()
    assert (canonical["unit"] == "index").all()


def test_incremental_fetch_only_requests_new_window(data_env, indicators, tmp_path):
    config = _build_config(_one_series())
    adapter = FakeAdapter(None, {}, {"CHN_CLI": _frame("CHN_CLI", "macro", RECENT, [98.5, 98.6, 98.7])})
    adapters = _wire(config, {"fake_a": adapter})

    state = {"CHN_CLI": {"last_observation_date": "2026-08-01"}}
    update_series("CHN_CLI", config, indicators, adapters, state)
    series_id, start_date = adapter.calls[0]
    assert series_id == "CHN_CLI"
    assert start_date == pd.Timestamp("2026-07-22")  # 2026-08-01 minus overlap 10d


def test_repeat_update_does_not_duplicate_rows(data_env, indicators, tmp_path):
    config = _build_config(_one_series())
    frame = _frame("CHN_CLI", "macro", RECENT, [98.5, 98.6, 98.7])
    adapters = _wire(config, {"fake_a": FakeAdapter(None, {}, {"CHN_CLI": frame})})
    state = {}

    update_series("CHN_CLI", config, indicators, adapters, state)
    update_series("CHN_CLI", config, indicators, adapters, state)

    canonical = read_canonical("macro")
    assert len(canonical) == 3
    assert not canonical.duplicated(subset=["series_id", "date"]).any()


def test_fallback_used_gets_explicit_status(data_env, indicators):
    config = _build_config(_one_series(primary="fake_a", fallback="fake_b"))
    adapters = _wire(config, {
        "fake_a": FakeAdapter(None, {}, {"CHN_CLI": FetchError("primary down")}),
        "fake_b": FakeAdapter(None, {}, {"CHN_CLI": _frame("CHN_CLI", "macro", RECENT, [98.5, 98.6, 98.7])}),
    })
    state = {}
    outcome = update_series("CHN_CLI", config, indicators, adapters, state)
    assert outcome.status == FetchStatus.FALLBACK_USED.value
    assert outcome.provider_used == "fake_b"


def test_unavailable_provider_reports_manual_required(data_env, indicators):
    config = _build_config(_one_series())
    adapters = _wire(config, {
        "fake_a": FakeAdapter(None, {}, {"CHN_CLI": ProviderUnavailable("akshare not installed")}),
    })
    outcome = update_series("CHN_CLI", config, indicators, adapters, {})
    assert outcome.status == FetchStatus.MANUAL_REQUIRED.value
    assert "akshare not installed" in outcome.message


def test_wind_manual_series_is_manual_required(data_env, indicators):
    config = _build_config(_one_series())
    adapters = _wire(config, {
        "fake_a": FakeAdapter(None, {}, {"CHN_CLI": ManualFetchRequired("use import_wind")}),
    })
    outcome = update_series("CHN_CLI", config, indicators, adapters, {})
    assert outcome.status == FetchStatus.MANUAL_REQUIRED.value
    assert "import_wind" in outcome.message


def test_all_providers_failing_reports_failed(data_env, indicators):
    config = _build_config(_one_series(primary="fake_a", fallback="fake_b"))
    adapters = _wire(config, {
        "fake_a": FakeAdapter(None, {}, {"CHN_CLI": FetchError("boom")}),
        "fake_b": FakeAdapter(None, {}, {"CHN_CLI": FetchError("boom too")}),
    })
    outcome = update_series("CHN_CLI", config, indicators, adapters, {})
    assert outcome.status == FetchStatus.FAILED.value
    assert "fake_a" in outcome.message and "fake_b" in outcome.message


def test_stale_when_last_observation_too_old(data_env, indicators):
    old = [date(2026, 1, 10), date(2026, 2, 10)]
    config = _build_config(_one_series(max_staleness_days=30))
    adapters = _wire(config, {
        "fake_a": FakeAdapter(None, {}, {"CHN_CLI": _frame("CHN_CLI", "macro", old, [98.1, 98.2])}),
    })
    outcome = update_series("CHN_CLI", config, indicators, adapters, {})
    assert outcome.status == FetchStatus.STALE.value
    assert outcome.stale_days > 30


def test_run_update_isolates_series_failures(data_env, indicators, status_paths, tmp_path, monkeypatch):
    """One broken series must not abort the remaining updates."""
    series_defs = {
        "CHN_CLI": SeriesSource(primary="fake_a", provider_code="KEY", frequency="monthly",
                                category="macro", max_staleness_days=90),
        "USD_CNY": SeriesSource(primary="fake_b", provider_code="KEY", frequency="daily",
                                category="macro", max_staleness_days=90),
    }
    config = _build_config(series_defs)
    ok_frame = _frame("USD_CNY", "macro", [date(2026, 8, 1)], [6.78])
    adapters = _wire(config, {
        "fake_a": FakeAdapter(None, {}, {"CHN_CLI": RuntimeError("hard crash")}),
        "fake_b": FakeAdapter(None, {}, {"USD_CNY": ok_frame}),
    })

    from macro_compass.data_sources import updater as updater_module
    monkeypatch.setattr(updater_module, "load_indicator_config", lambda path=None: indicators)
    monkeypatch.setattr(updater_module, "load_data_sources_config", lambda *a, **k: config)
    monkeypatch.setattr(updater_module, "DuckDBStore", _FakeDuckDB)
    monkeypatch.setattr(updater_module, "AdapterRegistry", lambda cfg: adapters)
    _FakeDuckDB.calls = []
    state_path = tmp_path / "state.json"

    report = updater_module.run_update(state_path=state_path)

    statuses = {o.series_id: o.status for o in report.outcomes}
    assert statuses["CHN_CLI"] == FetchStatus.FAILED.value
    assert statuses["USD_CNY"] == FetchStatus.OK.value
    assert len(read_canonical("macro")) == 1

    status_csv, manual_csv = status_paths
    status_df = pd.read_csv(status_csv)
    assert set(status_df["fetch_status"]) == {"OK", "FAILED"}
    manual_df = pd.read_csv(manual_csv)
    assert list(manual_df["series_id"]) == ["CHN_CLI"]


class _FakeDuckDB:
    calls: list = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def refresh_series_data(self, frame):
        _FakeDuckDB.calls.append(("data", len(frame)))

    def refresh_series_metadata(self, registry):
        _FakeDuckDB.calls.append(("meta", len(registry)))


def test_run_update_validates_before_writing(data_env, indicators, status_paths, tmp_path, monkeypatch):
    """A frame with an unregistered series id must fail validation, not write."""
    series_defs = {
        "CHN_CLI": SeriesSource(primary="fake_a", provider_code="KEY", frequency="monthly",
                                category="macro", max_staleness_days=90),
    }
    config = _build_config(series_defs)
    bad_frame = _frame("NOT_A_SERIES", "macro", RECENT, [1.0, 2.0, 3.0])
    adapters = _wire(config, {
        "fake_a": FakeAdapter(None, {}, {"CHN_CLI": bad_frame}),
    })

    from macro_compass.data_sources import updater as updater_module
    monkeypatch.setattr(updater_module, "load_indicator_config", lambda path=None: indicators)
    monkeypatch.setattr(updater_module, "load_data_sources_config", lambda *a, **k: config)
    monkeypatch.setattr(updater_module, "DuckDBStore", _FakeDuckDB)
    monkeypatch.setattr(updater_module, "AdapterRegistry", lambda cfg: adapters)
    _FakeDuckDB.calls = []

    report = updater_module.run_update(state_path=tmp_path / "state.json")
    outcome = report.outcomes[0]
    assert outcome.status == FetchStatus.FAILED.value
    assert "validation failed" in outcome.message
    assert read_canonical("macro").empty


def test_dry_run_writes_nothing(data_env, indicators, tmp_path, monkeypatch):
    series_defs = {
        "CHN_CLI": SeriesSource(primary="fake_a", provider_code="KEY", frequency="monthly",
                                category="macro", max_staleness_days=90),
    }
    config = _build_config(series_defs)
    frame = _frame("CHN_CLI", "macro", RECENT, [98.5, 98.6, 98.7])
    adapters = _wire(config, {"fake_a": FakeAdapter(None, {}, {"CHN_CLI": frame})})

    from macro_compass.data_sources import updater as updater_module
    monkeypatch.setattr(updater_module, "load_indicator_config", lambda path=None: indicators)
    monkeypatch.setattr(updater_module, "load_data_sources_config", lambda *a, **k: config)
    monkeypatch.setattr(updater_module, "DuckDBStore", _FakeDuckDB)
    monkeypatch.setattr(updater_module, "AdapterRegistry", lambda cfg: adapters)
    _FakeDuckDB.calls = []

    state_path = tmp_path / "state.json"
    report = updater_module.run_update(state_path=state_path, dry_run=True)

    assert report.outcomes[0].status == FetchStatus.OK.value
    assert read_canonical("macro").empty
    assert not state_path.exists()
    assert _FakeDuckDB.calls == []
