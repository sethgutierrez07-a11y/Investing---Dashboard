"""Stock Deep-Dive calculations: metrics, grading, price statistics, pros and cons."""

import datetime as dt
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import deep_lib as dlib  # noqa: E402
import idea_lib as il  # noqa: E402

TODAY = dt.date(2026, 11, 19)


def px(r, n=1500, start=100.0, end="2026-11-19"):
    """Prices from a daily return (scalar or array)."""
    r = np.full(n, r) if np.isscalar(r) else np.asarray(r)
    return pd.Series(start * np.cumprod(1 + r), index=pd.bdate_range(end=end, periods=len(r)))


GOOD = {"peTTM": 18.0, "revenueGrowthTTMYoy": 14.0, "netProfitMarginTTM": 22.0, "roeTTM": 30.0, "totalDebt/totalEquityQuarterly": 0.3,
        "52WeekHigh": 120.0, "52WeekLow": 80.0, "beta": 1.0, "dividendYieldIndicatedAnnual": 2.5, "marketCapitalization": 500_000}
QUOTE = {"c": 100.0, "dp": 1.0}
TRENDS = [{"period": "2026-11-01", "strongBuy": 8, "buy": 8, "hold": 2, "sell": 0, "strongSell": 0},
          {"period": "2026-10-01", "strongBuy": 8, "buy": 8, "hold": 2, "sell": 0, "strongSell": 0}]


# ---------------------------------------------------------------- metric lookup
def test_metric_tries_aliases_in_order_and_ignores_junk():
    assert dlib.metric({"psAnnual": 3.0, "psTTM": 2.0}, "ps") == 2.0
    assert dlib.metric({"psAnnual": 3.0}, "ps") == 3.0
    assert dlib.metric({"psTTM": "abc", "psAnnual": 4}, "ps") == 4.0
    assert dlib.metric({"psTTM": True}, "ps") is None and dlib.metric({"psTTM": float("nan")}, "ps") is None
    assert dlib.metric(None, "ps") is None and dlib.metric({}, "pe") is None
    assert dlib.metric({"peTTM": 20}, "pe") == 20.0                       # the dashboard's aliases still work
    assert dlib.metric({"customKey": 5}, "customKey") == 5.0


# ---------------------------------------------------------------- size and fund detection
@pytest.mark.parametrize("mcap,label", [(3_000_000, "mega-cap"), (200_000, "mega-cap"), (50_000, "large-cap"), (5_000, "mid-cap"),
                                        (500, "small-cap"), (100, "micro-cap")])
def test_size_buckets(mcap, label):
    assert dlib.size_bucket(mcap)[0] == label


def test_size_bucket_and_money_words_handle_missing():
    assert dlib.size_bucket(None) is None and dlib.size_bucket(0) is None and dlib.size_bucket(-5) is None
    assert dlib.money_words(None) is None
    assert dlib.money_words(3_200_000) == "about $3.2 trillion" and dlib.money_words(45_000) == "about $45 billion" and dlib.money_words(850) == "about $850 million"


def test_is_fund_only_when_no_company_data_at_all():
    assert dlib.is_fund({}, {"beta": 1.0, "52WeekHigh": 500})
    assert not dlib.is_fund({"name": "Apple"}, {"beta": 1.0})
    assert not dlib.is_fund({}, {"peTTM": 20})
    assert not dlib.is_fund(None, {"netProfitMarginTTM": 5})


# ---------------------------------------------------------------- grading
@pytest.mark.parametrize("rule,v,expect", [
    (("pe", 20, 40), 15, "good"), (("pe", 20, 40), 20, "good"), (("pe", 20, 40), 30, "ok"), (("pe", 20, 40), 41, "watch"),
    (("pe", 20, 40), 0, "watch"), (("pe", 20, 40), -5, "watch"),
    (("low", 0.5, 2), 0.5, "good"), (("low", 0.5, 2), 1.0, "ok"), (("low", 0.5, 2), 2.0, "watch"),
    (("high", 15, 0), 15, "good"), (("high", 15, 0), 5, "ok"), (("high", 15, 0), -0.1, "watch"), (("high", 15, 0), 0, "ok"),
    (("flag", 1.5), 1.49, "ok"), (("flag", 1.5), 1.5, "watch"),
    (None, 5, None), (("high", 1, 0), None, None)])
def test_grade(rule, v, expect):
    assert dlib.grade(rule, v) == expect


def test_grades_match_the_dashboards_screen_lines():
    # the screen (idea_lib) and the deep-dive must agree on every shared threshold
    for pe, g in ((20, "pro"), (20.1, None), (40.1, "con")):
        ev = il.evaluate("X", None, {"peTTM": pe}, None)
        got = "pro" if any(l == "Valuation" for l, _ in ev["pros"]) else "con" if any(l == "Valuation" for l, _ in ev["cons"]) else None
        assert got == g
        want = {"pro": "good", "con": "watch", None: "ok"}[g]
        assert dlib.grade(("pe", 20, 40), pe) == want
    for de, g in ((0.5, "pro"), (1.0, None), (2.0, "con")):
        ev = il.evaluate("X", None, {"totalDebt/totalEquityQuarterly": de}, None)
        got = "pro" if ev["pros"] else "con" if ev["cons"] else None
        assert got == g and dlib.grade(("low", 0.5, 2), de) == {"pro": "good", "con": "watch", None: "ok"}[g]


def test_key_numbers_rows_formats_and_missing():
    rows = {r["key"]: r for r in dlib.key_numbers(GOOD)}
    assert rows["pe"]["shown"] == "18.0×" and rows["pe"]["read"] == "Good"
    assert rows["rev_growth"]["shown"] == "14.0%" and rows["debt_equity"]["shown"] == "0.30"
    assert rows["div_yield"]["read"] == "" and rows["beta"]["read"] == "OK"
    assert "ps" not in rows and "pfcf" not in rows                         # absent data is left out, not shown as zero
    assert all(r["meaning"] and r["group"] for r in rows.values())
    assert dlib.key_numbers(None) == [] and dlib.key_numbers({}) == []


def test_every_key_is_unique_and_has_a_known_format():
    keys = [k for _g, _l, k, *_ in dlib.KEYS]
    assert len(keys) == len(set(keys))
    assert {kind for _g, _l, _k, kind, *_ in dlib.KEYS} <= {"x", "pct", "ratio", "mshares"}
    assert all(k in dlib.ALL_ALIASES for k in keys)


def test_rules_table_covers_every_graded_measure():
    graded = [l for _g, l, _k, _kind, rule, _m in dlib.KEYS if rule]
    assert [r[1] for r in dlib.rules_table()] == graded
    assert ("Valuation", "P/E (trailing 12 months)", "above 0 and up to 20", "0 or below, or above 40") in dlib.rules_table()


# ---------------------------------------------------------------- price statistics
def test_exact_returns_for_a_constant_daily_gain():
    g = 0.001
    s = dlib.price_stats(px(g))
    assert s["1M"] == pytest.approx((1 + g) ** 21 - 1) and s["3M"] == pytest.approx((1 + g) ** 63 - 1)
    assert s["1Y"] == pytest.approx((1 + g) ** 252 - 1) and s["3Y"] == pytest.approx((1 + g) ** 252 - 1)
    assert s["5Y"] == pytest.approx((1 + g) ** 252 - 1)
    assert s["volatility"] == pytest.approx(0, abs=1e-9) and s["max_drawdown"] == pytest.approx(0)
    assert s["trend"] == "up" and s["from_high"] == pytest.approx(0) and s["range_pos"] == pytest.approx(1)


def test_drawdown_is_the_worst_peak_to_trough_and_dated():
    r = np.full(1500, 0.0005)
    r[1000] = -0.5
    s = dlib.price_stats(px(r))
    assert s["max_drawdown"] == pytest.approx(-0.5, abs=0.01)
    assert s["max_drawdown_date"] == px(r).index[1000]
    assert s["worst_day"] == pytest.approx(-0.5) and s["worst_day_date"] == px(r).index[1000]
    assert s["max_drawdown"] < s["current_drawdown"] < 0                         # partly recovered since


def test_dividends_are_included_in_returns_but_not_in_the_price_trend():
    p = px(0.0)                                                                # flat price
    d = pd.Series([1.0], index=[p.index[-100]])
    s = dlib.price_stats(p, d)
    assert s["1Y"] == pytest.approx(0.01, abs=1e-6)                           # $1 on $100
    assert s["vs200"] == pytest.approx(0, abs=1e-9)
    assert dlib.price_stats(p)["1Y"] == pytest.approx(0)


def test_beta_and_excess_return_against_a_benchmark():
    rng = np.random.default_rng(3)
    b = rng.normal(0.0004, 0.01, 1500)
    bench, stock = px(b), px(2 * b)
    s = dlib.price_stats(stock, None, bench)
    assert s["beta"] == pytest.approx(2.0, abs=0.05)
    assert s["excess_1y"] == pytest.approx(s["1Y"] - s["bench_1y"]) and s["excess_3y"] is not None
    none = dlib.price_stats(stock)
    assert none["beta"] is None and none["excess_1y"] is None and none["bench_1y"] is None


def test_trend_down_mixed_and_short_history():
    assert dlib.price_stats(px(-0.001))["trend"] == "down"
    r = np.r_[np.full(1450, 0.001), np.full(50, -0.0005)]
    assert dlib.price_stats(px(r))["trend"] == "mixed"                          # long uptrend, recent dip below the 50-day
    s = dlib.price_stats(px(0.001, n=100))
    assert s["vs200"] is None and s["trend"] is None and s["3Y"] is None and s["volatility"] is None
    assert dlib.price_stats(px(0.001, n=40)) is None and dlib.price_stats(None) is None and dlib.price_stats(pd.Series(dtype=float)) is None


def test_bad_rows_in_prices_are_ignored():
    p = px(0.001)
    p.iloc[10] = np.nan
    p.iloc[20] = -1.0
    s = dlib.price_stats(p)
    assert s is not None and np.isfinite(s["1Y"])


def test_returns_table_and_compare_curves():
    stock, bench = px(0.001), px(0.0005)
    t = dlib.returns_table(stock, None, bench)
    assert list(t["Period"]) == ["1M", "3M", "6M", "1Y", "3Y per year", "5Y per year"]
    row = t[t["Period"] == "1Y"].iloc[0]
    assert row["Difference"] == pytest.approx(row["Stock"] - row["S&P 500"]) and row["Difference"] > 0
    no_bench = dlib.returns_table(stock, None, None)
    assert no_bench["S&P 500"].isna().all()
    c = dlib.compare_curves(stock, None, bench, None, years=3)
    assert set(c) == {"Stock", "S&P 500"} and c["Stock"].iloc[0] == pytest.approx(10_000) and c["S&P 500"].iloc[0] == pytest.approx(10_000)
    assert c["Stock"].index[0] == c["S&P 500"].index[0] and c["Stock"].iloc[-1] > c["S&P 500"].iloc[-1]
    assert set(dlib.compare_curves(stock, None, None, None)) == {"Stock"} and dlib.compare_curves(None, None, None, None) == {}


# ---------------------------------------------------------------- pros and cons
def test_assess_extends_the_dashboard_screen_without_changing_it():
    base = il.evaluate("X", QUOTE, GOOD, TRENDS)
    ev = dlib.assess("X", QUOTE, GOOD, TRENDS)
    assert ev["pros"][:len(base["pros"])] == base["pros"] and ev["cons"][:len(base["cons"])] == base["cons"]
    assert ev["base_pros"] == len(base["pros"]) and ev["facts"] == base["facts"]
    assert ev["net"] == len(ev["pros"]) - len(ev["cons"])


def labels(ev, kind):
    return {lab for lab, _ in ev[kind]}


def test_extra_company_signals_both_directions():
    good = dict(GOOD, pfcfShareTTM=15, revenueGrowth5Y=12, epsGrowth5Y=14, operatingMarginTTM=30, netInterestCoverageTTM=20)
    ev = dlib.assess("X", QUOTE, good, TRENDS)
    assert {"Valuation (cash)", "Growth over time", "Earnings over time", "Operating margin", "Interest costs"} <= labels(ev, "pros")
    bad = dict(GOOD, pfcfShareTTM=-5, revenueGrowth5Y=-3, epsGrowth5Y=-4, operatingMarginTTM=2, netInterestCoverageTTM=1.5,
               currentRatioQuarterly=0.7, payoutRatioTTM=120)
    ev = dlib.assess("X", QUOTE, bad, TRENDS)
    assert {"Valuation (cash)", "Growth over time", "Earnings over time", "Operating margin", "Interest costs", "Short-term cash", "Dividend safety"} <= labels(ev, "cons")


def test_payout_warning_needs_an_actual_dividend():
    ev = dlib.assess("X", QUOTE, {**GOOD, "dividendYieldIndicatedAnnual": 0, "payoutRatioTTM": 150}, TRENDS)
    assert "Dividend safety" not in labels(ev, "cons")


def test_price_signals_use_history():
    up = dlib.price_stats(px(0.0008, n=1500))
    ev = dlib.assess("X", QUOTE, GOOD, TRENDS, up)
    assert {"Trend", "Swings", "Worst fall"} <= labels(ev, "pros")
    crash = np.r_[np.full(1000, 0.001), [-0.6], np.full(499, -0.0005)]
    dn = dlib.price_stats(px(crash))
    ev = dlib.assess("X", QUOTE, GOOD, TRENDS, dn)
    assert "Trend" in labels(ev, "cons") and "Worst fall" in labels(ev, "cons")
    wild = dlib.price_stats(px(np.random.default_rng(1).normal(0.0, 0.04, 1500)))
    assert "Swings" in labels(dlib.assess("X", QUOTE, GOOD, TRENDS, wild), "cons")


def test_versus_the_market_needs_a_five_point_gap():
    b = np.random.default_rng(5).normal(0.0004, 0.01, 1500)
    stats = dlib.price_stats(px(b + 0.0006), None, px(b))
    assert "Versus the market" in labels(dlib.assess("X", QUOTE, GOOD, TRENDS, stats), "pros")
    stats = dlib.price_stats(px(b - 0.0006), None, px(b))
    assert "Versus the market" in labels(dlib.assess("X", QUOTE, GOOD, TRENDS, stats), "cons")
    stats = dlib.price_stats(px(b), None, px(b))
    both = labels(dlib.assess("X", QUOTE, GOOD, TRENDS, stats), "pros") | labels(dlib.assess("X", QUOTE, GOOD, TRENDS, stats), "cons")
    assert "Versus the market" not in both


def test_dividend_streak_and_earnings_flags():
    ev = dlib.assess("X", QUOTE, GOOD, TRENDS, None, {"active": True, "streak": 7})
    assert "Dividend record" in labels(ev, "pros")
    assert "Dividend record" not in labels(dlib.assess("X", QUOTE, GOOD, TRENDS, None, {"active": True, "streak": 4}), "pros")
    assert "Dividend record" not in labels(dlib.assess("X", QUOTE, GOOD, TRENDS, None, {"active": False, "streak": 9}), "pros")
    for days, word in ((0, "today"), (1, "tomorrow"), (5, "in 5 days")):
        ev = dlib.assess("X", QUOTE, GOOD, TRENDS, None, None, days)
        assert any(word in t for lab, t in ev["cons"] if lab == "Earnings soon")
    assert "Earnings soon" not in labels(dlib.assess("X", QUOTE, GOOD, TRENDS, None, None, 15), "cons")
    assert "Earnings soon" not in labels(dlib.assess("X", QUOTE, GOOD, TRENDS, None, None, None), "cons")


def test_extra_measures_raise_coverage_and_eligibility():
    thin = {"peTTM": 18.0, "beta": 1.0}
    assert not dlib.assess("X", QUOTE, thin, None)["eligible"]
    s = dlib.price_stats(px(0.0008))
    ev = dlib.assess("X", QUOTE, thin, None, s)
    assert ev["covered"] > il.evaluate("X", QUOTE, thin, None)["covered"]


def test_assess_on_nothing_does_not_crash():
    ev = dlib.assess("X", None, None, None)
    assert ev["pros"] == [] and ev["cons"] == [] and ev["avg"] is None and not ev["eligible"]


# ---------------------------------------------------------------- earnings and holdings
def test_earnings_in_days_picks_the_next_date_for_that_symbol_only():
    cal = {"earningsCalendar": [
        {"symbol": "AAPL", "date": "2026-12-03"}, {"symbol": "AAPL", "date": "2026-11-25"}, {"symbol": "MSFT", "date": "2026-11-20"},
        {"symbol": "AAPL", "date": "2026-11-01"}, {"symbol": "AAPL", "date": "bad"}, {"symbol": "AAPL"}, {"symbol": "AAPL", "date": "2099-01-01"}]}
    assert dlib.earnings_in_days(cal, "aapl", TODAY) == (6, dt.date(2026, 11, 25))
    assert dlib.earnings_in_days(cal, "NVDA", TODAY) is None
    assert dlib.earnings_in_days({"earningsCalendar": [{"symbol": "AAPL", "date": "2099-01-01"}]}, "AAPL", TODAY) is None
    assert dlib.earnings_in_days(None, "AAPL", TODAY) is None and dlib.earnings_in_days({}, "AAPL", TODAY) is None
    assert dlib.earnings_in_days({"earningsCalendar": [{"symbol": "AAPL", "date": "2026-11-19"}]}, "AAPL", TODAY)[0] == 0


def test_held_context_is_percent_only():
    assert dlib.held_context("voo", {"VOO": 72.8, "AAPL": 15.5}) == {"held": True, "weight": 72.8}
    assert dlib.held_context("NVDA", {"VOO": 72.8}) == {"held": False, "weight": None}
    assert dlib.held_context("VOO", {}) is None and dlib.held_context("VOO", None) is None


def test_swing_and_fall_thresholds_have_a_middle_band_with_no_verdict():
    mid_vol = dlib.price_stats(px(np.random.default_rng(2).normal(0.0004, 0.025, 1500)))
    assert 0.30 < mid_vol["volatility"] < 0.45
    ev = dlib.assess("X", QUOTE, GOOD, TRENDS, dict(mid_vol, trend=None, max_drawdown=-0.35, excess_3y=None))
    assert "Swings" not in labels(ev, "pros") | labels(ev, "cons")
    assert "Worst fall" not in labels(ev, "pros") | labels(ev, "cons")                       # -35%: neither mild nor severe
    edge = dict(mid_vol, trend=None, max_drawdown=-0.49)
    assert "Worst fall" not in labels(dlib.assess("X", QUOTE, GOOD, TRENDS, edge), "cons")
    assert "Worst fall" in labels(dlib.assess("X", QUOTE, GOOD, TRENDS, dict(edge, max_drawdown=-0.5)), "cons")
    assert "Worst fall" in labels(dlib.assess("X", QUOTE, GOOD, TRENDS, dict(edge, max_drawdown=-0.2)), "pros")
    assert "Worst fall" not in labels(dlib.assess("X", QUOTE, GOOD, TRENDS, dict(edge, max_drawdown=-0.2, years_of_history=1)), "pros")   # too little history
