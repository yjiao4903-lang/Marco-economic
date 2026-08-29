"""Shared fixtures for data_sources tests: isolated storage paths + a temp
indicator registry so parser/updater tests never depend on live YAML edits."""

from __future__ import annotations

from pathlib import Path

import pytest

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "data_sources"

from macro_compass import paths  # noqa: E402
from macro_compass.config import load_indicator_config  # noqa: E402

INDICATORS_YAML = """
CHN_CLI:
  name: 中国CLI领先指标
  category: macro
  factor: growth
  frequency: monthly
  unit: index

CHN_CPI_INDEX:
  name: 中国CPI指数(OECD)
  category: macro
  factor: inflation
  frequency: monthly
  unit: index

CHN_IND_PROD_INDEX:
  name: 中国工业生产指数(OECD)
  category: macro
  factor: growth
  frequency: monthly
  unit: index

CHN_RETAIL_SALES_INDEX:
  name: 中国社会消费品零售指数(OECD)
  category: macro
  factor: growth
  frequency: monthly
  unit: index

CHN_EXPORT_YOY:
  name: 中国出口同比(OECD)
  category: macro
  factor: growth
  frequency: monthly
  unit: percent

USD_CNY:
  name: 美元兑人民币
  category: macro
  factor: fx
  frequency: daily
  unit: cny_per_usd

CN_GOV_YIELD_10Y:
  name: 10年期国债收益率
  category: macro
  factor: rates
  frequency: daily
  unit: percent

CSI300:
  name: 沪深300
  category: market
  frequency: daily
  unit: index

US_SOFR:
  name: SOFR担保隔夜融资利率
  category: market
  frequency: daily
  unit: percent

ANFCI:
  name: 芝加哥联储调整后金融状况指数
  category: macro
  factor: liquidity
  frequency: weekly
  unit: index

US_REAL_YIELD_10Y:
  name: 美国10年期实际利率
  category: macro
  factor: rates
  frequency: daily
  unit: percent

USD_BROAD:
  name: 美元广义指数
  category: macro
  factor: fx
  frequency: daily
  unit: index

CN_LPR_1Y:
  name: 1年期LPR
  category: macro
  factor: rates
  frequency: monthly
  unit: percent

CHN_PMI_NEW_ORDERS:
  name: 中国制造业PMI新订单
  category: macro
  factor: growth
  frequency: monthly
  unit: index
"""


@pytest.fixture()
def indicators():
    # V1.2C: load the real config/indicators.yaml instead of a stale embedded
    # snapshot - new metadata-only series must not break the registry tests.
    return load_indicator_config(paths.INDICATORS_YAML)


@pytest.fixture()
def fixture_file():
    def _load(name: str) -> Path:
        path = FIXTURE_DIR / name
        if not path.exists():
            raise FileNotFoundError(f"fixture missing: {path}")
        return path

    return _load


@pytest.fixture()
def status_paths(tmp_path: Path, monkeypatch):
    status_csv = tmp_path / "local" / "data_status.csv"
    manual_csv = tmp_path / "local" / "manual_fetch_required.csv"
    monkeypatch.setattr(paths, "DATA_STATUS_CSV", status_csv)
    monkeypatch.setattr(paths, "MANUAL_FETCH_CSV", manual_csv)
    return status_csv, manual_csv
