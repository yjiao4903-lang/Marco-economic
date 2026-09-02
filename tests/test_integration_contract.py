from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from macro_compass.integration import (
    CANONICAL_ASSET_IDS,
    build_fundamental_asset_view,
    build_macro_snapshot,
    build_structural_snapshot,
    export_from_results,
)
from macro_compass.integration.contracts import FactorSnapshot, SnapshotStatus


AS_OF = "2026-09-02"
CUTOFF = "2026-08-31"
MODEL = "0.3.0"
GIT = "6fb42d950a29540d7a306d9c932868867288553d"
CONFIG_HASH = "a" * 64
GENERATED = datetime(2026, 9, 2, 5, 30, tzinfo=timezone.utc)


def factor(score, coverage=0.9, confidence=0.8):
    return SimpleNamespace(
        score=score,
        confidence={
            "coverage": coverage,
            "freshness": 1.0,
            "source_quality": 0.8,
            "composite": confidence,
        },
    )


def reading(
    percentile,
    *,
    level=None,
    status="READY",
    stale=False,
    inputs_total=1,
    available_count=1,
    history_length=40,
    percentile_window=40,
):
    return SimpleNamespace(
        status=status,
        stale=stale,
        percentile=percentile,
        level=percentile if level is None else level,
        inputs_total=inputs_total,
        available_count=available_count,
        history_length=history_length,
        percentile_window=percentile_window,
    )


def asset(score=0.2, *, status="READY", coverage=0.75, confidence=0.8):
    return SimpleNamespace(
        status=status,
        score=score,
        confidence={"coverage": coverage, "composite": confidence},
        factor_contributions={
            "growth": 0.1 if score is not None else None,
            "inflation": -0.05 if score is not None else None,
            "domestic_financial": 0.1 if score is not None else None,
            "global_financial": 0.05 if score is not None else None,
        },
        market_confirmation=SimpleNamespace(state="RISK_ON"),  # must never leak
    )


@pytest.fixture
def factor_results():
    return {
        "growth": factor(0.4, coverage=0.8, confidence=0.9),
        "inflation": factor(-0.2, coverage=0.9, confidence=0.7),
        "domestic_financial": factor(0.3),
        "global_financial": factor(-0.1),
    }


@pytest.fixture
def structural_readings():
    return {
        "S1": reading(0.6),
        "S2": reading(0.4),
        "S3": reading(
            0.8,
            level=0.8,
            inputs_total=4,
            available_count=4,
            history_length=20,
            percentile_window=20,
        ),
    }


@pytest.fixture
def asset_results():
    return {
        "CN_EQUITY": asset(0.25),
        "HK_EQUITY": asset(0.15),
        "CN_GOV_BOND": asset(0.10),
        "CN_CREDIT": asset(0.08),
        "GOLD": asset(0.20),
        "INDUSTRIAL_COMMODITY": asset(-0.05),
        "CNY": asset(0.12),
    }


def test_macro_snapshot_schema_and_missing_fiscal(factor_results):
    snap = build_macro_snapshot(
        factor_results,
        SimpleNamespace(regime="Goldilocks"),
        as_of=AS_OF,
        data_cutoff=CUTOFF,
        model_version=MODEL,
    )
    payload = snap.model_dump(mode="json")
    assert payload["schema_version"] == "1.0"
    assert set(payload["factors"]) == {
        "growth",
        "inflation",
        "domestic_financial",
        "global_financial",
        "fiscal",
    }
    assert payload["factors"]["growth"] == {
        "score": 0.4,
        "confidence": 0.9,
        "coverage": 0.8,
        "status": "READY",
    }
    assert payload["factors"]["fiscal"] == {
        "score": None,
        "confidence": None,
        "coverage": None,
        "status": "UNAVAILABLE",
    }
    assert payload["regime"]["confidence"] == pytest.approx(0.7)


def test_structural_snapshot_schema_and_fragility_direction(structural_readings):
    snap = build_structural_snapshot(structural_readings, as_of=AS_OF)
    payload = snap.model_dump(mode="json")
    assert payload["property_fragility"]["score"] == 0.8
    assert payload["property_fragility"]["status"] == "READY"
    assert payload["fragility_scale"] == {
        "lower_fragility": 0.0,
        "higher_fragility": 1.0,
    }
    assert payload["structural_risk"]["score"] == pytest.approx(0.6)
    assert payload["structural_risk"]["status"] == "READY"


def test_fundamental_asset_view_aliases_and_canonical_ids(asset_results):
    view = build_fundamental_asset_view(
        asset_results,
        as_of=AS_OF,
        data_cutoff=CUTOFF,
        model_version=MODEL,
    )
    payload = view.model_dump(mode="json")
    assert [row["asset_id"] for row in payload["assets"]] == list(CANONICAL_ASSET_IDS)
    by_id = {row["asset_id"]: row for row in payload["assets"]}
    assert by_id["CN_EQ"]["fundamental_score"] == 0.25
    assert by_id["HK_EQ"]["fundamental_score"] == 0.15
    assert by_id["COMMODITY"]["fundamental_score"] == -0.05
    assert by_id["CN_GOV_BOND"]["fundamental_score"] == 0.10
    assert payload["fx_views"][0]["asset_id"] == "CNY"
    assert "market_confirmation" not in json.dumps(payload)


def test_missing_is_not_zero_for_unsupported_assets(asset_results):
    view = build_fundamental_asset_view(
        asset_results,
        as_of=AS_OF,
        data_cutoff=CUTOFF,
        model_version=MODEL,
    )
    by_id = {row.asset_id: row for row in view.assets}
    for asset_id in ("US_EQ", "CASH"):
        assert by_id[asset_id].status == SnapshotStatus.UNAVAILABLE
        assert by_id[asset_id].fundamental_score is None
        assert by_id[asset_id].confidence is None
        assert by_id[asset_id].coverage is None


def test_asset_confidence_coverage_and_contributions(asset_results):
    view = build_fundamental_asset_view(
        asset_results,
        as_of=AS_OF,
        data_cutoff=CUTOFF,
        model_version=MODEL,
    )
    cn_eq = next(row for row in view.assets if row.asset_id == "CN_EQ")
    assert cn_eq.confidence == 0.8
    assert cn_eq.coverage == 0.75
    assert cn_eq.contributions.growth == 0.1
    assert cn_eq.contributions.structural is None


def test_partial_property_confidence_is_coverage_times_history():
    snap = build_structural_snapshot(
        {
            "S3": reading(
                0.7,
                status="PARTIAL",
                inputs_total=4,
                available_count=3,
                history_length=10,
                percentile_window=20,
            )
        },
        as_of=AS_OF,
    )
    assert snap.property_fragility.status == SnapshotStatus.PARTIAL
    assert snap.property_fragility.confidence == pytest.approx(0.75 * 0.5)
    assert snap.structural_risk.status == SnapshotStatus.DEGRADED


def test_stale_structural_reading_exports_no_signal_not_stale_number():
    snap = build_structural_snapshot(
        {"S3": reading(0.9, stale=True, inputs_total=4, available_count=4)},
        as_of=AS_OF,
    )
    assert snap.property_fragility.status == SnapshotStatus.NO_SIGNAL
    assert snap.property_fragility.score is None
    assert snap.property_fragility.confidence is None


def test_manifest_hash_matches_exact_written_bytes(
    tmp_path, factor_results, structural_readings, asset_results
):
    paths = export_from_results(
        tmp_path / "nested" / "latest",
        factors=factor_results,
        regime=SimpleNamespace(regime="Goldilocks"),
        structural_readings=structural_readings,
        assets=asset_results,
        as_of=AS_OF,
        data_cutoff=CUTOFF,
        model_version=MODEL,
        marco_git_commit=GIT,
        config_hash=CONFIG_HASH,
        generated_at=GENERATED,
    )
    manifest = json.loads(paths["integration_manifest.json"].read_text(encoding="utf-8"))
    assert set(paths) == {
        "macro_snapshot.json",
        "structural_snapshot.json",
        "fundamental_asset_view.json",
        "integration_manifest.json",
    }
    for name in (
        "macro_snapshot.json",
        "structural_snapshot.json",
        "fundamental_asset_view.json",
    ):
        digest = hashlib.sha256(paths[name].read_bytes()).hexdigest()
        assert manifest["files"][name]["sha256"] == digest


def test_export_is_deterministic_with_fixed_generated_at(
    tmp_path, factor_results, structural_readings, asset_results
):
    kwargs = dict(
        factors=factor_results,
        regime=SimpleNamespace(regime="Goldilocks"),
        structural_readings=structural_readings,
        assets=asset_results,
        as_of=AS_OF,
        data_cutoff=CUTOFF,
        model_version=MODEL,
        marco_git_commit=GIT,
        config_hash=CONFIG_HASH,
        generated_at=GENERATED,
    )
    left = export_from_results(tmp_path / "a", **kwargs)
    right = export_from_results(tmp_path / "b", **kwargs)
    for name in left:
        assert left[name].read_bytes() == right[name].read_bytes()


def test_invalid_or_unsupported_states_fail_loudly(asset_results):
    broken = dict(asset_results)
    broken["CN_EQUITY"] = asset()
    broken["CN_EQUITY"].status = "BROKEN"
    with pytest.raises(ValueError, match="unsupported integration status"):
        build_fundamental_asset_view(
            broken,
            as_of=AS_OF,
            data_cutoff=CUTOFF,
            model_version=MODEL,
        )

    with pytest.raises(ValueError, match="unsupported Marco asset id"):
        build_fundamental_asset_view(
            {"MYSTERY_ASSET": asset()},
            as_of=AS_OF,
            data_cutoff=CUTOFF,
            model_version=MODEL,
        )


def test_ready_status_cannot_hide_missing_values():
    with pytest.raises(ValidationError, match="READY factor requires"):
        FactorSnapshot(
            score=None,
            confidence=0.5,
            coverage=0.5,
            status="READY",
        )


def test_no_data_exports_explicit_unavailable_degraded_state(tmp_path):
    paths = export_from_results(
        tmp_path / "empty",
        factors={},
        regime=None,
        structural_readings={},
        assets={},
        as_of=AS_OF,
        data_cutoff=CUTOFF,
        model_version=MODEL,
        marco_git_commit=GIT,
        config_hash=CONFIG_HASH,
        generated_at=GENERATED,
    )
    macro = json.loads(paths["macro_snapshot.json"].read_text())
    structural = json.loads(paths["structural_snapshot.json"].read_text())
    assets = json.loads(paths["fundamental_asset_view.json"].read_text())
    assert all(value["status"] == "UNAVAILABLE" for value in macro["factors"].values())
    assert macro["regime"] == {"confidence": None, "state": "NO_SIGNAL"}
    assert structural["property_fragility"]["status"] == "UNAVAILABLE"
    assert structural["structural_risk"]["status"] == "UNAVAILABLE"
    assert all(row["status"] == "UNAVAILABLE" for row in assets["assets"])


def test_missing_confidence_is_not_zero_filled():
    macro = build_macro_snapshot(
        {"growth": SimpleNamespace(score=0.2, confidence={})},
        None,
        as_of=AS_OF,
        data_cutoff=CUTOFF,
        model_version=MODEL,
    )
    assert macro.factors.growth.status == SnapshotStatus.DEGRADED
    assert macro.factors.growth.score == 0.2
    assert macro.factors.growth.confidence is None
    assert macro.factors.growth.coverage is None

    view = build_fundamental_asset_view(
        {
            "CN_EQUITY": SimpleNamespace(
                status="READY",
                score=0.2,
                confidence={},
                factor_contributions={},
            )
        },
        as_of=AS_OF,
        data_cutoff=CUTOFF,
        model_version=MODEL,
    )
    cn_eq = next(row for row in view.assets if row.asset_id == "CN_EQ")
    assert cn_eq.status == SnapshotStatus.DEGRADED
    assert cn_eq.fundamental_score == 0.2
    assert cn_eq.confidence is None
    assert cn_eq.coverage is None


def test_duplicate_alias_mapping_is_rejected(asset_results):
    duplicated = dict(asset_results)
    duplicated["CN_EQ"] = asset(0.3)
    with pytest.raises(ValueError, match="multiple Marco assets map"):
        build_fundamental_asset_view(
            duplicated,
            as_of=AS_OF,
            data_cutoff=CUTOFF,
            model_version=MODEL,
        )
