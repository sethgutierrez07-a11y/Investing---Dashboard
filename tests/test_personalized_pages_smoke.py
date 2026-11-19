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

    def __init__(self, status=200):
        self.urls = []

    def get(self, url, params=None, headers=None, timeout=None):
        self.urls.append((url, dict(params or {})))
        resp = MagicMock()
        resp.raise_for_status.return_value = None
        sym = (params or {}).get("symbol")
        if url.endswith("/quote"):
            dp = -1.0 if sym == "MSFT" else 2.0
            resp.json.return_value = {"c": 100.0, "d": dp, "dp": dp, "pc": 98.0}
        elif url.endswith("/stock/profile2"):
            resp.json.return_value = {"name": f"{sym} Inc"}
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


def run(monkeypatch, path, unlocked, extras="", positions=POSITIONS):
    stub_plotly_if_missing()
    st = make_streamlit(unlocked, extras)
    http = Http()
    snap_calls = []

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
    return [p["symbol"] for u, p in http.urls if u.endswith(endpoint)]


def text_of(st):
    out = []
    for name in ("markdown", "caption", "metric", "info", "warning", "error", "subheader", "title", "success"):
        out += [str(c) for c in getattr(st, name).call_args_list]
    return " ".join(out)


@pytest.mark.parametrize("page", ["app.py", "pages/1_Daily_Brief.py"])
def test_locked_visitor_gets_sample_list_and_no_snaptrade_call(monkeypatch, page):
    st, http, snap = run(monkeypatch, page, unlocked=False)
    assert snap == []                                   # never touched the brokerage
    assert sorted(set(queried_symbols(http))) == ["AAPL", "MSFT", "VOO"]
    assert "Unlock in the sidebar" in text_of(st)


@pytest.mark.parametrize("page", ["app.py", "pages/1_Daily_Brief.py"])
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
    runpy.run_path(str(ROOT / "app.py"), run_name="__main__")  # must not raise
    assert st.dataframe.called


@pytest.mark.parametrize("page", ["app.py", "pages/1_Daily_Brief.py"])
@pytest.mark.parametrize("missing", ["all", "some"])
def test_unlocked_with_missing_cost_basis_does_not_crash(monkeypatch, page, missing):
    from test_holdings_page_smoke import rp
    pos = [dict(p) for p in POSITIONS]
    for i, p in enumerate(pos):
        if missing == "all" or i == 1:
            p["average_purchase_price"] = None
    st, http, _ = run(monkeypatch, page, unlocked=True, positions=pos)
    assert st.dataframe.called
