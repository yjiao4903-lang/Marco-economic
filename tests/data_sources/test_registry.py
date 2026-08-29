"""Config registry tests for data_sources.yaml (deterministic)."""

from __future__ import annotations

import pytest

from macro_compass.config import ConfigError
from macro_compass.data_sources.registry import (
    AdapterRegistry,
    DataSourcesConfig,
    ProviderSpec,
    SeriesSource,
    load_data_sources_config,
)
from macro_compass import paths


def _provider(module="fred", cls="FredAdapter", enabled=True, **kwargs):
    return ProviderSpec(module=module, adapter_class=cls, enabled=enabled, **kwargs)


def _series(primary="fred", fallback=None, provider_code="X", **kwargs):
    return SeriesSource(
        primary=primary,
        fallback=fallback,
        provider_code=provider_code,
        frequency="daily",
        category="macro",
        **kwargs,
    )


def _minimal_config() -> DataSourcesConfig:
    return DataSourcesConfig(
        providers={"fake_a": _provider(), "fake_b": _provider()},
        series={
            "CHN_CLI": _series(primary="fake_a"),
        },
    )


def test_chain_is_primary_then_fallback():
    config = DataSourcesConfig(
        providers={"a": _provider(), "b": _provider()},
        series={"CHN_CLI": _series(primary="a", fallback="b")},
    )
    assert config.chain_for("CHN_CLI") == ["a", "b"]


def test_chain_without_fallback_has_single_provider():
    config = _minimal_config()
    assert config.chain_for("CHN_CLI") == ["fake_a"]


def test_registry_substitutes_fallback_code():
    config = DataSourcesConfig(
        providers={"a": _provider(), "b": _provider()},
        series={
            "CHN_CLI": _series(
                primary="a", fallback="b", provider_code="PRIMARY", fallback_code="FALLBACK"
            )
        },
    )
    registry = AdapterRegistry(config)
    # bypass module loading by injecting a sentinel object that records specs
    class _Sentinel:
        def __init__(self, spec, series_specs, provider_id=""):
            self.spec = spec
            self.series_specs = series_specs
            self._provider_id = provider_id

    config.providers["b"].module = "fred"  # importable if ever loaded
    # rebuild through get() but with the class loader patched
    from macro_compass.data_sources import registry as registry_module

    original_loader = registry_module.load_adapter_class
    registry_module.load_adapter_class = lambda spec: _Sentinel
    try:
        adapter_b = registry.get("b")
    finally:
        registry_module.load_adapter_class = original_loader
    assert adapter_b.series_specs["CHN_CLI"].provider_code == "FALLBACK"


def test_load_real_config_validates_against_indicators(indicators):
    config = load_data_sources_config(paths.DATA_SOURCES_YAML, indicators)
    assert "CHN_CLI" in config.series
    assert config.overlap_days == 45
    for series_id in config.series:
        assert series_id in indicators, series_id


def test_load_config_rejects_unregistered_series(tmp_path, indicators):
    path = tmp_path / "data_sources.yaml"
    path.write_text(
        """
providers:
  fred:
    module: fred
    adapter_class: FredAdapter
series:
  NOT_REGISTERED:
    primary: fred
    frequency: daily
    category: macro
""",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="NOT_REGISTERED"):
        load_data_sources_config(path, indicators)


def test_load_config_rejects_unknown_provider(tmp_path, indicators):
    path = tmp_path / "data_sources.yaml"
    path.write_text(
        """
providers:
  fred:
    module: fred
    adapter_class: FredAdapter
series:
  CHN_CLI:
    primary: nosuchprovider
    frequency: monthly
    category: macro
""",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="unknown provider"):
        load_data_sources_config(path, indicators)


def test_disabled_provider_is_configurable() -> None:
    spec = _provider(enabled=False)
    assert spec.enabled is False
