"""
Smoke tests: run app.py and pages/1_Daily_Brief.py with stand-ins for Streamlit,
Finnhub (fake HTTP) and SnapTrade. Checks that locked visitors get the sample
watchlist and never trigger a SnapTrade call, and unlocked visitors get their holdings.
"""

import runpy
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
import holdings_lib as hl  # noqa: E402
from test_holdings_page_smoke import POSITIONS, FakeClient, Stopped, stub_plotly_if_missing  # noqa: E402

SECRETS = {
    "APP_PASSWORD": "pw", "SNAPTRADE_CLIENT_ID": "id", "SNAPTRADE_CONSUMER_KEY": "key",
    "FINNHUB_API_KEY": "fh",
}


class Http:
    """Fake Finnhub: every symbol is up 2% except MSFT (-1%)."""

    def __init__(self, status=200, fail_metric=False):
        self.urls = []
        self.fail_metric = fail_metric

    def get(self, url, params=None, headers=None, timeout=None):
        self.urls.append((url, dict(params or {})))
        resp = MagicMock()
        resp.raise_for_status.return_value = None
        sym = (params or {}).get("symbol")
        if url.endswith("/quote"):
            dp = -1.0 if sym == "MSFT" else 2.0
            resp.json.return_value = {"c": 100.0, "d": dp, "dp": dp, "pc": 98.0}
        elif url.endswith("/stock/profile2"):
            resp.json.return_value = {} if sym in ("VOO", "QQQ") else {"name": f"{sym} Inc"}  # ETFs have no company profile
        elif url.endswith("/stock/metric"):
            if self.fail_metric:
                resp.raise_for_status.side_effect = RuntimeError("429")
            resp.json.return_value = {"metric": {
                "peTTM": 18.0, "revenueGrowthTTMYoy": 14.0, "netProfitMarginTTM": 22.0, "roeTTM": 30.0,
                "totalDebt/totalEquityQuarterly": 0.3, "52WeekHigh": 120.0, "52WeekLow": 80.0, "beta": 1.0}}
        elif url.endswith("/calendar/earnings"):
            resp.json.return_value = {"earningsCalendar": [{"symbol": "AAPL", "date": "2099-01-01", "hour": "amc"}]}
        elif url.endswith("/stock/recommendation"):
            resp.json.return_value = [{"period": "2026-11-01", "strongBuy": 5, "buy": 5, "hold": 1, "sell": 0, "strongSell": 0},
                                      {"period": "2026-10-01", "strongBuy": 4, "buy": 5, "hold": 2, "sell": 0, "strongSell": 0}]
        else:
            resp.json.return_value = []
        return resp


def make_streamlit(unlocked, extras=""):
    st = MagicMock(name="streamlit")
    st.secrets = dict(SECRETS)
    st.session_state = {"holdings_unlocked": True} if unlocked else {}
    st.cache_data.side_effect = lambda *a, **k: (lambda f: f)
    st.toggle.return_value = True
    st.text_area.return_value = extras if unlocked else "AAPL, MSFT, VOO"
    st.text_input.return_value = ""
    st.button.return_value = False
    st.slider.side_effect = [2.0, 3, 14]
    st.columns.side_effect = lambda spec, **k: [MagicMock() for _ in range(spec if isinstance(spec, int) else len(spec))]
    st.tabs.side_effect = lambda labels: [MagicMock() for _ in labels]
    st.stop.side_effect = Stopped
    st.context.theme.type = "dark"
    return st


def run(monkeypatch, path, unlocked, extras="", positions=POSITIONS, ideas=False, http=None):
    stub_plotly_if_missing()
    st = make_streamlit(unlocked, extras)
    http = http or Http()
    snap_calls = []
    import idea_lib
    if not ideas:  # keep the original assertions about which tickers get quoted
        monkeypatch.setattr(idea_lib, "pick_candidates", lambda *a, **k: [])

    def client(cid, key):
        snap_calls.append(1)
        return FakeClient(positions)

    monkeypatch.setitem(sys.modules, "streamlit", st)
    monkeypatch.setattr(hl, "make_client", client)
    import requests
    monkeypatch.setattr(requests, "get", http.get)
    for m in ("holdings_charts", "brief_lib", "portfolio_state"):
        sys.modules.pop(m, None)
    runpy.run_path(str(ROOT / path), run_name="__main__")
    return st, http, snap_calls


def queried_symbols(http, endpoint="/quote"):
    return [p["symbol"] for u, p in http.urls if u.endswith(endpoint) and p["symbol"] != "SPY"]  # SPY is only the benchmark


def text_of(st):
    out = []
    for name in ("markdown", "caption", "metric", "info", "warning", "error", "subheader", "title", "success"):
        out += [str(c) for c in getattr(st, name).call_args_list]
    return " ".join(out)


@pytest.mark.parametrize("page", ["dashboard.py", "pages/1_Daily_Brief.py"])
def test_locked_visitor_gets_sample_list_and_no_snaptrade_call(monkeypatch, page):
    st, http, snap = run(monkeypatch, page, unlocked=False)
    assert snap == []                                   # never touched the brokerage
    assert sorted(set(queried_symbols(http))) == ["AAPL", "MSFT", "VOO"]
    assert "Unlock in the sidebar" in text_of(st)


@pytest.mark.parametrize("page", ["dashboard.py", "pages/1_Daily_Brief.py"])
def test_unlocked_visitor_gets_real_holdings_largest_first(monkeypatch, page):
    st, http, snap = run(monkeypatch, page, unlocked=True)
    assert snap                                         # portfolio was read
    syms = list(dict.fromkeys(queried_symbols(http)))
    assert syms == ["VOO", "AAPL", "MSFT"]              # by weight; SPAXX (cash equiv.) excluded
    text = text_of(st)
    assert "Your portfolio today" in text
    assert "$" not in text.replace("$%", "").replace("${", "")  # percent-only: no dollar amounts


def test_unlocked_extras_are_added_after_holdings(monkeypatch):
    st, http, _ = run(monkeypatch, "pages/1_Daily_Brief.py", unlocked=True, extras="NVDA, voo")
    assert list(dict.fromkeys(queried_symbols(http))) == ["VOO", "AAPL", "MSFT", "NVDA"]


def test_brief_earnings_exposure_uses_real_weights(monkeypatch):
    st, _, _ = run(monkeypatch, "pages/1_Daily_Brief.py", unlocked=True)
    # AAPL = 1600 of 10300 invested (VOO 7500 + AAPL 1600 + MSFT 1200) ≈ 16%
    assert "16% of your invested money" in text_of(st)


def test_wrong_snaptrade_failure_still_renders_sample(monkeypatch):
    def boom(cid, key):
        raise RuntimeError("down")

    st = make_streamlit(True)
    stub_plotly_if_missing()
    monkeypatch.setitem(sys.modules, "streamlit", st)
    monkeypatch.setattr(hl, "make_client", boom)
    import requests
    monkeypatch.setattr(requests, "get", Http().get)
    for m in ("holdings_charts", "brief_lib", "portfolio_state"):
        sys.modules.pop(m, None)
    st.text_area.return_value = "AAPL"
    runpy.run_path(str(ROOT / "dashboard.py"), run_name="__main__")  # must not raise
    assert st.dataframe.called


@pytest.mark.parametrize("page", ["dashboard.py", "pages/1_Daily_Brief.py"])
@pytest.mark.parametrize("missing", ["all", "some"])
def test_unlocked_with_missing_cost_basis_does_not_crash(monkeypatch, page, missing):
    from test_holdings_page_smoke import rp
    pos = [dict(p) for p in POSITIONS]
    for i, p in enumerate(pos):
        if missing == "all" or i == 1:
            p["average_purchase_price"] = None
    st, http, _ = run(monkeypatch, page, unlocked=True, positions=pos)
    assert st.dataframe.called


def markdown_text(st):
    return " ".join(str(c) for c in st.markdown.call_args_list)


def tab_labels(st):
    return [c.args[0] for c in st.tabs.call_args_list]


def test_stock_of_the_day_shows_pick_with_pros_cons_and_excludes_holdings(monkeypatch):
    st, http, _ = run(monkeypatch, "dashboard.py", unlocked=True, ideas=True)
    text = markdown_text(st) + text_of(st)
    assert "Stock of the day" in text and "What looks good" in text and "What to watch" in text
    pick = next(l.split("### ")[1].split(" ")[0].strip("'\"),") for l in [markdown_text(st)] if "### " in l)
    assert pick not in ("VOO", "AAPL", "MSFT")          # something you don't already own
    assert "14.0%" in text                              # a number behind a pro is on the page
    assert "not a recommendation" in text.lower() or "Not a recommendation" in text


def test_stock_of_the_day_survives_rate_limit(monkeypatch):
    st, _, _ = run(monkeypatch, "dashboard.py", unlocked=True, ideas=True, http=Http(fail_metric=True))
    assert "Couldn't screen enough candidates" in text_of(st)
    assert st.dataframe.called                          # rest of the page still rendered


def test_analyst_section_splits_stocks_and_funds_unlocked(monkeypatch):
    st, _, _ = run(monkeypatch, "dashboard.py", unlocked=True)
    assert tab_labels(st) == [["AAPL", "MSFT"]]         # VOO (an ETF) gets no analyst tab
    assert "ETFs & funds" in markdown_text(st)
    assert "no analyst ratings" in text_of(st)


def test_analyst_section_splits_stocks_and_funds_locked_sample_list(monkeypatch):
    st, http, _ = run(monkeypatch, "dashboard.py", unlocked=False)
    assert tab_labels(st) == [["AAPL", "MSFT"]]         # VOO has no company profile -> treated as a fund
    assert "ETFs & funds" in markdown_text(st)
    assert [p["symbol"] for u, p in http.urls if u.endswith("/stock/recommendation")] == ["AAPL", "MSFT"]


def test_brief_writes_free_rule_based_summary_locked_and_unlocked(monkeypatch):
    st, http, _ = run(monkeypatch, "pages/1_Daily_Brief.py", unlocked=True)
    text = markdown_text(st)
    assert tab_labels(st)[0][0] == "Bottom line" and "S&P 500" in text and "no AI" in text_of(st)
    assert "pp = percentage points" in text_of(st)
    assert any(p["symbol"] == "SPY" for u, p in http.urls if u.endswith("/quote"))
    st2, _, _ = run(monkeypatch, "pages/1_Daily_Brief.py", unlocked=False)
    assert tab_labels(st2)[0][0] == "Bottom line" and "simple average" in markdown_text(st2)


def test_brief_comes_before_the_data_it_summarizes(monkeypatch):
    st, _, _ = run(monkeypatch, "pages/1_Daily_Brief.py", unlocked=True)
    heads = [c.args[0] for c in st.subheader.call_args_list]
    assert heads[:2] == ["Today's brief", "The data behind it"]
    assert st.container.called


def test_entry_point_gives_pages_professional_names(monkeypatch):
    st = MagicMock(name="streamlit")
    st.Page.side_effect = lambda path, **k: (path, k)
    monkeypatch.setitem(sys.modules, "streamlit", st)
    runpy.run_path(str(ROOT / "app.py"), run_name="__main__")
    pages = st.navigation.call_args.args[0]
    assert [k["title"] for _, k in pages] == ["Investing Dashboard", "Daily Brief", "Holdings", "Strategy Lab", "Dividends", "Risk", "Market", "Stock Deep-Dive", "Learn"]
    assert [p for p, _ in pages] == ["dashboard.py", "pages/1_Daily_Brief.py", "pages/2_Holdings.py", "pages/3_Strategy_Lab.py", "pages/4_Dividends.py", "pages/5_Risk.py", "pages/6_Market.py", "pages/8_Deep_Dive.py", "pages/7_Learn.py"]
    assert st.navigation.call_args.kwargs.get("position") == "top"      # always-visible menu, sidebar left for controls
    assert sum(1 for _, k in pages if k.get("default")) == 1
    for p, _ in pages:
        assert (ROOT / p).exists()                       # a typo here would break the whole app
    st.navigation.return_value.run.assert_called_once()
