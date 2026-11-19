import datetime as dt
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import idea_lib as il  # noqa: E402

GOOD = {"peTTM": 18.0, "revenueGrowthTTMYoy": 14.0, "netProfitMarginTTM": 22.0, "roeTTM": 30.0,
        "totalDebt/totalEquityQuarterly": 0.3, "52WeekHigh": 120.0, "52WeekLow": 80.0, "beta": 1.0,
        "dividendYieldIndicatedAnnual": 2.5, "marketCapitalization": 250000}
BAD = {"peTTM": 80.0, "revenueGrowthTTMYoy": -5.0, "netProfitMarginTTM": -3.0, "roeTTM": -2.0,
       "totalDebt/totalEquityQuarterly": 3.0, "52WeekHigh": 100.0, "52WeekLow": 40.0, "beta": 2.0}
BULL = [{"strongBuy": 10, "buy": 10, "hold": 2, "sell": 0, "strongSell": 0},
        {"strongBuy": 8, "buy": 10, "hold": 4, "sell": 0, "strongSell": 0}]
BEAR = [{"strongBuy": 0, "buy": 2, "hold": 8, "sell": 4, "strongSell": 2}]


def test_good_company_gets_pros_with_numbers_and_no_cons():
    e = il.evaluate("GOOD", {"c": 100.0, "dp": 1.0}, GOOD, BULL)  # 16.7% below high
    labels = [l for l, _ in e["pros"]]
    assert {"Valuation", "Growth", "Profitability", "Returns", "Balance sheet", "Price", "Analysts", "Dividend"} <= set(labels)
    assert e["cons"] == [] and e["eligible"]
    assert any("14.0%" in t for _, t in e["pros"])             # the number behind the claim is shown
    assert dict(e["facts"])["Below 52-week high"] == "16.7%"


def test_bad_company_gets_cons():
    e = il.evaluate("BAD", {"c": 50.0, "dp": -2.0}, BAD, BEAR)  # 50% below high
    labels = {l for l, _ in e["cons"]}
    assert {"Valuation", "Growth", "Profitability", "Returns", "Balance sheet", "Price", "Analysts", "Volatility"} <= labels
    assert e["pros"] == [] and e["avg"] < 0


def test_negative_earnings_explains_missing_pe():
    e = il.evaluate("X", {"c": 10.0}, {"netProfitMarginTTM": -10.0}, None)
    assert any(l == "Valuation" and "No positive trailing earnings" in t for l, t in e["cons"])


def test_alias_names_and_junk_values_tolerated():
    assert il.metric({"peBasicExclExtraTTM": "22.5"}, "pe") == 22.5
    assert il.metric({"peTTM": None, "peExclExtraTTM": 9}, "pe") == 9.0
    assert il.metric({"peTTM": "n/a"}, "pe") is None
    assert il.metric(None, "pe") is None


def test_not_enough_data_is_not_eligible_and_not_chosen():
    e = il.evaluate("THIN", {"c": 10.0}, {"peTTM": 10.0}, None)
    assert not e["eligible"] and il.choose([e]) is None


def test_choose_prefers_best_score_per_factor_not_most_data():
    good = il.evaluate("GOOD", {"c": 100.0}, GOOD, BULL)
    bad = il.evaluate("BAD", {"c": 50.0}, BAD, BEAR)
    assert il.choose([bad, good])["symbol"] == "GOOD"
    rows = il.comparison_rows([bad, good])
    assert rows[0]["Symbol"] == "GOOD" and rows[1]["Symbol"] == "BAD"


def test_candidates_are_stable_for_the_day_exclude_holdings_and_rotate_on_request():
    day = dt.date(2026, 11, 18).toordinal()
    a = il.pick_candidates(il.UNIVERSE, {"aapl", "MSFT"}, day, 8)
    assert a == il.pick_candidates(il.UNIVERSE, {"AAPL", "MSFT"}, day, 8)  # same all day
    assert len(a) == 8 and "AAPL" not in a and "MSFT" not in a
    assert il.pick_candidates(il.UNIVERSE, set(), day, 8, offset=1) != il.pick_candidates(il.UNIVERSE, set(), day, 8)
    assert il.pick_candidates(["A", "B"], {"A"}, day, 8) == ["B"]


def test_universe_has_no_duplicates():
    assert len(il.UNIVERSE) == len(set(il.UNIVERSE))


def test_split_stocks_and_funds():
    cls = {"AAPL": "Stock", "VOO": "ETF", "FXAIX": "Fund"}
    stocks, funds = il.split_stocks_funds(["VOO", "AAPL", "FXAIX", "NVDA", "QQQ", "BAD"], cls,
                                          {"NVDA": "NVIDIA", "QQQ": "", "BAD": "Error: boom"})
    assert stocks == ["AAPL", "NVDA", "BAD"] and funds == ["VOO", "FXAIX", "QQQ"]


def test_consensus_slices_order_colours_and_zero_filter():
    s = il.consensus_slices({"strongBuy": 12, "buy": 15, "hold": 6, "sell": 0, "strongSell": 1})
    assert [x[0] for x in s] == ["Strong Buy", "Buy", "Hold", "Strong Sell"]   # best to worst, no empty Sell
    assert [x[1] for x in s] == [12, 15, 6, 1]
    assert s[0][2] == "#0f6b2a" and s[-1][2] == "#9b1c1c"
    assert il.consensus_slices({}) == [] and il.consensus_slices(None) == []


@pytest.mark.parametrize("score,label", [(None, "No ratings"), (1.8, "Strong Buy"), (1.0, "Leans Buy"), (0.0, "Hold"),
                                          (-1.0, "Leans Sell"), (-1.9, "Strong Sell")])
def test_consensus_verdict(score, label):
    assert il.consensus_verdict(score) == label
