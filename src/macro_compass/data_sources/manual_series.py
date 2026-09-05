"""Manual series provider (V1.2C).

Some series have no reliable automated source but ARE public official data
that changes rarely - e.g. the PBOC 7-day reverse repo policy rate, a step
function announced in official transaction announcements. For these, the
repository carries a small, committed, source-annotated CSV under
``data/manual_series/<series_id>.csv`` (columns: ``date,value``), transcribed
from official announcements. This is REAL data with MANUAL provenance -
explicitly distinct from synthetic fixtures (which never enter production,
see the synthetic-isolation rules).

The adapter expands the step series to DAILY rows (the policy rate is
constant between announcement dates, so the step expansion is exact, not an
interpolation). ``original_source`` in data_sources.yaml must document where
the steps came from and how to update the file.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from macro_compass.data_sources.base import (
    DataSourceAdapter,
    FetchError,
    build_canonical_frame,
    temporal_metadata_for_spec,
)


def read_steps(path: Path) -> list[tuple[pd.Timestamp, float]]:
    """Read the committed step CSV into (date, value) pairs, sorted."""
    path = Path(path)
    if not path.exists():
        raise FetchError(f"manual series file not found: {path}")
    frame = pd.read_csv(path)
    for column in ("date", "value"):
        if column not in frame.columns:
            raise FetchError(f"manual series file {path} lacks a '{column}' column")
    dates = pd.to_datetime(frame["date"], errors="coerce")
    values = pd.to_numeric(frame["value"], errors="coerce")
    steps = [
        (date, value)
        for date, value in zip(dates, values)
        if pd.notna(date) and pd.notna(value)
    ]
    if not steps:
        raise FetchError(f"manual series file {path} contains no usable rows")
    return sorted(steps)


def expand_steps_daily(
    steps: list[tuple[pd.Timestamp, float]], end: pd.Timestamp
) -> tuple[list, list]:
    """Expand step changes into a dense daily series up to ``end``.

    The value stays constant between step dates (exact for policy rates).
    """
    dates: list = []
    values: list[float] = []
    current_value = steps[0][1]
    cursor = steps[0][0]
    for step_date, step_value in steps[1:]:
        while cursor < step_date:
            dates.append(cursor.date())
            values.append(current_value)
            cursor += pd.Timedelta(days=1)
        current_value = step_value
        cursor = step_date
    while cursor <= end:
        dates.append(cursor.date())
        values.append(current_value)
        cursor += pd.Timedelta(days=1)
    return dates, values


class ManualSeriesAdapter(DataSourceAdapter):
    """Serves committed manual series files (``options``/convention: the file
    is ``data/manual_series/<series_id>.csv``)."""

    def fetch(self, series_id: str, start_date=None, end_date=None) -> pd.DataFrame:
        spec = self._require_series(series_id)
        path = Path(self.provider_spec.options.get(
            "directory", "data/manual_series"
        )) / f"{series_id}.csv"
        steps = read_steps(path)
        end = pd.Timestamp(end_date) if end_date is not None else pd.Timestamp.now()
        dates, values = expand_steps_daily(steps, end)
        if start_date is not None:
            start = pd.Timestamp(start_date)
            keep = [i for i, d in enumerate(dates) if pd.Timestamp(d) >= start]
            dates = [dates[i] for i in keep]
            values = [values[i] for i in keep]
        if not dates:
            raise FetchError(f"manual series '{series_id}' has no rows after {start_date}")
        temporal = temporal_metadata_for_spec(spec, dates)
        return build_canonical_frame(
            series_id,
            dates,
            values,
            provider=self.provider_id,
            source_file=str(path).replace("\\", "/"),
            series_name=series_id,
            unit="%",
            frequency=spec.frequency,
            category=spec.category,
            **temporal,
        )
