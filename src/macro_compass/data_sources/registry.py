"""Source Registry for V1.2: config/data_sources.yaml loading and validation.

Every externally fetched series is declared here with its primary provider,
optional fallback, provider-specific code, frequency and staleness threshold.
The registry cross-checks each series against ``config/indicators.yaml`` so a
misconfigured series fails loudly at load time instead of at validation time
inside an update run.
"""

from __future__ import annotations

import importlib
from typing import Literal, Optional

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from macro_compass.config import ConfigError
from macro_compass.data_sources.base import DataSourceAdapter

FREQUENCIES = ("monthly", "weekly", "daily")
CATEGORIES = ("macro", "market")


class ProviderSpec(BaseModel):
    """One provider entry from data_sources.yaml ``providers`` section."""

    model_config = ConfigDict(extra="forbid")

    module: str
    adapter_class: str
    enabled: bool = True
    timeout_seconds: int = 30
    options: dict = Field(default_factory=dict)


class SeriesSource(BaseModel):
    """Routing for one series_id: providers, codes and freshness budget."""

    model_config = ConfigDict(extra="forbid")

    primary: str
    fallback: Optional[str] = None
    provider_code: str = ""
    fallback_code: str = ""
    frequency: Literal["monthly", "weekly", "daily"]
    category: Literal["macro", "market"]
    max_staleness_days: int = Field(default=60, ge=1)
    original_source: str = ""
    manual_instructions: str = ""
    enabled: bool = True


class DataSourcesConfig(BaseModel):
    """Whole data_sources.yaml document."""

    model_config = ConfigDict(extra="forbid")

    providers: dict[str, ProviderSpec]
    series: dict[str, SeriesSource]
    overlap_days: int = Field(default=45, ge=0)

    def chain_for(self, series_id: str) -> list[str]:
        """Provider chain for a series: primary first, then the fallback."""
        spec = self.series[series_id]
        chain = [spec.primary]
        if spec.fallback:
            chain.append(spec.fallback)
        return chain


def _load_yaml(path) -> dict:
    path = __import__("pathlib").Path(path)
    if not path.exists():
        raise ConfigError(f"Config file not found: {path}")
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
    except yaml.YAMLError as exc:
        raise ConfigError(f"Config file is not valid YAML: {path}\n{exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"Config file must contain a YAML mapping at top level: {path}")
    return data


def load_data_sources_config(path, indicator_registry: dict | None = None) -> DataSourcesConfig:
    """Load and validate data_sources.yaml.

    Raises ``ConfigError`` on malformed YAML, unknown fields, invalid enum
    values, unknown providers referenced by a series, or a series that is not
    registered in indicators.yaml (when a registry is provided).
    """
    path = __import__("pathlib").Path(path)
    raw = _load_yaml(path)
    # `defaults` is a readability-only section: its keys merge into the
    # top-level document so yaml authors can group them.
    defaults = raw.pop("defaults", None)
    if defaults is not None:
        if not isinstance(defaults, dict):
            raise ConfigError(f"{path.name}: 'defaults' must be a mapping")
        for key, value in defaults.items():
            raw.setdefault(key, value)
    try:
        config = DataSourcesConfig(**raw)
    except ValidationError as exc:
        raise ConfigError(f"{path.name}: invalid data sources config:\n{exc}") from exc

    for series_id, spec in config.series.items():
        for provider_id in config.chain_for(series_id):
            if provider_id not in config.providers:
                raise ConfigError(
                    f"{path.name}: series '{series_id}' references unknown provider "
                    f"'{provider_id}'"
                )
        if indicator_registry is not None and series_id not in indicator_registry:
            raise ConfigError(
                f"{path.name}: series '{series_id}' is not registered in indicators.yaml"
            )
        for provider_id in config.chain_for(series_id):
            # adapter module must be importable at config load time - a typo
            # in `module:` should fail immediately, not mid-update.
            adapter_cls = load_adapter_class(config.providers[provider_id])
            if not issubclass(adapter_cls, DataSourceAdapter):
                raise ConfigError(
                    f"{path.name}: adapter class '{adapter_cls.__name__}' is not a "
                    f"DataSourceAdapter"
                )
    return config


def load_adapter_class(provider_spec: ProviderSpec) -> type:
    """Import ``module.adapter_class`` from the data_sources package."""
    try:
        module = importlib.import_module(f"macro_compass.data_sources.{provider_spec.module}")
        return getattr(module, provider_spec.adapter_class)
    except (ImportError, AttributeError) as exc:
        raise ConfigError(
            f"Cannot load adapter '{provider_spec.module}.{provider_spec.adapter_class}': {exc}"
        ) from exc


class AdapterRegistry:
    """Lazily builds and caches one adapter instance per provider."""

    def __init__(self, config: DataSourcesConfig):
        self.config = config
        self._adapters: dict[str, DataSourceAdapter] = {}

    def get(self, provider_id: str) -> DataSourceAdapter:
        if provider_id in self._adapters:
            return self._adapters[provider_id]
        provider_spec = self.config.providers[provider_id]
        series_specs: dict[str, SeriesSource] = {}
        for sid, spec in self.config.series.items():
            if provider_id not in self.config.chain_for(sid):
                continue
            if provider_id == spec.fallback and spec.fallback_code:
                # The fallback provider may need a different instrument code.
                spec = spec.model_copy(update={"provider_code": spec.fallback_code})
            series_specs[sid] = spec
        adapter_cls = load_adapter_class(provider_spec)
        adapter = adapter_cls(provider_spec, series_specs, provider_id=provider_id)
        self._adapters[provider_id] = adapter
        return adapter

    def enabled_series(self) -> list[str]:
        return [
            sid for sid, spec in self.config.series.items() if spec.enabled
        ]
