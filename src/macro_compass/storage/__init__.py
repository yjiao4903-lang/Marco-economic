"""Storage layer: raw archive, canonical parquet, DuckDB cache."""

from macro_compass.storage.raw_archive import (
    MANIFEST_PATH,
    archive_file,
    is_hash_imported,
    load_manifest,
    record_manifest,
    sha256_of_file,
)
from macro_compass.storage.canonical_store import append_canonical, read_canonical
from macro_compass.storage.duckdb_store import (
    DuckDBStore,
    rebuild_duckdb_from_canonical,
)

__all__ = [
    "MANIFEST_PATH",
    "archive_file",
    "is_hash_imported",
    "load_manifest",
    "record_manifest",
    "sha256_of_file",
    "append_canonical",
    "read_canonical",
    "DuckDBStore",
    "rebuild_duckdb_from_canonical",
]
