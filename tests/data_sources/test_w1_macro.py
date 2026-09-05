"""Offline acceptance tests for Marco external-macro W1."""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from macro_compass import paths
from macro_compass.config import IndicatorConfig
from macro_compass.data_sources.akshare_source import parse_monthly_macro_frame
from macro_compass.data_sources.base import FetchError, build_canonical_frame
from macro_compass.data_sources.derived import (
    DerivedSeriesError,
    derive_cn_dr007_spread,
    derive_us_10y2y_spread,
)
from macro_compass.data_sources.fred import FredAdapter
from macro_compass.data_sources.nbs import parse_pmi_headline
from macro_compass.data_sources.pit_release import actual_release_metadata
from macro_compass.data_sources.registry import (
    FreshnessMeta,
    ProviderSpec,
    SeriesSource,
    load_data_sources_config,
)
from macro_compass.ingestion.validator import validate_canonical
from macro_compass.storage.duckdb_store import DuckDBStore
from macro_compass.storage.canonical_store import append_canonical, read_canonical


def _temporal_frame(
    series_id: str,
    dates: list[date],
    values: list[float],
    *,
    available_at: list[pd.Timestamp] | None = None,
    unit: str = "percent",
) -> pd.DataFrame:
    available = available_at or [
        pd.Timestamp(d).tz_localize("UTC") + pd.Timedelta(hours=12)
        for d in dates
    ]
    return build_canonical_frame(
        series_id,
        dates,
        values,
        provider="fixture",
        source_file="fixture://w1",
        series_name=series_id,
        unit=unit,
        frequency="daily",
        category="macro",
        observation_dates=dates,
        release_at=available,
        available_at=available,
    )


def _pit_spec(code: str, *, frequency: str = "monthly") -> SeriesSource:
    return SeriesSource(
        primary="fixture",
        provider_code=code,
        frequency=frequency,
        category="macro",
        freshness=FreshnessMeta(
            expected_release_lag_days=31,
            availability_rule="end_of_day_after_lag",
            publication_timezone="UTC",
        ),
    )


def test_w1_registry_routes_and_derived_specs(indicators):
    config = load_data_sources_config(paths.DATA_SOURCES_YAML, indicators)

    assert config.series["CN_PMI"].primary == "nbs"
    assert config.series["CN_PMI"].provider_code == "PMI_HEADLINE"
    assert config.series["CN_PMI"].fallback == "wind_manual"
    assert config.series["CN_PPI_YOY"].provider_code == "CN_PPI_YOY"
    assert config.series["US_INITIAL_CLAIMS"].provider_code == "ICSA"
    assert config.series["US_CORE_CPI"].provider_code == "CPILFESL"
    assert config.series["US_TREASURY_NOMINAL_YIELD_10Y"].provider_code == "DGS10"
    assert config.series["US_TREASURY_NOMINAL_YIELD_2Y"].provider_code == "DGS2"
    assert config.series["CN_POLICY_RATE_7D"].frequency == "daily"

    cn_spread = config.derived_series["CN_DR007_SPREAD"]
    assert cn_spread.legs == ["CN_DR007", "CN_POLICY_RATE_7D"]
    assert cn_spread.formula == "CN_DR007 - CN_POLICY_RATE_7D"
    us_spread = config.derived_series["US_10Y2Y_SPREAD"]
    assert us_spread.legs == [
        "US_TREASURY_NOMINAL_YIELD_10Y",
        "US_TREASURY_NOMINAL_YIELD_2Y",
    ]
    assert "CN_NBS_PMI_MFG" not in indicators


def test_pmi_headline_parser_preserves_cn_pmi_canonical_semantics():
    rows = parse_pmi_headline(
        "2026年7月中国采购经理指数运行情况",
        "制造业PMI为49.4%，比上月下降0.3个百分点。",
    )
    assert rows == [(pd.Timestamp("2026-07-31"), 49.4)]

    assert parse_pmi_headline(
        "2026年7月中国采购经理指数运行情况", "非制造业PMI为50.3%。"
    ) == []
    with pytest.raises(FetchError, match="title not parseable"):
        parse_pmi_headline("2026年7月非制造业指数", "制造业PMI为49.4%。")


def test_ppi_parser_rejects_malformed_access_layer_schema():
    with pytest.raises(FetchError, match="missing column"):
        parse_monthly_macro_frame(
            pd.DataFrame({"月份": ["2026年07月份"], "wrong": [1.0]}),
            "CN_PPI_YOY",
            value_column="当月同比增长",
        )
    with pytest.raises(FetchError, match="no usable rows"):
        parse_monthly_macro_frame(
            pd.DataFrame({"月份": ["not-a-month"], "当月同比增长": ["-"]}),
            "CN_PPI_YOY",
            value_column="当月同比增长",
        )


def test_actual_release_metadata_requires_calendar_evidence():
    spec = _pit_spec("ICSA", frequency="weekly")
    with pytest.raises(FetchError, match="actual release-calendar evidence required"):
        actual_release_metadata(spec, [date(2026, 8, 1)])

    metadata = actual_release_metadata(
        spec,
        [date(2026, 8, 1)],
        release_at=[pd.Timestamp("2026-08-06T08:30:00-04:00")],
    )
    frame = build_canonical_frame(
        "US_INITIAL_CLAIMS",
        [date(2026, 8, 1)],
        [200000],
        provider="fixture",
        source_file="fixture://dol-release-calendar",
        series_name="claims",
        unit="persons",
        frequency="weekly",
        category="macro",
        **metadata,
    )
    assert frame.loc[0, "release_at"] == pd.Timestamp("2026-08-06T12:30:00Z")
    assert frame.loc[0, "available_at"] == frame.loc[0, "release_at"]

    registry = {
        "US_INITIAL_CLAIMS": IndicatorConfig(
            name="claims", frequency="weekly", unit="persons", factor="growth"
        )
    }
    assert validate_canonical(frame, registry).passed


def test_core_cpi_reference_month_arithmetic_cannot_create_release_at():
    spec = _pit_spec("CPILFESL")
    with pytest.raises(FetchError, match="observation-date lag cannot populate"):
        actual_release_metadata(spec, [date(2026, 7, 31)])

    metadata = actual_release_metadata(
        spec,
        [date(2026, 7, 31)],
        release_at=[pd.Timestamp("2026-08-12T08:30:00-04:00")],
        available_at=[pd.Timestamp("2026-08-12T08:30:00-04:00")],
    )
    assert metadata["observation_dates"] == [date(2026, 7, 31)]
    assert metadata["release_at"] == [pd.Timestamp("2026-08-12T12:30:00Z")]


def test_icsa_holiday_shift_is_explicit_not_observation_date_inferred():
    spec = _pit_spec("ICSA", frequency="weekly")
    observation = date(2026, 12, 26)
    holiday_shifted_release = pd.Timestamp("2026-12-31T08:30:00-05:00")
    metadata = actual_release_metadata(
        spec,
        [observation],
        release_at=[holiday_shifted_release],
    )
    assert metadata["release_at"] == [pd.Timestamp("2026-12-31T13:30:00Z")]


def test_cn_pmi_and_ppi_require_actual_nbs_calendar_timestamp():
    pmi = _pit_spec("PMI_HEADLINE")
    ppi = _pit_spec("CN_PPI_YOY")
    for spec, observation in (
        (pmi, date(2026, 7, 31)),
        (ppi, date(2026, 7, 31)),
    ):
        with pytest.raises(FetchError, match="actual release-calendar evidence required"):
            actual_release_metadata(spec, [observation])

    pmi_metadata = actual_release_metadata(
        pmi,
        [date(2026, 7, 31)],
        release_at=[pd.Timestamp("2026-07-31T09:30:00+08:00")],
    )
    ppi_metadata = actual_release_metadata(
        ppi,
        [date(2026, 7, 31)],
        release_at=[pd.Timestamp("2026-08-09T09:30:00+08:00")],
    )
    assert pmi_metadata["release_at"] == [pd.Timestamp("2026-07-31T01:30:00Z")]
    assert ppi_metadata["release_at"] == [pd.Timestamp("2026-08-09T01:30:00Z")]


def test_temporal_validator_rejects_partial_or_naive_metadata():
    base = {
        "series_id": ["S1"],
        "date": [date(2026, 8, 3)],
        "value": [1.0],
        "observation_date": [date(2026, 8, 3)],
        "release_at": [pd.Timestamp("2026-08-03 10:00")],
        "available_at": [pd.Timestamp("2026-08-03 10:00")],
    }
    registry = {
        "S1": IndicatorConfig(
            name="S1", frequency="daily", unit="percent", factor="growth"
        )
    }
    report = validate_canonical(pd.DataFrame(base), registry)
    assert not report.passed
    assert any("timezone-naive" in error for error in report.errors)

    partial = pd.DataFrame({k: v for k, v in base.items() if k != "available_at"})
    report = validate_canonical(partial, registry)
    assert not report.passed
    assert any("temporal provenance is partial" in error for error in report.errors)


def test_fred_w1_adapter_fails_closed_without_release_calendar(monkeypatch):
    provider = ProviderSpec(module="fred", adapter_class="FredAdapter")
    series = SeriesSource(
        primary="fred",
        provider_code="ICSA",
        frequency="weekly",
        category="macro",
        freshness=FreshnessMeta(
            expected_release_lag_days=7,
            availability_rule="end_of_day_after_lag",
            publication_timezone="America/New_York",
        ),
    )
    captured = {}

    def fake_http_get(url, timeout):
        captured["url"] = url
        captured["timeout"] = timeout
        return "observation_date,ICSA\n2026-08-06,200000\n"

    monkeypatch.delenv("FRED_API_KEY", raising=False)
    monkeypatch.setattr("macro_compass.data_sources.fred.http_get", fake_http_get)
    adapter = FredAdapter(provider, {"US_INITIAL_CLAIMS": series}, provider_id="fred")
    with pytest.raises(FetchError, match="actual release-calendar evidence required"):
        adapter.fetch("US_INITIAL_CLAIMS")
    assert "id=ICSA" in captured["url"]


def test_cn_spread_uses_latest_policy_published_by_cutoff_not_future_value():
    day = date(2026, 8, 3)
    dr = _temporal_frame(
        "CN_DR007",
        [day],
        [2.1],
        available_at=[pd.Timestamp("2026-08-03T12:00:00Z")],
    )
    policy = _temporal_frame(
        "CN_POLICY_RATE_7D",
        [date(2026, 8, 2), day],
        [1.8, 1.7],
        available_at=[
            pd.Timestamp("2026-08-02T23:00:00Z"),
            pd.Timestamp("2026-08-03T15:00:00Z"),
        ],
    )

    before = derive_cn_dr007_spread(
        dr, policy, decision_time=pd.Timestamp("2026-08-03T14:00:00Z")
    )
    after = derive_cn_dr007_spread(
        dr, policy, decision_time=pd.Timestamp("2026-08-03T16:00:00Z")
    )
    assert before.loc[0, "value"] == pytest.approx(0.3)
    assert after.loc[0, "value"] == pytest.approx(0.4)
    assert after.loc[0, "available_at"] == pd.Timestamp("2026-08-03T15:00:00Z")


def test_spreads_fail_closed_on_pit_missing_overlap_and_unit_mismatch():
    dates = [date(2026, 8, 3)]
    left = _temporal_frame("US_TREASURY_NOMINAL_YIELD_10Y", dates, [4.0])
    right = _temporal_frame("US_TREASURY_NOMINAL_YIELD_2Y", dates, [3.5])
    result = derive_us_10y2y_spread(left, right)
    assert result.loc[0, "value"] == pytest.approx(0.5)

    with pytest.raises(DerivedSeriesError, match="no exact-date overlap"):
        derive_us_10y2y_spread(
            left,
            _temporal_frame("US_TREASURY_NOMINAL_YIELD_2Y", [date(2026, 8, 4)], [3.5]),
        )
    with pytest.raises(DerivedSeriesError, match="unit"):
        derive_us_10y2y_spread(
            left,
            _temporal_frame(
                "US_TREASURY_NOMINAL_YIELD_2Y", dates, [3.5], unit="index"
            ),
        )
    with pytest.raises(DerivedSeriesError, match="decision_time"):
        derive_us_10y2y_spread(
            left, right, decision_time=pd.Timestamp("2026-08-03")
        )


def test_duckdb_cache_keeps_temporal_provenance_columns(data_env):
    frame = _temporal_frame("US_TREASURY_NOMINAL_YIELD_2Y", [date(2026, 8, 3)], [3.5])
    with DuckDBStore(data_env.duckdb_path) as store:
        assert store.refresh_series_data(frame) == 1
        row = store.conn.execute(
            "SELECT observation_date, release_at, available_at "
            "FROM series_data WHERE series_id = 'US_TREASURY_NOMINAL_YIELD_2Y'"
        ).fetchone()
    assert row[0] == date(2026, 8, 3)
    assert row[1] == row[2]


def test_canonical_parquet_accepts_legacy_rows_with_new_temporal_rows(data_env):
    legacy = build_canonical_frame(
        "LEGACY",
        [date(2026, 8, 2)],
        [1.0],
        provider="fixture",
        source_file="fixture://legacy",
        series_name="LEGACY",
        unit="percent",
        frequency="daily",
        category="macro",
    )
    append_canonical(legacy)
    append_canonical(
        _temporal_frame("US_TREASURY_NOMINAL_YIELD_2Y", [date(2026, 8, 3)], [3.5])
    )
    stored = read_canonical("macro")
    temporal = stored.loc[
        stored["series_id"].eq("US_TREASURY_NOMINAL_YIELD_2Y")
    ].iloc[0]
    assert temporal["available_at"].tzinfo is not None
    assert pd.isna(
        stored.loc[stored["series_id"].eq("LEGACY"), "available_at"]
    ).all()
