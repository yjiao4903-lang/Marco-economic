"""Shared test fixtures: isolate all storage paths into a temp directory."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from macro_compass import paths
from macro_compass.storage import canonical_store, raw_archive


@dataclass
class DataEnv:
    root: Path
    raw_dir: Path
    manifest_path: Path
    macro_parquet: Path
    market_parquet: Path
    duckdb_path: Path


@pytest.fixture()
def data_env(tmp_path: Path, monkeypatch) -> DataEnv:
    raw_dir = tmp_path / "raw" / "wind"
    manifest_path = raw_dir / "import_manifest.parquet"
    macro_parquet = tmp_path / "canonical" / "macro" / "macro.parquet"
    market_parquet = tmp_path / "canonical" / "market" / "market.parquet"
    duckdb_path = tmp_path / "local" / "macro.duckdb"

    monkeypatch.setattr(paths, "RAW_DIR", raw_dir)
    monkeypatch.setattr(raw_archive, "MANIFEST_PATH", manifest_path)
    monkeypatch.setattr(
        canonical_store,
        "CATEGORY_FILES",
        {"macro": macro_parquet, "market": market_parquet},
    )
    monkeypatch.setattr(paths, "DUCKDB_PATH", duckdb_path)

    return DataEnv(
        root=tmp_path,
        raw_dir=raw_dir,
        manifest_path=manifest_path,
        macro_parquet=macro_parquet,
        market_parquet=market_parquet,
        duckdb_path=duckdb_path,
    )
