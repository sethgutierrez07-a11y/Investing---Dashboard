"""
Smoke test: run pages/5_Risk.py end to end with stand-ins for Streamlit, SnapTrade and Yahoo.
Checks nothing crashes, the lock holds, only read endpoints are used, no dollar amounts of yours
reach the page, and the right things render. It does not check how the page looks.
"""

import re
import runpy
import sys
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
import dividend_data as dd  # noqa: E402
import holdings_lib as hl  # noqa: E402
import test_lab_charts  # noqa: F401,E402  (installs a plotly stand-in if plotly is missing)
from test_dividends_page_smoke import READ_ONLY, ActAcctInfo, Client, flat, tab_names, text_of  # noqa: E402
from test_holdings_page_smoke import GOOD_SECRETS, POSITIONS, Stopped  # noqa: E402

NOW = pd.Timestamp.now(tz="America/Chicago").tz_localize(None).normalize()
BETA = {"VOO": 1.0, "AAPL": 1.3, "MSFT": 0.9, "SPY": 1.0}


def fake_history(sym, years=8):
    idx = pd.bdate_range(end=NOW, periods=years * 261)
    mkt = np.random.default_rng(7).normal(0.0004, 0.010, len(idx))
    own = np.random.default_rng(abs(hash(sym)) % 1000).normal(0.0, 0.006, len(idx))
    r = BETA.get(sym, 1.0) * mkt + own
    prices = pd.Series(100 * np.exp(np.cumsum(r)), index=idx)
    divs = pd.Series([0.5] * 8, index=idx[::len(idx) // 8][:8]) if sym != "MSFT" else pd.Series(dtype=float)
    return {"prices": prices, "divs": divs, "error": None}


def make_streamlit(secrets=None, unlocked=True, window_index=1, shock=20):
    st = MagicMock(name="streamlit")
    st.secrets = dict(GOOD_SECRETS if secrets is None else secrets)
    st.session_state = {"holdings_unlocked": True} if unlocked else {}
    st.cache_data.side_effect = lambda *a, **k: (lambda f: f)
    st.cache_data.clear = MagicMock()
    st.button.return_value = False
    st.text_input.return_value = ""
    st.radio.side_effect = lambda label, options, **k: options[window_index]
    st.slider.side_effect = lambda *a, **k: shock
    st.columns.side_effect = lambda spec, **k: [MagicMock() for _ in range(spec if isinstance(spec, int) else len(spec))]
    st.tabs.side_effect = lambda labels: [MagicMock() for _ in labels]
    st.stop.side_effect = Stopped
    st.context.theme.type = "dark"
    return st


def run(monkeypatch, st, history=fake_history, positions=POSITIONS):
    info = ActAcctInfo(positions, [])
    made = []
    monkeypatch.setitem(sys.modules, "streamlit", st)
    monkeypatch.setattr(hl, "make_client", lambda cid, key: made.append(1) or Client(info))
    monkeypatch.setattr(dd, "fetch_history", history)
    for m in ("risk_charts", "lab_charts", "holdings_charts", "portfolio_state", "risk_text"):
        sys.modules.pop(m, None)
    runpy.run_path(str(ROOT / "pages" / "5_Risk.py"), run_name="__main__")
    return info, made


@pytest.mark.parametrize("window_index", [0, 1, 2])
def test_page_renders_end_to_end(monkeypatch, window_index):
    st = make_streamlit(window_index=window_index)
    info, made = run(monkeypatch, st)
    assert made and set(info.calls) <= READ_ONLY
    names = tab_names(st)
    assert ["Bottom line", "Diversification", "Bad stretches", "Stress test", "Worth knowing"] in names
    assert ["🧩 Diversification", "📉 Bad stretches", "🧪 Stress test"] in names
    # heatmap, risk-vs-money, growth, drawdown, stress bars
    assert st.plotly_chart.call_count == 5
    text = text_of(st)
    assert "Measured over" in text and "no AI" in text


def test_summary_is_first_and_dollars_are_never_shown(monkeypatch):
    st = make_streamlit()
    run(monkeypatch, st)
    assert [c.args[0] for c in st.subheader.call_args_list][0] == "Summary"
    bullets = [c.args[0] for c in st.markdown.call_args_list if c.args and str(c.args[0]).startswith("- ")]
    assert bullets and not any("$" in b for b in bullets)
    # the "growth of $10,000" label is a fixed hypothetical, the only dollar sign allowed; nothing from the account
    for c in st.dataframe.call_args_list:
        assert not set(c.args[0].columns) & {"Market value", "Value", "Amount", "Cost basis"}
    assert not re.search(r"\b500\.0\b|\b7,?500\b", " ".join(b for b in bullets))


def test_locked_without_a_password_secret_or_before_unlock(monkeypatch):
    st = make_streamlit(secrets={})
    with pytest.raises(Stopped):
        run(monkeypatch, st)
    st2 = make_streamlit(unlocked=False)
    with pytest.raises(Stopped):
        run(monkeypatch, st2)
    assert not st.plotly_chart.called and not st2.plotly_chart.called and not st2.dataframe.called
    assert "Password" in str(st2.text_input.call_args_list) and "Wrong" not in text_of(st2)   # the page shows its own lock


def test_never_reads_the_brokerage_while_locked(monkeypatch):
    st = make_streamlit(unlocked=False)
    made = []
    monkeypatch.setitem(sys.modules, "streamlit", st)
    monkeypatch.setattr(hl, "make_client", lambda *a: made.append(1))
    sys.modules.pop("portfolio_state", None)
    with pytest.raises(Stopped):
        runpy.run_path(str(ROOT / "pages" / "5_Risk.py"), run_name="__main__")
    assert made == []


def test_needs_snaptrade_keys(monkeypatch):
    with pytest.raises(Stopped):
        run(monkeypatch, make_streamlit(secrets={"APP_PASSWORD": "pw"}))


def test_stops_with_a_message_when_the_market_yardstick_is_missing(monkeypatch):
    st = make_streamlit()

    def hist(s):
        return {"prices": pd.Series(dtype=float), "divs": pd.Series(dtype=float), "error": "no"} if s == "SPY" else fake_history(s)

    with pytest.raises(Stopped):
        run(monkeypatch, st, history=hist)
    assert "SPY" in text_of(st) and not st.plotly_chart.called


def test_one_failed_ticker_is_named_and_left_out(monkeypatch):
    st = make_streamlit()

    def hist(s):
        return {"prices": pd.Series(dtype=float), "divs": pd.Series(dtype=float), "error": "no"} if s == "AAPL" else fake_history(s)

    run(monkeypatch, st, history=hist)
    assert "Couldn't load price history for AAPL" in text_of(st) and st.plotly_chart.call_count == 5


def test_short_history_ticker_is_excluded_and_said_so(monkeypatch):
    st = make_streamlit()

    def hist(s):
        h = fake_history(s)
        if s == "MSFT":
            h["prices"] = h["prices"].iloc[-80:]
        return h

    run(monkeypatch, st, history=hist)
    assert "Left out for short history: MSFT" in text_of(st)


def test_single_holding_still_renders(monkeypatch):
    st = make_streamlit()
    from test_holdings_page_smoke import rp
    run(monkeypatch, st, positions=[rp("VOO", 15, 500.0, 420.0, "et", "ETF")])
    assert st.plotly_chart.called and "nothing to compare" in text_of(st)


def test_yahoo_down_for_everything_fails_politely(monkeypatch):
    st = make_streamlit()
    bad = lambda s: {"prices": pd.Series(dtype=float), "divs": pd.Series(dtype=float), "error": "down"}
    with pytest.raises(Stopped):
        run(monkeypatch, st, history=bad)
    assert not st.plotly_chart.called


@pytest.mark.parametrize("shock", [10, 20, 40])
def test_market_fall_slider_is_a_fall_not_a_rise(monkeypatch, shock):
    st = make_streamlit(shock=shock)
    run(monkeypatch, st)
    text = text_of(st)
    assert f"Where a {shock}% market fall would come from" in text
    # every stress-bar label and value is a fall: values passed to the chart are negative
    bullets = " ".join(c.args[0] for c in st.markdown.call_args_list if c.args and str(c.args[0]).startswith("- "))
    assert re.search(r"-20% → your mix about -\d", bullets) and "→ your mix about 1" not in bullets


def test_where_the_fall_comes_from_table_only_shows_losses(monkeypatch):
    st = make_streamlit(shock=20)
    run(monkeypatch, st)
    tables = [c.args[0] for c in st.dataframe.call_args_list if "Adds to the fall (points)" in c.args[0].columns]
    assert len(tables) == 1 and (tables[0]["Adds to the fall (points)"] <= 0).all()
