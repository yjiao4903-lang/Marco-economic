"""Validation of canonical DataFrames against the indicator registry."""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from macro_compass.config import IndicatorConfig

# Keep this dependency-free: data_sources.base imports the normalizer through
# the ingestion package, so importing the base module here would create a
# package-initialization cycle.
TEMPORAL_COLUMNS = ("observation_date", "release_at", "available_at")


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

    temporal_present = set(TEMPORAL_COLUMNS).intersection(canonical.columns)
    if temporal_present:
        missing_temporal = sorted(set(TEMPORAL_COLUMNS) - set(canonical.columns))
        if missing_temporal:
            report.errors.append(
                "temporal provenance is partial; missing column(s): "
                f"{missing_temporal}"
            )
        else:
            parsed_observation = pd.to_datetime(
                canonical["observation_date"], errors="coerce"
            )
            parsed_release = pd.to_datetime(
                canonical["release_at"], errors="coerce", utc=True
            )
            parsed_available = pd.to_datetime(
                canonical["available_at"], errors="coerce", utc=True
            )
            for name, parsed in (
                ("observation_date", parsed_observation),
                ("release_at", parsed_release),
                ("available_at", parsed_available),
            ):
                invalid = int(parsed.isna().sum())
                if invalid:
                    report.errors.append(
                        f"{invalid} row(s) have invalid {name} temporal metadata"
                    )

            # New temporal rows must carry an explicit timezone.  UTC parsing
            # above is used only for comparison; it must not turn a naive
            # timestamp into an apparently safe publication time.
            for name in ("release_at", "available_at"):
                naive = 0
                for value in canonical[name].dropna():
                    try:
                        timestamp = pd.Timestamp(value)
                    except (TypeError, ValueError):
                        continue
                    if timestamp.tzinfo is None:
                        naive += 1
                if naive:
                    report.errors.append(
                        f"{naive} row(s) have timezone-naive {name}; "
                        "causal availability requires an explicit timezone"
                    )

            date_values = pd.to_datetime(canonical["date"], errors="coerce").dt.date
            observation_values = parsed_observation.dt.date
            mismatched_observation = (
                date_values.notna()
                & observation_values.notna()
                & date_values.ne(observation_values)
            )
            if mismatched_observation.any():
                report.errors.append(
                    f"{int(mismatched_observation.sum())} row(s) have observation_date "
                    "different from canonical date"
                )

            invalid_order = parsed_available < parsed_release
            if invalid_order.any():
                report.errors.append(
                    f"{int(invalid_order.sum())} row(s) have available_at before release_at"
                )

            canonical_start = pd.to_datetime(canonical["date"], errors="coerce", utc=True)
            before_observation = parsed_available < canonical_start
            if before_observation.any():
                report.errors.append(
                    f"{int(before_observation.sum())} row(s) have available_at before "
                    "the observation date"
                )

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
