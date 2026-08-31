"""V1 tests: fingerprint dedup, raw archive, canonical parquet, DuckDB rebuild, quality."""

from __future__ import annotations

import sys
from pathlib import Path

import duckdb
import pandas as pd
import pytest

from macro_compass import paths
from macro_compass.config import load_indicator_config
from macro_compass.ingestion.quality import check_quality
from macro_compass.pipeline import import_wind_file
from macro_compass.storage.canonical_store import append_canonical, read_canonical
from macro_compass.storage.duckdb_store import DuckDBStore, rebuild_duckdb_from_canonical

PROJECT_ROOT = paths.PROJECT_ROOT
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from generate_fixtures import build_fixture_frame  # noqa: E402

REGISTRY = load_indicator_config(paths.INDICATORS_YAML)


@pytest.fixture()
def sample_file(tmp_path: Path) -> Path:
    df = build_fixture_frame()
    path = tmp_path / "wind_macro_sample.xlsx"
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="data", index=False)
    return path


@pytest.fixture()
def mapping():
    from macro_compass.config import WindMapping

    return WindMapping.from_file(paths.WIND_MAPPING_YAML)


# --- V1-01 / V1-02: fingerprint, dedup, archive ------------------------------


def test_import_and_dedup(data_env, sample_file, mapping):
    result1 = import_wind_file(sample_file, mapping, REGISTRY)
    assert result1.status == "IMPORTED"
    assert result1.rows > 0

    # Same content, different file name -> still skipped by SHA256.
    copy = sample_file.with_name("renamed_copy.xlsx")
    copy.write_bytes(sample_file.read_bytes())
    result2 = import_wind_file(copy, mapping, REGISTRY)
    assert result2.status == "SKIPPED_ALREADY_IMPORTED"

    # Manifest records both attempts.
    manifest = pd.read_parquet(data_env.manifest_path)
    assert list(manifest["status"]) == ["IMPORTED", "SKIPPED_ALREADY_IMPORTED"]


def test_raw_archive_preserves_original(data_env, sample_file, mapping):
    import_wind_file(sample_file, mapping, REGISTRY)
    archives = list(data_env.raw_dir.rglob("*.xlsx"))
    assert len(archives) == 1
    assert archives[0].read_bytes() == sample_file.read_bytes()


def test_failed_validation_writes_nothing(data_env, tmp_path, mapping):
    # A mapping entry pointing to an unregistered series_id must be blocked.
    from macro_compass.config import MappingColumn

    bad_columns = dict(mapping.columns)
    bad_columns["PMI"] = MappingColumn(
        series_id="GHOST_SERIES", category="macro", frequency="monthly", unit="index"
    )
    bad_mapping = mapping.model_copy(update={"columns": bad_columns})

    path = tmp_path / "bad_mapping.xlsx"
    df = build_fixture_frame()
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="data", index=False)

    result = import_wind_file(path, bad_mapping, REGISTRY)
    assert result.status == "FAILED_VALIDATION"
    assert not data_env.macro_parquet.exists()
    assert not data_env.duckdb_path.exists()
    assert not data_env.manifest_path.exists()


# --- V1-03 / V1-04: canonical parquet + DuckDB -------------------------------


def test_canonical_split_and_duckdb_sync(data_env, sample_file, mapping):
    import_wind_file(sample_file, mapping, REGISTRY)

    macro = pd.read_parquet(data_env.macro_parquet)
    market = pd.read_parquet(data_env.market_parquet)
    assert set(macro["category"]) == {"macro"}
    assert set(market["category"]) == {"market"}
    assert {"CN_PMI", "CN_CPI_YOY", "USD_CNY"} <= set(macro["series_id"])
    assert {"CSI300", "GOLD"} <= set(market["series_id"])

    with DuckDBStore(data_env.duckdb_path) as store:
        counts = store.row_counts()
    assert counts["series_data"] == len(macro) + len(market)
    assert counts["series_metadata"] >= 8
    assert counts["import_manifest"] == 1


def test_overlapping_new_file_updates_instead_of_duplicating(data_env, tmp_path, mapping):
    # Import a fixture, then a second file that overlaps all dates.
    df1 = build_fixture_frame()
    p1 = tmp_path / "first.xlsx"
    with pd.ExcelWriter(p1, engine="openpyxl") as w:
        df1.to_excel(w, sheet_name="data", index=False)
    import_wind_file(p1, mapping, REGISTRY)

    df2 = build_fixture_frame(seed=999)  # different values, same dates
    df2 = df2.dropna(how="all")
    p2 = tmp_path / "second.xlsx"
    with pd.ExcelWriter(p2, engine="openpyxl") as w:
        df2.to_excel(w, sheet_name="data", index=False)
    import_wind_file(p2, mapping, REGISTRY)

    macro = pd.read_parquet(data_env.macro_parquet)
    dup = macro.duplicated(subset=["series_id", "date"]).sum()
    assert dup == 0, "overlapping imports must not create duplicate (series_id, date) rows"

    with DuckDBStore(data_env.duckdb_path) as store:
        db_dup = store.conn.execute(
            "SELECT COUNT(*) FROM (SELECT series_id, date, COUNT(*) c "
            "FROM series_data GROUP BY 1, 2 HAVING c > 1)"
        ).fetchone()[0]
    assert db_dup == 0


def test_append_normalizes_new_timestamp_against_existing_date(data_env):
    """The canonical write boundary accepts mixed legacy and adapter date types."""
    common = {
        "series_id": ["S1"],
        "value": [1.0],
        "source": ["fake"],
        "source_file": ["fake://old"],
        "import_time": [pd.Timestamp("2026-08-01")],
        "series_name": ["S1"],
        "unit": ["index"],
        "frequency": ["daily"],
        "category": ["macro"],
        "file_hash": [None],
    }
    existing = pd.DataFrame({**common, "date": [pd.Timestamp("2026-08-01").date()]})
    append_canonical(existing)

    revised = pd.DataFrame({
        **{**common, "value": [2.0], "source_file": ["fake://new"],
           "import_time": [pd.Timestamp("2026-08-02")]},
        "date": [pd.Timestamp("2026-08-01")],
    })
    result = append_canonical(revised)

    stored = read_canonical("macro")
    assert result == {"macro": 1}
    assert len(stored) == 1
    assert stored.loc[0, "value"] == 2.0
    assert stored.loc[0, "date"] == pd.Timestamp("2026-08-01").date()


def test_rebuild_db_from_canonical(data_env, sample_file, mapping):
    import_wind_file(sample_file, mapping, REGISTRY)

    with DuckDBStore(data_env.duckdb_path) as store:
        before = store.read_series("CN_PMI")

    data_env.duckdb_path.unlink()
    counts = rebuild_duckdb_from_canonical(REGISTRY)

    with DuckDBStore(data_env.duckdb_path) as store:
        after = store.read_series("CN_PMI")
        counts_live = store.row_counts()

    pd.testing.assert_frame_equal(before, after)
    assert counts_live["series_data"] == counts["series_data"] > 0
    assert counts_live["import_manifest"] == 1, "manifest must survive DuckDB deletion"


def test_incremental_duckdb_refresh_preserves_older_history(data_env):
    """A revision-window frame must upsert keys, not replace the whole series."""
    old = pd.DataFrame({
        "series_id": ["S1", "S1"],
        "date": pd.to_datetime(["2026-01-01", "2026-02-01"]),
        "value": [1.0, 2.0], "source": ["x", "x"],
        "source_file": ["a", "a"], "import_time": [pd.Timestamp("2026-02-02")] * 2,
        "file_hash": ["h1", "h1"],
    })
    revision = old.iloc[[1]].copy()
    revision["value"] = 20.0
    with DuckDBStore(data_env.duckdb_path) as store:
        store.refresh_series_data(old)
        store.refresh_series_data(revision)
        result = store.read_series("S1")
    assert list(result["date"].astype(str)) == ["2026-01-01", "2026-02-01"]
    assert list(result["value"]) == [1.0, 20.0]


# --- V1-05: quality checks ---------------------------------------------------


def test_quality_flags_frequency_and_gaps():
    registry = dict(REGISTRY)
    # 10 days apart is not monthly -> frequency anomaly expected.
    dates = pd.date_range("2026-01-01", periods=12, freq="10D")
    canonical = pd.DataFrame(
        {"series_id": ["CN_PMI"] * 12, "date": dates.date, "value": [50.0] * 12}
    )
    report = check_quality(canonical, registry)
    assert report.passed
    assert any("median observation gap" in w for w in report.warnings)


def test_quality_flags_unregistered_and_duplicates():
    registry = dict(REGISTRY)
    d = pd.Timestamp("2026-01-31").date()
    canonical = pd.DataFrame(
        {
            "series_id": ["GHOST", "CN_PMI", "CN_PMI"],
            "date": [d, d, d],
            "value": [1.0, 50.0, 50.0],
        }
    )
    report = check_quality(canonical, registry)
    assert not report.passed
    assert any("GHOST" in e for e in report.errors)
    assert any("duplicate date" in w for w in report.warnings)
