import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import lab_lib as lab  # noqa: E402


def walk(n=1500, drift=0.0003, vol=0.01, seed=1, start="2015-01-01"):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range(start, periods=n)
    return pd.Series(100 * np.exp(np.cumsum(rng.normal(drift, vol, n))), index=idx)


# ---------- no look-ahead ----------
@pytest.mark.parametrize("shock", [0.2, 5.0])          # the future crashes / spikes
@pytest.mark.parametrize("make", [lambda p: lab.run_trend(p, 50), lambda p: lab.run_momentum(p, 60)])
def test_changing_the_future_never_changes_the_past(make, shock):
    p = walk()
    cut = p.index[900]
    q = p.copy()
    q[q.index > cut] *= shock
    a, b = make(p), make(q)
    pd.testing.assert_series_equal(a.positions[:cut], b.positions[:cut])
    pd.testing.assert_series_equal(a.equity[:cut], b.equity[:cut])


def test_signal_is_acted_on_after_the_lag_not_the_same_day():
    idx = pd.bdate_range("2020-01-01", periods=6)
    sig = pd.Series([0, 0, 1, 1, 0, 0], index=idx, dtype=float)
    pos = lab.to_positions(sig, lag_days=1)
    # signal first true after day 3's close -> trade at day 4's close -> earns from day 5
    assert pos.tolist() == [0, 0, 0, 0, 1, 1]
    assert lab.to_positions(sig, lag_days=0).tolist() == [0, 0, 0, 1, 1, 0]


def test_trend_signal_values():
    idx = pd.bdate_range("2020-01-01", periods=8)
    p = pd.Series([10, 10, 10, 12, 12, 8, 8, 8], index=idx, dtype=float)
    s = lab.trend_signal(p, window=3)
    assert s.tolist() == [0, 0, 0, 1, 1, 0, 0, 0]   # needs a full window first; below average -> cash


# ---------- costs ----------
def test_costs_are_charged_on_entry_and_exit_only():
    idx = pd.bdate_range("2020-01-01", periods=6)
    p = pd.Series(100.0, index=idx)                       # flat prices: any change in equity is cost
    pos = pd.Series([0, 1, 1, 0, 0, 0], index=idx, dtype=float)
    r = lab.run_positions(p, pos, cost_bps=10, name="x")
    assert r.equity.iloc[-1] / lab.START_CAPITAL == pytest.approx((1 - 0.001) ** 2)   # in + out
    free = lab.run_positions(p, pos, cost_bps=0, name="x")
    assert free.equity.iloc[-1] == pytest.approx(lab.START_CAPITAL)


def test_starting_invested_counts_as_a_trade():
    p = pd.Series(100.0, index=pd.bdate_range("2020-01-01", periods=5))
    r = lab.run_positions(p, pd.Series(1.0, index=p.index), cost_bps=100, name="x")
    assert r.equity.iloc[-1] / lab.START_CAPITAL == pytest.approx(0.99)


def test_buy_and_hold_matches_price_ratio():
    p = walk(300)
    bh = lab.run_buy_hold(p)
    assert bh.equity.iloc[-1] / lab.START_CAPITAL == pytest.approx(p.iloc[-1] / p.iloc[0])


# ---------- metrics ----------
def test_metrics_known_values():
    idx = pd.bdate_range("2020-01-01", periods=253)
    ret = pd.Series(0.0, index=idx); ret.iloc[1:] = 0.001
    m = lab.metrics(ret)
    assert m["total_return"] == pytest.approx(1.001**252 - 1)
    assert m["max_drawdown"] == 0 and m["cagr"] > 0
    # a 50% crash then recovery to flat
    ret2 = pd.Series([0.0] * 40 + [-0.5] + [0.0] * 40 + [1.0], index=pd.bdate_range("2020-01-01", periods=82))
    assert lab.metrics(ret2)["max_drawdown"] == pytest.approx(-0.5)
    assert lab.metrics(ret.iloc[:10]) is None            # too short to mean anything


def test_metrics_time_invested_and_trades():
    p = walk(600)
    r = lab.run_trend(p, 50)
    m = lab.metrics(r.returns, r.positions)
    assert 0 < m["time_invested"] < 1 and m["trades"] >= 2


def test_window_and_split():
    p = walk(500)
    d = lab.split_date(p.index, 0.7)
    assert d == p.index[350]
    r = lab.run_buy_hold(p).returns
    assert len(lab.window_returns(r, end=d)) == 350 and len(lab.window_returns(r, start=d)) == 150
    assert lab.split_date(p.index, 5) == p.index[int(500 * 0.95)]


# ---------- DCA ----------
def test_dca_flat_prices_only_loses_costs():
    idx = pd.bdate_range("2020-01-01", periods=300)
    p = pd.Series(50.0, index=idx)
    r = lab.run_dca(p, cost_bps=0)
    assert r.equity.iloc[-1] == pytest.approx(lab.START_CAPITAL)
    assert lab.run_dca(p, cost_bps=10).equity.iloc[-1] < lab.START_CAPITAL


def test_dca_trails_lump_sum_in_a_steadily_rising_market_and_holds_cash_early():
    idx = pd.bdate_range("2020-01-01", periods=500)
    p = pd.Series(np.linspace(100, 200, 500), index=idx)
    d, l = lab.run_dca(p, 0), lab.run_lump_sum(p, 0)
    assert d.equity.iloc[-1] < l.equity.iloc[-1]
    assert d.equity.iloc[0] == pytest.approx(lab.START_CAPITAL)             # first part bought, rest still cash
    assert d.equity.iloc[-1] > lab.START_CAPITAL


# ---------- is it luck? ----------
def test_luck_test_detects_foresight_but_not_a_random_rule():
    p = walk(1200, seed=3)
    ret = p.pct_change().fillna(0.0)
    cheat = (ret > 0).astype(float)                                   # knows the future
    res = lab.timing_luck_test(cheat, ret, n_sims=500, seed=0)
    assert res["p_value"] < 0.01 and res["percentile"] > 99
    rng = np.random.default_rng(5)
    coin = pd.Series((rng.random(len(ret)) > 0.5).astype(float), index=ret.index)
    pvals = [lab.timing_luck_test(pd.Series((np.random.default_rng(s).random(len(ret)) > 0.5).astype(float), index=ret.index),
                                  ret, n_sims=300, seed=s)["p_value"] for s in range(20)]
    assert sum(v < 0.05 for v in pvals) <= 4                          # ~5% expected, never most of them
    assert lab.timing_luck_test(coin, ret, n_sims=300)["p_value"] > 0.01


def test_luck_test_is_deterministic_and_handles_degenerate_inputs():
    p = walk(800)
    r = lab.run_trend(p, 50)
    a = lab.timing_luck_test(r.positions, p.pct_change().fillna(0), n_sims=200, seed=7)
    b = lab.timing_luck_test(r.positions, p.pct_change().fillna(0), n_sims=200, seed=7)
    assert a["p_value"] == b["p_value"]
    always = lab.timing_luck_test(pd.Series(1.0, index=p.index), p.pct_change().fillna(0))
    assert always["p_value"] is None and always["reason"] == "no_timing"
    assert lab.timing_luck_test(r.positions[:30], p.pct_change().fillna(0)[:30])["reason"] == "too_short"


def test_multiple_testing_math():
    assert lab.chance_of_false_hit(1) == pytest.approx(0.05)
    assert lab.chance_of_false_hit(14) == pytest.approx(1 - 0.95**14) and lab.chance_of_false_hit(14) > 0.5
    assert lab.adjusted_threshold(10) == pytest.approx(0.005)
    assert lab.adjusted_threshold(0) == 0.05


def test_luck_verdict_levels_and_honest_wording():
    assert lab.luck_verdict(0.001, 1)[0] == "good"
    lvl, text = lab.luck_verdict(0.03, 12)
    assert lvl == "warn" and "12 variations" in text and "0.42%" in text      # significant alone, not after 12 tries
    assert lab.luck_verdict(0.15, 1)[0] == "warn"
    assert lab.luck_verdict(0.6, 1)[0] == "neutral"
    assert "no timing" in lab.luck_verdict(None, 1, "no_timing")[1]
    assert "proof" in lab.luck_verdict(0.001, 1)[1]                           # never oversells


# ---------- registry ----------
@pytest.mark.parametrize("key,params", [("trend", {"window": 100}), ("momentum", {"lookback": 60}), ("dca", {})])
def test_registry_runs_every_strategy(key, params):
    r = lab.run_strategy(key, walk(700), params, cost_bps=10)
    assert len(r.equity) == 700 and r.equity.iloc[-1] > 0
    assert (r.positions is None) == (not lab.STRATEGIES[key].has_timing)


# ---------- presentation helpers ----------
def test_rebased_equity_and_metrics_table():
    p = walk(400)
    r = lab.run_trend(p, 50)
    eq = lab.rebased_equity(r.returns[200:])
    assert eq.iloc[0] == pytest.approx(lab.START_CAPITAL * (1 + r.returns.iloc[200]))
    t = lab.metrics_table({"Rule": lab.metrics(r.returns, r.positions), "Buy and hold": lab.metrics(lab.run_buy_hold(p).returns),
                           "Short": lab.metrics(r.returns[:5])})
    assert list(t.columns) == ["Rule", "Buy and hold", "Short"]
    assert t.loc["Trades", "Buy and hold"] == "—" and t.loc["Yearly return (CAGR)", "Short"] == "too short"
    assert t.loc["Worst drop from a peak", "Rule"].endswith("%")


def m(cagr, dd=-0.2):
    return {"cagr": cagr, "max_drawdown": dd}


@pytest.mark.parametrize("a,b,c,d,level,word", [
    (m(.12), m(.08), m(.10), m(.07), "good", "held up"),
    (m(.12), m(.08), m(.06), m(.07), "warn", "disappeared"),
    (m(.12), m(.08), m(.09), m(.08), "warn", "faded"),
    (m(.05), m(.08), m(.06), m(.07), "neutral", "no edge in training"),
])
def test_overfit_note(a, b, c, d, level, word):
    lv, text = lab.overfit_note(a, b, c, d)
    assert lv == level and word in text


def test_overfit_note_mentions_shallower_drawdown_and_short_window():
    _, t = lab.overfit_note(m(.12), m(.08), m(.06, -0.10), m(.07, -0.30))
    assert "shallower" in t
    assert lab.overfit_note(m(.1), m(.1), None, m(.1))[0] == "neutral"
