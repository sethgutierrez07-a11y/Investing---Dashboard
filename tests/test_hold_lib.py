"""How-long-to-hold: rolling-window history, recovery times, the planning window, re-check prompts, wording, chart."""

import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_lab_charts  # noqa: F401,E402  (installs a plotly stand-in if plotly is missing)

for m in ("deep_charts", "risk_charts", "holdings_charts"):
    sys.modules.pop(m, None)
import deep_charts as dc  # noqa: E402
import deep_lib as dlib  # noqa: E402
import deep_text as dtx  # noqa: E402
import hold_lib as hl  # noqa: E402
from test_deep_lib import px  # noqa: E402


# ---------------------------------------------------------------- history windows
def test_steady_climb_always_gains_and_matches_the_math():
    w = {x["years"]: x for x in hl.history_windows(px(0.0004, 1500))}
    assert set(w) == {1, 3, 5}
    for y, row in w.items():
        assert row["share_gain"] == 1.0 and row["worst_total"] > 0
        assert row["median_total"] == pytest.approx(1.0004 ** (252 * y) - 1, rel=1e-6)
        assert row["median_per_year"] == pytest.approx(1.0004 ** 252 - 1, rel=1e-6)


def test_a_flat_stock_is_not_counted_as_a_gain():
    assert all(r["share_gain"] == 0.0 for r in hl.history_windows(px(0.0, 1500)))


def test_steady_decline_never_gains():
    w = hl.history_windows(px(-0.0004, 1500))
    assert w and all(r["share_gain"] == 0.0 and r["worst_total"] < 0 and r["best_total"] < 0 for r in w)


def test_windows_need_enough_history_for_each_length():
    assert hl.history_windows(px(0.001, 300)) == []                       # under a year plus a sample of start dates
    assert [r["years"] for r in hl.history_windows(px(0.001, 400))] == [1]
    assert [r["years"] for r in hl.history_windows(px(0.001, 900))] == [1, 3]
    assert hl.history_windows(None) == [] and hl.history_windows(pd.Series(dtype=float)) == []


def test_windows_count_overlapping_start_dates():
    rows = {r["years"]: r for r in hl.history_windows(px(0.001, 1500))}
    assert rows[1]["periods"] > rows[3]["periods"] > rows[5]["periods"] >= 120


def test_dividends_are_counted_in_the_result():
    p = px(0.0, 800)
    d = pd.Series([2.0] * 8, index=p.index[100::90][:8])
    no, yes = hl.history_windows(p)[0], hl.history_windows(p, d)[0]
    assert no["median_total"] == pytest.approx(0.0) and yes["median_total"] > 0.02


# ---------------------------------------------------------------- recoveries
def dip(recover: bool):
    r = np.r_[np.full(300, 0.001), np.full(120, -0.005), np.full(500 if recover else 80, 0.004)]
    return px(r, start=100.0)


def test_a_recovered_fall_reports_peak_to_recovery_time():
    out = hl.recoveries(dip(True))
    e = out["episodes"][0]
    assert e["depth"] < -0.30 and e["recovered"] is not None and e["total_days"] == e["days_down"] + e["days_to_recover"] > 300
    assert out["longest_days"] == e["total_days"] and out["still_down"] is None


def test_an_unrecovered_fall_says_so_and_has_no_recovery_length():
    out = hl.recoveries(dip(False))
    e = out["episodes"][0]
    assert e["recovered"] is None and e["total_days"] is None
    assert out["still_down"] is e and out["longest_days"] is None


def test_small_dips_and_short_history_are_ignored():
    assert hl.recoveries(px(0.001, 600))["episodes"] == []
    assert hl.recoveries(px(0.001, 50)) == {"episodes": [], "longest_days": None, "still_down": None}
    assert hl.recoveries(None)["episodes"] == []
    r = np.r_[np.full(300, 0.001), np.full(25, -0.005), np.full(300, 0.003)]       # about a 12% dip
    assert hl.recoveries(px(r))["episodes"] == [] and hl.recoveries(px(r), min_depth=0.05)["episodes"]
    wiggle = px(np.tile([0.01, -0.0095], 400))
    assert hl.recoveries(wiggle, min_depth=0.15)["episodes"] == []


# ---------------------------------------------------------------- tiers
@pytest.mark.parametrize("vol,tier,base", [(0.05, "steady", 3), (0.1999, "steady", 3), (0.20, "moderate", 5), (0.2999, "moderate", 5),
                                           (0.30, "bumpy", 5), (0.4499, "bumpy", 5), (0.45, "very bumpy", 7), (1.2, "very bumpy", 7)])
def test_volatility_picks_the_tier_with_clean_boundaries(vol, tier, base):
    assert hl.tier_for({"volatility": vol, "max_drawdown": -0.9}) == (tier, base)      # vol wins over drawdown


@pytest.mark.parametrize("md,tier", [(-0.05, "steady"), (-0.1999, "steady"), (-0.20, "moderate"), (-0.3499, "moderate"),
                                     (-0.35, "bumpy"), (-0.4999, "bumpy"), (-0.50, "very bumpy"), (-0.9, "very bumpy")])
def test_worst_fall_is_the_fallback_when_swings_are_missing(md, tier):
    assert hl.tier_for({"volatility": None, "max_drawdown": md})[0] == tier


def test_no_stats_means_no_tier():
    assert hl.tier_for(None) is None and hl.tier_for({}) is None and hl.tier_for({"volatility": None, "max_drawdown": None}) is None


# ---------------------------------------------------------------- the window
STEADY, BUMPY, WILD = {"volatility": 0.15}, {"volatility": 0.35}, {"volatility": 0.6}


def test_steady_stock_gets_the_base_window_and_text():
    h = hl.horizon(STEADY, None)
    assert (h["tier"], h["low"], h["text"], h["style"], h["small_slice"]) == ("steady", 3, "3–5 years", "Medium-term (a few years)", False)
    assert hl.horizon(None, None) is None


def test_long_recoveries_stretch_the_window_but_not_past_ten_years():
    fits = hl.horizon(STEADY, {"longest_days": 3 * 365})
    assert fits["low"] == 3 and not any("recovery" in w for w in fits["why"])          # recovery fits inside the base: no extra reason
    h = hl.horizon(STEADY, {"longest_days": int(4.2 * 365)})
    assert h["low"] == 5 and any("peak to recovery" in w for w in h["why"])
    h = hl.horizon(STEADY, {"longest_days": 12 * 365})
    assert h["low"] == 10 and h["text"] == "10+ years"
    assert hl.horizon(STEADY, {"longest_days": 2 * 365})["low"] == 3 and hl.horizon(STEADY, {"longest_days": None})["low"] == 3


def test_expensive_or_unprofitable_adds_a_year_only_past_the_line():
    assert hl.horizon(STEADY, None, metrics={"peTTM": 40.0})["low"] == 3
    assert hl.horizon(STEADY, None, metrics={"peTTM": 40.5})["low"] == 4
    ev = {"cons": [("Valuation", "No positive trailing earnings, so there is no P/E to judge the price by.")], "pros": []}
    assert hl.horizon(STEADY, None, ev=ev)["low"] == 4
    ev2 = {"cons": [("Valuation", "P/E of 45.0 is above 40")], "pros": []}
    assert hl.horizon(STEADY, None, ev=ev2, metrics={"peTTM": 45.0})["low"] == 4        # one year, not two
    assert hl.horizon(WILD, {"longest_days": 10 * 365}, metrics={"peTTM": 90.0})["low"] == 10


def test_funds_get_at_least_five_years_and_no_price_tag_year():
    h = hl.horizon(STEADY, None, fund=True, metrics={"peTTM": 90.0})
    assert h["low"] == 5 and not h["small_slice"] and any("fund" in w for w in h["why"])
    assert hl.horizon(WILD, None, fund=True)["low"] == 7                             # already above five


def test_bumpier_stocks_get_longer_windows_and_a_size_note():
    assert [hl.horizon(s, None)["low"] for s in (STEADY, {"volatility": 0.25}, BUMPY, WILD)] == [3, 5, 5, 7]
    assert [hl.horizon(s, None)["small_slice"] for s in (STEADY, {"volatility": 0.25}, BUMPY, WILD)] == [False, False, True, True]
    assert hl.horizon(WILD, None)["style"] == "Long-term, and keep it small" and hl.horizon(BUMPY, None)["style"] == "Long-term"


@pytest.mark.parametrize("low,text", [(3, "3–5 years"), (7, "7–9 years"), (8, "8–10 years"), (9, "9–10 years"), (10, "10+ years"), (12, "10+ years")])
def test_window_text(low, text):
    assert hl.window_text(low) == text


# ---------------------------------------------------------------- re-check prompts
def cons(*labels):
    return {"cons": [(lab, "x") for lab in labels], "pros": []}


def by(rows):
    return {r["what"]: r for r in rows}


def test_rechecks_flag_only_what_is_actually_flagged():
    quiet = by(hl.rechecks({"trend": "up"}, cons(), None, None))
    assert not any(r["flag"] for r in quiet.values()) and "The dividend" not in quiet
    loud = by(hl.rechecks({"trend": "down"}, cons("Growth", "Balance sheet", "Analysts"), {"active": True}, 3))
    assert all(loud[k]["flag"] for k in ("Each earnings report", "Sales and profit", "Debt and cash", "Analyst opinion", "The long-term trend"))
    assert not loud["The dividend"]["flag"] and not loud["Your own reason for buying"]["flag"]
    assert by(hl.rechecks({}, cons("Dividend safety"), {"active": True}, None))["The dividend"]["flag"]
    assert "The dividend" not in by(hl.rechecks({}, cons("Dividend safety"), {"active": False}, None))


@pytest.mark.parametrize("days,flag", [(0, True), (14, True), (15, False), (None, False)])
def test_earnings_soon_boundary(days, flag):
    assert by(hl.rechecks({}, cons(), None, days))["Each earnings report"]["flag"] is flag


def test_each_company_label_maps_to_its_own_prompt():
    for lab, what in (("Growth over time", "Sales and profit"), ("Earnings over time", "Sales and profit"), ("Operating margin", "Sales and profit"),
                      ("Profitability", "Sales and profit"), ("Short-term cash", "Debt and cash"), ("Interest costs", "Debt and cash")):
        assert by(hl.rechecks({}, cons(lab), None, None))[what]["flag"], lab
    assert not by(hl.rechecks({}, cons("Valuation"), None, None))["Sales and profit"]["flag"]


def test_funds_only_get_the_prompts_that_apply():
    assert set(by(hl.rechecks({"trend": "mixed"}, None, None, None, fund=True))) == {"The long-term trend", "Your own reason for buying"}
    assert by(hl.rechecks({}, None, None, None))["Each earnings report"]                                                      # no ev: still builds
    assert "Analyst opinion" not in by(hl.rechecks({}, None, None, None))


# ---------------------------------------------------------------- wording
W = [{"years": 1, "periods": 1000, "share_gain": 0.8, "median_total": 0.1, "median_per_year": 0.1, "worst_total": -0.3, "best_total": 0.9},
     {"years": 3, "periods": 800, "share_gain": 0.9, "median_total": 0.4, "median_per_year": 0.12, "worst_total": -0.1, "best_total": 2.0},
     {"years": 5, "periods": 600, "share_gain": 1.0, "median_total": 0.8, "median_per_year": 0.12, "worst_total": 0.05, "best_total": 3.0}]
H = hl.horizon(BUMPY, {"longest_days": 800})
REC = {"episodes": [{"peak": pd.Timestamp("2022-01-03"), "trough": pd.Timestamp("2022-10-01"), "depth": -0.42, "recovered": pd.Timestamp("2023-12-01"),
                     "days_down": 271, "days_to_recover": 426, "total_days": 697}], "longest_days": 697, "still_down": None}


def words(**kw):
    base = dict(symbol="ACME", h=H, windows=W, recov=REC, div=None, held=None, fund=False)
    base.update(kw)
    return " ".join(dtx.holding_summary(base["symbol"], base["h"], base["windows"], base["recov"], base["div"], base["held"], base["fund"]))


def test_summary_states_the_window_history_and_recovery_with_the_numbers():
    t = words()
    assert f"Planning window: {H['text']}" in t and "not a prediction" in t
    assert "1 year: 80%" in t and "3 years: 90%" in t and "5 years: 100%" in t
    assert "worst 5-year stretch ended +5% overall" in t and "typical one +80%" in t
    assert "-42%" in t and "Jan 2022" in t and "23 months" in t
    assert "Long is not forever" in t and "bumpy" in t


def test_summary_without_history_or_window_degrades_plainly():
    assert "isn't enough price history" in words(h=None)
    t = words(windows=[], recov=None)
    assert "not enough price history to test" in t and "Recovery" not in t
    assert "no fall deeper than 15%" in words(recov={"episodes": [], "longest_days": None, "still_down": None})


def test_unrecovered_fall_is_not_promised_to_come_back():
    rec = {"episodes": [{**REC["episodes"][0], "recovered": None, "total_days": None}], "longest_days": None, "still_down": REC["episodes"][0]}
    t = words(recov=rec)
    assert "not been fully recovered" in t and "not guaranteed" in t


def test_size_note_names_your_share_only_as_a_percent_and_only_above_the_line():
    assert "5% of invested money" in words()
    assert "You hold 8% of invested money" in words(held={"held": True, "weight": 8.0})
    assert "You hold" not in words(held={"held": True, "weight": 5.0}) and "You hold" not in words(held={"held": False, "weight": None})
    assert "$" not in words(held={"held": True, "weight": 8.0})
    assert "5% of invested" not in words(h=hl.horizon(STEADY, None))                           # steady stocks get no size note
    assert "5% of invested" not in words(h=hl.horizon(WILD, None, fund=True), fund=True)


def test_dividend_line_needs_a_five_year_streak_and_an_active_payer():
    assert "raised its dividend 5 years in a row" in words(div={"active": True, "streak": 5})
    assert "raised its dividend" not in words(div={"active": True, "streak": 4}) and "pays no regular dividend" not in words(div={"active": True, "streak": 4})
    assert "pays no regular dividend" in words(div={"active": False})
    assert "regular dividend" not in words(div=None)
    assert "regular dividend" not in words(div={"active": False}, fund=True) and "raised its dividend" not in words(div={"active": True, "streak": 9}, fund=True)


def test_recovery_length_reads_in_months_then_years():
    assert dtx._length(200) == "7 months" and dtx._length(700) == "23 months" and dtx._length(730) == "2.0 years" and dtx._length(1826) == "5.0 years"


# ---------------------------------------------------------------- chart
@pytest.mark.parametrize("mode", ["light", "dark"])
def test_hold_chart_builds_with_every_bar_labelled(mode):
    fig = dc.hold_chart(W, mode)
    assert fig is not None
    dc.hold_chart(W[:1], mode)
