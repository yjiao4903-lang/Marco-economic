from __future__ import annotations

import urllib.error

import pytest

from macro_compass.data_sources import fred
from macro_compass.data_sources.base import FetchError
from macro_compass.data_sources.registry import ProviderSpec, SeriesSource


class _Response:
    def __init__(self, payload):
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        import json

        return json.dumps(self._payload).encode("utf-8")


def _adapter():
    provider = ProviderSpec(module="fred", adapter_class="FredAdapter", timeout_seconds=1)
    series = SeriesSource(provider_code="DTWEXBGS", frequency="daily", category="macro", primary="fred")
    return fred.FredAdapter(provider, {"USD_BROAD": series}, provider_id="fred")


def test_fred_api_is_opt_in_and_paginates(monkeypatch):
    monkeypatch.setenv("FRED_API_KEY", "placeholder-for-test")
    monkeypatch.setattr(fred, "_FRED_API_PAGE_SIZE", 2)
    calls = []
    pages = [
        {"observations": [{"date": "2026-01-01", "value": "100"}, {"date": "2026-01-01", "value": "100"}]},
        {"observations": [{"date": "2026-01-02", "value": "101"}]},
    ]

    def fake_get(params, *, timeout):
        calls.append(params)
        return pages.pop(0)

    monkeypatch.setattr(fred, "_fred_api_get", fake_get)
    frame = _adapter().fetch("USD_BROAD")
    assert len(calls) == 2
    assert calls[0]["sort_order"] == "asc"
    assert calls[1]["offset"] == 2
    assert frame["value"].tolist() == [100.0, 100.0, 101.0]
    assert "placeholder-for-test" not in frame["source_file"].iloc[0]


def test_fred_without_api_key_keeps_fredgraph_path(monkeypatch):
    monkeypatch.delenv("FRED_API_KEY", raising=False)
    monkeypatch.setattr(
        fred,
        "http_get",
        lambda url, **kwargs: "DATE,DTWEXBGS\n2026-01-01,100\n",
    )
    frame = _adapter().fetch("USD_BROAD")
    assert frame["value"].tolist() == [100.0]
    assert frame["source_file"].iloc[0].startswith(fred.FREDGRAPH_URL)


def test_fred_api_http_errors_are_bounded_and_redacted(monkeypatch):
    monkeypatch.setenv("FRED_API_KEY", "placeholder-for-test")
    attempts = []

    def fake_urlopen(request, timeout):
        attempts.append(1)
        raise urllib.error.HTTPError(request.full_url, 500, "server", {}, None)

    monkeypatch.setattr(fred.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(fred.time, "sleep", lambda _: None)
    with pytest.raises(FetchError) as exc_info:
        fred._fred_api_get({"api_key": "placeholder-for-test"}, timeout=1)
    assert len(attempts) == 3
    assert "placeholder-for-test" not in str(exc_info.value)
    assert "HTTP 500" in str(exc_info.value)
