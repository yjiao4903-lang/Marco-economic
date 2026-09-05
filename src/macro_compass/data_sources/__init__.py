"""Multi-source data acquisition subsystem (V1.2).

Layout:
    base.py       - adapter interface, statuses, error contract, HTTP helper
    registry.py   - config/data_sources.yaml loading + adapter factory
    updater.py    - incremental update engine, fetch state, status outputs
    fred.py       - FRED (fredgraph.csv)
    oecd.py       - OECD SDMX REST API
    akshare_source.py - AKShare (optional dependency)
    chinabond.py  - ChinaBond yield curve
    chinamoney.py - ChinaMoney central parity
    pbc.py        - PBOC LPR announcements
    safe.py       - SAFE central parity announcements
    nyfed.py      - NY Fed reference rates (SOFR)
    chicagofed.py - Chicago Fed NFCI / ANFCI
    wind_manual.py - manual Wind exports (always MANUAL_REQUIRED)

W1 PIT note:
    The pre-evidence ``temporal_metadata_for_spec`` implementation in base.py
    used configured lag metadata to manufacture a publication timestamp.  The
    accepted Cross #37 evidence forbids that interpretation.  Until the helper
    is physically retired from the legacy base module, package initialization
    replaces it with ``actual_release_metadata`` so every adapter import uses
    the fail-closed actual-release gate.  This preserves the legacy module
    surface without allowing observation-date arithmetic into PIT admission.
"""

from macro_compass.data_sources import base as _base
from macro_compass.data_sources.pit_release import actual_release_metadata

# Compatibility shim: adapter modules import ``temporal_metadata_for_spec``
# from base.py.  Replace that symbol before registry/updater can import any
# adapter.  The replacement never derives release_at from observation dates.
_base.temporal_metadata_for_spec = actual_release_metadata

from macro_compass.data_sources.base import (  # noqa: E402
    DataSourceAdapter,
    DataSourceError,
    FetchError,
    FetchStatus,
    ManualFetchRequired,
    ProviderUnavailable,
)
from macro_compass.data_sources.registry import (  # noqa: E402
    AdapterRegistry,
    DataSourcesConfig,
    DerivedSeriesSpec,
    ProviderSpec,
    SeriesSource,
    load_data_sources_config,
)
from macro_compass.data_sources.derived import (  # noqa: E402
    DerivedSeriesError,
    derive_cn_dr007_spread,
    derive_configured_series,
    derive_difference,
    derive_us_10y2y_spread,
)
from macro_compass.data_sources.updater import (  # noqa: E402
    FetchOutcome,
    UpdateReport,
    load_fetch_state,
    run_update,
    save_fetch_state,
)

__all__ = [
    "DataSourceAdapter",
    "DataSourceError",
    "FetchError",
    "FetchStatus",
    "ManualFetchRequired",
    "ProviderUnavailable",
    "AdapterRegistry",
    "DataSourcesConfig",
    "DerivedSeriesSpec",
    "ProviderSpec",
    "SeriesSource",
    "load_data_sources_config",
    "DerivedSeriesError",
    "derive_cn_dr007_spread",
    "derive_configured_series",
    "derive_difference",
    "derive_us_10y2y_spread",
    "FetchOutcome",
    "UpdateReport",
    "load_fetch_state",
    "run_update",
    "save_fetch_state",
    "actual_release_metadata",
]
