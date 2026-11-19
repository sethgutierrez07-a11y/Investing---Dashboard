"""
Smoke tests: run pages/8_Deep_Dive.py (and the Stock-of-the-day links on the dashboard and Daily Brief) with stand-ins
for Streamlit, Finnhub (fake HTTP), Yahoo (fake history) and SnapTrade. Checks nothing crashes, every section degrades
on its own, the lock holds, nothing in dollars from the account reaches the page, and the three pages agree on the pick.
"""

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
import test_personalized_pages_smoke as sp  # noqa: E402
from test_holdings_page_smoke import POSITIONS, FakeClient  # noqa: E402

TODAY = pd.Timestamp.now(tz="America/Chicago").tz_localize(None).normalize()
DROP = ("holdings_charts", "brief_lib", "portfolio_state", "idea_state", "deep_charts", "risk_charts")


def fake_history(sym, years=8):
    idx = pd.bdate_range(end=TODAY, periods=1500)
    rng = np.random.default_rng(sum(map(ord, sym)))
    p = pd.Series(100 * np.exp(np.cumsum(rng.normal(0.0004, 0.013, len(idx)))), index=idx)
    d = pd.Series([0.4] * 20, index=pd.date_range(end=TODAY - pd.Timedelta(days=30), periods=20, freq="91D"))
    return {"prices": p, "divs": d, "error": None}


class Fh(sp.Http):
    """Finnhub stand-in with switches for the cases the page must survive."""

    def __init__(self, fund=(), fail=(), news=None, unknown=(), earnings_in=None):
        super().__init__()
        self.fund, self.fail, self.news, self.unknown, self.earnings_in = set(fund), set(fail), news, set(unknown), earnings_in

    def get(self, url, params=None, headers=None, timeout=None):
        sym = (params or {}).get("symbol")
        endpoint = url.rsplit("/", 1)[-1]
        if (sym, endpoint) in self.fail or ("*", endpoint) in self.fail:
            self.urls.append((url, dict(params or {})))
            resp = MagicMock()
            resp.raise_for_status.side_effect = RuntimeError("429")
            return resp
        resp = super().get(url, params, headers, timeout)
        if sym in self.unknown:
            resp.json.return_value = {"c": 0, "dp": None} if endpoint == "quote" else {} if endpoint in ("profile2", "metric") else []
        elif sym in self.fund and endpoint in ("metric",):
            resp.json.return_value = {"metric": {"beta": 1.0, "52WeekHigh": 120.0, "52WeekLow": 80.0}}
        elif endpoint == "company-news" and self.news is not None:
            resp.json.return_value = self.news
        elif endpoint == "earnings" and self.earnings_in is not None and sym:
            d = (TODAY + pd.Timedelta(days=self.earnings_in)).date().isoformat()
            resp.json.return_value = {"earningsCalendar": [{"symbol": sym, "date": d, "hour": "amc"}]}
        return resp


def make_st(unlocked=False, typed="AAPL", pick="Type a ticker", state=None, secrets=None):
    st = sp.make_streamlit(unlocked)
    if secrets is not None:
        st.secrets = secrets
    st.session_state.update(state or {})
    if typed is not None:
        st.session_state.setdefault("deep_typed", typed)          # what the visitor has typed into the ticker box
    st.text_input.side_effect = lambda label, key=None, **k: st.session_state.get(key, "")
    st.selectbox.side_effect = lambda label, options, **k: pick if pick in options else options[0]
    st.radio.side_effect = lambda label, options, **k: options[1]
    st.tabs.side_effect = lambda labels: [MagicMock() for _ in labels]
    return st


def run(monkeypatch, st, http=None, history=fake_history, page="pages/8_Deep_Dive.py", positions=POSITIONS):
    http = http or Fh()
    snap = []
    import requests
    monkeypatch.setitem(sys.modules, "streamlit", st)
    monkeypatch.setattr(requests, "get", http.get)
    monkeypatch.setattr(dd, "fetch_history", history)
    monkeypatch.setattr(hl, "make_client", lambda cid, key: snap.append(1) or FakeClient(positions))
    for m in DROP:
        sys.modules.pop(m, None)
    runpy.run_path(str(ROOT / page), run_name="__main__")
    return http, snap


def md(st):
    return " ".join(str(c.args[0]) for c in st.markdown.call_args_list if c.args)


def text(st):
    return sp.text_of(st) + " " + md(st)


def heads(st):
    return [c.args[0] for c in st.header.call_args_list]


# ---------------------------------------------------------------- the page
def test_company_page_renders_summary_tabs_and_charts(monkeypatch):
    st = make_st(typed="AAPL")
    http, snap = run(monkeypatch, st)
    assert heads(st) == ["AAPL Inc (AAPL)"] and snap == []                         # locked: never touched the brokerage
    t = md(st)
    assert "What looks good" in t and "What to watch" in t and "Bottom line" in t
    assert [c.args[0] for c in st.tabs.call_args_list][-1] == ["📊 Key numbers", "📈 Price, risk & dividends", "🧑‍🏫 Analysts & news", "🧮 How it's scored"]
    assert "Analyst consensus" in t and "Recent headlines" in t and "Next earnings report" in t


def test_chart_set_is_price_growth_falls_and_analysts(monkeypatch):
    st = make_st(typed="AAPL")
    run(monkeypatch, st)
    # price chart, growth-vs-S&P, falls-from-peak, analyst bars = 4 charts
    assert st.plotly_chart.call_count == 4


def test_key_numbers_are_grouped_with_read_labels(monkeypatch):
    st = make_st(typed="AAPL")
    run(monkeypatch, st)
    t = md(st)
    for group in ("Valuation", "Growth", "Profitability", "Financial health"):
        assert f"##### {group}" in t
    frames = [c.args[0] for c in st.dataframe.call_args_list if isinstance(c.args[0], pd.DataFrame)]
    keyed = next(f for f in frames if list(f.columns) == ["Measure", "Value", "Read", "What it means"] and "P/E (trailing 12 months)" in set(f["Measure"]))
    row = keyed[keyed["Measure"] == "P/E (trailing 12 months)"].iloc[0]
    assert row["Value"] == "18.0×" and row["Read"] == "🟢 Good"


def test_default_ticker_is_todays_stock_idea_shared_with_the_dashboard(monkeypatch):
    st = make_st(typed=None)                      # nothing typed: the page picks for you
    run(monkeypatch, st)
    sym = st.session_state["deep_typed"]
    dash, _, _ = sp.run(monkeypatch, "dashboard.py", unlocked=False, ideas=True)
    picks = [str(c.args[0]) for c in dash.markdown.call_args_list if c.args and str(c.args[0]).startswith("### ")]
    assert picks and picks[0].split()[1] == sym
    assert any("today's stock idea" in o for o in st.selectbox.call_args.args[1])
    assert "Stock of the day" in " ".join(str(c) for c in st.markdown.call_args_list)


def test_brief_dashboard_and_deep_dive_all_show_the_same_pick(monkeypatch):
    st = make_st(typed=None)
    run(monkeypatch, st)
    deep = st.session_state["deep_typed"]
    brief, _, _ = sp.run(monkeypatch, "pages/1_Daily_Brief.py", unlocked=False, ideas=True)
    assert f"**{deep}**" in md(brief) and any(c.args[0].startswith("Open the full deep-dive") for c in brief.button.call_args_list)
    dash, _, _ = sp.run(monkeypatch, "dashboard.py", unlocked=False, ideas=True)
    assert any(c.args[0].startswith("Open the full deep-dive") for c in dash.button.call_args_list)


def test_jump_from_another_page_sets_the_ticker_and_clears_the_inbox(monkeypatch):
    st = make_st(typed="IGNORED", state={"deep_symbol": "NVDA"})
    run(monkeypatch, st)
    assert st.session_state["deep_typed"] == "NVDA" and "deep_symbol" not in st.session_state and heads(st) == ["NVDA Inc (NVDA)"]


def test_quick_pick_dropdown_sets_the_ticker_and_resets_itself(monkeypatch):
    st = make_st(unlocked=True, typed="AAPL")
    run(monkeypatch, st)
    opts = st.selectbox.call_args.args[1]
    assert opts[0] == "Type a ticker" and any(o.startswith("VOO · you hold") for o in opts)
    cb = st.selectbox.call_args.kwargs["on_change"]
    st.session_state["deep_pick"] = "MSFT · you hold this"
    cb()
    assert st.session_state["deep_typed"] == "MSFT" and st.session_state["deep_pick"] == "Type a ticker"
    st.session_state["deep_pick"] = "Type a ticker"
    st.session_state["deep_typed"] = "KEEP"
    cb()
    assert st.session_state["deep_typed"] == "KEEP"                                # leaving it on the placeholder changes nothing


@pytest.mark.parametrize("bad", ["", "12$", "A B", "TOOLONGTICKERS", "-X"])
def test_invalid_ticker_is_refused_politely(monkeypatch, bad):
    from test_holdings_page_smoke import Stopped
    st = make_st(typed=bad)
    with pytest.raises(Stopped):
        run(monkeypatch, st)
    assert "Enter a ticker" in " ".join(str(c) for c in st.warning.call_args_list)


def test_class_share_tickers_are_accepted(monkeypatch):
    st = make_st(typed="brk.b")
    run(monkeypatch, st)
    assert heads(st) == ["BRK.B Inc (BRK.B)"]


# ---------------------------------------------------------------- degrading
def test_fund_gets_price_view_not_company_numbers(monkeypatch):
    st = make_st(typed="VOO")
    run(monkeypatch, st, http=Fh(fund={"VOO"}))
    t = text(st)
    assert "looks like a fund or ETF" in t and "What looks good" not in md(st)
    assert "company measures don't apply" in t
    assert any("Fund / ETF" in str(c) for c in st.markdown.call_args_list)
    assert st.plotly_chart.call_count >= 3                                         # price, growth, falls still shown


def test_unknown_ticker_says_so_and_stops(monkeypatch):
    from test_holdings_page_smoke import Stopped
    st = make_st(typed="ZZZZ")
    empty = lambda sym, years=8: {"prices": pd.Series(dtype=float), "divs": pd.Series(dtype=float), "error": "no history"}  # noqa: E731
    with pytest.raises(Stopped):
        run(monkeypatch, st, http=Fh(unknown={"ZZZZ"}), history=empty)
    assert "Couldn't find data for ZZZZ" in " ".join(str(c) for c in st.error.call_args_list)


def test_yahoo_failure_keeps_company_numbers(monkeypatch):
    bad = lambda sym, years=8: {"prices": pd.Series(dtype=float), "divs": pd.Series(dtype=float), "error": "Yahoo didn't answer (X)."}  # noqa: E731
    st = make_st(typed="AAPL")
    run(monkeypatch, st, history=bad)
    t = text(st)
    assert "Couldn't load price history" in t and "What looks good" in md(st) and "Price history isn't available" in t


def test_finnhub_metric_failure_keeps_price_history(monkeypatch):
    st = make_st(typed="AAPL")
    run(monkeypatch, st, http=Fh(fail={("AAPL", "metric")}))
    t = text(st)
    assert "Couldn't load company numbers (RuntimeError)" in t and "aren't available right now" in t
    assert "What looks good" not in md(st) and st.plotly_chart.call_count >= 3


def test_no_finnhub_key_still_shows_prices(monkeypatch):
    st = make_st(typed="AAPL", secrets={"APP_PASSWORD": "pw"})
    http, _ = run(monkeypatch, st)
    assert "FINNHUB_API_KEY" in text(st) and http.urls == [] and st.plotly_chart.call_count >= 3
    assert "Add `FINNHUB_API_KEY` to Secrets to see analyst ratings" in " ".join(str(c) for c in st.info.call_args_list)


def test_news_and_earnings_flow_through(monkeypatch):
    news = [{"headline": "Acme beats $2 estimates", "source": "Wire", "url": "https://example.com/a", "datetime": int(pd.Timestamp.now().timestamp())}]
    st = make_st(typed="AAPL")
    run(monkeypatch, st, http=Fh(news=news, earnings_in=5))
    t = md(st)
    assert "[Acme beats \\$2 estimates](https://example.com/a)" in t                # dollar signs escaped inside links
    assert "in 5 days" in t and "Earnings soon" in t                                # shows in the cons too


def test_news_failure_is_a_note(monkeypatch):
    st = make_st(typed="AAPL")
    run(monkeypatch, st, http=Fh(fail={("AAPL", "company-news")}))
    assert "Couldn't load news" in text(st)


def test_price_target_block_is_remembered(monkeypatch):
    st = make_st(typed="AAPL")
    run(monkeypatch, st, http=Fh(fail={("*", "price-target")}))
    assert st.session_state.get("price_targets_blocked") is True


# ---------------------------------------------------------------- the lock and the account
def test_unlocked_shows_weight_in_percent_only(monkeypatch):
    st = make_st(unlocked=True, typed="AAPL")
    http, snap = run(monkeypatch, st)
    t = text(st)
    assert snap and "You hold 16% of invested" in " ".join(str(c) for c in st.markdown.call_args_list)
    assert "**16%**" in t
    shown = " ".join(m for m in (str(c.args[0]) for c in st.markdown.call_args_list if c.args) if not m.startswith("<style>"))
    for needle in ("7500", "7,500", "1600", "1,600", "10300", "10,300", "1200"):
        assert needle not in shown


def test_locked_never_mentions_holdings(monkeypatch):
    st = make_st(unlocked=False, typed="AAPL")
    run(monkeypatch, st)
    assert "How it fits you" not in md(st) and "You hold" not in " ".join(str(c) for c in st.markdown.call_args_list)


def test_page_applies_style_and_names_itself(monkeypatch):
    st = make_st(typed="AAPL")
    run(monkeypatch, st)
    assert any(str(c.args[0]).startswith("<style>") for c in st.markdown.call_args_list if c.args)
    assert st.set_page_config.call_args.kwargs["page_title"] == "Stock Deep-Dive"


# ---------------------------------------------------------------- links from other pages
def test_deep_dive_button_stores_symbol_and_switches_page():
    import ui
    st = MagicMock()
    st.session_state = {}
    st.button.return_value = True
    saved = sys.modules.get("streamlit")
    sys.modules["streamlit"] = st
    try:
        ui.deep_dive_button("MSFT", "k")
    finally:
        sys.modules["streamlit"] = saved
    assert st.session_state["deep_symbol"] == "MSFT" and st.switch_page.call_args.args[0] == "pages/8_Deep_Dive.py"


def test_deep_dive_button_does_nothing_until_clicked_and_survives_switch_failure():
    import ui
    st = MagicMock()
    st.session_state = {}
    st.button.return_value = False
    saved = sys.modules.get("streamlit")
    sys.modules["streamlit"] = st
    try:
        ui.deep_dive_button("MSFT", "k")
        assert "deep_symbol" not in st.session_state and not st.switch_page.called
        st.button.return_value = True
        st.switch_page.side_effect = RuntimeError("no")
        ui.deep_dive_button("MSFT", "k")
    finally:
        sys.modules["streamlit"] = saved
    assert st.info.called


def test_idea_compact_with_and_without_a_pick():
    import ui
    st = MagicMock()
    st.session_state = {}
    st.button.return_value = False
    saved = sys.modules.get("streamlit")
    sys.modules["streamlit"] = st
    try:
        pick = {"symbol": "KO", "price": 60.5, "day_pct": -0.5, "pros": [("Dividend", "x"), ("Balance sheet", "y")], "cons": []}
        ui.idea_compact({"best": pick, "name": "Coca-Cola"}, "k")
        shown = " ".join(str(c.args[0]) for c in st.markdown.call_args_list if c.args)
        assert "**KO** · Coca-Cola · \\$60.50 (-0.50% today)" in shown and "dividend; balance sheet" in shown and "no red flags" in shown
        st2 = MagicMock()
        st2.session_state = {}
        sys.modules["streamlit"] = st2
        ui.idea_compact({"best": None, "name": ""}, "k")
        assert "Couldn't screen enough candidates" in " ".join(str(c) for c in st2.caption.call_args_list) and not st2.button.called
    finally:
        sys.modules["streamlit"] = saved


def test_exclusions_skip_what_you_hold_plus_the_sample_list_only_while_locked(monkeypatch):
    run(monkeypatch, make_st(typed="AAPL"))                      # imports idea_state with the stand-in streamlit
    import idea_state as ist
    assert ist.exclusions(set()) == {"AAPL", "MSFT", "VOO"}
    assert ist.exclusions({"NVDA", "KO"}) == {"NVDA", "KO"}
    assert ist.exclusions({"NVDA"}, ["AAPL"]) == {"NVDA", "AAPL"}
