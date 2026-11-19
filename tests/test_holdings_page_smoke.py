"""
Smoke test: run pages/2_Holdings.py end to end with stand-ins for Streamlit
(and Plotly, if it isn't installed) and fake SnapTrade data. This does not check
how the page LOOKS; it checks that nothing crashes and the right things render.
"""

import runpy
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import holdings_lib as hl  # noqa: E402


# ---------- fake data in SnapTrade's real nesting ----------
def rp(ticker, units, price, avg, code="cs", desc="Common Stock", cash_eq=False):
    return {
        "symbol": {"id": "x", "symbol": {
            "id": "u", "symbol": ticker, "raw_symbol": ticker, "description": f"{ticker} Corp",
            "currency": {"code": "USD", "symbol": "$"}, "exchange": {"code": "X", "symbol": "XNYS"},
            "type": {"code": code, "description": desc}}},
        "units": units, "price": price, "average_purchase_price": avg, "cash_equivalent": cash_eq,
        "currency": {"code": "USD"},
    }


class Resp:
    def __init__(self, body):
        self.body = body


class FakeAcctInfo:
    def __init__(self, positions, cash=250.0):
        self._p, self._c = positions, cash

    def list_user_accounts(self):
        return Resp([{"id": "a1", "name": "Individual", "institution_name": "Fidelity",
                      "balance": {"total": {"amount": 10000.0}}}])

    def get_user_account_balance(self, account_id):
        return Resp([{"currency": {"code": "USD"}, "cash": self._c}])

    def get_all_account_positions(self, account_id):
        return Resp(self._p)


class FakeClient:
    def __init__(self, positions, cash=250.0):
        self.account_information = FakeAcctInfo(positions, cash)


POSITIONS = [
    rp("VOO", 15, 500.0, 420.0, "et", "ETF"),
    rp("AAPL", 8, 200.0, 150.0),
    rp("MSFT", 3, 400.0, 450.0),             # a loser
    rp("SPAXX", 500, 1.0, 1.0, "oef", "Money Market", cash_eq=True),
]


# ---------- stand-ins ----------
class Stopped(Exception):
    pass


def make_streamlit(hide, combine, secrets):
    st = MagicMock(name="streamlit")
    st.secrets = secrets
    st.session_state = {"holdings_unlocked": True}
    st.cache_data.side_effect = lambda *a, **k: (lambda f: f)  # pass-through decorator
    st.cache_data.clear = MagicMock()
    toggles = iter([hide, combine])
    st.toggle.side_effect = lambda *a, **k: next(toggles)
    st.button.return_value = False
    st.columns.side_effect = lambda spec, **k: [MagicMock() for _ in range(spec if isinstance(spec, int) else len(spec))]
    st.stop.side_effect = Stopped
    st.context.theme.type = "dark"
    return st


def stub_plotly_if_missing():
    try:
        import plotly.graph_objects  # noqa: F401
        return
    except ImportError:
        pass

    class Fig:
        def __init__(self, *traces):
            self.traces = list(traces)
            self.layout = {}

        def add_trace(self, t):
            self.traces.append(t)

        def update_layout(self, **k):
            self.layout.update(k)

        def update_xaxes(self, **k):
            pass

        def update_yaxes(self, **k):
            pass

        def update_traces(self, **k):
            pass

    go = types.ModuleType("plotly.graph_objects")
    go.Figure = Fig
    go.Bar = lambda **k: k
    pkg = types.ModuleType("plotly")
    pkg.graph_objects = go
    sys.modules["plotly"], sys.modules["plotly.graph_objects"] = pkg, go


def run_page(monkeypatch, st, positions=POSITIONS, cash=250.0):
    stub_plotly_if_missing()
    monkeypatch.setitem(sys.modules, "streamlit", st)
    monkeypatch.setattr(hl, "make_client", lambda cid, key: FakeClient(positions, cash))
    for m in ("holdings_charts", "brief_lib", "portfolio_state"):
        sys.modules.pop(m, None)
    runpy.run_path(str(ROOT / "pages" / "2_Holdings.py"), run_name="__main__")


GOOD_SECRETS = {"APP_PASSWORD": "pw", "SNAPTRADE_CLIENT_ID": "id", "SNAPTRADE_CONSUMER_KEY": "key"}


def rendered_text(st):
    """Everything passed to markdown/caption/metric/etc., flattened."""
    out = []
    for name in ("markdown", "caption", "metric", "info", "warning", "error", "progress", "subheader", "title"):
        for call in getattr(st, name).call_args_list:
            out.append(str(call))
    return " ".join(out)


# ---------- tests ----------
@pytest.mark.parametrize("hide", [False, True])
@pytest.mark.parametrize("combine", [True, False])
def test_page_renders_end_to_end(monkeypatch, hide, combine):
    st = make_streamlit(hide, combine, GOOD_SECRETS)
    run_page(monkeypatch, st)
    assert st.plotly_chart.call_count == 3  # allocation, mix, gains
    assert st.dataframe.called
    text = rendered_text(st)
    assert "Total portfolio value" in text
    if hide:
        assert "••••••" in text
        assert "$" not in text.replace("$%", "")  # no dollar amounts anywhere when hidden
    else:
        # VOO 7500 + AAPL 1600 + MSFT 1200 + SPAXX 500 + cash 250 = 11050
        assert "$11,050" in text


def test_page_survives_no_cost_basis_and_single_holding(monkeypatch):
    st = make_streamlit(False, True, GOOD_SECRETS)
    only = [dict(rp("VOO", 10, 100.0, None, "et", "ETF"), average_purchase_price=None)]
    run_page(monkeypatch, st, positions=only, cash=0.0)
    assert st.plotly_chart.call_count == 2  # gains chart skipped (no cost data)
    assert "single position" in rendered_text(st)


def test_page_locked_without_password_secret(monkeypatch):
    st = make_streamlit(False, True, {})  # no APP_PASSWORD
    with pytest.raises(Stopped):
        run_page(monkeypatch, st)
    assert not st.plotly_chart.called and not st.dataframe.called


def test_page_locked_until_unlocked(monkeypatch):
    st = make_streamlit(False, True, GOOD_SECRETS)
    st.session_state = {}  # not unlocked
    with pytest.raises(Stopped):
        run_page(monkeypatch, st)
    assert not st.plotly_chart.called and not st.dataframe.called


def test_page_needs_snaptrade_keys(monkeypatch):
    st = make_streamlit(False, True, {"APP_PASSWORD": "pw"})
    with pytest.raises(Stopped):
        run_page(monkeypatch, st)
    assert not st.dataframe.called


def test_page_shows_error_not_traceback_when_snaptrade_fails(monkeypatch):
    st = make_streamlit(False, True, GOOD_SECRETS)
    stub_plotly_if_missing()
    monkeypatch.setitem(sys.modules, "streamlit", st)

    def boom(cid, key):
        raise RuntimeError("nope")

    monkeypatch.setattr(hl, "make_client", boom)
    for m in ("holdings_charts", "brief_lib", "portfolio_state"):
        sys.modules.pop(m, None)
    with pytest.raises(Stopped):
        runpy.run_path(str(ROOT / "pages" / "2_Holdings.py"), run_name="__main__")
    assert st.error.called and not st.dataframe.called
