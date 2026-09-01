"""Import pipeline orchestration (V1).

Flow: fingerprint -> dedup/resume check -> parse -> normalize -> validate ->
archive raw -> merge canonical parquet -> refresh DuckDB -> finalize manifest.

The manifest is used as a lightweight recovery journal. If canonical Parquet
was written but the core DuckDB refresh/finalization failed, the next import of
the same file resumes from canonical instead of treating the hash as complete
or writing the canonical rows a second time.
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
from macro_compass.storage.duckdb_store import DuckDBStore

logger = get_logger(__name__)

STATUS_IMPORTED = raw_archive.STATUS_IMPORTED
STATUS_SKIPPED = raw_archive.STATUS_SKIPPED
STATUS_CANONICAL_WRITTEN = raw_archive.STATUS_CANONICAL_WRITTEN
STATUS_FAILED_POST_CANONICAL = raw_archive.STATUS_FAILED_POST_CANONICAL
STATUS_FAILED_VALIDATION = "FAILED_VALIDATION"
STATUS_DRY_RUN = "DRY_RUN"

RESUMABLE_STATES = {STATUS_CANONICAL_WRITTEN, STATUS_FAILED_POST_CANONICAL}


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


def _archive_path_from_state(state) -> str | None:
    if state is None:
        return None
    value = state.get("archive_path", "")
    if value is None or pd.isna(value):
        return None
    value = str(value).strip()
    return value or None


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
    latest_state = raw_archive.latest_hash_state(file_hash)
    latest_status = str(latest_state["status"]) if latest_state is not None else None

    # Fully completed imports remain idempotent. SKIPPED events are ignored by
    # latest_hash_state(), so repeated checks still resolve to IMPORTED.
    if raw_archive.is_hash_imported(file_hash):
        raw_archive.record_manifest(
            file_name=path.name,
            file_hash=file_hash,
            import_time=import_time,
            rows=0,
            status=STATUS_SKIPPED,
            archive_path=None,
        )
        return ImportResult(
            status=STATUS_SKIPPED,
            file_name=path.name,
            file_hash=file_hash,
            message="File already imported (SHA256 match) - no data written",
        )

    # Even on a recovery attempt we re-parse and re-validate the supplied file.
    # This gives the DuckDB refresh the exact canonical rows without re-merging
    # them into Parquet and catches accidental file corruption before recovery.
    canonical, _norm_report = parse_wind_file(path, mapping, source, file_hash=file_hash)
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

    resume_after_canonical = latest_status in RESUMABLE_STATES
    archive_path = _archive_path_from_state(latest_state) if resume_after_canonical else None

    if resume_after_canonical:
        # The canonical merge already completed in a prior attempt. Do not
        # archive or append again unless the old event lacks its archive path.
        if archive_path is None:
            archive_path = str(raw_archive.archive_file(path, import_time))
        logger.warning(
            "resuming import after canonical write: file=%s hash=%s prior_status=%s",
            path.name,
            file_hash,
            latest_status,
        )
        written = None
    else:
        # V1-02: archive the untouched original first.
        archive_path = str(raw_archive.archive_file(path, import_time))

        # V1-03: merge into canonical parquet (latest import wins per series/date).
        written = append_canonical(canonical)
        logger.info("canonical updated: %s", written)

        # Recovery checkpoint. rows=0 because this is a state event, not a
        # second imported-data accounting row; only IMPORTED carries row count.
        raw_archive.record_manifest(
            file_name=path.name,
            file_hash=file_hash,
            import_time=import_time,
            rows=0,
            status=STATUS_CANONICAL_WRITTEN,
            archive_path=archive_path,
        )

    mirror_warning = None
    try:
        # V1-04: refresh the core DuckDB cache from the canonical rows.
        with DuckDBStore(db_path) as store:
            store.refresh_series_data(canonical)
            store.refresh_series_metadata(registry)

            # Only now is the import complete. If this write fails, the prior
            # CANONICAL_WRITTEN checkpoint keeps the hash resumable.
            raw_archive.record_manifest(
                file_name=path.name,
                file_hash=file_hash,
                import_time=import_time,
                rows=len(canonical),
                status=STATUS_IMPORTED,
                archive_path=archive_path,
            )

            # import_manifest inside DuckDB is only a rebuildable mirror. A
            # mirror refresh failure must not reopen an otherwise complete
            # import; it is logged and surfaced as an operational warning.
            try:
                store.refresh_import_manifest()
            except Exception as exc:
                logger.exception("DuckDB import_manifest mirror refresh failed for %s", path.name)
                mirror_warning = (
                    "DuckDB import_manifest mirror refresh failed; canonical data, "
                    "series_data and series_metadata are complete. Rebuild DuckDB if needed. "
                    f"Error: {exc}"
                )
    except Exception as exc:  # core post-canonical boundary: recoverable
        logger.exception("post-canonical import finalization failed for %s", path.name)
        try:
            raw_archive.record_manifest(
                file_name=path.name,
                file_hash=file_hash,
                import_time=import_time,
                rows=0,
                status=STATUS_FAILED_POST_CANONICAL,
                archive_path=archive_path,
            )
        except Exception:
            # If the manifest itself is unavailable, canonical remains
            # idempotent and the next run can safely re-merge. Preserve the
            # original failure as the user-facing error.
            logger.exception("failed to persist recovery marker for %s", path.name)
        return ImportResult(
            status=STATUS_FAILED_POST_CANONICAL,
            file_name=path.name,
            file_hash=file_hash,
            rows=len(canonical),
            archive_path=archive_path,
            canonical=canonical,
            validation_warnings=validation.warnings,
            message=(
                "Canonical data is present but core DuckDB/manifest finalization failed; "
                f"rerun the same file to resume safely. Error: {exc}"
            ),
        )

    if resume_after_canonical:
        message = "Recovered prior partial import; canonical was not written twice"
    else:
        message = f"Imported; canonical rows now: {written}"
    warnings = list(validation.warnings)
    if mirror_warning:
        warnings.append(mirror_warning)
        message = f"{message}. WARNING: {mirror_warning}"

    return ImportResult(
        status=STATUS_IMPORTED,
        file_name=path.name,
        file_hash=file_hash,
        rows=len(canonical),
        archive_path=archive_path,
        canonical=canonical,
        validation_warnings=warnings,
        message=message,
    )
