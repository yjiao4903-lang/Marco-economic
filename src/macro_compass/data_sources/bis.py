"""BIS adapter (V2.6 Structural Risk).

Serves the two quarterly BIS long series used by the Structural Risk layer:

* ``CN_CREDIT_TO_GDP_GAP`` - BIS ``WS_CREDIT_GAP(1.0)``, China, private
  non-financial sector (``P``), data type ``C`` = credit-to-GDP gap
  (actual - HP trend), in percent. Verified 2026-08-30: 1995-Q4 .. 2025-Q4,
  latest -7.6881%.
* ``CN_DSR`` - BIS ``WS_DSR(1.0)``, China, private non-financial sector,
  debt service ratio in percent. Verified 2026-08-30: 1999-Q1 .. 2025-Q4,
  latest 18.8%.

Both come from the keyless BIS bulk-CSV ZIP endpoints (``data.bis.org``,
HTTP 200). The flat CSV holds one row per observation; its header carries
suffixed dimension labels (``BORROWERS_CTY:Borrowers' country``), so the
parser normalises the header by truncating each label at ``:``. ``TIME_PERIOD``
uses ``YYYY-Qn`` and the row's ``COLLECTION`` flag is ``E: End of period``, so
a quarter is dated to its QUARTER END (e.g. ``2025-Q4`` -> ``2025-12-31``),
matching the canonical date semantics of a period observation.

The whole gap history is re-estimated each quarter (the trend is a two-sided
HP filter), so the series are routed ``update_policy: full_refresh`` with
vintage snapshots (GSCPI precedent). Because a full-refresh fetch must return
the ENTIRE series, the adapter ignores ``start_date``/``end_date`` and always
returns the full bulk file (the files are tiny: ~250KB / ~40KB).
"""

from __future__ import annotations

import csv
import io
import re
import urllib.error
import urllib.request
import zipfile

import pandas as pd

from macro_compass.data_sources.base import (
    DEFAULT_HEADERS,
    DataSourceAdapter,
    FetchError,
    _ssl_context,
    build_canonical_frame,
)

CREDIT_GAP_URL = "https://data.bis.org/static/bulk/WS_CREDIT_GAP_csv_flat.zip"
DSR_URL = "https://data.bis.org/static/bulk/WS_DSR_csv_flat.zip"

# country label used by BIS for China in both flat files (verified 2026-08-30)
_COUNTRY_CN = "CN: China"

# provider_code -> (download url, dimension selectors)
# selectors are (normalised header key, prefix) that a row's value must start
# with; they pin the China/private/gap-type slice inside the flat file.
ROUTES = {
    "CREDIT_GAP_C": (CREDIT_GAP_URL, [("TC_BORROWERS", "P"), ("CG_DTYPE", "C")]),
    "DSR_P": (DSR_URL, [("DSR_BORROWERS", "P")]),
}

_PERIOD_RE = re.compile(r"^(\d{4})-Q([1-4])$")


def _download_zip_member_text(url: str, timeout: int) -> str:
    """Download a BIS bulk zip and return the decoded first member (CSV)."""
    try:
        request = urllib.request.Request(url, headers=dict(DEFAULT_HEADERS))
        with urllib.request.urlopen(request, timeout=timeout, context=_ssl_context) as response:
            body = response.read()
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as exc:
        raise FetchError(f"BIS bulk download failed for {url}: {exc}") from exc
    try:
        archive = zipfile.ZipFile(io.BytesIO(body))
        name = archive.namelist()[0]
        return archive.read(name).decode("utf-8", errors="replace")
    except (zipfile.BadZipFile, KeyError) as exc:
        raise FetchError(f"BIS bulk response is not a readable zip for {url}: {exc}") from exc


def period_to_quarter_end(value: str):
    """``2025-Q4`` -> ``date(2025, 12, 31)`` (quarter-end dating); else None."""
    match = _PERIOD_RE.match(str(value).strip())
    if not match:
        return None
    year, quarter = int(match.group(1)), int(match.group(2))
    try:
        return (pd.Timestamp(year=year, month=quarter * 3, day=1) + pd.offsets.MonthEnd(0)).date()
    except ValueError:
        return None


def parse_bis_flat_csv(
    text: str, *, country: str = _COUNTRY_CN, selectors: list[tuple[str, str]] = ()
) -> tuple[list, list]:
    """Parse a BIS flat CSV into (dates, values) for the requested slice.

    The header may carry suffixed labels (``BORROWERS_CTY:Borrowers' country``);
    it is normalised by truncating each label at ``:``. A row is kept when its
    BORROWERS_CTY equals ``country`` and every selector's column value starts
    with the given prefix. Rows with a missing quarter / non-numeric value are
    dropped (never zero-filled). Returns dates sorted ascending.
    """
    rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        raise FetchError("BIS CSV is empty")
    header = [str(label).split(":")[0].strip() for label in rows[0]]
    required = {"BORROWERS_CTY", "TIME_PERIOD", "OBS_VALUE"}
    missing = required - set(header)
    if missing:
        raise FetchError(f"BIS CSV missing column(s): {sorted(missing)}")
    index = {key: header.index(key) for key in required}
    extra = {
        key: header.index(key)
        for key, _ in selectors
        if key in header
    }
    missing_extra = [key for key, _ in selectors if key not in extra]
    if missing_extra:
        raise FetchError(f"BIS CSV missing selector column(s): {sorted(missing_extra)}")

    i_cty, i_period, i_val = index["BORROWERS_CTY"], index["TIME_PERIOD"], index["OBS_VALUE"]
    pairs: list[tuple] = []
    for row in rows[1:]:
        if len(row) <= i_val:
            continue
        if row[i_cty].strip() != country:
            continue
        if any(not row[extra[key]].strip().startswith(prefix) for key, prefix in selectors):
            continue
        parsed = period_to_quarter_end(row[i_period])
        if parsed is None:
            continue
        try:
            value = float(row[i_val])
        except (TypeError, ValueError):
            continue
        pairs.append((parsed, value))
    pairs.sort(key=lambda pair: pair[0])
    # de-duplicate a (date, value) pair by keeping the last occurrence
    seen: dict = {}
    for day, value in pairs:
        seen[day] = value
    return list(seen.keys()), list(seen.values())


class BisAdapter(DataSourceAdapter):
    """BIS quarterly long series (credit gap / debt service ratio).

    ``provider_code`` selects the slice: ``CREDIT_GAP_C`` (WS_CREDIT_GAP, CN/P,
    Type C gap) or ``DSR_P`` (WS_DSR, CN/P). Always returns the full series
    (the bulk file is the whole history; full-refresh requires it).
    """

    def fetch(self, series_id: str, start_date=None, end_date=None) -> pd.DataFrame:
        spec = self._require_series(series_id)
        code = self._require_code(series_id)
        route = ROUTES.get(code)
        if route is None:
            raise FetchError(
                f"BIS provider_code '{code}' is not a known route "
                f"(expected {sorted(ROUTES)})"
            )
        url, selectors = route
        text = _download_zip_member_text(url, self.provider_spec.timeout_seconds)
        dates, values = parse_bis_flat_csv(text, selectors=selectors)
        if not dates:
            raise FetchError(f"BIS returned no observations for '{code}'")
        return build_canonical_frame(
            series_id,
            dates,
            values,
            provider=self.provider_id,
            source_file=url,
            series_name=series_id,
            unit="percent",
            frequency=spec.frequency,
            category=spec.category,
        )
