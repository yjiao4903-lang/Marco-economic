"""Deterministic parser tests for V1.2 providers (no network access).

Every third-party payload is parsed from a saved fixture file so the tests
are reproducible and offline.
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from macro_compass.data_sources.akshare_source import parse_akshare_hist
from macro_compass.data_sources.chicagofed import parse_nfci_csv
from macro_compass.data_sources.chinabond import parse_search_yc
from macro_compass.data_sources.chinamoney import parse_ccpr_json
from macro_compass.data_sources.fred import parse_fred_csv
from macro_compass.data_sources.nyfed import parse_ref_rates_json
from macro_compass.data_sources.oecd import parse_sdmx_csv, period_to_date
from macro_compass.data_sources.pbc import parse_lpr_announcement, parse_lpr_listing
from macro_compass.data_sources.safe import parse_parity_links, parse_parity_table


def test_fred_parse_drops_missing_and_dots(fixture_file):
    text = fixture_file("fred_sample.csv").read_text(encoding="utf-8")
    dates, values = parse_fred_csv(text, "DFII10")
    assert dates == [
        date(2026, 8, 20), date(2026, 8, 21), date(2026, 8, 24),
    ]
    assert values == [2.05, 2.07, 2.03]


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
    text = fixture_file("chinabond_searchyc_sample.json").read_text(encoding="utf-8")
    dates, values = parse_search_yc(text, "10")
    assert dates == [date(2026, 8, 27), date(2026, 8, 26)]
    assert values == [1.8210, 1.8350]


def test_chicagofed_parse_drops_missing(fixture_file):
    text = fixture_file("chicagofed_nfci_sample.csv").read_text(encoding="utf-8")
    dates, values = parse_nfci_csv(text, "ANFCI")
    assert dates == [date(2026, 8, 22), date(2026, 8, 15)]
    assert values == [0.31, 0.29]

    with pytest.raises(Exception, match="no column"):
        parse_nfci_csv(text, "XYZ")


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
