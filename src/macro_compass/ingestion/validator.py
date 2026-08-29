"""Validation of canonical DataFrames against the indicator registry."""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from macro_compass.config import IndicatorConfig


@dataclass
class ValidationReport:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.errors

    def summary(self) -> str:
        status = "PASS" if self.passed else "FAIL"
        lines = [f"Validation: {status}"]
        for e in self.errors:
            lines.append(f"  ERROR: {e}")
        for w in self.warnings:
            lines.append(f"  WARN:  {w}")
        return "\n".join(lines)


def validate_canonical(
    canonical: pd.DataFrame,
    registry: dict[str, IndicatorConfig],
) -> ValidationReport:
    """Hard errors block the import; warnings are reported but do not block.

    Errors:
      - empty dataframe
      - series_id not registered in indicators.yaml
      - invalid (missing) dates
      - non-numeric values

    Warnings:
      - duplicate (series_id, date) observations
      - dates in descending order within a series
      - series registered as a different category than the mapping said
    """
    report = ValidationReport()

    if canonical.empty:
        report.errors.append("canonical dataframe is empty - nothing to import")
        return report

    required = {"series_id", "date", "value"}
    missing = required - set(canonical.columns)
    if missing:
        report.errors.append(f"canonical dataframe missing column(s): {sorted(missing)}")
        return report

    unknown = sorted(set(canonical["series_id"]) - set(registry))
    if unknown:
        report.errors.append(
            f"series_id not registered in indicators.yaml: {unknown}. "
            "Register them in config/indicators.yaml or fix the wind mapping."
        )

    bad_dates = canonical["date"].isna().sum()
    if bad_dates:
        report.errors.append(f"{bad_dates} row(s) have invalid dates")

    values = pd.to_numeric(canonical["value"], errors="coerce")
    bad_values = int(values.isna().sum())
    if bad_values:
        report.errors.append(f"{bad_values} row(s) have non-numeric values")

    dup_mask = canonical.duplicated(subset=["series_id", "date"], keep=False)
    if dup_mask.any():
        examples = canonical.loc[dup_mask, ["series_id", "date"]].head(5).values.tolist()
        report.warnings.append(
            f"{int(dup_mask.sum())} duplicate (series_id, date) rows, e.g. {examples}"
        )

    for series_id, group in canonical.groupby("series_id"):
        dates = pd.to_datetime(group["date"])
        if dates.is_monotonic_decreasing and len(dates) > 1:
            report.warnings.append(f"series '{series_id}': dates are in descending order")

    return report
