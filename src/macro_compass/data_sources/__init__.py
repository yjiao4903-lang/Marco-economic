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
"""

from macro_compass.data_sources.base import (
    DataSourceAdapter,
    DataSourceError,
    FetchError,
    FetchStatus,
    ManualFetchRequired,
    ProviderUnavailable,
)
from macro_compass.data_sources.registry import (
    AdapterRegistry,
    DataSourcesConfig,
    ProviderSpec,
    SeriesSource,
    load_data_sources_config,
)
from macro_compass.data_sources.updater import (
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
    "ProviderSpec",
    "SeriesSource",
    "load_data_sources_config",
    "FetchOutcome",
    "UpdateReport",
    "load_fetch_state",
    "run_update",
    "save_fetch_state",
]
