import datetime as dt
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import lab_text as lt  # noqa: E402


def M(cagr, dd, sharpe=0.8, **extra):
    return {"cagr": cagr, "max_drawdown": dd, "sharpe": sharpe, "years": 8.0, **extra}


BASE = dict(symbol="SPY", key="trend", label="Trend following", params={"window": 200}, cost_bps=10, source="Yahoo Finance",
            start=dt.date(2010, 1, 4), end=dt.date(2024, 1, 2), split=dt.date(2019, 6, 3), train_pct=70, benchmark_name="Buy and hold",
            ms=M(0.07, -0.19, time_invested=0.72, trades=24), mb=M(0.09, -0.34, sharpe=0.6), cagr_no_cost=0.075,
            luck={"p_value": 0.2, "observed": 0.05, "median_random": 0.04}, luck_text="20% of random placements did as well or better. Nothing here beats luck.",
            n_trials=1, has_timing=True, revealed=False)


def build(**over):
    return dict(lt.write_summary(**{**BASE, **over}))


def txt(s, name):
    return " ".join(s[name])


def test_setup_explains_rule_period_costs_and_yardstick():
    t = txt(build(), "The setup")
    assert "above its 200-day average" in t and "about 10 months" in t
    assert "Jan 2010 to Jan 2024" in t and "to Jun 2019" in t and "10 basis points (0.10%)" in t
    assert "buy and hold" in t.lower()
    assert "higher than it was 126 trading days" in txt(build(key="momentum", params={"lookback": 126}), "The setup")
    assert "first trading day of every month" in txt(build(key="dca", params={}, has_timing=False), "The setup")


def test_lower_return_but_shallower_drawdown_is_framed_as_a_trade():
    t = txt(build(), "What happened")
    assert "7.0% a year against 9.0%" in t and "-2.0 points" in t
    assert "19.0% from a peak, against 34.0%" in t and "shallower by 15 points" in t
    assert "trade, not a free lunch" in t and "78% of the return" in t        # 7/9
    assert "0.80 against 0.60" in t and "more efficient" in t


@pytest.mark.parametrize("ms,mb,expect", [
    (M(0.11, -0.20), M(0.09, -0.34), "rare and worth being suspicious"),
    (M(0.11, -0.40), M(0.09, -0.34), "taking more risk"),
    (M(0.05, -0.40), M(0.09, -0.34), "worse on return and no better on risk"),
])
def test_other_return_risk_combinations(ms, mb, expect):
    assert expect in txt(build(ms=ms, mb=mb), "What happened")


def test_costs_and_activity_quantifies_drag_and_cash_time():
    t = txt(build(), "Costs & activity")
    assert "24 trades in 8.0 years (about 3.0 a year), invested 72%" in t
    assert "costs took 0.5 points a year" in t
    cheap = txt(build(cagr_no_cost=0.0702), "Costs & activity")
    assert "small" in cheap
    assert "spent a lot of time in cash" in txt(build(ms=M(0.07, -0.19, time_invested=0.4, trades=10)), "Costs & activity")


def test_dca_has_its_own_cash_drag_explanation_and_no_luck_test():
    s = build(key="dca", params={}, has_timing=False, ms=M(0.05, -0.2), mb=M(0.08, -0.3))
    assert "money waiting to be invested" in txt(s, "Costs & activity")
    assert "no market timing to test" in txt(s, "Is it luck?")


def test_luck_section_passes_verdict_scale_and_trial_warning():
    t = txt(build(n_trials=6), "Is it luck?")
    assert "Nothing here beats luck" in t and "earned 5.0% a year before costs" in t and "typical random placement" in t and "6 variations" in t
    assert "variations" not in txt(build(n_trials=1), "Is it luck?")


def test_held_out_section_only_when_revealed_and_carries_the_note():
    assert "Held-out test" not in build()
    s = build(revealed=True, overfit=("warn", "Edge over buy-and-hold: +2.0 points a year in training, -1.0 in the held-out period."),
              ms_test=M(0.04, -0.15), mb_test=M(0.05, -0.2))
    t = txt(s, "Held-out test")
    assert "-1.0 in the held-out period" in t and "returned 4.0% a year against 5.0%" in t and "one test on one stretch" in t
    assert "weakened the case" in txt(s, "Takeaway")


def test_takeaway_branches_and_next_steps():
    t = txt(build(ms=M(0.05, -0.40), mb=M(0.09, -0.34)), "Takeaway")
    assert "did not earn its complexity" in t
    assert "risk-management tool" in txt(build(), "Takeaway")
    lucky = txt(build(ms=M(0.11, -0.4), mb=M(0.09, -0.34)), "Takeaway")
    assert "cannot separate that from chance" in lucky
    good = txt(build(ms=M(0.11, -0.4), mb=M(0.09, -0.34), luck={"p_value": 0.01}), "Takeaway")
    assert "better than chance" in good and "other tickers" in good
    assert "reveal the held-out period once" in txt(build(), "Takeaway")
    assert "reveal the held-out period once" not in txt(build(revealed=True, overfit=("good", "x")), "Takeaway")
    assert "Educational, not advice" in t


def test_section_order_and_no_dollar_signs():
    s = lt.write_summary(**BASE)
    assert [n for n, _ in s] == ["The setup", "What happened", "Costs & activity", "Is it luck?", "Takeaway"]
    assert "$" not in " ".join(" ".join(b) for _, b in s)


def test_luck_section_separates_return_luck_from_the_drawdown_benefit():
    assert "does not judge the shallower worst drop" in txt(build(), "Is it luck?")          # p=0.2 and a 15-point shallower drop
    assert "does not judge" not in txt(build(luck={"p_value": 0.01, "observed": .1, "median_random": .04}), "Is it luck?")
    assert "does not judge" not in txt(build(ms=M(0.07, -0.40), mb=M(0.09, -0.34)), "Is it luck?")
