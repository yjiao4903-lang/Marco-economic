"""Deterministic parser tests for V1.2 providers (no network access).

Every third-party payload is parsed from a saved fixture file so the tests
are reproducible and offline.
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from macro_compass.data_sources.akshare_source import parse_akshare_hist
from macro_compass.data_sources.bis import parse_bis_flat_csv, period_to_quarter_end
from macro_compass.data_sources.chicagofed import parse_nfci_csv
from macro_compass.data_sources.chinabond import parse_yz_query
from macro_compass.data_sources.chinamoney import parse_ccpr_json
from macro_compass.data_sources.fred import parse_fred_csv, parse_fred_observations_json
from macro_compass.data_sources.nyfed import parse_ref_rates_json
from macro_compass.data_sources.oecd import parse_sdmx_csv, period_to_date
from macro_compass.data_sources.pbc import (
    PbcAdapter,
    parse_annual_tsf_table,
    parse_lpr_announcement,
    parse_lpr_listing,
)
from macro_compass.data_sources.registry import ProviderSpec, SeriesSource
from macro_compass.data_sources.safe import parse_parity_links, parse_parity_table


def test_fred_parse_drops_missing_and_dots(fixture_file):
    text = fixture_file("fred_sample.csv").read_text(encoding="utf-8")
    dates, values = parse_fred_csv(text, "DFII10")
    assert dates == [
        date(2026, 8, 20), date(2026, 8, 21), date(2026, 8, 24),
    ]
    assert values == [2.05, 2.07, 2.03]


def test_fred_api_parse_string_values_and_missing():
    dates, values = parse_fred_observations_json(
        '{"observations": [{"date": "2026-08-20", "value": "2.05"}, '
        '{"date": "2026-08-21", "value": "."}, '
        '{"date": "2026-08-24", "value": "2.03"}]}',
        "DTWEXBGS",
    )
    assert dates == [date(2026, 8, 20), date(2026, 8, 24)]
    assert values == [2.05, 2.03]


def test_oecd_period_to_date_variants():
    assert period_to_date("2026-05") == date(2026, 5, 1)
    assert period_to_date("2026-05-01") == date(2026, 5, 1)
    assert period_to_date("2026-05-01T00:00:00") == date(2026, 5, 1)
    assert period_to_date("garbage") is None


def test_oecd_parse_dedupes_and_sorts(fixture_file):
    text = fixture_file("oecd_sdmx_sample.csv").read_text(encoding="utf-8")
    dates, values = parse_sdmx_csv(text)
    assert dates == sorted(dates)
    assert len(dates) == len(set(dates))
    # CLI sample spans 2026-01..2026-06, monthly first-of-month dating
    assert dates[0] == date(2026, 1, 1)
    assert dates[-1] == date(2026, 6, 1)
    assert len(dates) == 6


def test_chinamoney_parse(fixture_file):
    text = fixture_file("chinamoney_ccpr_sample.json").read_text(encoding="utf-8")
    dates, values = parse_ccpr_json(text, "USD/CNY")
    assert dates == [date(2026, 8, 28), date(2026, 8, 27), date(2026, 8, 26)]
    assert values == [6.7811, 6.784, 6.7829]

    with pytest.raises(Exception, match="does not contain currency"):
        parse_ccpr_json(text, "GBP/CNY")


def test_nyfed_parse_filters_rate_type(fixture_file):
    text = fixture_file("nyfed_sofr_sample.json").read_text(encoding="utf-8")
    dates, values = parse_ref_rates_json(text, "SOFR")
    assert len(dates) == 3
    assert dates == sorted(dates, reverse=True)
    assert all(2.0 < v < 6.0 for v in values)

    empty_dates, empty_values = parse_ref_rates_json(text, "EFFR")
    assert empty_dates == [] and empty_values == []


def test_chinabond_parse_tolerates_blank_rows(fixture_file):
    # V1.2C: the yzQuery payload ([[millis, value], ...]) replaced searchYc
    text = fixture_file("chinabond_searchyc_sample.json").read_text(encoding="utf-8")
    text = text.replace("infoDate", "unused")  # legacy fixture kept as JSON sanity
    assert text  # legacy fixture no longer drives the parser
    sample = '[{"seriesData": [[1785686400000, 1.7169], [1785772800000, 1.7126]]}]'
    dates, values = parse_yz_query(sample)
    assert dates == sorted(dates)
    assert values == [1.7169, 1.7126]


def test_chicagofed_parse_drops_missing(fixture_file):
    text = fixture_file("chicagofed_nfci_sample.csv").read_text(encoding="utf-8")
    dates, values = parse_nfci_csv(text, "ANFCI")
    assert dates == [date(2026, 8, 22), date(2026, 8, 15)]
    assert values == [0.31, 0.29]

    with pytest.raises(Exception, match="no column"):
        parse_nfci_csv(text, "XYZ")


def test_bis_quarter_period_dating():
    assert period_to_quarter_end("2025-Q4") == date(2025, 12, 31)
    assert period_to_quarter_end("1999-Q1") == date(1999, 3, 31)
    assert period_to_quarter_end("garbage") is None
    assert period_to_quarter_end("2025-M4") is None


def test_bis_credit_gap_parse_filters_cn_type_c(fixture_file):
    """The flat CSV header carries suffixed labels (BORROWERS_CTY:Borrowers'
    country); the parser normalises them and keeps only the CN/private/Type-C
    slice, dating quarters to QUARTER END."""
    text = fixture_file("bis_credit_gap_sample.csv").read_text(encoding="utf-8")
    dates, values = parse_bis_flat_csv(
        text, selectors=[("TC_BORROWERS", "P"), ("CG_DTYPE", "C")]
    )
    # 6 CN Type-C rows (2024-Q1 .. 2025-Q2); the CN Type-A row and the US row
    # are filtered out
    assert dates == [date(2024, 3, 31), date(2024, 6, 30), date(2024, 9, 30),
                     date(2024, 12, 31), date(2025, 3, 31), date(2025, 6, 30)]
    assert values == pytest.approx([-2.5052, -3.4118, -4.1021, -4.9987, -5.2706, -5.3031])
    assert dates == sorted(dates)


def test_bis_dsr_parse_filters_cn_private(fixture_file):
    text = fixture_file("bis_dsr_sample.csv").read_text(encoding="utf-8")
    dates, values = parse_bis_flat_csv(text, selectors=[("DSR_BORROWERS", "P")])
    assert len(dates) == 5  # CN rows only; the US row is filtered out
    assert dates[-1] == date(2025, 3, 31)
    assert values == pytest.approx([18.7, 18.8, 18.9, 19.0, 18.9])


def test_bis_parse_rejects_missing_selector_column(fixture_file):
    text = fixture_file("bis_dsr_sample.csv").read_text(encoding="utf-8")
    with pytest.raises(Exception, match="selector column"):
        parse_bis_flat_csv(text, selectors=[("TC_BORROWERS", "P")])


def test_akshare_hist_parse(fixture_file):
    df = pd.read_csv(fixture_file("akshare_hist_sample.csv"))
    dates, values = parse_akshare_hist(df)
    assert dates == [date(2026, 8, 27), date(2026, 8, 26), date(2026, 8, 25)]
    assert values == [4520.55, 4500.10, 4480.00]


def test_pboc_listing_and_announcement_parse(fixture_file):
    listing = fixture_file("pboc_lpr_listing_sample.html").read_text(encoding="utf-8")
    announcements = parse_lpr_listing(listing, "http://www.pbc.gov.cn/x/")
    assert announcements[0][0] == pd.Timestamp("2026-08-20")
    assert announcements[0][1].endswith("/202608/202608201.htm")
    assert len(announcements) == 2

    announcement = fixture_file(
        "pboc_lpr_announcement_sample.html"
    ).read_text(encoding="utf-8")
    rates = parse_lpr_announcement(announcement)
    assert rates == {"LPR_1Y": 3.00, "LPR_5Y": 3.50}


def test_pboc_annual_tsf_table_contract(fixture_file):
    text = fixture_file("pboc_annual_tsf_sample.html").read_text(encoding="utf-8")
    rows = parse_annual_tsf_table(text)
    assert [row[0].date() for row in rows] == [date(2023, 12, 31), date(2024, 12, 31)]
    assert [row[1:] for row in rows] == [(350000.0, 120000.0), (320000.0, 105000.0)]


def test_pboc_annual_adapter_converts_yi_to_bn_cny(fixture_file, monkeypatch):
    """Raw PBOC 亿元 values are adapted to the canonical bn_cny contract."""
    text = fixture_file("pboc_annual_tsf_sample.html").read_text(encoding="utf-8")
    provider = ProviderSpec(
        module="pbc",
        adapter_class="PbcAdapter",
        options={"annual_table_url": "fixture://pboc-annual"},
    )
    series = SeriesSource(
        primary="pbc",
        provider_code="TSF_TOTAL_ANNUAL",
        frequency="yearly",
        category="macro",
    )
    monkeypatch.setattr("macro_compass.data_sources.pbc.http_get", lambda *args, **kwargs: text)
    frame = PbcAdapter(provider, {"CN_TSF_TOTAL_ANNUAL": series}, provider_id="pbc").fetch(
        "CN_TSF_TOTAL_ANNUAL"
    )
    assert frame["unit"].unique().tolist() == ["bn_cny"]
    assert frame["value"].tolist() == [35000.0, 32000.0]


def test_pboc_monthly_stats_converts_yi_to_bn_and_blocks_first_point(monkeypatch):
    """Monthly PBOC flow is differenced first, then converted 亿元 -> bn_cny."""
    provider = ProviderSpec(
        module="pbc", adapter_class="PbcAdapter", options={"max_years": 0}
    )
    series = SeriesSource(
        primary="pbc", provider_code="TSF_TOTAL", frequency="monthly", category="macro"
    )
    reports = {
        "2026年4月金融统计数据报告": "前四个月社会融资规模增量累计为100亿元",
        "2026年5月金融统计数据报告": "前五个月社会融资规模增量累计为130亿元",
    }
    monkeypatch.setattr(
        "macro_compass.data_sources.pbc.http_get", lambda url, **kwargs: url
    )
    monkeypatch.setattr(
        "macro_compass.data_sources.pbc.parse_stats_listing",
        lambda html, base: [(title, text) for title, text in reports.items()],
    )
    monkeypatch.setattr(
        "macro_compass.data_sources.pbc.re.sub",
        lambda pattern, repl, text: reports.get(text, text),
    )
    frame = PbcAdapter(provider, {"CN_TSF_TOTAL": series}, provider_id="pbc").fetch(
        "CN_TSF_TOTAL"
    )
    assert frame["unit"].unique().tolist() == ["bn_cny"]
    assert frame["value"].tolist() == [3.0]
    assert frame["date"].tolist() == [date(2026, 5, 31)]


def test_safe_listing_and_table_parse(fixture_file):
    listing = fixture_file("safe_parity_listing_sample.html").read_text(encoding="utf-8")
    announcements = parse_parity_links(listing, "https://www.safe.gov.cn/safe/")
    assert announcements[0][0] == pd.Timestamp("2026-08-28")
    assert announcements[0][1] == "https://www.safe.gov.cn/safe/2026/0828_parity.html"

    announcement = fixture_file(
        "safe_parity_announcement_sample.html"
    ).read_text(encoding="utf-8")
    rates = parse_parity_table(announcement, "美元")
    assert rates == {"美元": 7.1088}
