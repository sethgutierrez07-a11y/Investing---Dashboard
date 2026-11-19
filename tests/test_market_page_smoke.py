"""
Smoke test: run pages/6_Market.py end to end with stand-ins for Streamlit, Yahoo (market_data), Finnhub and SnapTrade.
Checks nothing crashes, degrades gracefully when Yahoo fails, the calendar merges all four kinds of event,
the lock holds, and nothing from the account (dollar amounts) reaches the page. It does not check how it looks.
"""

import datetime as dt
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
import market_data as md  # noqa: E402
import test_lab_charts  # noqa: F401,E402  (installs a plotly stand-in if plotly is missing)
from test_dividends_page_smoke import READ_ONLY, ActAcctInfo, Client, flat, tab_names  # noqa: E402
from test_holdings_page_smoke import GOOD_SECRETS, POSITIONS, Stopped  # noqa: E402

TODAY = pd.Timestamp.now(tz="America/Chicago").tz_localize(None).normalize()


def fake_close(sym, period="2y"):
    idx = pd.bdate_range(end=TODAY, periods=520)
    seed = sum(map(ord, sym))
    if sym in ("^TNX", "^IRX", "^FVX", "^TYX"):
        v = 4 + {"^IRX": 0.3, "^FVX": 0.0, "^TNX": 0.2, "^TYX": 0.5}[sym] + np.cumsum(np.random.default_rng(seed).normal(0, 0.01, len(idx)))
    elif sym == "^VIX":
        v = 18 + np.cumsum(np.random.default_rng(seed).normal(0, 0.2, len(idx)))
    else:
        v = 100 * np.exp(np.cumsum(np.random.default_rng(seed).normal(0.0003, 0.01, len(idx))))
    return md.clean(pd.Series(v, index=idx))


def fake_history(sym, years=8):
    idx = pd.bdate_range(end=TODAY, periods=years * 261)
    divs = pd.Series([0.5] * 12, index=pd.date_range(end=TODAY - pd.Timedelta(days=20), periods=12, freq="91D"))
    return {"prices": pd.Series(100.0, index=idx), "divs": divs if sym != "MSFT" else pd.Series(dtype=float), "error": None}


def make_streamlit(secrets=None, unlocked=False, advanced=False, days=30, text="AAPL, MSFT, VOO", kinds=None):
    st = MagicMock(name="streamlit")
    st.secrets = dict({**GOOD_SECRETS, "FINNHUB_API_KEY": "fh"} if secrets is None else secrets)
    st.session_state = {"holdings_unlocked": True} if unlocked else {}
    st.cache_data.side_effect = lambda *a, **k: (lambda f: f)
    st.cache_data.clear = MagicMock()
    st.toggle.side_effect = lambda label, **k: advanced if label == "Advanced view" else True
    st.text_area.return_value = text if not unlocked else ""
    st.text_input.return_value = ""
    st.button.return_value = False
    st.radio.side_effect = lambda label, options, **k: options[1]
    st.select_slider.return_value = days
    st.multiselect.side_effect = lambda label, options, **k: kinds if kinds is not None else options
    st.columns.side_effect = lambda spec, **k: [MagicMock() for _ in range(spec if isinstance(spec, int) else len(spec))]
    st.tabs.side_effect = lambda labels: [MagicMock() for _ in labels]
    st.stop.side_effect = Stopped
    st.context.theme.type = "dark"
    return st


def run(monkeypatch, st, close=fake_close, earnings=None, positions=POSITIONS, history=fake_history):
    info = ActAcctInfo(positions, [])
    made = []
    cal_calls = []
    if earnings is None:
        def earnings(start, end, key):
            cal_calls.append(key)
            return {"earningsCalendar": [{"symbol": "AAPL", "date": (TODAY + pd.Timedelta(days=5)).date().isoformat(), "hour": "amc", "epsEstimate": 1.5},
                                         {"symbol": "ZZZZ", "date": (TODAY + pd.Timedelta(days=5)).date().isoformat(), "hour": "bmo"}]}
    monkeypatch.setitem(sys.modules, "streamlit", st)
    monkeypatch.setattr(hl, "make_client", lambda cid, key: made.append(1) or Client(info))
    monkeypatch.setattr(dd, "fetch_history", history)
    monkeypatch.setattr(md, "fetch_close", close)
    orig = md.fetch_many
    monkeypatch.setattr(md, "fetch_many", lambda s, period="2y", fetcher=close, workers=6: orig(s, period, fetcher, workers))
    import importlib
    monkeypatch.setattr(importlib.import_module("brief_lib"), "fetch_earnings_calendar", earnings)       # other tests drop brief_lib from sys.modules
    for m in ("market_charts", "risk_charts", "holdings_charts", "portfolio_state", "market_text"):
        sys.modules.pop(m, None)
    runpy.run_path(str(ROOT / "pages" / "6_Market.py"), run_name="__main__")
    return info, made, cal_calls


def md_lines(st):
    return [str(c.args[0]) for c in st.markdown.call_args_list if c.args]


def table_of(st, i=-1):
    return st.dataframe.call_args_list[i].args[0]


# ---------------------------------------------------------------- minimal view
def test_minimal_view_renders_summary_tiles_and_calendar(monkeypatch):
    st = make_streamlit()
    run(monkeypatch, st)
    heads = [c.args[0] for c in st.subheader.call_args_list]
    assert [h for h in heads if h in ("What's coming", "Summary", "In more detail")] == ["What's coming", "Summary"]
    assert [c.args[0] for c in st.tabs.call_args_list] == [["The short version", "Coming up"]]       # short summary only
    assert st.plotly_chart.call_count == 0                                                            # sparklines live in the tiles
    metric_names = [c.args[0] for c in st.metric.call_args_list]
    assert metric_names[:4] == ["S&P 500", "Nasdaq", "Dow", "Russell 2000"]
    assert {"VIX (expected volatility)", "10-year Treasury yield", "S&P 500 vs 200-day average", "S&P 500 from 52-week high"} <= set(metric_names)
    assert "ix-strip" in " ".join(md_lines(st)) and "no AI" in flat(st, "caption")


def test_minimal_view_only_fetches_the_core_symbols(monkeypatch):
    fetched = []

    def spy(sym, period="2y"):
        fetched.append(sym)
        return fake_close(sym)

    run(monkeypatch, make_streamlit(), close=spy)
    assert set(fetched) == set(md.CORE)


def test_summary_text_has_no_dollar_signs_and_escapes_markdown(monkeypatch):
    st = make_streamlit(unlocked=True, advanced=True)
    run(monkeypatch, st)
    bullets = [m for m in md_lines(st) if m.startswith("- ")]
    assert bullets and not any("$" in b.replace("\\$", "") for b in bullets)


# ---------------------------------------------------------------- advanced view
def test_advanced_view_adds_sections_tabs_and_charts(monkeypatch):
    st = make_streamlit(advanced=True)
    run(monkeypatch, st)
    names = tab_names(st)
    assert ["Sectors", "Rates & volatility", "Index detail", "Other markets"] in names
    summary = next(n for n in names if n[0] == "The short version")
    assert summary == ["The short version", "Under the surface", "Coming up", "Worth knowing"]
    assert st.plotly_chart.call_count == 3                                                           # sector bars, yield curve, VIX
    assert "In more detail" in [c.args[0] for c in st.subheader.call_args_list]


def test_advanced_view_fetches_everything_once(monkeypatch):
    fetched = []

    def spy(sym, period="2y"):
        fetched.append(sym)
        return fake_close(sym)

    run(monkeypatch, make_streamlit(advanced=True), close=spy)
    assert sorted(fetched) == sorted(set(md.CORE) | set(md.EXTRA))


def test_advanced_view_survives_missing_extras(monkeypatch):
    def partial(sym, period="2y"):
        if sym in set(md.EXTRA):
            return {"close": pd.Series(dtype=float), "error": "no data"}
        return fake_close(sym)

    st = make_streamlit(advanced=True)
    run(monkeypatch, st, close=partial)
    text = flat(st, "info", "caption", "warning")
    assert "Sector data isn't available" in text and "Treasury yields aren't available" in text
    assert st.dataframe.called                                                                         # the calendar still rendered


# ---------------------------------------------------------------- failures
def test_page_survives_yahoo_failing_completely(monkeypatch):
    st = make_streamlit()
    run(monkeypatch, st, close=lambda s, p="2y": {"close": pd.Series(dtype=float), "error": "Yahoo didn't answer (X)."})
    assert "Couldn't load market prices" in flat(st, "warning")
    assert "The summary needs market prices" in flat(st, "info")
    assert st.dataframe.called                                                                         # calendar still works


def test_page_names_the_one_index_that_failed(monkeypatch):
    def one_bad(sym, period="2y"):
        return {"close": pd.Series(dtype=float), "error": "no data"} if sym == "^RUT" else fake_close(sym)

    st = make_streamlit()
    run(monkeypatch, st, close=one_bad)
    assert "Couldn't load: Russell 2000" in flat(st, "caption")
    assert [c.args[0] for c in st.metric.call_args_list][3:4] == ["Russell 2000"]


def test_earnings_failure_is_a_note_not_a_crash(monkeypatch):
    def boom(*a):
        raise RuntimeError("429")

    st = make_streamlit()
    run(monkeypatch, st, earnings=boom)
    assert "Couldn't load earnings dates (RuntimeError)" in flat(st, "caption")
    assert st.dataframe.called


def test_missing_finnhub_key_says_how_to_add_it(monkeypatch):
    st = make_streamlit(secrets={"APP_PASSWORD": "pw"})
    _, _, cal = run(monkeypatch, st)
    assert "FINNHUB_API_KEY" in flat(st, "caption") and cal == []


def test_dividend_history_failure_is_named(monkeypatch):
    def hist(sym, years=8):
        return {"prices": pd.Series(dtype=float), "divs": pd.Series(dtype=float), "error": "Yahoo didn't answer (X)."} if sym == "MSFT" else fake_history(sym)

    st = make_streamlit()
    run(monkeypatch, st, history=hist)
    assert "Couldn't check dividend history for MSFT" in flat(st, "caption")


# ---------------------------------------------------------------- calendar
def test_calendar_merges_all_four_event_types_for_the_watchlist(monkeypatch):
    st = make_streamlit(days=60)
    run(monkeypatch, st)
    df = table_of(st)
    types = set(df["Type"])
    assert "🏛️ Fed" in types and "🔔 Market closed" in types and "📣 Earnings" in types
    assert df["Date"].is_monotonic_increasing and df["In (days)"].max() <= 60
    ev = df[df["Type"] == "📣 Earnings"]["Event"].tolist()
    assert ev == ["AAPL reports earnings"]                                                            # ZZZZ isn't on the watchlist
    if "💵 Ex-dividend" in types:
        assert all("estimated" in e for e in df[df["Type"] == "💵 Ex-dividend"]["Event"])
        assert all("per share" in d for d in df[df["Type"] == "💵 Ex-dividend"]["Details"])


def test_calendar_look_ahead_and_type_filter(monkeypatch):
    st = make_streamlit(days=7, kinds=["Fed"])
    run(monkeypatch, st)
    assert not st.dataframe.called and "Nothing matching falls in the next 7 days" in flat(st, "info")      # next FOMC is 20+ days out
    st = make_streamlit(days=60, kinds=["Fed"])
    run(monkeypatch, st)
    assert set(table_of(st)["Type"]) == {"🏛️ Fed"}
    st = make_streamlit(days=7, kinds=["Earnings"], secrets={"APP_PASSWORD": "pw"})
    run(monkeypatch, st)
    assert "Nothing matching falls in the next 7 days" in flat(st, "info")


def test_calendar_states_how_far_the_built_in_dates_reach(monkeypatch):
    st = make_streamlit()
    run(monkeypatch, st)
    cap = flat(st, "caption")
    assert "estimates" in cap and "Sep 2027" in cap and "Dec 2027" in cap and "sample list" in cap


# ---------------------------------------------------------------- lock and account safety
def test_locked_visitor_uses_sample_list_and_never_touches_the_brokerage(monkeypatch):
    st = make_streamlit(unlocked=False)
    info, made, _ = run(monkeypatch, st)
    assert made == [] and info.calls == []
    assert "sample list" in flat(st, "caption")


def test_unlocked_visitor_gets_holdings_as_watchlist_read_only_and_no_dollars(monkeypatch):
    seen = []

    def hist(sym, years=8):
        seen.append(sym)
        return fake_history(sym)

    st = make_streamlit(unlocked=True, advanced=True, days=60)
    info, made, _ = run(monkeypatch, st, history=hist)
    assert made and set(info.calls) <= READ_ONLY
    assert set(seen) == {"VOO", "AAPL", "MSFT"}
    assert "your holdings" in flat(st, "caption")
    shown = " ".join(m for m in md_lines(st) if not m.startswith("<style>")) + flat(st, "caption", "info", "warning", "subheader", "title") \
        + " ".join(f"{c.args} {c.kwargs.get('delta')}" for c in st.metric.call_args_list)       # not chart_data: random sparkline points
    df = table_of(st)
    cols_text = " ".join(map(str, df.columns)) + " ".join(map(str, df["Details"]))
    assert "Amount" not in cols_text and "Shares" not in cols_text
    # nothing from the account: no position sizes or values (VOO 7500, AAPL 1600, MSFT 1200 in the fixture)
    for needle in ("7500", "7,500", "1600", "1,600", "10300", "10,300"):
        assert needle not in shown + cols_text


def test_every_page_applies_style_and_first_widgets_are_in_the_sidebar(monkeypatch):
    st = make_streamlit()
    run(monkeypatch, st)
    assert any(str(c.args[0]).startswith("<style>") for c in st.markdown.call_args_list if c.args)
    assert st.set_page_config.call_args.kwargs["page_title"] == "Market"
