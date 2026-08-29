"""Real-network integration tests for V1.2 providers.

These are NOT part of the default deterministic suite - run them explicitly:

    python -m pytest -m network

Providers whose endpoints are known-blocked or unstable from the current
network (FRED, ChinaBond) skip instead of fail, while a real observation of
their unavailability is expected during acceptance runs.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from macro_compass.data_sources.base import DataSourceError
from macro_compass.data_sources.registry import AdapterRegistry, load_data_sources_config
from macro_compass.config import load_indicator_config
from macro_compass import paths

pytestmark = pytest.mark.network


def _adapter_for(provider_id: str):
    indicators = load_indicator_config(paths.INDICATORS_YAML)
    config = load_data_sources_config(paths.DATA_SOURCES_YAML, indicators)
    registry = AdapterRegistry(config)
    return registry, registry.get(provider_id), config


def test_oecd_real_fetch():
    registry, adapter, config = _adapter_for("oecd")
    frame = adapter.fetch("CHN_CLI", start_date=date.today() - timedelta(days=180))
    assert not frame.empty
    assert (frame["series_id"] == "CHN_CLI").all()
    assert (frame["category"] == "macro").all()
    assert frame["value"].notna().all()
    assert frame["date"].max() >= date.today() - timedelta(days=120)


def test_chinamoney_real_fetch_usd_cny():
    _, adapter, config = _adapter_for("chinamoney")
    frame = adapter.fetch("USD_CNY", start_date=date.today() - timedelta(days=30))
    assert not frame.empty
    assert (frame["series_id"] == "USD_CNY").all()
    assert (frame["value"] > 3).all() and (frame["value"] < 12).all()


def test_nyfed_real_fetch_sofr():
    _, adapter, config = _adapter_for("nyfed")
    frame = adapter.fetch("US_SOFR", start_date=date.today() - timedelta(days=30))
    assert not frame.empty
    assert (frame["series_id"] == "US_SOFR").all()
    assert (frame["value"] > 0).all() and (frame["value"] < 15).all()


def test_pbc_real_fetch_lpr():
    _, adapter, config = _adapter_for("pbc")
    frame = adapter.fetch("CN_LPR_1Y")
    assert not frame.empty
    assert (frame["series_id"] == "CN_LPR_1Y").all()
    assert (frame["value"] > 0).all() and (frame["value"] < 10).all()


def test_fred_real_fetch_or_skip():
    """FRED is commonly unreachable from CN networks; skip if so."""
    _, adapter, config = _adapter_for("fred")
    try:
        frame = adapter.fetch("US_REAL_YIELD_10Y", start_date=date.today() - timedelta(days=30))
    except DataSourceError as exc:
        pytest.skip(f"FRED unreachable from this network: {exc}")
    assert not frame.empty
    assert (frame["series_id"] == "US_REAL_YIELD_10Y").all()


def test_chinabond_real_fetch_or_skip():
    """ChinaBond's token-guarded endpoint is unstable; skip if degraded."""
    _, adapter, config = _adapter_for("chinabond")
    try:
        frame = adapter.fetch("CN_GOV_YIELD_10Y", start_date=date.today() - timedelta(days=30))
    except DataSourceError as exc:
        pytest.skip(f"ChinaBond endpoint degraded: {exc}")
    assert not frame.empty
    assert (frame["series_id"] == "CN_GOV_YIELD_10Y").all()
    assert (frame["value"] > 0).all() and (frame["value"] < 10).all()
