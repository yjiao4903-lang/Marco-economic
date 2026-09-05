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
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pandas as pd

from macro_compass.ingestion.normalizer import CANONICAL_COLUMNS

CANONICAL_REQUIRED = ("series_id", "date", "value", "category")
# Optional provenance columns used by sources whose publication timing is
# explicitly configured.  The legacy Wind normalizer keeps the original
# CANONICAL_COLUMNS surface; source adapters opt into these fields so existing
# contract consumers are not widened by this task.
TEMPORAL_COLUMNS = ("observation_date", "release_at", "available_at")


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
    observation_dates=None,
    release_at=None,
    available_at=None,
) -> pd.DataFrame:
    """Assemble adapter output into the canonical long-format layout.

    Drops rows without a parseable date or value and returns rows sorted by
    date with exactly the canonical column order.  When temporal provenance
    is supplied, all three temporal columns are emitted and invalid temporal
    rows are dropped as a fail-closed boundary.
    """
    import_time = import_time or pd.Timestamp.now()

    date_values = list(dates)
    value_values = list(values)
    if len(date_values) != len(value_values):
        raise ValueError(
            f"dates and values must have equal length, got {len(date_values)} and "
            f"{len(value_values)}"
        )

    temporal_enabled = any(
        value is not None for value in (observation_dates, release_at, available_at)
    )
    if temporal_enabled and (release_at is None or available_at is None):
        raise ValueError(
            "observation provenance requires both release_at and available_at"
        )

    def _aligned(values_arg, default, label):
        values_list = list(default if values_arg is None else values_arg)
        if len(values_list) != len(date_values):
            raise ValueError(
                f"{label} must have length {len(date_values)}, got {len(values_list)}"
            )
        return values_list

    frame = pd.DataFrame(
        {
            "series_id": series_id,
            "date": pd.to_datetime(pd.Series(date_values), errors="coerce"),
            "value": pd.to_numeric(pd.Series(value_values, dtype="object"), errors="coerce"),
        }
    )
    if temporal_enabled:
        frame["observation_date"] = pd.to_datetime(
            pd.Series(_aligned(observation_dates, date_values, "observation_dates")),
            errors="coerce",
        )
        frame["release_at"] = pd.to_datetime(
            pd.Series(_aligned(release_at, [None] * len(date_values), "release_at")),
            errors="coerce",
            utc=True,
        )
        frame["available_at"] = pd.to_datetime(
            pd.Series(_aligned(available_at, [None] * len(date_values), "available_at")),
            errors="coerce",
            utc=True,
        )

    frame = frame.dropna(subset=["date", "value"])
    if temporal_enabled:
        frame = frame.dropna(subset=list(TEMPORAL_COLUMNS))
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

    columns = list(CANONICAL_COLUMNS)
    if temporal_enabled:
        columns.extend(TEMPORAL_COLUMNS)
    return frame[columns].sort_values("date").reset_index(drop=True)


def temporal_metadata_for_spec(spec, dates) -> dict:
    """Build conservative publication metadata from an explicit source rule.

    The project does not infer release timing from an observation date.  A
    configured ``end_of_day_after_lag`` rule means the row is considered
    available only at the end of the configured publication day in the
    configured IANA timezone.  This is a deterministic safety boundary, not
    a claim that the exact source release timestamp was observed.
    """
    freshness = getattr(spec, "freshness", None)
    rule = getattr(freshness, "availability_rule", "unknown")
    if rule in (None, "unknown"):
        return {}
    if rule != "end_of_day_after_lag":
        raise FetchError(f"unsupported availability rule: {rule!r}")

    lag_days = getattr(freshness, "expected_release_lag_days", None)
    if lag_days is None:
        raise FetchError(
            "availability rule end_of_day_after_lag requires expected_release_lag_days"
        )
    timezone_name = getattr(freshness, "publication_timezone", "UTC")
    try:
        timezone = ZoneInfo(str(timezone_name))
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise FetchError(f"invalid publication timezone: {timezone_name!r}") from exc

    observation_values = list(dates)
    observation_dates = []
    boundaries = []
    for raw_date in observation_values:
        try:
            timestamp = pd.Timestamp(raw_date)
        except (TypeError, ValueError) as exc:
            raise FetchError(f"unparseable observation date: {raw_date!r}") from exc
        if pd.isna(timestamp):
            raise FetchError(f"unparseable observation date: {raw_date!r}")
        observation_date = timestamp.date()
        observation_dates.append(observation_date)
        local_start = pd.Timestamp(observation_date).tz_localize(timezone)
        local_end = (
            local_start
            + pd.Timedelta(days=int(lag_days) + 1)
            - pd.Timedelta(nanoseconds=1)
        )
        boundaries.append(local_end.tz_convert("UTC"))

    return {
        "observation_dates": observation_dates,
        "release_at": boundaries,
        "available_at": boundaries.copy(),
    }
