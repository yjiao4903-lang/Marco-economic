"""Raw file fingerprinting, import manifest and raw archiving (V1-01 / V1-02).

- Every imported file gets a SHA256 fingerprint.
- The import manifest is an append-only parquet at ``data/raw/wind/import_manifest.parquet``;
  it survives DuckDB deletion and is used to rebuild the DuckDB manifest table.
- Original files are archived under ``data/raw/wind/<year>/`` and never overwritten.
- A hash is considered fully imported only when its latest meaningful state is
  ``IMPORTED``. ``FAILED_POST_CANONICAL`` makes a caught partial import
  resumable without changing the one-row manifest contract for normal imports.
"""

from __future__ import annotations

import hashlib
import shutil
from datetime import datetime
from pathlib import Path

import pandas as pd

from macro_compass import paths

MANIFEST_PATH = paths.RAW_DIR / "import_manifest.parquet"

MANIFEST_COLUMNS = ["file_name", "sha256", "import_time", "rows", "status", "archive_path"]

STATUS_IMPORTED = "IMPORTED"
STATUS_SKIPPED = "SKIPPED_ALREADY_IMPORTED"
STATUS_FAILED_POST_CANONICAL = "FAILED_POST_CANONICAL"


def sha256_of_file(path: Path) -> str:
    """Stream a file through SHA256 so large exports stay memory-friendly."""
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_manifest() -> pd.DataFrame:
    if MANIFEST_PATH.exists():
        return pd.read_parquet(MANIFEST_PATH)
    return pd.DataFrame(columns=MANIFEST_COLUMNS)


def latest_hash_state(file_hash: str) -> pd.Series | None:
    """Return the latest meaningful manifest event for ``file_hash``.

    ``SKIPPED_ALREADY_IMPORTED`` is audit noise rather than a state transition,
    so it is ignored when deciding whether a file is complete or resumable.
    Append order is authoritative because events in one attempt can share a
    timestamp.
    """
    manifest = load_manifest()
    if manifest.empty or "sha256" not in manifest or "status" not in manifest:
        return None
    matching = manifest.loc[manifest["sha256"] == file_hash]
    if matching.empty:
        return None
    meaningful = matching.loc[matching["status"] != STATUS_SKIPPED]
    if meaningful.empty:
        return matching.iloc[-1]
    return meaningful.iloc[-1]


def is_hash_imported(file_hash: str) -> bool:
    state = latest_hash_state(file_hash)
    return state is not None and str(state["status"]) == STATUS_IMPORTED


def record_manifest(
    file_name: str,
    file_hash: str,
    import_time: datetime,
    rows: int,
    status: str,
    archive_path: str | None,
) -> None:
    """Append one manifest row. Append-only: existing rows are never modified."""
    row = pd.DataFrame(
        [
            {
                "file_name": file_name,
                "sha256": file_hash,
                "import_time": pd.Timestamp(import_time),
                "rows": rows,
                "status": status,
                "archive_path": archive_path or "",
            }
        ]
    )
    manifest = load_manifest()
    manifest = pd.concat([manifest, row], ignore_index=True)
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = MANIFEST_PATH.with_suffix(".parquet.tmp")
    manifest.to_parquet(tmp, index=False)
    tmp.replace(MANIFEST_PATH)


def archive_file(path: Path, import_time: datetime) -> Path:
    """Copy the original file into ``data/raw/wind/<year>/`` with a timestamp
    prefix. Returns the archive path; never overwrites an existing archive."""
    year_dir = paths.RAW_DIR / f"{import_time:%Y}"
    year_dir.mkdir(parents=True, exist_ok=True)
    dest = year_dir / f"{import_time:%Y%m%d_%H%M%S}_{path.name}"

    # Collisions (two imports within the same second of a same-named file)
    # must not overwrite the original archive; disambiguate with a counter.
    counter = 1
    while dest.exists():
        dest = year_dir / f"{import_time:%Y%m%d_%H%M%S}_{counter:02d}_{path.name}"
        counter += 1

    shutil.copy2(path, dest)
    return dest
