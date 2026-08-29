"""Import pipeline orchestration (V1).

Flow: fingerprint -> dedup check -> parse -> normalize -> validate ->
archive raw -> merge canonical parquet -> refresh DuckDB -> record manifest.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import pandas as pd

from macro_compass.config import IndicatorConfig, WindMapping
from macro_compass.ingestion import (
    normalize_to_canonical,
    read_csv_table,
    read_excel_table,
    validate_canonical,
)
from macro_compass.logging import get_logger
from macro_compass.storage import raw_archive
from macro_compass.storage.canonical_store import append_canonical
from macro_compass.storage.raw_archive import is_hash_imported
from macro_compass.storage.duckdb_store import DuckDBStore

logger = get_logger(__name__)

STATUS_IMPORTED = raw_archive.STATUS_IMPORTED
STATUS_SKIPPED = raw_archive.STATUS_SKIPPED
STATUS_FAILED_VALIDATION = "FAILED_VALIDATION"
STATUS_DRY_RUN = "DRY_RUN"


@dataclass
class ImportResult:
    status: str
    file_name: str
    file_hash: str
    rows: int = 0
    archive_path: str | None = None
    canonical: pd.DataFrame | None = None
    validation_errors: list[str] = field(default_factory=list)
    validation_warnings: list[str] = field(default_factory=list)
    message: str = ""

    @property
    def ok(self) -> bool:
        return self.status in (STATUS_IMPORTED, STATUS_SKIPPED, STATUS_DRY_RUN)


def parse_wind_file(path: Path, mapping: WindMapping, source: str, file_hash: str | None = None):
    """Read + normalize one Wind export file into canonical long format."""
    suffix = path.suffix.lower()
    if suffix in (".xlsx", ".xlsm", ".xls"):
        df = read_excel_table(path, mapping.date_column)
    elif suffix == ".csv":
        df = read_csv_table(path, mapping.date_column)
    else:
        raise ValueError(f"Unsupported file type '{suffix}' - expected .xlsx or .csv")
    return normalize_to_canonical(df, mapping, source=source, source_file=path.name,
                                  file_hash=file_hash)


def import_wind_file(
    path: Path,
    mapping: WindMapping,
    registry: dict[str, IndicatorConfig],
    source: str = "WIND",
    dry_run: bool = False,
    db_path: Path | None = None,
) -> ImportResult:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    import_time = datetime.now()
    file_hash = raw_archive.sha256_of_file(path)

    # V1-01: the same file content must never be written twice.
    if is_hash_imported(file_hash):
        raw_archive.record_manifest(
            file_name=path.name,
            file_hash=file_hash,
            import_time=import_time,
            rows=0,
            status=raw_archive.STATUS_SKIPPED,
            archive_path=None,
        )
        return ImportResult(
            status=STATUS_SKIPPED,
            file_name=path.name,
            file_hash=file_hash,
            message="File already imported (SHA256 match) - no data written",
        )

    canonical, norm_report = parse_wind_file(path, mapping, source, file_hash=file_hash)
    validation = validate_canonical(canonical, registry)

    if not validation.passed:
        return ImportResult(
            status=STATUS_FAILED_VALIDATION,
            file_name=path.name,
            file_hash=file_hash,
            canonical=canonical,
            validation_errors=validation.errors,
            validation_warnings=validation.warnings,
            message="Validation failed - nothing was written",
        )

    if dry_run:
        return ImportResult(
            status=STATUS_DRY_RUN,
            file_name=path.name,
            file_hash=file_hash,
            rows=len(canonical),
            canonical=canonical,
            validation_warnings=validation.warnings,
            message="Dry run - nothing was written",
        )

    # V1-02: archive the untouched original first.
    archive_path = raw_archive.archive_file(path, import_time)

    # V1-03: merge into canonical parquet (latest import wins per series/date).
    written = append_canonical(canonical)
    logger.info("canonical updated: %s", written)

    # V1-01: record the manifest entry before refreshing the cache so the
    # DuckDB manifest mirror includes this import.
    raw_archive.record_manifest(
        file_name=path.name,
        file_hash=file_hash,
        import_time=import_time,
        rows=len(canonical),
        status=STATUS_IMPORTED,
        archive_path=str(archive_path),
    )

    # V1-04: refresh the DuckDB cache from the new canonical state.
    with DuckDBStore(db_path) as store:
        store.refresh_series_data(canonical)
        store.refresh_series_metadata(registry)
        store.refresh_import_manifest()

    return ImportResult(
        status=STATUS_IMPORTED,
        file_name=path.name,
        file_hash=file_hash,
        rows=len(canonical),
        archive_path=str(archive_path),
        canonical=canonical,
        validation_warnings=validation.warnings,
        message=f"Imported; canonical rows now: {written}",
    )
