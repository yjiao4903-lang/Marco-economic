"""Cumulative-to-period conversion (V1.2C).

NBS/PBOC publish many monthly series as year-to-date CUMULATIVE values
(e.g. ``1-7月累计政府债券净融资 7.76万亿``). The signal layer consumes
single-period flows, so cumulative inputs must be converted BEFORE they are
stored as canonical series. The conversion is explicit and fixture-tested:

* within a calendar year, month t flow = cumulative(t) - cumulative(t-1);
* January (or the first reported month) flow = cumulative itself;
* the Jan-Feb combined release (NBS convention) reports the cumulative
  through February - it is treated as the first observation of the year;
* a cumulative value SMALLER than its predecessor (revision or rounding)
  yields a negative flow, which is kept as-is: revisions must not be
  silently dropped (no silent fallback);
* missing months produce no row (never zero-filled).

The function is pure: lists in, lists out, no I/O.
"""

from __future__ import annotations

import pandas as pd


def cumulative_to_monthly(
    months: list[int],  # month numbers (1..12), one per cumulative value
    years: list[int],   # calendar year per value
    cumulative: list[float | None],
) -> tuple[list, list]:
    """Convert year-to-date cumulative values to single-month flows.

    Returns (dates, monthly_values) sorted by date; dates are month-end
    timestamps. Values that cannot be converted (first month of a year with
    no prior year end value, missing months, None cumulative) are skipped.
    """
    if not (len(months) == len(years) == len(cumulative)):
        raise ValueError("months/years/cumulative must have equal length")

    # sort by (year, month) ascending; keep last occurrence per (year, month)
    # so later reports (revisions) win over earlier ones.
    by_period: dict[tuple[int, int], float | None] = {}
    for year, month, value in zip(years, months, cumulative):
        by_period[(int(year), int(month))] = value

    periods = sorted(by_period)
    dates: list = []
    flows: list[float] = []
    prev_key: tuple[int, int] | None = None
    prev_cum: float | None = None
    for year, month in periods:
        value = by_period[(year, month)]
        if value is None:
            # missing cumulative: cannot convert; the chain restarts here
            prev_key, prev_cum = (year, month), None
            continue
        if prev_key is not None and prev_cum is not None and prev_key[0] == year:
            flow = value - prev_cum
        else:
            # first reported period of a year (or after a gap): the
            # cumulative IS the period flow (Jan / Jan-Feb combined release)
            flow = value
        dates.append(pd.Timestamp(year=year, month=month, day=1) + pd.offsets.MonthEnd(0))
        flows.append(float(flow))
        prev_key, prev_cum = (year, month), value
    return dates, flows
