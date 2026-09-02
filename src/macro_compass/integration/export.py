"""Build and write the narrow Marco -> cross-asset integration contract."""

from __future__ import annotations

from datetime import date, datetime, timezone
import hashlib
from importlib.metadata import PackageNotFoundError, version
import json
from pathlib import Path
import subprocess
from typing import Any, Mapping, Optional

from .contracts import (
    ASSET_ALIASES,
    CANONICAL_ASSET_IDS,
    DATA_FILES,
    AssetContributions,
    FactorSet,
    FactorSnapshot,
    FundamentalAsset,
    FundamentalAssetView,
    FxView,
    IntegrationManifest,
    MacroSnapshot,
    ManifestFile,
    RegimeSnapshot,
    SnapshotStatus,
    StructuralMetric,
    StructuralSnapshot,
)

DEFAULT_CONFIG_FILES = (
    "config/indicators.yaml",
    "config/data_sources.yaml",
    "config/signals.yaml",
    "config/macro.yaml",
    "config/assets.yaml",
    "config/structural.yaml",
)
CORE_FACTOR_IDS = (
    "growth",
    "inflation",
    "domestic_financial",
    "global_financial",
)
ALL_FACTOR_IDS = (*CORE_FACTOR_IDS, "fiscal")
STRUCTURAL_IDS = ("S1", "S2", "S3")


def _get(obj: Any, name: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, Mapping):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _as_date(value: date | str) -> date:
    return value if isinstance(value, date) and not isinstance(value, datetime) else date.fromisoformat(str(value)[:10])


def _confidence_block(result: Any) -> Mapping[str, Any]:
    value = _get(result, "confidence", {})
    return value if isinstance(value, Mapping) else {}


def _validate_status(value: Any, *, allowed: set[SnapshotStatus]) -> SnapshotStatus:
    try:
        status = SnapshotStatus(str(value))
    except ValueError as exc:
        raise ValueError(f"unsupported integration status: {value!r}") from exc
    if status not in allowed:
        raise ValueError(f"status {status.value!r} is not valid for this integration object")
    return status


def _factor_snapshot(result: Any) -> FactorSnapshot:
    if result is None:
        return FactorSnapshot(status=SnapshotStatus.UNAVAILABLE)
    score = _get(result, "score")
    confidence = _confidence_block(result)
    composite = confidence.get("composite")
    coverage = confidence.get("coverage")
    if score is None:
        return FactorSnapshot(
            score=None,
            confidence=float(composite) if composite is not None else None,
            coverage=float(coverage) if coverage is not None else None,
            status=SnapshotStatus.NO_SIGNAL,
        )
    return FactorSnapshot(
        score=float(score),
        confidence=float(composite) if composite is not None else 0.0,
        coverage=float(coverage) if coverage is not None else 0.0,
        status=SnapshotStatus.READY,
    )


def build_macro_snapshot(
    factors: Mapping[str, Any],
    regime: Any,
    *,
    as_of: date | str,
    data_cutoff: date | str,
    model_version: str,
) -> MacroSnapshot:
    """Adapt factor/regime engine outputs without exposing internal signal ids."""
    factor_payload = {factor: _factor_snapshot(factors.get(factor)) for factor in ALL_FACTOR_IDS}
    state = str(_get(regime, "regime", _get(regime, "state", "NO_SIGNAL")))
    growth = factor_payload["growth"]
    inflation = factor_payload["inflation"]
    if (
        growth.score is None
        or inflation.score is None
        or growth.confidence is None
        or inflation.confidence is None
    ):
        regime_confidence = None
    else:
        regime_confidence = min(growth.confidence, inflation.confidence)
    return MacroSnapshot(
        as_of=_as_date(as_of),
        data_cutoff=_as_date(data_cutoff),
        model_version=model_version,
        factors=FactorSet(**factor_payload),
        regime=RegimeSnapshot(state=state, confidence=regime_confidence),
    )


def _reading_status(reading: Any) -> SnapshotStatus:
    if reading is None:
        return SnapshotStatus.UNAVAILABLE
    engine_status = str(_get(reading, "status", ""))
    if engine_status == "MISSING_INPUT" or bool(_get(reading, "stale", False)):
        return SnapshotStatus.NO_SIGNAL
    return _validate_status(
        engine_status,
        allowed={
            SnapshotStatus.READY,
            SnapshotStatus.WARMUP,
            SnapshotStatus.PARTIAL,
        },
    )


def _reading_confidence(reading: Any) -> Optional[float]:
    if reading is None or _reading_status(reading) in (
        SnapshotStatus.NO_SIGNAL,
        SnapshotStatus.UNAVAILABLE,
    ):
        return None
    inputs_total = int(_get(reading, "inputs_total", 1) or 1)
    available = int(_get(reading, "available_count", inputs_total) or 0)
    input_coverage = min(max(available / inputs_total, 0.0), 1.0)

    window = int(_get(reading, "percentile_window", 0) or 0)
    history = int(_get(reading, "history_length", 0) or 0)
    history_coverage = min(max(history / window, 0.0), 1.0) if window else 1.0
    return input_coverage * history_coverage


def _fragility_value(reading: Any, *, property_metric: bool = False) -> Optional[float]:
    if reading is None or _reading_status(reading) in (
        SnapshotStatus.NO_SIGNAL,
        SnapshotStatus.UNAVAILABLE,
    ):
        return None
    value = _get(reading, "level" if property_metric else "percentile")
    if value is None and property_metric:
        value = _get(reading, "percentile")
    if value is None:
        return None
    value = float(value)
    if not 0.0 <= value <= 1.0:
        raise ValueError(f"fragility percentile must be in [0, 1], got {value}")
    return value


def build_structural_snapshot(
    readings: Mapping[str, Any],
    *,
    as_of: date | str,
) -> StructuralSnapshot:
    """Expose S3 directly and a simple equal-weight diagnostic structural summary.

    Every source component is already on a 0=lower fragility / 1=higher
    fragility percentile scale. The summary is intentionally not fitted and is
    never fed into the fundamental asset score.
    """
    s3 = readings.get("S3")
    property_status = _reading_status(s3)
    property_score = _fragility_value(s3, property_metric=True)
    property_confidence = _reading_confidence(s3)
    if property_score is None and property_status not in (
        SnapshotStatus.NO_SIGNAL,
        SnapshotStatus.UNAVAILABLE,
    ):
        property_status = SnapshotStatus.NO_SIGNAL
        property_confidence = None

    usable: list[tuple[float, float, SnapshotStatus]] = []
    for signal_id in STRUCTURAL_IDS:
        reading = readings.get(signal_id)
        status = _reading_status(reading)
        value = _fragility_value(reading)
        confidence = _reading_confidence(reading)
        if value is not None and confidence is not None:
            usable.append((value, confidence, status))

    if not usable:
        structural_risk = StructuralMetric(
            score=None,
            confidence=None,
            status=SnapshotStatus.UNAVAILABLE,
        )
    else:
        score = sum(item[0] for item in usable) / len(usable)
        component_coverage = len(usable) / len(STRUCTURAL_IDS)
        confidence = component_coverage * (
            sum(item[1] for item in usable) / len(usable)
        )
        status = (
            SnapshotStatus.READY
            if len(usable) == len(STRUCTURAL_IDS)
            and all(item[2] == SnapshotStatus.READY for item in usable)
            else SnapshotStatus.DEGRADED
        )
        structural_risk = StructuralMetric(
            score=score,
            confidence=confidence,
            status=status,
        )

    return StructuralSnapshot(
        as_of=_as_date(as_of),
        property_fragility=StructuralMetric(
            score=property_score,
            confidence=property_confidence,
            status=property_status,
        ),
        structural_risk=structural_risk,
    )


def canonical_asset_id(asset_id: str) -> str:
    if asset_id in ASSET_ALIASES:
        return ASSET_ALIASES[asset_id]
    if asset_id == "CNY":
        return "CNY"
    raise ValueError(f"unsupported Marco asset id for integration v1: {asset_id}")


def _asset_contributions(result: Any) -> AssetContributions:
    values = _get(result, "factor_contributions", {}) or {}
    return AssetContributions(
        growth=values.get("growth"),
        inflation=values.get("inflation"),
        domestic_financial=values.get("domestic_financial"),
        global_financial=values.get("global_financial"),
        structural=None,
    )


def _asset_status(result: Any) -> SnapshotStatus:
    return _validate_status(
        _get(result, "status", ""),
        allowed={
            SnapshotStatus.READY,
            SnapshotStatus.WARMUP,
            SnapshotStatus.PARTIAL,
            SnapshotStatus.NO_SIGNAL,
        },
    )


def _asset_fields(result: Any) -> tuple[Optional[float], Optional[float], Optional[float], SnapshotStatus]:
    status = _asset_status(result)
    score = _get(result, "score")
    confidence = _confidence_block(result)
    composite = confidence.get("composite")
    coverage = confidence.get("coverage")
    return (
        float(score) if score is not None else None,
        float(composite) if composite is not None else None,
        float(coverage) if coverage is not None else None,
        status,
    )


def build_fundamental_asset_view(
    assets: Mapping[str, Any],
    *,
    as_of: date | str,
    data_cutoff: date | str,
    model_version: str,
) -> FundamentalAssetView:
    """Alias Marco ids at the boundary; never include market confirmation."""
    normalized: dict[str, Any] = {}
    cny = None
    for source_id, result in assets.items():
        target = canonical_asset_id(str(source_id))
        if target == "CNY":
            if cny is not None:
                raise ValueError("duplicate CNY FX view")
            cny = result
            continue
        if target in normalized:
            raise ValueError(f"multiple Marco assets map to canonical id {target}")
        normalized[target] = result

    output_assets: list[FundamentalAsset] = []
    for asset_id in CANONICAL_ASSET_IDS:
        result = normalized.get(asset_id)
        if result is None:
            output_assets.append(
                FundamentalAsset(
                    asset_id=asset_id,
                    fundamental_score=None,
                    confidence=None,
                    coverage=None,
                    status=SnapshotStatus.UNAVAILABLE,
                    contributions=AssetContributions(),
                )
            )
            continue
        score, confidence, coverage, status = _asset_fields(result)
        output_assets.append(
            FundamentalAsset(
                asset_id=asset_id,
                fundamental_score=score,
                confidence=confidence,
                coverage=coverage,
                status=status,
                contributions=_asset_contributions(result),
            )
        )

    fx_views: list[FxView] = []
    if cny is not None:
        score, confidence, coverage, status = _asset_fields(cny)
        fx_views.append(
            FxView(
                asset_id="CNY",
                fundamental_score=score,
                confidence=confidence,
                coverage=coverage,
                status=status,
                contributions=_asset_contributions(cny),
            )
        )

    return FundamentalAssetView(
        as_of=_as_date(as_of),
        data_cutoff=_as_date(data_cutoff),
        model_version=model_version,
        assets=output_assets,
        fx_views=fx_views,
    )


def canonical_json_bytes(model: Any) -> bytes:
    payload = model.model_dump(mode="json") if hasattr(model, "model_dump") else model
    return (
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def hash_config_files(
    project_root: Path,
    relative_paths: tuple[str, ...] = DEFAULT_CONFIG_FILES,
) -> str:
    hasher = hashlib.sha256()
    root = Path(project_root)
    for relative in sorted(relative_paths):
        path = root / relative
        if not path.exists():
            raise FileNotFoundError(f"integration config dependency not found: {path}")
        hasher.update(relative.encode("utf-8"))
        hasher.update(b"\0")
        hasher.update(path.read_bytes())
        hasher.update(b"\0")
    return hasher.hexdigest()


def current_git_commit(project_root: Path) -> str:
    try:
        return subprocess.check_output(
            ["git", "-C", str(project_root), "rev-parse", "HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise RuntimeError("cannot resolve Marco git commit for manifest") from exc


def installed_model_version() -> str:
    try:
        return version("macro-compass")
    except PackageNotFoundError as exc:
        raise RuntimeError("macro-compass package metadata is unavailable") from exc


def export_contract_bundle(
    output_dir: Path,
    *,
    macro_snapshot: MacroSnapshot,
    structural_snapshot: StructuralSnapshot,
    fundamental_asset_view: FundamentalAssetView,
    marco_git_commit: str,
    config_hash: str,
    generated_at: Optional[datetime] = None,
) -> dict[str, Path]:
    """Write all four files and compute hashes from the exact bytes on disk."""
    if structural_snapshot.as_of != macro_snapshot.as_of:
        raise ValueError("snapshot as_of values must match")
    if (
        fundamental_asset_view.as_of != macro_snapshot.as_of
        or fundamental_asset_view.data_cutoff != macro_snapshot.data_cutoff
        or fundamental_asset_view.model_version != macro_snapshot.model_version
    ):
        raise ValueError("fundamental metadata must match macro snapshot metadata")

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    models = {
        "macro_snapshot.json": macro_snapshot,
        "structural_snapshot.json": structural_snapshot,
        "fundamental_asset_view.json": fundamental_asset_view,
    }
    paths: dict[str, Path] = {}
    files: dict[str, ManifestFile] = {}
    for name in DATA_FILES:
        payload = canonical_json_bytes(models[name])
        path = output_dir / name
        path.write_bytes(payload)
        paths[name] = path
        files[name] = ManifestFile(sha256=sha256_bytes(payload))

    timestamp = generated_at or datetime.now(timezone.utc)
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError("generated_at must be timezone-aware")

    manifest = IntegrationManifest(
        generated_at=timestamp,
        as_of=macro_snapshot.as_of,
        data_cutoff=macro_snapshot.data_cutoff,
        marco_model_version=macro_snapshot.model_version,
        marco_git_commit=marco_git_commit,
        config_hash=config_hash,
        files=files,
    )
    manifest_path = output_dir / "integration_manifest.json"
    manifest_path.write_bytes(canonical_json_bytes(manifest))
    paths["integration_manifest.json"] = manifest_path
    return paths


def export_from_results(
    output_dir: Path,
    *,
    factors: Mapping[str, Any],
    regime: Any,
    structural_readings: Mapping[str, Any],
    assets: Mapping[str, Any],
    as_of: date | str,
    data_cutoff: date | str,
    model_version: str,
    marco_git_commit: str,
    config_hash: str,
    generated_at: Optional[datetime] = None,
) -> dict[str, Path]:
    macro_snapshot = build_macro_snapshot(
        factors,
        regime,
        as_of=as_of,
        data_cutoff=data_cutoff,
        model_version=model_version,
    )
    structural_snapshot = build_structural_snapshot(
        structural_readings,
        as_of=as_of,
    )
    asset_view = build_fundamental_asset_view(
        assets,
        as_of=as_of,
        data_cutoff=data_cutoff,
        model_version=model_version,
    )
    return export_contract_bundle(
        output_dir,
        macro_snapshot=macro_snapshot,
        structural_snapshot=structural_snapshot,
        fundamental_asset_view=asset_view,
        marco_git_commit=marco_git_commit,
        config_hash=config_hash,
        generated_at=generated_at,
    )


def export_live_repository(
    *,
    today: date | str,
    output_dir: Path,
    project_root: Path,
    allow_synthetic: bool = False,
) -> dict[str, Path]:
    """Run the existing read-only engines once and export their current state.

    This deliberately omits Market Confirmation from compute_assets: the
    integration contract is fundamental-only.
    """
    import pandas as pd

    from macro_compass import paths as repo_paths
    from macro_compass.assets import compute_assets, load_asset_config
    from macro_compass.config import load_indicator_config
    from macro_compass.data_sources.registry import load_data_sources_config
    from macro_compass.macro import (
        classify_provenance,
        classify_regime,
        compute_factor,
        load_macro_config,
    )
    from macro_compass.macro.config import CORE_FACTORS
    from macro_compass.signals import load_core_computations, load_signal_registry
    from macro_compass.structural import compute_structural_readings, load_structural_config

    as_of = _as_date(today)
    today_ts = pd.Timestamp(as_of)

    indicators = load_indicator_config(repo_paths.INDICATORS_YAML)
    registry = load_signal_registry(repo_paths.SIGNALS_YAML, indicators_registry=indicators)
    macro_config = load_macro_config(repo_paths.MACRO_YAML)
    structural_config = load_structural_config(repo_paths.STRUCTURAL_YAML)
    assets_config = load_asset_config(repo_paths.ASSETS_YAML, registry=registry)
    sources_cfg = load_data_sources_config(
        repo_paths.DATA_SOURCES_YAML,
        indicator_registry=indicators,
    )

    snapshot = load_core_computations(
        registry,
        macro_config,
        allow_synthetic=allow_synthetic,
        today=today_ts,
    )
    canonical = snapshot.canonical
    if canonical.empty or "date" not in canonical.columns:
        raise RuntimeError("no canonical data available for integration export")
    dates = pd.to_datetime(canonical["date"], errors="coerce")
    eligible = dates[dates <= today_ts.normalize()].dropna()
    if eligible.empty:
        raise RuntimeError("no canonical data available on or before requested as-of")
    data_cutoff = eligible.max().date()

    provenance_by_series = classify_provenance(
        canonical.groupby("series_id")["source_file"]
        .agg(lambda values: list(values.dropna().unique()))
        .to_dict(),
        macro_config.get("synthetic_markers") or [],
    )
    source_by_series = (
        canonical.sort_values("import_time")
        .groupby("series_id")["source"]
        .last()
        .to_dict()
    )
    staleness = {
        series_id: spec.max_staleness_days
        for series_id, spec in sources_cfg.series.items()
    }

    factor_signal_ids = {
        factor: [sid for sid, spec in registry.core.items() if spec.factor == factor]
        for factor in CORE_FACTORS
    }
    factor_results = {
        factor: compute_factor(
            factor,
            factor_signal_ids[factor],
            snapshot.computations,
            macro_config,
            staleness,
            today_ts,
        )
        for factor in CORE_FACTORS
    }
    regime = classify_regime(factor_results, macro_config)

    structural_readings = compute_structural_readings(
        registry,
        structural_config,
        snapshot.series,
        today_ts,
        staleness=staleness,
        provenance_by_series=provenance_by_series,
        sources_by_series=source_by_series,
    )
    assets = compute_assets(
        assets_config,
        factor_results,
        snapshot.computations,
        macro_config,
        staleness,
        today_ts,
        factor_signal_ids=factor_signal_ids,
        market_confirmations=None,
    )

    root = Path(project_root)
    return export_from_results(
        output_dir,
        factors=factor_results,
        regime=regime,
        structural_readings=structural_readings,
        assets=assets,
        as_of=as_of,
        data_cutoff=data_cutoff,
        model_version=installed_model_version(),
        marco_git_commit=current_git_commit(root),
        config_hash=hash_config_files(root),
    )
