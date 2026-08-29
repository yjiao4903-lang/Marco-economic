"""YAML configuration loading with Pydantic validation.

All config errors raise ``ConfigError`` with a readable message -
silent failures are not allowed.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal, Optional

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

FACTORS = ("growth", "inflation", "rates", "credit", "liquidity", "fx")
DIRECTIONS = ("positive", "negative")
FREQUENCIES = ("monthly", "weekly", "daily")
CATEGORIES = ("macro", "market")


class ConfigError(Exception):
    """Raised when a configuration file is missing, malformed or incomplete."""


class TransformSpec(BaseModel):
    """A single indicator transform, e.g. ``{type: zscore, window: 60}``."""

    model_config = ConfigDict(extra="allow")

    type: str
    # Extra keys (window, periods, reference, ...) are allowed and kept as-is.


class IndicatorConfig(BaseModel):
    """One registered series in ``config/indicators.yaml``."""

    name: str
    category: Literal["macro", "market"] = "macro"
    factor: Optional[Literal["growth", "inflation", "rates", "credit", "liquidity", "fx"]] = None
    frequency: Literal["monthly", "weekly", "daily"]
    unit: str
    direction: Optional[Literal["positive", "negative"]] = None
    weight: float = Field(default=1.0, gt=0)
    enabled: bool = True
    transform: list[TransformSpec] = Field(default_factory=list)

    @classmethod
    def from_raw(cls, series_id: str, raw: dict) -> "IndicatorConfig":
        if not isinstance(raw, dict):
            raise ConfigError(
                f"indicators.yaml: entry '{series_id}' must be a mapping, got {type(raw).__name__}"
            )
        missing = [k for k in ("name", "frequency", "unit") if k not in raw]
        if missing:
            raise ConfigError(
                f"indicators.yaml: entry '{series_id}' is missing required field(s): {', '.join(missing)}"
            )
        try:
            return cls(**raw)
        except ValidationError as exc:
            raise ConfigError(f"indicators.yaml: entry '{series_id}' is invalid:\n{exc}") from exc


class MappingColumn(BaseModel):
    """Mapping of one Wind export column to an internal series_id."""

    series_id: str
    category: Literal["macro", "market"] = "macro"
    frequency: Optional[Literal["monthly", "weekly", "daily"]] = None
    unit: Optional[str] = None
    name: Optional[str] = None


class WindMapping(BaseModel):
    """Mapping of a Wind Excel/CSV export layout to internal series ids.

    ``date_column`` is the header name of the column holding observation dates.
    ``columns`` maps the Wind column header (as it appears in the file) to the
    internal series metadata. The calculation engine only ever sees series_id.
    """

    date_column: str
    columns: dict[str, MappingColumn]

    @classmethod
    def from_file(cls, path: Path) -> "WindMapping":
        raw = _load_yaml(path)
        if "date_column" not in raw:
            raise ConfigError(f"{path.name}: missing required field 'date_column'")
        if not raw.get("columns"):
            raise ConfigError(f"{path.name}: 'columns' must be a non-empty mapping")
        try:
            return cls(**raw)
        except ValidationError as exc:
            raise ConfigError(f"{path.name}: invalid wind mapping:\n{exc}") from exc


def _load_yaml(path: Path) -> dict:
    path = Path(path)
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


def load_indicator_config(path: Path) -> dict[str, IndicatorConfig]:
    """Load and validate the indicator registry.

    Returns ``{series_id: IndicatorConfig}``. Raises ``ConfigError`` on any
    missing required field, unknown factor/direction/frequency value, or
    duplicate registration.
    """
    raw = _load_yaml(path)
    registry: dict[str, IndicatorConfig] = {}
    for series_id, entry in raw.items():
        if series_id in registry:
            raise ConfigError(f"indicators.yaml: duplicate series_id '{series_id}'")
        cfg = IndicatorConfig.from_raw(series_id, entry)
        if cfg.category == "macro" and cfg.factor is None:
            raise ConfigError(
                f"indicators.yaml: macro indicator '{series_id}' must declare a factor "
                f"(one of {', '.join(FACTORS)})"
            )
        registry[series_id] = cfg
    if not registry:
        raise ConfigError(f"indicators.yaml contains no indicators: {path}")
    return registry
