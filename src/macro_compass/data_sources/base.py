"""Base building blocks for V1.2 multi-source data acquisition.

A ``DataSourceAdapter`` fetches one registered series from a single external
provider and returns a canonical-compatible DataFrame. Adapters do NOT write
any storage themselves - the updater (``updater.py``) owns canonical writes,
fetch-state bookkeeping and status reporting.

Error contract (used by the updater to decide between FAILED /
FALLBACK_USED / MANUAL_REQUIRED):

- ``FetchError``          - the provider was reachable but the request or
                            parsing failed; the updater may try the fallback.
- ``ProviderUnavailable`` - the provider cannot run at all on this machine
                            (e.g. optional dependency missing); treated as
                            MANUAL_REQUIRED.
- ``ManualFetchRequired`` - the provider is by definition manual (Wind);
                            never retried, reported as MANUAL_REQUIRED.

Any other exception is caught by the updater as a generic failure so a single
broken provider can never abort the whole update run (failure isolation).
"""

from __future__ import annotations

import urllib.error
import urllib.request
import urllib.parse
import ssl
from abc import ABC, abstractmethod
from enum import Enum
from typing import Optional

import pandas as pd

from macro_compass.ingestion.normalizer import CANONICAL_COLUMNS

CANONICAL_REQUIRED = ("series_id", "date", "value", "category")


class FetchStatus(str, Enum):
    """Per-series update status (V1.2 Task Spec)."""

    OK = "OK"
    STALE = "STALE"
    FAILED = "FAILED"
    FALLBACK_USED = "FALLBACK_USED"
    MANUAL_REQUIRED = "MANUAL_REQUIRED"


class DataSourceError(Exception):
    """Base class for all data-source failures."""


class FetchError(DataSourceError):
    """A provider request or parse failed; fallback may still be tried."""


class ProviderUnavailable(DataSourceError):
    """The provider cannot run on this machine (e.g. missing dependency)."""


class ManualFetchRequired(DataSourceError):
    """The series can only be fetched manually (e.g. via Wind export)."""


DEFAULT_HEADERS = {
    # Keep the UA a plain browser string: several CN endpoints (ChinaMoney,
    # SAFE, PBOC) WAF-block requests carrying a bot-style UA suffix.
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
    "Accept": "*/*",
}

_ssl_context = ssl.create_default_context()


def http_get(
    url: str,
    timeout: int = 30,
    headers: dict | None = None,
    data: str | bytes | None = None,
    encoding: str | None = None,
) -> str:
    """HTTP GET (or POST when ``data`` is given) returning the body as text.

    Raises ``FetchError`` with the original cause on any network / HTTP
    failure so callers never see raw urllib exceptions.
    """
    merged = {**DEFAULT_HEADERS, **(headers or {})}
    if isinstance(data, str):
        data = data.encode("utf-8")
    try:
        request = urllib.request.Request(url, data=data, headers=merged)
        with urllib.request.urlopen(request, timeout=timeout, context=_ssl_context) as response:
            body = response.read()
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as exc:
        raise FetchError(f"HTTP request failed for {url}: {exc}") from exc
    if encoding:
        return body.decode(encoding, errors="replace")
    charset = response_charset(body)
    return body.decode(charset, errors="replace")


def response_charset(body: bytes) -> str:
    """Guess a decode charset: utf-8 first, gbk fallback for CN sites."""
    try:
        body.decode("utf-8")
        return "utf-8"
    except UnicodeDecodeError:
        return "gbk"


def build_url(base: str, params: dict | None = None) -> str:
    """Append query parameters to a base URL (URL-encoded, stable order)."""
    if not params:
        return base
    query = urllib.parse.urlencode(params)
    separator = "&" if "?" in base else "?"
    return f"{base}{separator}{query}"


class DataSourceAdapter(ABC):
    """Common adapter interface.

    Concrete adapters are constructed with their provider spec and the
    mapping of the series routed to them (``series_specs``), so ``fetch``
    keeps the simple spec-defined signature ``fetch(series_id, start_date,
    end_date)`` and resolves the provider-specific code itself.
    """

    def __init__(self, provider_spec, series_specs: dict, provider_id: str = ""):
        self.provider_spec = provider_spec
        self.series_specs = series_specs
        self._provider_id = provider_id

    @property
    def provider_id(self) -> str:
        return self._provider_id or getattr(self.provider_spec, "provider_id", "")

    def _require_series(self, series_id: str):
        spec = self.series_specs.get(series_id)
        if spec is None:
            raise FetchError(
                f"series '{series_id}' is not routed to provider '{self.provider_id}'"
            )
        return spec

    def _require_code(self, series_id: str) -> str:
        spec = self._require_series(series_id)
        if not spec.provider_code:
            raise FetchError(f"series '{series_id}' has no provider_code configured")
        return spec.provider_code

    @abstractmethod
    def fetch(
        self,
        series_id: str,
        start_date=None,
        end_date=None,
    ) -> pd.DataFrame:
        """Return canonical-compatible rows for ``series_id``.

        Must contain at least ``series_id / date / value / category`` and
        only observations within ``[start_date, end_date]`` (when given).
        Raises ``DataSourceError`` subclasses on failure.
        """


def build_canonical_frame(
    series_id: str,
    dates,
    values,
    *,
    provider: str,
    source_file: str,
    series_name: str,
    unit: str,
    frequency: str,
    category: str,
    import_time: pd.Timestamp | None = None,
) -> pd.DataFrame:
    """Assemble adapter output into the canonical long-format layout.

    Drops rows without a parseable date or value and returns rows sorted by
    date with exactly the canonical column order.
    """
    import_time = import_time or pd.Timestamp.now()

    frame = pd.DataFrame(
        {
            "series_id": series_id,
            "date": pd.to_datetime(pd.Series(list(dates)), errors="coerce"),
            "value": pd.to_numeric(pd.Series(list(values), dtype="object"), errors="coerce"),
        }
    )
    frame = frame.dropna(subset=["date", "value"])
    if frame.empty:
        return frame

    frame["date"] = frame["date"].dt.date
    frame["value"] = frame["value"].astype(float)
    frame["source"] = provider.upper()
    frame["source_file"] = source_file
    frame["import_time"] = import_time
    frame["series_name"] = series_name
    frame["unit"] = unit
    frame["frequency"] = frequency
    frame["category"] = category
    frame["file_hash"] = None

    return frame[CANONICAL_COLUMNS].sort_values("date").reset_index(drop=True)
