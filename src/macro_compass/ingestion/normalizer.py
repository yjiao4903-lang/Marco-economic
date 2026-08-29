"""Normalize a raw wide-format table into the canonical long format."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

import pandas as pd

from macro_compass.config import WindMapping

CANONICAL_COLUMNS = [
    "series_id",
    "date",
    "value",
    "source",
    "source_file",
    "import_time",
    "series_name",
    "unit",
    "frequency",
    "category",
    "file_hash",
]


@dataclass
class NormalizationReport:
    unmapped_columns: list[str] = field(default_factory=list)
    unparseable_dates: int = 0
    unparseable_values: int = 0
    empty_rows_dropped: int = 0
    rows_per_series: dict[str, int] = field(default_factory=dict)
    date_range: tuple | None = None

    def summary(self) -> str:
        lines = [
            f"rows_per_series: {self.rows_per_series}",
            f"date_range: {self.date_range}",
            f"empty_rows_dropped: {self.empty_rows_dropped}",
            f"unparseable_dates: {self.unparseable_dates}",
            f"unparseable_values: {self.unparseable_values}",
            f"unmapped_columns: {self.unmapped_columns or 'none'}",
        ]
        return "\n".join(lines)


def normalize_to_canonical(
    df: pd.DataFrame,
    mapping: WindMapping,
    source: str,
    source_file: str,
    import_time: datetime | None = None,
    file_hash: str | None = None,
) -> tuple[pd.DataFrame, NormalizationReport]:
    """Convert a wide table (date column + one column per series) into the
    canonical long format defined by the data contract.

    - Only columns listed in ``mapping.columns`` are converted; other columns
      are reported as unmapped and ignored.
    - Rows with an unparseable date or unparseable value are dropped and
      counted in the report (never silently ignored).
    """
    if mapping.date_column not in df.columns:
        raise KeyError(
            f"Date column '{mapping.date_column}' not found in table columns: {list(df.columns)}"
        )

    report = NormalizationReport()
    import_time = import_time or datetime.now()

    date_values = pd.to_datetime(df[mapping.date_column], errors="coerce")
    report.unparseable_dates = int(date_values.isna().sum())

    mapped_frames: list[pd.DataFrame] = []
    unmapped = []
    for column in df.columns:
        if column == mapping.date_column:
            continue
        column_meta = mapping.columns.get(str(column).strip())
        if column_meta is None:
            unmapped.append(str(column))
            continue
        raw_values = pd.to_numeric(df[column], errors="coerce")
        report.unparseable_values += int((raw_values.isna() & df[column].notna()).sum())

        part = pd.DataFrame(
            {
                "series_id": column_meta.series_id,
                "date": date_values,
                "value": raw_values,
                "source": source,
                "source_file": source_file,
                "import_time": import_time,
                "series_name": column_meta.name or column_meta.series_id,
                "unit": column_meta.unit or "",
                "frequency": column_meta.frequency or "",
                "category": column_meta.category,
                "file_hash": file_hash,
            }
        )
        mapped_frames.append(part)

    report.unmapped_columns = unmapped
    if not mapped_frames:
        raise ValueError(
            "No columns matched the wind mapping. Table columns: "
            f"{list(df.columns)}. Mapped headers expected: {list(mapping.columns)}"
        )

    canonical = pd.concat(mapped_frames, ignore_index=True)

    # Drop rows without a date or without a value; count them, never hide them.
    before = len(canonical)
    canonical = canonical.dropna(subset=["date", "value"])
    report.empty_rows_dropped = before - len(canonical)

    canonical["date"] = canonical["date"].dt.date
    canonical["value"] = canonical["value"].astype(float)
    canonical = canonical.sort_values(["series_id", "date"]).reset_index(drop=True)

    report.rows_per_series = {k: int(v) for k, v in canonical["series_id"].value_counts().items()}
    if not canonical.empty:
        report.date_range = (canonical["date"].min(), canonical["date"].max())

    canonical = canonical[CANONICAL_COLUMNS]
    return canonical, report
