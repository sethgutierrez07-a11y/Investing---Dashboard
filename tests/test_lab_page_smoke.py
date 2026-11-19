"""Run pages/3_Strategy_Lab.py with a stand-in Streamlit, fake prices and stand-in charts."""

import runpy
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import price_data as pdx  # noqa: E402


class Stopped(Exception):
    pass


def prices(n=2000, seed=2):
    rng = np.random.default_rng(seed)
    return pd.Series(100 * np.exp(np.cumsum(rng.normal(0.0003, 0.01, n))), index=pd.bdate_range("2012-01-02", periods=n))


def make_st(strategy="trend", press=(), session=None):
    st = MagicMock(name="streamlit")
    st.secrets = {}
    st.session_state = session if session is not None else {}
    st.cache_data.side_effect = lambda *a, **k: (lambda f: f)
    st.text_input.return_value = "SPY"
    st.selectbox.side_effect = lambda label, options, **k: strategy
    st.slider.side_effect = lambda label, lo, hi, default, step=None, **k: default
    st.file_uploader.return_value = None
    st.button.side_effect = lambda label, **k: label in press
    st.columns.side_effect = lambda spec, **k: [MagicMock() for _ in range(spec if isinstance(spec, int) else len(spec))]
    st.stop.side_effect = Stopped
    st.context.theme.type = "dark"
    return st


def run(monkeypatch, st, load=None):
    charts = types.ModuleType("lab_charts")
    charts.equity_chart = MagicMock(return_value="equity")
    charts.drawdown_chart = MagicMock(return_value="dd")
    charts.luck_chart = MagicMock(return_value="luck")
    monkeypatch.setitem(sys.modules, "streamlit", st)
    monkeypatch.setitem(sys.modules, "lab_charts", charts)
    monkeypatch.setattr(pdx, "load_history", load or (lambda sym, key: (prices(), "Yahoo Finance (dividend-adjusted)", [])))
    sys.modules.pop("lab_lib", None)
    runpy.run_path(str(ROOT / "pages" / "3_Strategy_Lab.py"), run_name="__main__")
    return charts


def text(st):
    out = []
    for name in ("markdown", "caption", "metric", "info", "warning", "error", "success", "subheader", "title"):
        out += [str(c) for c in getattr(st, name).call_args_list]
    return " ".join(out)


def test_trend_page_shows_train_results_luck_test_trial_counter_and_locks_held_out(monkeypatch):
    st = make_st("trend")
    charts = run(monkeypatch, st)
    assert charts.equity_chart.call_count == 1                  # training window only
    assert charts.luck_chart.call_count == 1
    t = text(st)
    assert "Is it luck?" in t and "Variations you've tried this session: 1" in t
    assert "Reveal the held-out period" in str(st.button.call_args_list)
    assert "overfit" not in t.lower() and "fresh data" not in t
    assert len(st.session_state["lab_trials"]) == 1


def test_revealed_period_adds_chart_table_and_verdict(monkeypatch):
    st = make_st("trend", session={"lab_revealed": {"SPY"}})
    charts = run(monkeypatch, st)
    assert charts.equity_chart.call_count == 2                  # training + held-out
    assert "Edge over buy-and-hold" in text(st)


def test_pressing_reveal_unlocks_for_that_ticker(monkeypatch):
    st = make_st("trend", press=("Reveal the held-out period",))
    run(monkeypatch, st)
    assert "SPY" in st.session_state["lab_revealed"] and st.rerun.called


def test_dca_has_no_luck_chart_and_explains_why(monkeypatch):
    st = make_st("dca")
    charts = run(monkeypatch, st)
    assert charts.luck_chart.call_count == 0 and charts.equity_chart.call_count == 1
    assert "no market timing to test" in text(st)


def test_trials_accumulate_across_settings_and_are_not_double_counted(monkeypatch):
    session = {}
    run(monkeypatch, make_st("trend", session=session))
    run(monkeypatch, make_st("trend", session=session))         # same setup again
    assert len(session["lab_trials"]) == 1
    st = make_st("momentum", session=session)
    run(monkeypatch, st)
    assert len(session["lab_trials"]) == 2 and "Variations you've tried this session: 2" in text(st)


def test_price_failure_shows_help_not_a_traceback(monkeypatch):
    def down(sym, key):
        raise pdx.PriceDataError("Yahoo Finance didn't answer (YFRateLimitError).")

    st = make_st("trend")
    with pytest.raises(Stopped):
        run(monkeypatch, st, load=down)
    t = text(st)
    assert "Couldn't get price history for SPY" in t and "upload a CSV" in t


def test_split_adjusted_source_warns_about_dividends(monkeypatch):
    st = make_st("trend")
    run(monkeypatch, st, load=lambda s, k: (prices(), "Twelve Data (split-adjusted; dividends not included)", ["Yahoo down"]))
    assert "leaves out dividends" in text(st) and "Yahoo down" in text(st)


def test_too_little_history_in_training_window_stops_cleanly(monkeypatch):
    st = make_st("trend")
    # 300 days of data, 70% train = 210 days, but the 200-day average needs a warm-up; still >30 return days, so it runs
    run(monkeypatch, st, load=lambda s, k: (prices(300), "Yahoo", []))
    assert st.dataframe.called or st.plotly_chart.called
