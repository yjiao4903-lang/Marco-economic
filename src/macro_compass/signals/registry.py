"""Signal Registry (V1.3): config-driven declaration of 15+6+3 signals.

``config/signals.yaml`` is the single declaration surface. The registry
validates structure (required fields per layer), the transform whitelist
(V1.5A), and that every referenced ``series_id`` is registered in
``config/indicators.yaml`` - the unchanged single source of truth for series
metadata. ``signals.yaml`` only *references* series ids; it never duplicates
their metadata.

This module does no scoring and no aggregation: availability assessment
produces explicit per-signal statuses (READY / PARTIAL / MISSING_INPUT /
DECLARED) so missing inputs surface instead of silently becoming zeros. The
Signal Engine consumes these declarations from V1.5B onwards.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional

import yaml
from pydantic import BaseModel, ConfigDict, Field

from macro_compass.config import CORE_FACTORS, DIRECTIONS
from macro_compass.transforms import TRANSFORM_REGISTRY

LAYERS = ("core", "market", "structural")

# Statuses produced by availability assessment.
READY = "READY"                # every declared input has canonical data
PARTIAL = "PARTIAL"            # some inputs available (composite can run degraded)
MISSING_INPUT = "MISSING_INPUT"  # none of the declared inputs has data
DECLARED = "DECLARED"          # placeholder (market/structural) without inputs


class SignalConfigError(Exception):
    """Raised when signals.yaml is missing, malformed or inconsistent."""


class SignalInput(BaseModel):
    """One input series of a signal and its economic role in it."""

    series_id: str
    role: str = "component"


class SignalTransformStep(BaseModel):
    """One step of a declared transform chain (V1.5A whitelist)."""

    model_config = ConfigDict(extra="allow")

    type: str


class SignalSpec(BaseModel):
    """One declared signal (core, market or structural placeholder)."""

    model_config = ConfigDict(extra="forbid")

    signal_id: str
    name: str
    layer: Literal["core", "market", "structural"]
    mechanism: str
    factor: Optional[str] = None
    inputs: list[SignalInput] = Field(default_factory=list)
    transforms: list[SignalTransformStep] = Field(default_factory=list)
    momentum_transform: Optional[SignalTransformStep] = None
    # Descriptive only in V1.3: how multiple inputs combine into one composite
    # (e.g. "difference"). The actual combination is implemented by V1.5B.
    combination: Optional[str] = None
    direction: Optional[str] = None
    neutral: Optional[float] = None
    level_weight: Optional[float] = None
    momentum_weight: Optional[float] = None
    enabled: bool = True


class SignalRegistry:
    """Validated signal catalogue plus its input availability assessment."""

    def __init__(self, signals: dict[str, SignalSpec]):
        self.signals = signals

    def __len__(self) -> int:
        return len(self.signals)

    def by_layer(self, layer: str) -> dict[str, SignalSpec]:
        return {sid: s for sid, s in self.signals.items() if s.layer == layer}

    @property
    def core(self) -> dict[str, SignalSpec]:
        return self.by_layer("core")

    def referenced_series_ids(self) -> set[str]:
        ids: set[str] = set()
        for signal in self.signals.values():
            ids.update(i.series_id for i in signal.inputs)
        return ids

    def missing_series(self, available: set[str]) -> list[str]:
        """Referenced series ids with no canonical data, sorted."""
        return sorted(self.referenced_series_ids() - set(available))


@dataclass
class SignalAvailability:
    signal_id: str
    status: str
    available: list[str]
    missing: list[str]


def _load_yaml(path: Path) -> dict:
    path = Path(path)
    if not path.exists():
        raise SignalConfigError(f"Signal registry file not found: {path}")
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
    except yaml.YAMLError as exc:
        raise SignalConfigError(f"signals.yaml is not valid YAML: {path}\n{exc}") from exc
    if not isinstance(data, dict):
        raise SignalConfigError(f"signals.yaml must contain a YAML mapping at top level: {path}")
    return data


def _validate_transform_steps(signal_id: str, steps: list[SignalTransformStep]) -> None:
    for step in steps:
        if step.type not in TRANSFORM_REGISTRY:
            raise SignalConfigError(
                f"signals.yaml: signal '{signal_id}' declares transform type '{step.type}' "
                f"which is not in the V1.5A whitelist: {sorted(TRANSFORM_REGISTRY)}"
            )


def _validate_signal(signal_id: str, spec: SignalSpec) -> None:
    if spec.layer == "core":
        if spec.factor not in CORE_FACTORS:
            raise SignalConfigError(
                f"signals.yaml: core signal '{signal_id}' must declare a MASTER SPEC factor "
                f"(one of {', '.join(CORE_FACTORS)}), got '{spec.factor}'"
            )
        if not spec.inputs:
            raise SignalConfigError(
                f"signals.yaml: core signal '{signal_id}' must declare at least one input series"
            )
        if spec.direction not in DIRECTIONS:
            raise SignalConfigError(
                f"signals.yaml: core signal '{signal_id}' must declare direction "
                f"(one of {', '.join(DIRECTIONS)})"
            )
        if spec.neutral is None:
            raise SignalConfigError(
                f"signals.yaml: core signal '{signal_id}' must declare a neutral anchor "
                "(the raw level at which the mechanism is neutral; use 0 if none)"
            )
        weights = (spec.level_weight, spec.momentum_weight)
        if any(w is None for w in weights):
            raise SignalConfigError(
                f"signals.yaml: core signal '{signal_id}' must declare both "
                "level_weight and momentum_weight"
            )
        if spec.level_weight < 0 or spec.momentum_weight < 0:
            raise SignalConfigError(
                f"signals.yaml: signal '{signal_id}' weights must be >= 0"
            )
        if spec.level_weight + spec.momentum_weight <= 0:
            raise SignalConfigError(
                f"signals.yaml: signal '{signal_id}' level_weight + momentum_weight must be > 0"
            )
    _validate_transform_steps(signal_id, spec.transforms)
    if spec.momentum_transform is not None:
        _validate_transform_steps(signal_id, [spec.momentum_transform])


def load_signal_registry(
    path: Path, indicators_registry: Optional[dict] = None
) -> SignalRegistry:
    """Load and validate ``config/signals.yaml``.

    ``indicators_registry`` is the ``{series_id: IndicatorConfig}`` mapping from
    ``macro_compass.config.load_indicator_config``; when given, every referenced
    input series must be registered there or a ``SignalConfigError`` naming the
    offenders is raised.
    """
    raw = _load_yaml(path)
    # Canonical layout: {version, notes?, signals: {id: spec}}. A flat
    # {id: spec} mapping is also accepted (used by tests and simple files).
    entries = raw.get("signals")
    if not isinstance(entries, dict):
        entries = {k: v for k, v in raw.items() if k not in ("version", "notes")}
    signals: dict[str, SignalSpec] = {}
    for key, entry in entries.items():
        if not isinstance(entry, dict):
            raise SignalConfigError(
                f"signals.yaml: entry '{key}' must be a mapping, got {type(entry).__name__}"
            )
        entry = dict(entry)
        inline_id = entry.pop("signal_id", None)
        if inline_id is not None and inline_id != key:
            raise SignalConfigError(
                f"signals.yaml: inline signal_id '{inline_id}' does not match key '{key}'"
            )
        try:
            spec = SignalSpec(signal_id=key, **entry)
        except ValidationError as exc:
            raise SignalConfigError(f"signals.yaml: signal '{key}' is invalid:\n{exc}") from exc
        _validate_signal(key, spec)
        signals[key] = spec

    if not signals:
        raise SignalConfigError(f"signals.yaml declares no signals: {path}")

    if indicators_registry is not None:
        unknown = sorted(_referenced_but_unregistered(signals, indicators_registry))
        if unknown:
            raise SignalConfigError(
                "signals.yaml references series_id(s) not registered in indicators.yaml: "
                + ", ".join(unknown)
            )
    return SignalRegistry(signals)


def _referenced_but_unregistered(
    signals: dict[str, SignalSpec], indicators_registry: dict
) -> list[str]:
    return sorted(_registry_series_ids(signals) - set(indicators_registry))


def _registry_series_ids(signals: dict[str, SignalSpec]) -> set[str]:
    ids: set[str] = set()
    for signal in signals.values():
        ids.update(i.series_id for i in signal.inputs)
    return ids


def assess_availability(
    registry: SignalRegistry, available_series: set[str]
) -> dict[str, SignalAvailability]:
    """Assess per-signal input availability against canonical series ids.

    Core signals get READY / PARTIAL / MISSING_INPUT; market and structural
    placeholders without inputs get DECLARED (their engines are V1.6 and are
    intentionally not implemented here).
    """
    available = set(available_series)
    result: dict[str, SignalAvailability] = {}
    for signal_id, spec in registry.signals.items():
        missing = [i.series_id for i in spec.inputs if i.series_id not in available]
        found = [i.series_id for i in spec.inputs if i.series_id in available]
        if spec.layer == "core":
            if not found:
                status = MISSING_INPUT
            elif missing:
                status = PARTIAL
            else:
                status = READY
        else:
            status = MISSING_INPUT if (spec.inputs and not found) else DECLARED
        result[signal_id] = SignalAvailability(
            signal_id=signal_id, status=status, available=found, missing=missing
        )
    return result
