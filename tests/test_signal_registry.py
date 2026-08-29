"""V1.3 Signal Registry tests: coverage, validation, availability."""

from __future__ import annotations

from pathlib import Path

import pytest

from macro_compass import paths
from macro_compass.config import load_indicator_config
from macro_compass.signals import (
    DECLARED,
    MISSING_INPUT,
    PARTIAL,
    READY,
    SignalConfigError,
    assess_availability,
    load_signal_registry,
)

CORE_IDS = {f"G{i}" for i in range(1, 6)} | {f"I{i}" for i in range(1, 4)} | {
    f"D{i}" for i in range(1, 5)
} | {f"X{i}" for i in range(1, 4)}
MARKET_IDS = {f"M{i}" for i in range(1, 7)}
STRUCTURAL_IDS = {f"S{i}" for i in range(1, 4)}

MASTER_SPEC_FACTORS = {"growth", "inflation", "domestic_financial", "global_financial"}


@pytest.fixture(scope="module")
def registry():
    indicators = load_indicator_config(paths.INDICATORS_YAML)
    return load_signal_registry(paths.SIGNALS_YAML, indicators_registry=indicators)


# --- real config/signals.yaml -------------------------------------------------


def test_registry_covers_15_6_3(registry) -> None:
    assert set(registry.core) == CORE_IDS
    assert set(registry.by_layer("market")) == MARKET_IDS
    assert set(registry.by_layer("structural")) == STRUCTURAL_IDS
    assert len(registry) == 24


def test_core_signals_have_required_fields(registry) -> None:
    for signal_id, spec in registry.core.items():
        assert spec.mechanism.strip(), signal_id
        assert spec.factor in MASTER_SPEC_FACTORS, signal_id
        assert spec.inputs, signal_id
        assert spec.direction in ("positive", "negative"), signal_id
        assert spec.neutral is not None, signal_id
        assert spec.level_weight + spec.momentum_weight > 0, signal_id
        assert spec.transforms or spec.combination, signal_id


def test_core_transform_chains_use_whitelist(registry) -> None:
    from macro_compass.transforms import TRANSFORM_REGISTRY

    for spec in registry.signals.values():
        for step in spec.transforms:
            assert step.type in TRANSFORM_REGISTRY, (spec.signal_id, step.type)
        if spec.momentum_transform is not None:
            assert spec.momentum_transform.type in TRANSFORM_REGISTRY


def test_market_structural_are_placeholders(registry) -> None:
    # Placeholders declare layer + mechanism but no scoring config (V1.6).
    for signal_id in MARKET_IDS | STRUCTURAL_IDS:
        spec = registry.signals[signal_id]
        assert spec.mechanism.strip(), signal_id
        assert spec.level_weight is None
        assert spec.momentum_weight is None


def test_signals_reference_registered_series_only(registry) -> None:
    indicators = load_indicator_config(paths.INDICATORS_YAML)
    unknown = registry.referenced_series_ids() - set(indicators)
    assert not unknown


# --- validation errors ----------------------------------------------------------


def _write_registry(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "signals.yaml"
    path.write_text(f"signals:\n{body}", encoding="utf-8")
    return path


VALID_SIGNAL = """
  T1:
    name: Test
    layer: core
    factor: growth
    mechanism: test mechanism
    inputs:
      - series_id: CN_PMI
        role: level
    transforms:
      - type: neutral_gap
        reference: 50
    direction: positive
    neutral: 0
    level_weight: 0.5
    momentum_weight: 0.5
"""


def test_unknown_series_id_raises_clear_error(tmp_path: Path) -> None:
    path = _write_registry(tmp_path, VALID_SIGNAL.replace("CN_PMI", "NOT_A_SERIES"))
    indicators = load_indicator_config(paths.INDICATORS_YAML)
    with pytest.raises(SignalConfigError, match="NOT_A_SERIES"):
        load_signal_registry(path, indicators_registry=indicators)


def test_unknown_transform_type_rejected(tmp_path: Path) -> None:
    path = _write_registry(
        tmp_path, VALID_SIGNAL.replace("neutral_gap", "zscore")
    )
    with pytest.raises(SignalConfigError, match="whitelist"):
        load_signal_registry(path)


CORE_BODY = """
  T1:
    name: Test
    layer: core
    mechanism: test mechanism
    inputs:
      - series_id: CN_PMI
    transforms:
      - type: level
"""


@pytest.mark.parametrize(
    "field_snippet",
    [
        "    factor: boom\n    direction: positive\n    neutral: 0\n"
        "    level_weight: 0.5\n    momentum_weight: 0.5\n",
        "    factor: growth\n    neutral: 0\n    level_weight: 0.5\n"
        "    momentum_weight: 0.5\n",
        "    factor: growth\n    direction: positive\n    level_weight: 0.5\n"
        "    momentum_weight: 0.5\n",
    ],
    ids=["bad-factor", "missing-direction", "missing-neutral"],
)
def test_core_signal_required_fields_enforced(tmp_path: Path, field_snippet: str) -> None:
    path = _write_registry(tmp_path, CORE_BODY + field_snippet)
    with pytest.raises(SignalConfigError, match="T1"):
        load_signal_registry(path)


def test_zero_total_weight_rejected(tmp_path: Path) -> None:
    body = VALID_SIGNAL.replace("momentum_weight: 0.5", "momentum_weight: 0.0").replace(
        "level_weight: 0.5", "level_weight: 0.0"
    )
    path = _write_registry(tmp_path, body)
    with pytest.raises(SignalConfigError, match="weight"):
        load_signal_registry(path)


def test_duplicate_signal_key_rejected(tmp_path: Path) -> None:
    # YAML itself collapses duplicate keys, so this is the structural check:
    # two entries mapping to the same id cannot happen via dict keys, but an
    # inline signal_id mismatch must fail loudly.
    body = VALID_SIGNAL.replace("name: Test", 'name: Test\n    signal_id: OTHER')
    path = _write_registry(tmp_path, body)
    with pytest.raises(SignalConfigError, match="signal_id"):
        load_signal_registry(path)


def test_flat_layout_accepted(tmp_path: Path) -> None:
    path = tmp_path / "signals.yaml"
    path.write_text(VALID_SIGNAL, encoding="utf-8")
    registry = load_signal_registry(path)
    assert "T1" in registry.signals


def test_missing_registry_file(tmp_path: Path) -> None:
    with pytest.raises(SignalConfigError, match="not found"):
        load_signal_registry(tmp_path / "nope.yaml")


# --- availability assessment ------------------------------------------------------


def test_availability_statuses(registry) -> None:
    # V1.6A G0: G3's live inputs are the NBS growth series; OECD indices are
    # declared fallbacks - a partial input set still yields PARTIAL with the
    # full declared-missing list.
    available = {"CHN_CLI", "CN_IND_PROD_YOY", "CSI300"}
    states = assess_availability(registry, available)
    assert states["G1"].status == READY          # CHN_CLI available
    assert states["G3"].status == PARTIAL        # industrial yes, retail no
    assert states["G4"].status == MISSING_INPUT  # property series absent
    assert states["X1"].status == MISSING_INPUT  # registered but no FRED data
    assert states["M1"].status == DECLARED       # market placeholder w/ data
    assert states["M2"].status == MISSING_INPUT  # HSI absent
    assert states["S3"].status == DECLARED       # structural placeholder, no inputs
    assert states["G3"].missing == [
        "CN_RETAIL_SALES_YOY",
        "CHN_IND_PROD_INDEX",
        "CHN_RETAIL_SALES_INDEX",
    ]


def test_missing_series_manifest_inputs(registry) -> None:
    available = {"CHN_CLI"}
    missing = registry.missing_series(available)
    assert "CHN_PMI_NEW_ORDERS" in missing       # registered, no data
    assert "CN_DR007" in missing                 # metadata-only registration
    assert "CHN_CLI" not in missing
