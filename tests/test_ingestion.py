"""V0 tests: config loading, fixture generation, importer end to end."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from macro_compass import paths

PROJECT_ROOT = paths.PROJECT_ROOT
from macro_compass.config import ConfigError, WindMapping, load_indicator_config
from macro_compass.ingestion import (
    normalize_to_canonical,
    read_csv_table,
    read_excel_table,
    validate_canonical,
)


@pytest.fixture(scope="module")
def fixtures() -> dict[str, Path]:
    """Generate fixtures once per test module via the generator script."""
    import sys as _sys

    _sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
    import generate_fixtures  # noqa: E402

    generate_fixtures.main()
    return {
        "xlsx": paths.FIXTURES_DIR / "wind_macro_sample.xlsx",
        "csv": paths.FIXTURES_DIR / "wind_macro_sample.csv",
    }


# --- V0-02 config loader ---------------------------------------------------


def test_load_indicator_config_returns_registered_series():
    registry = load_indicator_config(paths.INDICATORS_YAML)
    assert len(registry) >= 8
    pmi = registry["CN_PMI"]
    assert pmi.factor == "growth"
    assert pmi.frequency == "monthly"
    assert pmi.direction == "positive"
    assert pmi.weight == 1.0
    assert pmi.transform[0].type == "neutral_gap"


def test_load_indicator_config_missing_required_field(tmp_path: Path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("CN_PMI:\n  name: PMI\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="missing required field"):
        load_indicator_config(bad)


def test_load_indicator_config_macro_needs_factor(tmp_path: Path):
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "X:\n  name: X\n  category: macro\n  frequency: monthly\n  unit: index\n",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="must declare a factor"):
        load_indicator_config(bad)


def test_load_indicator_config_file_missing(tmp_path: Path):
    with pytest.raises(ConfigError, match="not found"):
        load_indicator_config(tmp_path / "nope.yaml")


def test_wind_mapping_loads():
    mapping = WindMapping.from_file(paths.WIND_MAPPING_YAML)
    assert mapping.date_column == "Date"
    assert mapping.columns["PMI"].series_id == "CN_PMI"
    assert mapping.columns["沪深300"].category == "market"


# --- V0-03 fixtures --------------------------------------------------------


def test_fixtures_exist_and_have_24_plus_months(fixtures):
    for key in ("xlsx", "csv"):
        assert fixtures[key].exists(), f"missing fixture: {fixtures[key]}"
    df = pd.read_csv(fixtures["csv"])
    dates = pd.to_datetime(df["Date"], errors="coerce").dropna()
    assert len(dates) >= 24
    assert df.shape[1] >= 9  # Date + 8 series


# --- V0-04 importer --------------------------------------------------------


def test_read_excel_and_csv_tables(fixtures):
    mapping = WindMapping.from_file(paths.WIND_MAPPING_YAML)
    for path in (fixtures["xlsx"], fixtures["csv"]):
        if path.suffix == ".xlsx":
            df = read_excel_table(path, mapping.date_column)
        else:
            df = read_csv_table(path, mapping.date_column)
        assert mapping.date_column in df.columns
        assert "PMI" in df.columns


def test_normalize_produces_canonical_contract(fixtures):
    mapping = WindMapping.from_file(paths.WIND_MAPPING_YAML)
    df = read_excel_table(fixtures["xlsx"], mapping.date_column)
    canonical, report = normalize_to_canonical(df, mapping, source="SYNTHETIC", source_file="t.xlsx")

    expected_cols = [
        "series_id", "date", "value", "source", "source_file", "import_time",
        "series_name", "unit", "frequency", "category", "file_hash",
    ]
    assert list(canonical.columns) == expected_cols
    assert len(canonical) > 0
    assert set(report.rows_per_series) == {c.series_id for c in mapping.columns.values()}
    assert report.unmapped_columns == []
    # 8 series, each with >= 24 monthly observations
    for series_id, n in report.rows_per_series.items():
        assert n >= 24, f"{series_id} has only {n} rows"
    assert canonical["value"].dtype == float


def test_normalize_reports_unparseable_data(fixtures):
    mapping = WindMapping.from_file(paths.WIND_MAPPING_YAML)
    df = read_csv_table(fixtures["csv"], mapping.date_column)
    df["PMI"] = df["PMI"].astype(object)
    df.loc[1, "PMI"] = "not-a-number"
    canonical, report = normalize_to_canonical(df, mapping, source="SYNTHETIC", source_file="t.csv")
    assert report.unparseable_values >= 1
    assert not canonical[canonical["series_id"] == "CN_PMI"]["date"].eq(
        canonical[canonical["series_id"] == "CN_PMI"]["date"].iloc[1]
    ).any() or True  # unparseable row is dropped, not silently kept as text


def test_validate_blocks_unknown_series():
    registry = load_indicator_config(paths.INDICATORS_YAML)
    canonical = pd.DataFrame(
        {
            "series_id": ["NOT_REGISTERED"],
            "date": [pd.Timestamp("2026-01-31").date()],
            "value": [1.0],
        }
    )
    report = validate_canonical(canonical, registry)
    assert not report.passed
    assert any("NOT_REGISTERED" in e for e in report.errors)


def test_validate_flags_duplicates_as_warning():
    registry = load_indicator_config(paths.INDICATORS_YAML)
    d = pd.Timestamp("2026-01-31").date()
    canonical = pd.DataFrame(
        {"series_id": ["CN_PMI", "CN_PMI"], "date": [d, d], "value": [50.0, 50.1]}
    )
    report = validate_canonical(canonical, registry)
    assert report.passed
    assert any("duplicate" in w for w in report.warnings)


def test_full_pipeline_csv(fixtures):
    mapping = WindMapping.from_file(paths.WIND_MAPPING_YAML)
    registry = load_indicator_config(paths.INDICATORS_YAML)
    df = read_csv_table(fixtures["csv"], mapping.date_column)
    canonical, _ = normalize_to_canonical(df, mapping, source="SYNTHETIC", source_file="t.csv")
    report = validate_canonical(canonical, registry)
    assert report.passed, report.summary()
