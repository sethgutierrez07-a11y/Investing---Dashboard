import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import risk_lib as rl  # noqa: E402

IDX = pd.bdate_range("2021-01-04", periods=800)


def rets(seed, vol=0.01, drift=0.0004, idx=IDX):
    return pd.Series(np.random.default_rng(seed).normal(drift, vol, len(idx)), index=idx)


# ---- total returns
def test_total_returns_adds_the_dividend_on_the_ex_date():
    p = pd.Series([100.0, 100.0, 98.0, 99.0], index=pd.bdate_range("2024-01-02", periods=4))
    d = pd.Series([2.0], index=[p.index[2]])
    r = rl.total_returns(p, d)
    assert r.iloc[0] == 0.0 and r.iloc[1] == pytest.approx((98 + 2) / 100 - 1) and r.iloc[2] == pytest.approx(99 / 98 - 1)
    assert rl.total_returns(p, None).iloc[1] == pytest.approx(-0.02)
    assert rl.total_returns(p.iloc[:1], None).empty


# ---- alignment
def test_aligned_returns_uses_a_common_window_and_drops_short_histories():
    a, b = rets(1), rets(2)
    short = rets(3, idx=IDX[-100:])
    df, ex = rl.aligned_returns({"A": a, "B": b, "NEW": short}, years=None)
    assert list(df.columns) == ["A", "B"] and ex == ["NEW"] and len(df) == 800
    df2, ex2 = rl.aligned_returns({"A": a, "B": b}, years=1)
    assert ex2 == [] and 250 <= len(df2) <= 262
    assert rl.aligned_returns({}, 3)[0].empty


def test_aligned_returns_keeps_a_lone_ticker_and_empty_inputs_safe():
    df, ex = rl.aligned_returns({"A": rets(1, idx=IDX[:100])}, None)
    assert list(df.columns) == ["A"] and ex == []


# ---- weights, mix
def test_normalize_weights_handles_zero_and_negative():
    assert rl.normalize_weights({"A": 3, "B": 1}, ["A", "B"]) == {"A": 0.75, "B": 0.25}
    assert rl.normalize_weights({"A": 0, "B": 0}, ["A", "B"]) == {"A": 0.5, "B": 0.5}
    assert rl.normalize_weights({"A": -5, "B": 1}, ["A", "B"]) == {"A": 0.0, "B": 1.0}


def test_portfolio_return_is_the_weighted_average():
    df = pd.DataFrame({"A": [0.02, -0.01], "B": [0.00, 0.03]}, index=pd.bdate_range("2024-01-02", periods=2))
    r = rl.portfolio_returns(df, {"A": 1, "B": 3})
    assert r.tolist() == pytest.approx([0.005, 0.0200])


# ---- diversification
def test_correlation_and_diversification_ratio_behave_sensibly():
    base = rets(1)
    twin = base * 1.0
    indep = rets(9)
    same = pd.DataFrame({"A": base, "B": twin})
    mixed = pd.DataFrame({"A": base, "B": indep})
    w = {"A": 0.5, "B": 0.5}
    assert rl.avg_pairwise_corr(rl.correlation(same), w) == pytest.approx(1.0)
    assert abs(rl.avg_pairwise_corr(rl.correlation(mixed), w)) < 0.15
    assert rl.diversification_ratio(same, w) == pytest.approx(1.0)
    assert rl.diversification_ratio(mixed, w) == pytest.approx(1.38, abs=0.08)              # ~sqrt(2) for two independent equals
    assert rl.avg_pairwise_corr(rl.correlation(mixed[["A"]]), {"A": 1}) is None


def test_extreme_pairs():
    df = pd.DataFrame({"A": rets(1), "B": rets(1) + rets(2, 0.002), "C": rets(7)})
    hi, lo = rl.extreme_pairs(rl.correlation(df))
    assert {hi[0], hi[1]} == {"A", "B"} and hi[2] > 0.9 and "C" in (lo[0], lo[1])
    assert rl.extreme_pairs(rl.correlation(df[["A"]])) == (None, None)


def test_risk_contributions_sum_to_one_and_follow_volatility():
    df = pd.DataFrame({"CALM": rets(1, 0.005), "WILD": rets(2, 0.03)})
    rc = rl.risk_contributions(df, {"CALM": 0.5, "WILD": 0.5})
    assert rc.sum() == pytest.approx(1.0) and rc["WILD"] > 0.9               # half the money, nearly all the risk
    rc2 = rl.risk_contributions(df, {"CALM": 0.95, "WILD": 0.05})
    assert rc2["WILD"] < 0.5 and rc2.sum() == pytest.approx(1.0)


# ---- beta and stress
def test_betas_recover_known_sensitivities():
    m = rets(5)
    df = pd.DataFrame({"HI": 1.5 * m + rets(6, 0.001, 0), "LO": 0.5 * m + rets(7, 0.001, 0), "NOISE": rets(8)})
    b = rl.betas(df, m)
    assert b["HI"] == pytest.approx(1.5, abs=0.1) and b["LO"] == pytest.approx(0.5, abs=0.1) and abs(b["NOISE"]) < 0.2
    assert rl.portfolio_beta({"HI": 0.5, "LO": 0.5}, b) == pytest.approx(1.0, abs=0.1)
    assert rl.portfolio_beta({"A": 1}, {"A": None}) is None
    short = rl.betas(df.iloc[:30], m)
    assert all(v is None for v in short.values())


def test_stress_table_scales_with_the_shock_and_adds_up():
    t = rl.stress_table({"A": 0.6, "B": 0.4}, {"A": 1.2, "B": 0.5}, shocks=(-10, -20))
    assert t["Your mix %"].tolist() == pytest.approx([-(0.6 * 1.2 + 0.4 * 0.5) * 10, -(0.6 * 1.2 + 0.4 * 0.5) * 20])
    assert (t["A"] + t["B"]).tolist() == pytest.approx(t["Your mix %"].tolist())
    assert t.loc[1, "Market move %"] == -20.0
    assert rl.stress_table({"A": 1}, {"A": None}).loc[0, "Your mix %"] is None


# ---- metrics and episodes
def test_risk_metrics_on_known_series():
    idx = pd.bdate_range("2022-01-03", periods=300)
    r = pd.Series(0.0, index=idx)
    r.iloc[100] = -0.10
    m = rl.risk_metrics(r)
    assert m["max_drawdown"] == pytest.approx(-0.10) and m["worst_day"] == pytest.approx(-0.10) and m["worst_day_date"] == idx[100]
    assert m["worst_month"] == pytest.approx(-0.10) and m["total_return"] == pytest.approx(-0.10)
    assert rl.risk_metrics(r.iloc[:10]) is None


def test_drawdown_episodes_find_depth_dates_and_recovery():
    idx = pd.bdate_range("2022-01-03", periods=400)
    r = pd.Series(0.003, index=idx)
    r.iloc[50:60] = -0.02          # first fall (~-18%), recovered within about 3 months
    r.iloc[200:205] = -0.02        # second, smaller fall (~-9.6%), also recovered
    eps = rl.drawdown_episodes(r, n=3)
    assert eps[0]["depth"] < eps[1]["depth"] < -0.05
    first = eps[0]
    assert first["peak"] == idx[49] and first["trough"] == idx[59] and first["recovered"] is not None and first["days_to_recover"] > 0
    assert rl.drawdown_episodes(pd.Series(0.003, index=idx)) == []
    assert rl.drawdown_episodes(None) == []


def test_unrecovered_episode_has_no_recovery_date():
    idx = pd.bdate_range("2022-01-03", periods=200)
    r = pd.Series(0.001, index=idx)
    r.iloc[150:] = -0.003
    e = rl.drawdown_episodes(r)[0]
    assert e["recovered"] is None and e["days_to_recover"] is None


def test_window_returns_need_coverage_and_match_hand_math():
    idx = pd.bdate_range("2020-01-02", "2020-12-31")
    r = pd.Series(0.001, index=idx)
    got = rl.window_return(r, "2020-02-19", "2020-03-23")
    n = int(((idx > "2020-02-19") & (idx <= "2020-03-23")).sum())
    assert got == pytest.approx(1.001 ** n - 1)
    assert rl.window_return(r, "2018-09-20", "2018-12-24") is None            # not covered
    rows = rl.history_table(r, r)
    assert [x["label"] for x in rows] == ["COVID crash"]
