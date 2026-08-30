"""Shared filesystem layout for the project.

All paths derive from the project root (the directory containing
``pyproject.toml``), located relative to this file - no absolute or
machine-specific paths are hardcoded.
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

SRC_DIR = PROJECT_ROOT / "src"
CONFIG_DIR = PROJECT_ROOT / "config"
DATA_DIR = PROJECT_ROOT / "data"

INBOX_DIR = DATA_DIR / "inbox" / "wind"
RAW_DIR = DATA_DIR / "raw" / "wind"
CANONICAL_DIR = DATA_DIR / "canonical"
CANONICAL_MACRO_DIR = CANONICAL_DIR / "macro"
CANONICAL_MARKET_DIR = CANONICAL_DIR / "market"
LOCAL_DIR = DATA_DIR / "local"
DUCKDB_PATH = LOCAL_DIR / "macro.duckdb"
FIXTURES_DIR = DATA_DIR / "fixtures"

MACRO_PARQUET = CANONICAL_MACRO_DIR / "macro.parquet"
MARKET_PARQUET = CANONICAL_MARKET_DIR / "market.parquet"

INDICATORS_YAML = CONFIG_DIR / "indicators.yaml"
WIND_MAPPING_YAML = CONFIG_DIR / "wind_mapping.yaml"
DATA_SOURCES_YAML = CONFIG_DIR / "data_sources.yaml"
SIGNALS_YAML = CONFIG_DIR / "signals.yaml"
MACRO_YAML = CONFIG_DIR / "macro.yaml"
MARKET_YAML = CONFIG_DIR / "market.yaml"
ASSETS_YAML = CONFIG_DIR / "assets.yaml"
STRUCTURAL_YAML = CONFIG_DIR / "structural.yaml"

# V1.2 multi-source acquisition state and status outputs. All operational
# state lives under data/local/ (git-ignored, safe to delete - it is rebuilt
# on the next update run; only fetch history is lost, never data).
FETCH_STATE_PATH = LOCAL_DIR / "fetch_state.json"
DATA_STATUS_CSV = LOCAL_DIR / "data_status.csv"
MANUAL_FETCH_CSV = LOCAL_DIR / "manual_fetch_required.csv"
MISSING_SERIES_CSV = LOCAL_DIR / "missing_series.csv"
SIGNAL_SCORES_CSV = LOCAL_DIR / "signal_scores.csv"
MARKET_CONFIRMATION_CSV = LOCAL_DIR / "market_confirmation.csv"
ASSET_SCORES_CSV = LOCAL_DIR / "asset_scores.csv"
STRUCTURAL_RISK_CSV = LOCAL_DIR / "structural_risk.csv"
VINTAGE_DIR = LOCAL_DIR / "vintage"

LOGS_DIR = PROJECT_ROOT / "logs"
