import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import risk_lib as rl  # noqa: E402
import risk_text as rt  # noqa: E402

IDX = pd.bdate_range("2021-01-04", periods=800)


def metrics(vol=0.01, drift=0.0004, seed=0):
    return rl.risk_metrics(pd.Series(np.random.default_rng(seed).normal(drift, vol, len(IDX)), index=IDX))


def kwargs(**over):
    pm, sm = metrics(0.008, seed=1), metrics(0.01, seed=2)
    w = {"AAA": 0.6, "BBB": 0.4}
    base = dict(
        pm=pm, sm=sm, years=3.2, n=2, n_days=800, rc=pd.Series({"AAA": 0.8, "BBB": 0.2}), weights=w, beta_p=0.9, avg_corr=0.45,
        div_ratio=1.2, hi=("AAA", "BBB", 0.45), lo=("AAA", "BBB", 0.45), excluded=[],
        episodes=[{"peak": pd.Timestamp("2022-01-03"), "trough": pd.Timestamp("2022-10-12"), "depth": 0.22, "recovered": None,
                   "days_down": 300, "days_to_recover": None}],
        hist=[{"label": "2022 bear market", "start": "2022-01-03", "end": "2022-10-12", "mix": -0.2, "market": -0.25}],
        stress_rows=[{"market": -10.0, "mix": -9.0}, {"market": -20.0, "mix": -18.0}], biggest=("AAA", 0.7))
    base.update(over)
    return base


def alltext(sections):
    return "\n".join(b for _, bullets in sections for b in bullets)


def test_sections_and_titles():
    s = rt.write_summary(**kwargs())
    assert [t for t, _ in s] == ["Bottom line", "Diversification", "Bad stretches", "Stress test", "Worth knowing"]


def test_percent_only_and_no_dollar_signs_or_nan():
    text = alltext(rt.write_summary(**kwargs()))
    assert "$" not in text and not re.search(r"\bnan\b|\bNone\b|\binf\b", text, re.I)


def test_bottom_line_names_the_concentrated_holding_with_real_numbers():
    text = alltext(rt.write_summary(**kwargs()))
    assert "AAA is 60% of your money but 80% of your risk" in text
    assert "calmer than the S&P 500" in text


def test_in_line_risk_when_no_holding_stands_out():
    text = alltext(rt.write_summary(**kwargs(rc=pd.Series({"AAA": 0.62, "BBB": 0.38}))))
    assert "roughly in line" in text


def test_single_holding_does_not_talk_about_correlation():
    s = rt.write_summary(**kwargs(n=1, rc=pd.Series({"AAA": 1.0}), weights={"AAA": 1.0}, avg_corr=None, div_ratio=None, hi=None, lo=None))
    d = dict(s)["Diversification"]
    assert len(d) == 1 and "single holding" in d[0]


@pytest.mark.parametrize("c,word", [(0.1, "low"), (0.45, "moderate"), (0.8, "high")])
def test_correlation_levels(c, word):
    assert f"({word})" in alltext(rt.write_summary(**kwargs(avg_corr=c)))


def test_unrecovered_fall_is_said_plainly_and_recovered_gives_months():
    assert "had not yet gotten back" in alltext(rt.write_summary(**kwargs()))
    ep = [{"peak": pd.Timestamp("2022-01-03"), "trough": pd.Timestamp("2022-10-12"), "depth": 0.1, "recovered": pd.Timestamp("2023-06-01"),
           "days_down": 300, "days_to_recover": 304}]
    assert "10 months" in alltext(rt.write_summary(**kwargs(episodes=ep)))


def test_no_episodes_and_no_history_windows_still_read_fine():
    t = alltext(rt.write_summary(**kwargs(episodes=[], hist=[])))
    assert "No fall of 5% or more" in t


def test_history_window_wording_for_gains_and_smaller_losses():
    t = alltext(rt.write_summary(**kwargs()))
    assert "lost 20% against 25%" in t and "a smaller loss" in t
    g = alltext(rt.write_summary(**kwargs(hist=[{"label": "Rally", "start": "a", "end": "b", "mix": 0.1, "market": 0.05}])))
    assert "gained 10% against 5%" in g


def test_stress_text_and_the_missing_data_fallback():
    assert "-20% → your mix about -18%" in alltext(rt.write_summary(**kwargs()))
    assert "Not enough overlapping" in alltext(rt.write_summary(**kwargs(beta_p=None, stress_rows=[], biggest=None)))


def test_excluded_tickers_are_named():
    assert "NEW and OLD" in alltext(rt.write_summary(**kwargs(excluded=["NEW", "OLD"])))
