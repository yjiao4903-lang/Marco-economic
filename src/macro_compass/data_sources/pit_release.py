"""PIT release-calendar validation for evidence-bearing source rows.

This module deliberately does not derive publication timestamps from an
observation/reference date or an expected lag.  Expected lag remains useful
for freshness monitoring, but it is not release evidence.  Callers must pass
actual source-calendar timestamps (or a frozen vintage timestamp that is at
least as strict); otherwise the source remains unadmitted.
"""

from __future__ import annotations

import pandas as pd

from .base import FetchError


def actual_release_metadata(
    spec,
    dates,
    *,
    release_at=None,
    available_at=None,
) -> dict:
    """Validate explicit release evidence and return canonical PIT columns.

    A configured availability rule means the series requires evidence-bearing
    temporal metadata.  ``expected_release_lag_days`` is never used to create
    ``release_at``.  This is intentional for reference-period series such as
    CPILFESL, holiday-shifted ICSA releases, and NBS monthly publications.
    """

    freshness = getattr(spec, "freshness", None)
    rule = getattr(freshness, "availability_rule", "unknown")
    if rule not in (None, "unknown", "end_of_day_after_lag"):
        raise FetchError(f"unsupported availability rule: {rule!r}")

    observations = list(dates)
    if rule in (None, "unknown") and release_at is None and available_at is None:
        return {}
    if release_at is None:
        raise FetchError(
            "actual release-calendar evidence required; observation-date lag "
            "cannot populate PIT release_at"
        )

    releases_raw = list(release_at)
    available_raw = releases_raw if available_at is None else list(available_at)
    if len(releases_raw) != len(observations):
        raise FetchError(
            f"release_at must have length {len(observations)}, got {len(releases_raw)}"
        )
    if len(available_raw) != len(observations):
        raise FetchError(
            f"available_at must have length {len(observations)}, got {len(available_raw)}"
        )

    observation_dates: list[object] = []
    releases: list[pd.Timestamp] = []
    available: list[pd.Timestamp] = []
    for raw_observation, raw_release, raw_available in zip(
        observations, releases_raw, available_raw
    ):
        try:
            observation = pd.Timestamp(raw_observation)
            release = pd.Timestamp(raw_release)
            usable = pd.Timestamp(raw_available)
        except (TypeError, ValueError) as exc:
            raise FetchError("unparseable PIT temporal evidence") from exc
        if pd.isna(observation) or pd.isna(release) or pd.isna(usable):
            raise FetchError("PIT temporal evidence cannot be missing")
        if release.tzinfo is None or usable.tzinfo is None:
            raise FetchError("PIT release_at/available_at must be timezone-aware")
        release_utc = release.tz_convert("UTC")
        usable_utc = usable.tz_convert("UTC")
        if usable_utc < release_utc:
            raise FetchError("available_at cannot precede actual release_at")
        observation_dates.append(observation.date())
        releases.append(release_utc)
        available.append(usable_utc)

    return {
        "observation_dates": observation_dates,
        "release_at": releases,
        "available_at": available,
    }


__all__ = ["actual_release_metadata"]
