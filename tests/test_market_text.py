"""The rule-based market summary: right facts, right direction, no hype, no dollar signs."""

import datetime as dt
import re
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import event_lib as el  # noqa: E402
import market_lib as ml  # noqa: E402
import market_text as mt  # noqa: E402

TODAY = dt.date(2026, 11, 19)
LATEST = pd.Timestamp("2026-11-18")
SP_UP = {"last": 7000, "vs50": 0.03, "vs200": 0.08, "from_high": -0.012, "trend": "up"}
SP_DOWN = {"last": 5000, "vs50": -0.04, "vs200": -0.09, "from_high": -0.2, "trend": "down"}
IDX = {"S&P 500": 0.0123, "Nasdaq": -0.004, "Dow": 0.0, "Russell 2000": 0.009}


def text(sections):
    return " ".join(b for _, bullets in sections for b in bullets)


def test_formatting_helpers():
    assert mt.pc(0.0123) == "1.2%" and mt.pc(0.0123, signed=True) == "+1.2%" and mt.pc(-0.05, 0, signed=True) in ("-5%", "−5%")
    assert mt.pc(None) in ("n/a", "—", "") or isinstance(mt.pc(None), str)
    assert "0.25" in mt.pp(0.25) and "percentage point" in mt.pp(0.25)


def test_short_version_reports_the_move_in_the_right_direction():
    out = " ".join(mt.short_version(IDX, LATEST, SP_UP, 14.0, {"level": 4.3, "m1": 0.1}))
    assert "S&P 500 rose 1.2%" in out and "Nov 18" in out
    assert "Nasdaq -0.4%" in out and "Russell 2000 +0.9%" in out
    down = " ".join(mt.short_version({"S&P 500": -0.021}, LATEST, SP_DOWN, 35.0, None))
    assert "fell 2.1%" in down and "downtrend" in down and "below its 200-day" in down and "stressed" in down


def test_short_version_trend_sentence_matches_the_data():
    up = " ".join(mt.short_version(IDX, LATEST, SP_UP, None, None))
    assert "above both its 50-day and 200-day averages" in up and "uptrend" in up and "8.0% above its 200-day" in up and "1.2% below its 52-week high" in up
    mixed = " ".join(mt.short_version(IDX, LATEST, dict(SP_UP, vs50=-0.01, trend="mixed"), None, None))
    assert "mixed signals" in mixed
    at_high = " ".join(mt.short_version(IDX, LATEST, dict(SP_UP, from_high=0.0), None, None))
    assert "at its 52-week high" in at_high


def test_short_version_says_so_when_there_is_nothing():
    assert mt.short_version({}, None, None, None, None) == ["Not enough market data loaded to summarize."]


def test_yield_sentence_handles_up_down_and_flat():
    for m1, expect in ((0.2, "up 0.20"), (-0.15, "down 0.15"), (0.0, "about unchanged")):
        s = " ".join(mt.short_version({}, LATEST, None, None, {"level": 4.0, "m1": m1}))
        assert "4.00%" in s and expect in s


def test_under_the_surface_sector_and_curve_statements():
    t = pd.DataFrame({"Symbol": ["XLE", "XLK"], "Sector": ["Energy", "Technology"], "1M": [0.08, -0.05]})
    s = " ".join(mt.under_the_surface(t, (1, 2), {"offense": -0.05, "defense": 0.03, "gap": -0.08}, -0.4, 4.4, 4.0))
    assert "Energy** led (+8.0%)" in s and "Technology** lagged (-5.0%)" in s and "1 of 2 sectors rose" in s
    assert s.index("Defensive sectors") < s.index("growth-oriented ones") and "8.0 percentage points" in s
    assert "inverted" in s and "below the 3-month" in s and "recessions" in s and "varied" in s
    flat = " ".join(mt.under_the_surface(None, None, {"offense": 0.01, "defense": 0.012, "gap": -0.002}, 0.3, 4.0, 4.3))
    assert "moving about together" in flat and "recession" not in flat
    assert mt.under_the_surface(None, None, None, None, None, None) == []
    same = " ".join(mt.under_the_surface(None, None, None, 0.0, 4.0, 4.0))
    assert "about the same as" in same


def test_coming_up_lists_first_event_of_each_kind_with_relative_days():
    ev = el.builtin_events(TODAY, 60) + [
        {"date": dt.date(2026, 11, 19), "type": "Earnings", "title": "NVDA reports earnings", "detail": ""},
        {"date": dt.date(2026, 11, 20), "type": "Ex-dividend", "title": "KO ex-dividend (estimated)", "detail": ""}]
    s = mt.coming_up(ev, TODAY)
    joined = " ".join(s)
    assert "Next Fed decision: **FOMC rate decision**, Dec 9 (in 20 days)" in joined
    assert "**NVDA**, Nov 19 (today)" in joined and "**KO**, Nov 20 (tomorrow)" in joined
    assert "Thanksgiving" in joined and "(in 7 days)" in joined
    assert mt.coming_up([], TODAY) == ["Nothing from your watchlist or the built-in calendar falls in this window."]


def test_write_summary_sections_and_optionality():
    base = dict(idx=IDX, latest=LATEST, sp=SP_UP, vix=18.0, ten={"level": 4.3, "m1": 0.0})
    titles = [t for t, _ in mt.write_summary(**base)]
    assert titles == ["The short version", "Worth knowing"]
    full = mt.write_summary(**base, table=pd.DataFrame({"Symbol": ["XLE"], "Sector": ["Energy"], "1M": [0.01]}), br=(1, 1), events=[], today=TODAY)
    assert [t for t, _ in full] == ["The short version", "Under the surface", "Coming up", "Worth knowing"]


def test_summary_never_uses_dollar_signs_hype_or_advice():
    ev = el.builtin_events(TODAY, 60)
    t = pd.DataFrame({"Symbol": ["XLE", "XLK"], "Sector": ["Energy", "Technology"], "1M": [0.08, -0.05]})
    for sp in (SP_UP, SP_DOWN):
        out = text(mt.write_summary(idx=IDX, latest=LATEST, sp=sp, vix=22.0, ten={"level": 4.3, "m1": 0.2}, table=t, br=(1, 2),
                                    od={"offense": 0.0, "defense": 0.05, "gap": -0.05}, spread=-0.3, y_short=4.6, y_long=4.3, events=ev, today=TODAY))
        assert "$" not in out
        low = out.lower()
        for w in (r"you should", r"\bbuy\b", r"\bsell\b", r"will rise", r"will fall", r"guaranteed", r"crash", r"soar", r"plunge"):
            assert not re.search(w, low), w
        assert "not financial advice" in low and "already happened" in low
