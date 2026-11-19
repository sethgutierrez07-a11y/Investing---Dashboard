import datetime as dt
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import lab_text as lt  # noqa: E402


def M(cagr, dd, sharpe=0.8, **extra):
    return {"cagr": cagr, "max_drawdown": dd, "sharpe": sharpe, "years": 8.0, "volatility": 0.22, **extra}


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
    assert "faded or vanished" in txt(s, "Takeaway")


PROFILE = {"years_total": 8, "years_up": 6, "best_year": (2013, 0.32), "worst_year": (2018, -0.06),
           "longest_underwater_years": 1.5, "still_underwater": False, "from_peak": -0.04}


@pytest.mark.parametrize("d_ret,d_dd,code", [
    (0.02, 0.10, "win"), (0.02, -0.10, "win_risky"), (-0.02, 0.15, "safer"), (-0.02, -0.05, "lose"), (-0.02, 0.0, "lose"),
    (0.001, 0.10, "smoother"), (0.001, -0.10, "bumpier"), (0.001, 0.0, "tie"), (0.005, 0.0, "win"), (-0.005, 0.03, "safer"),
])
def test_outcome_codes(d_ret, d_dd, code):
    assert lt.outcome(d_ret, d_dd) == code


def test_takeaway_leads_with_a_plain_verdict_and_the_dollar_outcome():
    t = build()["Takeaway"]
    assert t[0].startswith("**In short:** The 200-day trend rule traded return for a smoother ride on SPY.")
    assert "SPY itself was" in t[0]
    out = txt(build(), "Takeaway")
    # 7% for 8 years from $10,000 = 17,182; 9% = 19,926
    assert "$10,000 became $17,182 with the rule against $19,926 for buy and hold" in out
    assert "giving up 2.0 points a year" in out and "worst drop was 19.0% against 34.0%" in out
    assert "What to try next" not in out and "Run the same rule" not in out        # no new homework, just the outcome


@pytest.mark.parametrize("ms,mb,head", [
    (M(0.11, -0.20), M(0.09, -0.34), "beat buy and hold on SPY."),
    (M(0.11, -0.40), M(0.09, -0.34), "earned more than buy and hold on SPY, but with deeper drops."),
    (M(0.05, -0.40), M(0.09, -0.34), "did not beat buy and hold on SPY."),
    (M(0.0905, -0.34), M(0.09, -0.34), "about the same on SPY."),
    (M(0.0905, -0.20), M(0.09, -0.34), "matched buy and hold on SPY with a smoother ride."),
])
def test_takeaway_headline_for_each_outcome(ms, mb, head):
    assert head in build(ms=ms, mb=mb)["Takeaway"][0]


def test_significance_uses_the_luck_test_only_where_it_applies():
    win = dict(ms=M(0.11, -0.20), mb=M(0.09, -0.34))
    strong = txt(build(**win, luck={"p_value": 0.01}), "Takeaway")
    assert "unlikely to be luck: only 1.0% of random placements did as well." in strong and "looks real rather than luck" in strong
    assert "suggestive but not proven: 10%" in txt(build(**win, luck={"p_value": 0.10}), "Takeaway")
    weak = txt(build(**win, luck={"p_value": 0.5}), "Takeaway")
    assert "Luck can explain it: 50%" in weak
    lost = txt(build(ms=M(0.05, -0.40), mb=M(0.09, -0.34)), "Takeaway")
    assert "beside the point" in lost and "random placements" not in lost
    safer = txt(build(luck={"p_value": 0.01}), "Takeaway")                       # lower return, shallower drop
    assert "smoother ride is built in" in safer and "timing also beat chance: only 1.0%" in safer
    assert "still earned less than simply holding" in safer and "looks real rather than luck" not in safer
    assert "no better than random (50% of" in txt(build(luck={"p_value": 0.5}), "Takeaway")
    assert "out of the market at all" in txt(build(luck={"p_value": 0.5}), "Takeaway")
    assert "somewhat better than random (10%" in txt(build(luck={"p_value": 0.10}), "Takeaway")


def test_significance_mentions_small_samples_held_out_and_sealed_state():
    few = txt(build(ms=M(0.11, -0.2, trades=6, time_invested=0.8), mb=M(0.09, -0.34)), "Takeaway")
    assert "only 6 trades" in few and "still sealed" in few
    assert "still sealed" not in txt(build(revealed=True, overfit=("good", "x")), "Takeaway")
    assert "held up" in txt(build(revealed=True, overfit=("good", "x")), "Takeaway")
    assert "faded or vanished" in txt(build(revealed=True, overfit=("warn", "x")), "Takeaway")
    assert "just 3.0 years" in txt(build(ms=M(0.07, -0.19, years=3.0, trades=24, time_invested=0.7)), "Takeaway")


def test_dca_takeaway_says_there_is_nothing_to_test_for_luck():
    s = build(key="dca", params={}, has_timing=False, ms=M(0.05, -0.2), mb=M(0.08, -0.3), benchmark_name="Lump sum on day one")
    t = txt(s, "Takeaway")
    assert t.startswith("**In short:** Dollar-cost averaging") and "lump sum on day one" in t
    assert "Nothing to test for luck" in t and "random placements" not in t


def test_stock_section_reports_return_risk_recovery_and_calendar_years():
    t = txt(build(profile=PROFILE), "Takeaway")
    assert "**How SPY held up:** it grew 9.0% a year over 8.0 years ($19,926 from $10,000)" in t
    assert "worst drop of 34.0%" in t and "yearly swings of about 22%" in t
    assert "longest wait to get back to an earlier high was 1.5 years" in t
    assert "up in 6 of 8 full calendar years (best 2013: +32%, worst 2018: -6%)" in t
    still = txt(build(profile={**PROFILE, "still_underwater": True, "longest_underwater_years": 3.0}), "Takeaway")
    assert "had not recovered by the end of the period" in still
    assert "calendar years" not in txt(build(profile=None), "Takeaway")                # profile is optional


@pytest.mark.parametrize("cagr,dd,descr", [
    (-0.02, -0.5, "a stock that lost money"), (0.01, -0.2, "a weak performer"), (0.15, -0.45, "a strong but volatile stock"),
    (0.09, -0.45, "a decent but volatile stock"), (0.14, -0.2, "a strong, fairly steady stock"), (0.16, -0.30, "a strong stock with real swings"),
    (0.09, -0.2, "a solid, fairly steady stock"), (0.06, -0.25, "a solid, ordinary performer"),
])
def test_stock_class(cagr, dd, descr):
    assert lt.stock_class(cagr, dd)[0] == descr


def test_read_connects_the_stock_to_the_outcome():
    strong = txt(build(ms=M(0.10, -0.15), mb=M(0.16, -0.30)), "Takeaway")
    assert "hard for any sit-out rule to beat" in strong
    scary = txt(build(ms=M(0.10, -0.12), mb=M(0.12, -0.45)), "Takeaway")
    assert "a deep fall for the rule to sidestep" in scary and "fall" in scary
    assert "Educational, not advice" in strong


def test_section_order_and_dollars_are_escaped_for_markdown():
    s = lt.write_summary(**BASE)
    assert [n for n, _ in s] == ["The setup", "What happened", "Costs & activity", "Is it luck?", "Takeaway"]
    assert "$" in " ".join(s[-1][1])
    assert "$" not in " ".join(" ".join(b) for n, b in s if n != "Takeaway")
    esc = lt.md("$10,000 became $17,182")
    assert esc == "\\$10,000 became \\$17,182"


def test_luck_section_separates_return_luck_from_the_drawdown_benefit():
    assert "does not judge the shallower worst drop" in txt(build(), "Is it luck?")          # p=0.2 and a 15-point shallower drop
    assert "does not judge" not in txt(build(luck={"p_value": 0.01, "observed": .1, "median_random": .04}), "Is it luck?")
    assert "does not judge" not in txt(build(ms=M(0.07, -0.40), mb=M(0.09, -0.34)), "Is it luck?")


def test_multiple_tries_are_counted_in_the_significance_line():
    win = dict(ms=M(0.11, -0.20), mb=M(0.09, -0.34), luck={"p_value": 0.001})
    assert "even after counting your 4 tries" in txt(build(**win, n_trials=4), "Takeaway")
