import pandas as pd

from scripts.historical_coverage import _dataframe_to_markdown, _refresh_usd_broad_state


def _canonical_usd(start: str, periods: int) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "series_id": ["USD_BROAD"] * periods,
            "date": pd.bdate_range(start, periods=periods),
            "value": [100.0] * periods,
        }
    )


def test_usd_broad_report_state_clears_stale_blocker_for_long_canonical_history():
    transitions, blockers = _refresh_usd_broad_state(_canonical_usd("2006-01-02", 5174))

    assert "X2" not in blockers
    assert transitions["USD_BROAD"]["historical_source"] == "FRED DTWEXBGS (canonical)"
    assert "5174 observations" in transitions["USD_BROAD"]["notes"]


def test_usd_broad_report_state_retains_warmup_for_short_canonical_history():
    transitions, blockers = _refresh_usd_broad_state(_canonical_usd("2026-08-17", 5))

    assert "WARMUP" in blockers["X2"]
    assert "5 observations" in transitions["USD_BROAD"]["notes"]


def test_markdown_renderer_does_not_require_tabulate_and_escapes_cells():
    frame = pd.DataFrame({"name": ["A | B", None], "value": [1, "line\nbreak"]})

    rendered = _dataframe_to_markdown(frame)

    assert rendered == (
        "| name | value |\n"
        "| --- | --- |\n"
        r"| A \| B | 1 |"
        "\n|  | line<br>break |"
    )
