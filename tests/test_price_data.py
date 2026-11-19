import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import price_data as pdx  # noqa: E402


def test_clean_prices_sorts_dedupes_drops_junk_and_removes_timezone():
    idx = pd.to_datetime(["2024-01-03 05:00", "2024-01-02 05:00", "2024-01-02 05:00", "2024-01-04 05:00", "2024-01-05 05:00"]).tz_localize("America/New_York")
    s = pdx.clean_prices(pd.Series([11, 10, 10.5, None, -3], index=idx))
    assert s.index.tz is None
    assert list(s.index.strftime("%Y-%m-%d")) == ["2024-01-02", "2024-01-03"]
    assert s.tolist() == [10.5, 11.0]                      # duplicate keeps the last value


def test_parse_twelvedata_orders_oldest_first():
    s = pdx.parse_twelvedata({"status": "ok", "values": [{"datetime": "2024-01-03", "close": "11.5"}, {"datetime": "2024-01-02", "close": "10"}]})
    assert s.tolist() == [10.0, 11.5] and s.index.is_monotonic_increasing


@pytest.mark.parametrize("payload,msg", [
    ({"status": "error", "message": "You have run out of API credits"}, "run out"),
    ({"code": 429, "status": "error", "message": "rate limit"}, "rate limit"),
    ({"values": []}, "no prices"),
    ([], "Unexpected"),
])
def test_parse_twelvedata_errors_carry_the_providers_message(payload, msg):
    with pytest.raises(pdx.PriceDataError, match=msg):
        pdx.parse_twelvedata(payload)


def test_parse_csv_prefers_adjusted_close_and_checks_columns():
    csv = b"Date,Open,Close,Adj Close\n2024-01-02,1,10,9\n2024-01-03,1,11,10\n"
    assert pdx.parse_csv(csv).tolist() == [9.0, 10.0]
    assert pdx.parse_csv(b"date,close\n2024-01-02,5\n").tolist() == [5.0]
    with pytest.raises(pdx.PriceDataError, match="Date column"):
        pdx.parse_csv(b"a,b\n1,2\n")
    with pytest.raises(pdx.PriceDataError):
        pdx.parse_csv(b"\x00\x01not,a,csv\xff" * 3)


def test_require_enough_history():
    short = pd.Series(1.0, index=pd.bdate_range("2024-01-01", periods=100))
    with pytest.raises(pdx.PriceDataError, match="Only 100 days"):
        pdx.require_enough(short, "XYZ")
    ok = pd.Series(1.0, index=pd.bdate_range("2020-01-01", periods=300))
    assert pdx.require_enough(ok, "XYZ") is ok


def good(n=400):
    return pd.Series(range(100, 100 + n), index=pd.bdate_range("2020-01-01", periods=n), dtype=float)


def test_load_history_uses_yahoo_first(monkeypatch):
    monkeypatch.setattr(pdx, "fetch_yahoo", lambda sym: good())
    s, src, problems = pdx.load_history(" voo ", "key")
    assert len(s) == 400 and "Yahoo" in src and problems == []


def test_load_history_falls_back_to_twelve_data_and_says_dividends_missing(monkeypatch):
    def yahoo_down(sym):
        raise pdx.PriceDataError("Yahoo Finance didn't answer (YFRateLimitError).")

    monkeypatch.setattr(pdx, "fetch_yahoo", yahoo_down)
    monkeypatch.setattr(pdx, "fetch_twelvedata", lambda sym, key: good())
    s, src, problems = pdx.load_history("VOO", "key")
    assert "Twelve Data" in src and "dividends not included" in src and "Yahoo" in problems[0]


def test_load_history_reports_every_failure_when_nothing_works(monkeypatch):
    def down(*a):
        raise pdx.PriceDataError("down")

    monkeypatch.setattr(pdx, "fetch_yahoo", down)
    monkeypatch.setattr(pdx, "fetch_twelvedata", lambda s, k: (_ for _ in ()).throw(pdx.PriceDataError("no credits")))
    with pytest.raises(pdx.PriceDataError, match="down.*no credits"):
        pdx.load_history("VOO", "key")
    with pytest.raises(pdx.PriceDataError, match="down"):
        pdx.load_history("VOO", None)                        # no key: only Yahoo was tried


def test_network_error_from_twelve_data_is_reported_not_raised_raw(monkeypatch):
    import requests

    def yahoo_down(sym):
        raise pdx.PriceDataError("y")

    def net(sym, key):
        raise requests.ConnectionError("boom")

    monkeypatch.setattr(pdx, "fetch_yahoo", yahoo_down)
    monkeypatch.setattr(pdx, "fetch_twelvedata", net)
    with pytest.raises(pdx.PriceDataError, match="ConnectionError"):
        pdx.load_history("VOO", "key")
