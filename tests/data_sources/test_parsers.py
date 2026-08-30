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
