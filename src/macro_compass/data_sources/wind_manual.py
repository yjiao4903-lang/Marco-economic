"""Wind manual adapter (V1.2B).

Wind has no machine-readable API in this project; its exports arrive via the
V1 manual importer (``scripts/import_wind.py``). Routing a series here makes
the updater report it as MANUAL_REQUIRED with actionable instructions, which
is exactly what manual_fetch_required.csv is for.
"""

from __future__ import annotations

import pandas as pd

from macro_compass.data_sources.base import (
    DataSourceAdapter,
    ManualFetchRequired,
    build_canonical_frame,
)

DEFAULT_INSTRUCTIONS = (
    "Export the series from Wind to data/inbox/wind/ and run: "
    "python scripts/import_wind.py <file> (register the column in "
    "config/wind_mapping.yaml first)"
)


class WindManualAdapter(DataSourceAdapter):
    def fetch(self, series_id: str, start_date=None, end_date=None) -> pd.DataFrame:
        spec = self._require_series(series_id)
        instructions = spec.manual_instructions or (
            self.provider_spec.options.get("instructions") or DEFAULT_INSTRUCTIONS
        )
        raise ManualFetchRequired(instructions)


def manual_placeholder_frame(series_id: str) -> pd.DataFrame:
    """Empty canonical-compatible frame (never written; used in tests)."""
    return pd.DataFrame(columns=["series_id", "date", "value", "category"])
