"""Calendar and market-clock logic."""

import datetime as dt
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import event_lib as el  # noqa: E402

UTC = dt.timezone.utc
ET = el.ET


def et(y, m, d, hh, mm=0):
    return dt.datetime(y, m, d, hh, mm, tzinfo=ET)


# ---------------------------------------------------------------- built-in data
def test_fomc_dates_are_wednesdays_in_order_and_inside_coverage():
    ds = [d for d, _, _ in el.FOMC]
    assert ds == sorted(ds) and len(set(ds)) == len(ds)
    assert all(d.weekday() == 2 for d in ds)                      # decisions are announced on Wednesdays
    assert max(ds) <= el.FED_COVERS_THROUGH
    # projections come every other meeting (Mar, Jun, Sep, Dec)
    assert all(sep == (d.month in (3, 6, 9, 12)) for d, _, sep in el.FOMC)


def test_closures_are_weekdays_with_valid_kinds():
    for d, (name, kind) in el.CLOSURES.items():
        assert d.weekday() < 5 and kind in ("closed", "early") and d <= el.COVERS_THROUGH, (d, name)
    assert el.CLOSURES[dt.date(2026, 11, 26)] == ("Thanksgiving Day", "closed")
    assert el.CLOSURES[dt.date(2026, 11, 27)][1] == "early"


def test_thanksgiving_is_the_fourth_thursday():
    for d, (name, _) in el.CLOSURES.items():
        if name == "Thanksgiving Day":
            assert d.weekday() == 3 and 22 <= d.day <= 28


# ---------------------------------------------------------------- trading days
def test_trading_days():
    assert el.is_trading_day(dt.date(2026, 11, 19))               # Thursday
    assert not el.is_trading_day(dt.date(2026, 11, 21))           # Saturday
    assert not el.is_trading_day(dt.date(2026, 11, 26))           # Thanksgiving
    assert el.is_trading_day(dt.date(2026, 11, 27))               # early close still trades


def test_next_trading_day_skips_weekend_and_holiday():
    assert el.next_trading_day(dt.date(2026, 11, 20)) == dt.date(2026, 11, 23)      # Fri -> Mon
    assert el.next_trading_day(dt.date(2026, 11, 25)) == dt.date(2026, 11, 27)      # Wed -> Fri (Thanksgiving)


# ---------------------------------------------------------------- market status
@pytest.mark.parametrize("when,state,tone", [
    (et(2026, 11, 19, 8, 0), "pre", "warn"),
    (et(2026, 11, 19, 9, 29), "pre", "warn"),
    (et(2026, 11, 19, 9, 30), "open", "ok"),
    (et(2026, 11, 19, 15, 59), "open", "ok"),
    (et(2026, 11, 19, 16, 0), "after", "off"),
    (et(2026, 11, 21, 11, 0), "closed", "off"),                   # Saturday
    (et(2026, 11, 26, 11, 0), "closed", "off"),                   # Thanksgiving
    (et(2026, 11, 27, 12, 59), "open", "ok"),                     # early-close day, still open
    (et(2026, 11, 27, 13, 0), "after", "off"),
])
def test_market_status_states(when, state, tone):
    s = el.market_status(when)
    assert s["state"] == state and s["tone"] == tone and s["label"]


def test_market_status_converts_from_utc_and_names_the_next_open():
    s = el.market_status(dt.datetime(2026, 11, 19, 15, 0, tzinfo=UTC))        # 10:00 AM Eastern
    assert s["state"] == "open" and "closes 4:00 PM" in s["label"]
    s = el.market_status(et(2026, 11, 20, 17, 0))                             # Friday after close
    assert s["state"] == "after" and "Mon Nov 23" in s["label"]
    s = el.market_status(et(2026, 11, 25, 18, 0))
    assert "Fri Nov 27" in s["label"]                                         # skips Thanksgiving
    assert "early close" in el.market_status(et(2026, 11, 27, 10, 0))["label"]
    assert "Thanksgiving" in el.market_status(et(2026, 11, 26, 10, 0))["label"]


def test_market_status_flags_dates_beyond_the_built_in_calendar():
    assert el.market_status(et(2026, 11, 19, 11))["covered"] is True
    assert el.market_status(et(2028, 3, 1, 11))["covered"] is False


# ---------------------------------------------------------------- events
TODAY = dt.date(2026, 11, 19)


def test_builtin_events_window_and_content():
    ev = el.builtin_events(TODAY, 30)
    kinds = {(e["type"], pd.Timestamp(e["date"]).date()) for e in ev}
    assert ("Fed", dt.date(2026, 12, 9)) in kinds and ("Market closed", dt.date(2026, 11, 26)) in kinds
    assert all(TODAY <= pd.Timestamp(e["date"]).date() <= TODAY + dt.timedelta(days=30) for e in ev)
    assert any("projections" in e["detail"] for e in ev if e["type"] == "Fed")
    assert any("1:00 PM" in e["detail"] for e in ev if "Day after" in e["title"])
    assert el.builtin_events(TODAY, 0) == []


def test_passed_dates_drop_out():
    assert el.builtin_events(dt.date(2027, 1, 2), 3) == []
    assert not any(pd.Timestamp(e["date"]).date() < dt.date(2027, 1, 2) for e in el.builtin_events(dt.date(2027, 1, 2), 60))


def test_earnings_events_from_finnhub_frame():
    df = pd.DataFrame({"Symbol": ["AAPL", "MSFT"], "Date": [dt.date(2026, 12, 1), dt.date(2026, 12, 2)],
                       "Timing": ["After close", ""], "EPS est.": [1.234, None]})
    ev = el.earnings_events(df)
    assert [e["title"] for e in ev] == ["AAPL reports earnings", "MSFT reports earnings"]
    assert ev[0]["detail"] == "After close · EPS est. 1.23" and ev[1]["detail"] == ""
    assert el.earnings_events(None) == [] and el.earnings_events(pd.DataFrame()) == []


def test_exdividend_events_are_estimates_and_show_per_share_only():
    proj = pd.DataFrame({"Symbol": ["VOO", "AAPL", "KO"], "ExDate": pd.to_datetime(["2026-12-10", "2026-11-01", "2027-06-01"]),
                         "PerShare": [1.7, 0.26, 0.5], "Shares": [10.0, 5.0, 1.0], "Amount": [17.0, 1.3, 0.5]})
    ev = el.exdividend_events(proj, TODAY, 60)
    assert [e["title"] for e in ev] == ["VOO ex-dividend (estimated)"]          # past and far-future dates dropped
    assert ev[0]["detail"] == "about $1.70 per share"
    assert "17" not in ev[0]["detail"] and "10" not in ev[0]["detail"]          # never the account's own amounts
    assert el.exdividend_events(None, TODAY, 60) == [] and el.exdividend_events(proj.iloc[0:0], TODAY, 60) == []


def test_build_timeline_sorts_filters_and_counts_days():
    ev = el.builtin_events(TODAY, 60) + el.earnings_events(pd.DataFrame({"Symbol": ["AAPL"], "Date": [dt.date(2026, 11, 26)], "Timing": [""], "EPS est.": [None]}))
    df = el.build_timeline(ev, TODAY, 14)
    assert list(df.columns) == ["Date", "Day", "In (days)", "Type", "Event", "Details"]
    assert df["Date"].is_monotonic_increasing
    assert df["Date"].max() <= TODAY + dt.timedelta(days=14)
    assert list(df["In (days)"]) == [(d - TODAY).days for d in df["Date"]]
    same_day = df[df["Date"] == dt.date(2026, 11, 26)]["Type"].tolist()
    assert same_day == ["📣 Earnings", "🔔 Market closed"]                       # fixed type order within a day
    only_fed = el.build_timeline(ev, TODAY, 60, ["Fed"])
    assert set(only_fed["Type"]) == {"🏛️ Fed"}
    assert el.build_timeline(ev, TODAY, 60, []).empty
    assert list(el.build_timeline([], TODAY, 14).columns) == ["Date", "Day", "In (days)", "Type", "Event", "Details"]


def test_next_event():
    ev = el.builtin_events(TODAY, 60)
    n = el.next_event(ev, TODAY, "Fed")
    assert pd.Timestamp(n["date"]).date() == dt.date(2026, 12, 9)
    assert el.next_event(ev, TODAY, "Earnings") is None
