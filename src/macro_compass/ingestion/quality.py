"""Data quality checks (V1-05).

Errors block usage; warnings are reported but data is never silently
modified (no winsorizing, no interpolation, no deletion).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from macro_compass.config import IndicatorConfig

FREQUENCY_EXPECTED_MEDIAN_GAP_DAYS = {
    "monthly": (28, 35),
    "weekly": (6, 9),
    "daily": (1, 3),
}


@dataclass
class QualityReport:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.errors

    def summary(self) -> str:
        lines = ["Quality: PASS" if self.passed else "Quality: FAIL"]
        lines.extend(f"  ERROR: {e}" for e in self.errors)
        lines.extend(f"  WARN:  {w}" for w in self.warnings)
        return "\n".join(lines)


def check_quality(
    canonical: pd.DataFrame,
    registry: dict[str, IndicatorConfig],
) -> QualityReport:
    report = QualityReport()

    if canonical.empty:
        report.errors.append("no data to check - canonical dataframe is empty")
        return report

    unregistered = sorted(set(canonical["series_id"]) - set(registry))
    if unregistered:
        report.errors.append(f"unregistered series_id: {unregistered}")

    bad_dates = int(pd.to_datetime(canonical["date"], errors="coerce").isna().sum())
    if bad_dates:
        report.errors.append(f"{bad_dates} row(s) with invalid dates")

    bad_values = int(pd.to_numeric(canonical["value"], errors="coerce").isna().sum())
    if bad_values:
        report.errors.append(f"{bad_values} row(s) with non-numeric values")

    for series_id, group in canonical.groupby("series_id"):
        cfg = registry.get(series_id)
        label = cfg.name if cfg else series_id
        dates = pd.to_datetime(group["date"]).sort_values()

        if len(dates) == 0:
            report.errors.append(f"series '{label}' ({series_id}) is completely empty")
            continue

        if dates.duplicated().any():
            n = int(dates.duplicated().sum())
            report.warnings.append(
                f"series '{label}' ({series_id}): {n} duplicate date(s)"
            )

        if not dates.is_monotonic_increasing:
            report.warnings.append(
                f"series '{label}' ({series_id}): dates are not in ascending order"
            )

        gaps = dates.diff().dropna().dt.days
        if len(gaps) == 0:
            continue

        median_gap = float(gaps.median())
        if cfg is not None and cfg.frequency in FREQUENCY_EXPECTED_MEDIAN_GAP_DAYS:
            lo, hi = FREQUENCY_EXPECTED_MEDIAN_GAP_DAYS[cfg.frequency]
            if not (lo <= median_gap <= hi):
                report.warnings.append(
                    f"series '{label}' ({series_id}): declared '{cfg.frequency}' but "
                    f"median observation gap is {median_gap:.1f} days"
                )

        big_gap_threshold = max(3.0 * median_gap, 3.0)
        big_gaps = gaps[gaps > big_gap_threshold]
        if not big_gaps.empty:
            report.warnings.append(
                f"series '{label}' ({series_id}): {len(big_gaps)} unusually long gap(s), "
                f"largest {big_gaps.max():.0f} days (median gap {median_gap:.1f} days)"
            )

    return report
