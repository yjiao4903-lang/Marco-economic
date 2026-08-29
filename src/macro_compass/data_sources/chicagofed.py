"""Chicago Fed adapter (V1.2B).

Serves the NFCI / ANFCI weekly indexes. The Chicago Fed keeps reshuffling its
download-center URLs, so the data file URL is configurable through the
provider ``options.url``; if it is not configured the adapter raises
``ProviderUnavailable`` (reported as MANUAL_REQUIRED) instead of guessing.

The parser accepts the weekly CSV layout (first column = week date, one
column per index, e.g. ``date,nfci,anfci``) and is tested against a fixture.

ANFCI is also mirrored on FRED (series ``ANFCI``), which can be wired as the
series fallback in data_sources.yaml.
"""

from __future__ import annotations

import io

import pandas as pd

from macro_compass.data_sources.base import (
    DataSourceAdapter,
    FetchError,
    ProviderUnavailable,
    build_canonical_frame,
    http_get,
)


def parse_nfci_csv(text: str, code: str) -> tuple[list, list]:
    """Parse the weekly NFCI/ANFCI CSV into (dates, values) for ``code``."""
    df = pd.read_csv(io.StringIO(text))
    lowered = {str(c).strip().lower(): c for c in df.columns}
    date_col = lowered.get("date") or lowered.get("friday_of_week") or lowered.get("weekdate") or df.columns[0]
    code_col = lowered.get(code.lower())
    if code_col is None:
        raise FetchError(f"Chicago Fed CSV has no column '{code}': {list(df.columns)}")

    dates = pd.to_datetime(df[date_col], errors="coerce")
    values = pd.to_numeric(df[code_col], errors="coerce")
    mask = dates.notna() & values.notna()
    return list(dates[mask].dt.date), list(values[mask])


class ChicagoFedAdapter(DataSourceAdapter):
    def fetch(self, series_id: str, start_date=None, end_date=None) -> pd.DataFrame:
        spec = self._require_series(series_id)
        code = self._require_code(series_id)
        url = self.provider_spec.options.get("url")
        if not url:
            raise ProviderUnavailable(
                "Chicago Fed data URL is not configured (provider option 'url'); "
                "the Chicago Fed download center changes URLs frequently - "
                "set it in config/data_sources.yaml or fetch ANFCI manually"
            )
        text = http_get(url, timeout=self.provider_spec.timeout_seconds)
        dates, values = parse_nfci_csv(text, code)
        if start_date is not None:
            start = pd.Timestamp(start_date).date()
            keep = [i for i, d in enumerate(dates) if d >= start]
            dates = [dates[i] for i in keep]
            values = [values[i] for i in keep]
        if not dates:
            raise FetchError(f"Chicago Fed returned no usable observations for '{code}'")
        return build_canonical_frame(
            series_id,
            dates,
            values,
            provider=self.provider_id,
            source_file=url,
            series_name=series_id,
            unit="",
            frequency=spec.frequency,
            category=spec.category,
        )
