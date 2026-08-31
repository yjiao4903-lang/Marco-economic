"""DuckDB local analysis cache (V1-04).

Tables:
  series_data      - canonical long-format observations (mirror of parquet)
  series_metadata  - per-series summary (name/unit/frequency/coverage)
  import_manifest  - mirror of the append-only raw import manifest

The DuckDB file is a cache: deleting it loses nothing, and
``rebuild_duckdb_from_canonical`` recreates everything from the canonical
parquet files plus the manifest parquet.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

from macro_compass import paths
from macro_compass.storage import raw_archive
from macro_compass.storage.canonical_store import read_canonical

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS series_data (
    series_id   VARCHAR NOT NULL,
    date        DATE NOT NULL,
    value       DOUBLE,
    source      VARCHAR,
    source_file VARCHAR,
    import_time TIMESTAMP,
    file_hash   VARCHAR
);
CREATE TABLE IF NOT EXISTS series_metadata (
    series_id   VARCHAR PRIMARY KEY,
    series_name VARCHAR,
    unit        VARCHAR,
    frequency   VARCHAR,
    category    VARCHAR,
    first_date  DATE,
    last_date   DATE,
    row_count   BIGINT,
    updated_at  TIMESTAMP
);
CREATE TABLE IF NOT EXISTS import_manifest (
    file_name    VARCHAR,
    sha256       VARCHAR,
    import_time  TIMESTAMP,
    rows         BIGINT,
    status       VARCHAR,
    archive_path VARCHAR
);
"""


class DuckDBStore:
    def __init__(self, db_path: Path | None = None):
        self.db_path = Path(db_path) if db_path else paths.DUCKDB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = duckdb.connect(str(self.db_path))
        self.conn.execute(SCHEMA_SQL)

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "DuckDBStore":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # --- writes ------------------------------------------------------------

    def refresh_series_data(self, canonical: pd.DataFrame) -> int:
        """Upsert observations without truncating history.

        Incremental providers pass only a revision window.  Delete only the
        fetched ``(series_id, date)`` keys before inserting, so older
        observations already cached in DuckDB remain available.
        """
        if canonical.empty:
            return 0
        df = canonical[["series_id", "date", "value", "source", "source_file",
                        "import_time", "file_hash"]].copy()
        df["date"] = pd.to_datetime(df["date"]).dt.date
        df["import_time"] = pd.to_datetime(df["import_time"])
        self.conn.register("df_new", df)
        self.conn.execute(
            "DELETE FROM series_data AS old USING df_new AS new "
            "WHERE old.series_id = new.series_id AND old.date = new.date"
        )
        self.conn.execute("INSERT INTO series_data SELECT * FROM df_new")
        self.conn.unregister("df_new")
        return len(df)

    def refresh_series_metadata(self, registry: dict) -> int:
        """Recompute series_metadata from canonical parquet + the registry."""
        rows = []
        for category in ("macro", "market"):
            df = read_canonical(category)
            if df.empty:
                continue
            summary = df.groupby("series_id").agg(
                first_date=("date", "min"),
                last_date=("date", "max"),
                row_count=("date", "count"),
            )
            for series_id, row in summary.iterrows():
                cfg = registry.get(series_id)
                rows.append(
                    {
                        "series_id": series_id,
                        "series_name": cfg.name if cfg else series_id,
                        "unit": cfg.unit if cfg else "",
                        "frequency": cfg.frequency if cfg else "",
                        "category": category,
                        "first_date": row["first_date"],
                        "last_date": row["last_date"],
                        "row_count": int(row["row_count"]),
                        "updated_at": pd.Timestamp.now(),
                    }
                )
        self.conn.execute("DELETE FROM series_metadata")
        if rows:
            self.conn.register("df_meta", pd.DataFrame(rows))
            self.conn.execute(
                "INSERT INTO series_metadata SELECT * FROM df_meta"
            )
            self.conn.unregister("df_meta")
        return len(rows)

    def refresh_import_manifest(self) -> int:
        manifest = raw_archive.load_manifest()
        self.conn.execute("DELETE FROM import_manifest")
        if manifest.empty:
            return 0
        self.conn.register("df_manifest", manifest)
        self.conn.execute("INSERT INTO import_manifest SELECT * FROM df_manifest")
        self.conn.unregister("df_manifest")
        return len(manifest)

    # --- reads -------------------------------------------------------------

    def read_series(self, series_id: str) -> pd.DataFrame:
        return self.conn.execute(
            "SELECT series_id, date, value FROM series_data WHERE series_id = ? ORDER BY date",
            [series_id],
        ).df()

    def row_counts(self) -> dict[str, int]:
        out = {}
        for table in ("series_data", "series_metadata", "import_manifest"):
            out[table] = self.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        return out


def rebuild_duckdb_from_canonical(registry: dict, db_path: Path | None = None) -> dict[str, int]:
    """Fully rebuild the DuckDB cache from canonical parquet + manifest."""
    if db_path is None:
        paths.DUCKDB_PATH.unlink(missing_ok=True)
    with DuckDBStore(db_path) as store:
        canonical = pd.concat(
            [read_canonical("macro"), read_canonical("market")], ignore_index=True
        )
        n_data = store.refresh_series_data(canonical)
        n_meta = store.refresh_series_metadata(registry)
        n_manifest = store.refresh_import_manifest()
        counts = store.row_counts()
    counts["inserted_series_data"] = n_data
    counts["metadata_series"] = n_meta
    counts["manifest_rows"] = n_manifest
    return counts
