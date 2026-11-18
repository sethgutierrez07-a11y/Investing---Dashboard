import datetime as dt
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import brief_lib as bl  # noqa: E402

TODAY = dt.date(2026, 11, 18)


def test_movers_sorted_and_flagged():
    quotes = {
        "AAA": {"c": 100, "dp": 0.5},
        "BBB": {"c": 50, "dp": -4.2},
        "CCC": {"c": 20, "dp": 3.1},
    }
    df = bl.build_movers(quotes, threshold_pct=2.0)
    assert list(df["Symbol"]) == ["BBB", "CCC", "AAA"]
    assert df.loc[df.Symbol == "BBB", "Flag"].iloc[0].startswith("▼")
    assert df.loc[df.Symbol == "CCC", "Flag"].iloc[0].startswith("▲")
    assert df.loc[df.Symbol == "AAA", "Flag"].iloc[0] == ""


def test_movers_handles_unknown_and_failed_symbols():
    # Finnhub returns zeros / nulls for unknown tickers; a failed call is None.
    quotes = {"REAL": {"c": 10, "dp": 1.0}, "ZERO": {"c": 0, "dp": None}, "FAIL": None}
    df = bl.build_movers(quotes)
    assert df.iloc[0]["Symbol"] == "REAL"
    assert set(df[df.Flag == "no data"]["Symbol"]) == {"ZERO", "FAIL"}


def test_movers_empty():
    assert bl.build_movers({}).empty


def test_analyst_score_bounds_and_empty():
    assert bl.analyst_score({"strongBuy": 10}) == 2
    assert bl.analyst_score({"strongSell": 4}) == -2
    assert bl.analyst_score({"hold": 7}) == 0
    assert bl.analyst_score({}) is None


def test_analyst_shift_directions():
    newer_bull = [
        {"period": "2026-11-01", "strongBuy": 10, "buy": 10, "hold": 5, "sell": 0, "strongSell": 0},
        {"period": "2026-10-01", "strongBuy": 5, "buy": 10, "hold": 10, "sell": 0, "strongSell": 0},
    ]
    assert bl.analyst_shift(newer_bull)["direction"] == "more bullish"
    bear = list(reversed(newer_bull))
    assert bl.analyst_shift(bear)["direction"] == "more bearish"
    same = [newer_bull[0], dict(newer_bull[0], period="2026-10-01")]
    assert bl.analyst_shift(same)["direction"] == "little changed"


def test_analyst_shift_needs_two_snapshots():
    assert bl.analyst_shift([]) is None
    assert bl.analyst_shift([{"strongBuy": 1}]) is None
    assert bl.analyst_shift([{"strongBuy": 1}, {}]) is None  # prior has no analysts


def test_filter_earnings_watchlist_only_and_sorted():
    cal = {
        "earningsCalendar": [
            {"symbol": "ZZZ", "date": "2026-11-19", "hour": "amc"},
            {"symbol": "MSFT", "date": "2026-11-25", "hour": "amc", "epsEstimate": 3.1},
            {"symbol": "aapl", "date": "2026-11-20", "hour": "bmo", "epsEstimate": 1.5},
            {"symbol": "AAPL", "date": "not-a-date"},
            {"symbol": "AAPL"},
        ]
    }
    df = bl.filter_earnings(cal, ["AAPL", "MSFT"], TODAY)
    assert list(df["Symbol"]) == ["AAPL", "MSFT"]
    assert df.iloc[0]["In (days)"] == 2
    assert df.iloc[0]["Timing"] == "Before open"


def test_filter_earnings_empty_inputs():
    assert bl.filter_earnings({}, ["AAPL"], TODAY).empty
    assert bl.filter_earnings(None, ["AAPL"], TODAY).empty
    assert bl.filter_earnings({"earningsCalendar": None}, ["AAPL"], TODAY).empty


def test_select_news_dedupes_sorts_limits():
    items = [
        {"headline": "Old story", "datetime": 1000, "source": "A", "url": "u1"},
        {"headline": "New story", "datetime": 3000, "source": "B", "url": "u2"},
        {"headline": "new story ", "datetime": 2900, "source": "C", "url": "u3"},  # dup
        {"headline": "", "datetime": 5000},  # blank
        {"headline": "Mid story", "datetime": 2000, "source": "D", "url": "u4"},
    ]
    out = bl.select_news(items, limit=2)
    assert [o["headline"] for o in out] == ["New story", "Mid story"]
    assert out[0]["published"].tzinfo is not None
    assert bl.select_news(None) == []


def test_describe_8k_items():
    assert bl.describe_8k_items("2.02,9.01") == "Earnings results; Financial statements / exhibits"
    assert bl.describe_8k_items("9.99") == "Item 9.99"
    assert bl.describe_8k_items("") == ""


def _subs():
    return {
        "filings": {
            "recent": {
                "accessionNumber": ["0001-26-000003", "0001-26-000002", "0001-26-000001", "0001-26-000000"],
                "filingDate": ["2026-11-17", "2026-11-16", "2026-11-10", "2026-11-17"],
                "form": ["8-K", "4", "8-K", "10-Q"],
                "primaryDocument": ["a.htm", "xslF345X05/f4.xml", "old.htm", "q.htm"],
                "items": ["2.02,9.01", "", "5.02", ""],
            }
        }
    }


def test_recent_filings_filters_by_form_and_date_and_builds_links():
    out = bl.recent_filings(_subs(), 320193, dt.date(2026, 11, 14))
    assert [f["Form"] for f in out] == ["8-K", "4"]  # 10-Q excluded, old 8-K excluded
    assert out[0]["What"] == "Earnings results; Financial statements / exhibits"
    assert out[0]["Link"] == "https://www.sec.gov/Archives/edgar/data/320193/000126000003/a.htm"
    assert "Form 4" in out[1]["What"]


def test_recent_filings_empty_or_missing():
    assert bl.recent_filings({}, 1, TODAY) == []
    assert bl.recent_filings({"filings": {}}, 1, TODAY) == []


def test_digest_contains_key_facts_and_is_bounded():
    movers = bl.build_movers({"AAA": {"c": 10.0, "dp": 5.0}, "BBB": None})
    earnings = bl.filter_earnings(
        {"earningsCalendar": [{"symbol": "AAA", "date": "2026-11-20", "hour": "amc"}]}, ["AAA"], TODAY
    )
    shifts = {"AAA": {"score_before": 0.5, "score_now": 0.9, "direction": "more bullish"}, "BBB": None}
    news = {"AAA": [{"headline": "AAA beats", "source": "Wire"}]}
    filings = {"AAA": [{"Form": "8-K", "Filed": dt.date(2026, 11, 17), "What": "Earnings results"}]}
    d = bl.build_digest(movers, earnings, shifts, news, filings)
    for needle in ["AAA: +5.00%", "BBB: no data", "2026-11-20", "more bullish", "AAA beats", "8-K filed"]:
        assert needle in d
    long = bl.build_digest(movers, earnings, shifts, {"AAA": [{"headline": "x" * 100, "source": "s"}] * 200}, filings)
    assert len(long) <= 6000 + len("\n[digest truncated]")


def test_digest_with_empty_frames():
    d = bl.build_digest(pd.DataFrame(columns=["Symbol", "Price", "Change %", "Flag"]), pd.DataFrame(), {}, {}, {})
    assert "none in window" in d
