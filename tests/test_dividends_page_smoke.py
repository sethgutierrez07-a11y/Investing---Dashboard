"""
Smoke test: run pages/4_Dividends.py end to end with stand-ins for Streamlit, SnapTrade (including the
activity endpoint) and Yahoo. Checks that nothing crashes, the lock holds, only read endpoints are used,
and the right things render. It does not check how the page looks.
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
from test_holdings_page_smoke import GOOD_SECRETS, POSITIONS, FakeAcctInfo, Resp, Stopped  # noqa: E402

NOW = pd.Timestamp.now(tz="America/Chicago").tz_localize(None).normalize()
READ_ONLY = {"list_user_accounts", "get_user_account_balance", "get_all_account_positions", "get_user_holdings",
             "get_account_activities"}


def quarterly_back(end, n, per_share, growth=0.0, step=3):
    idx = [end - pd.DateOffset(months=step * i) for i in range(n)][::-1]
    vals = [per_share * (1 + growth) ** (i // 4) for i in range(n)]
    return pd.Series(vals, index=pd.DatetimeIndex(idx))


def fake_history(sym):
    if sym == "MSFT":                                           # pays nothing in this fake
        divs = pd.Series(dtype=float)
    elif sym == "AAPL":
        divs = quarterly_back(NOW - pd.Timedelta(days=40), 40, 0.25, 0.05)
    else:
        divs = quarterly_back(NOW - pd.Timedelta(days=30), 40, 1.8)
    idx = pd.bdate_range(end=NOW, periods=12 * 261)
    prices = pd.Series(np.linspace(60, 200, len(idx)), index=idx)
    return {"prices": prices, "divs": divs, "error": None}


def activities():
    rows = []
    for i in range(1, 9):                                      # AAPL: a dividend every ~quarter, reinvested
        d = (NOW - pd.DateOffset(months=3 * i) - pd.Timedelta(days=30)).strftime("%Y-%m-%d")
        rows.append({"id": f"a{i}", "type": "DIVIDEND", "trade_date": d, "amount": 2.0 + i * 0.1, "symbol": {"symbol": "AAPL"}})
        rows.append({"id": f"r{i}", "type": "REI", "trade_date": d, "amount": -(2.0 + i * 0.1), "units": 0.01,
                     "price": 200.0, "symbol": {"symbol": "AAPL"}})
    for i in range(1, 9):                                      # VOO: cash only
        d = (NOW - pd.DateOffset(months=3 * i) - pd.Timedelta(days=25)).strftime("%Y-%m-%d")
        rows.append({"id": f"v{i}", "type": "DIVIDEND", "trade_date": d, "amount": 25.0, "symbol": {"symbol": "VOO"}})
    return rows


class ActAcctInfo(FakeAcctInfo):
    def __init__(self, positions, rows, fail=False):
        super().__init__(positions)
        self.rows, self.fail, self.calls = rows, fail, []

    def __getattribute__(self, name):
        if name.startswith(("get_", "list_")):
            object.__getattribute__(self, "calls").append(name)
        return object.__getattribute__(self, name)

    def get_account_activities(self, account_id, start_date, end_date, offset=0, limit=1000, type=None):
        if self.fail:
            raise TimeoutError("slow")
        rows = [r for r in self.rows if not type or r["type"] in type.split(",")]
        return Resp({"data": rows[offset: offset + limit], "pagination": {"total": len(rows)}})


class Client:
    def __init__(self, info):
        self.account_information = info

    def __getattr__(self, name):
        raise AssertionError(f"read-only violation: client.{name} was accessed")


def make_streamlit(hide=False, secrets=None, unlocked=True, other_ticker="", horizon_index=2):
    st = MagicMock(name="streamlit")
    st.secrets = dict(GOOD_SECRETS if secrets is None else secrets)
    st.session_state = {"holdings_unlocked": True} if unlocked else {}
    st.cache_data.side_effect = lambda *a, **k: (lambda f: f)
    st.cache_data.clear = MagicMock()
    st.toggle.return_value = hide
    st.button.return_value = False
    st.text_input.return_value = other_ticker
    st.selectbox.side_effect = lambda label, options, **k: options[0]
    st.radio.side_effect = lambda label, options, **k: options[horizon_index]
    st.slider.side_effect = lambda *a, **k: k["value"]
    def col():
        c = MagicMock()
        c.slider.side_effect = lambda *a, **k: k["value"]          # widgets placed on a column object
        return c

    st.columns.side_effect = lambda spec, **k: [col() for _ in range(spec if isinstance(spec, int) else len(spec))]
    st.tabs.side_effect = lambda labels: [MagicMock() for _ in labels]
    st.stop.side_effect = Stopped
    st.context.theme.type = "dark"
    return st


def run(monkeypatch, st, rows=None, fail_activities=False, history=fake_history, positions=POSITIONS):
    info = ActAcctInfo(positions, activities() if rows is None else rows, fail=fail_activities)
    made = []
    monkeypatch.setitem(sys.modules, "streamlit", st)
    monkeypatch.setattr(hl, "make_client", lambda cid, key: made.append(1) or Client(info))
    monkeypatch.setattr(dd, "fetch_history", history)
    for m in ("dividend_charts", "holdings_charts", "portfolio_state"):
        sys.modules.pop(m, None)
    runpy.run_path(str(ROOT / "pages" / "4_Dividends.py"), run_name="__main__")
    return info, made


def flat(st, *names):
    out = []
    for n in names:
        out += [str(c) for c in getattr(st, n).call_args_list]
    return " ".join(out)


def text_of(st):
    return flat(st, "markdown", "caption", "metric", "info", "warning", "error", "subheader", "title", "success")


def tab_names(st):
    return [list(c.args[0]) for c in st.tabs.call_args_list]


@pytest.mark.parametrize("hide", [False, True])
def test_page_renders_end_to_end(monkeypatch, hide):
    st = make_streamlit(hide=hide)
    info, made = run(monkeypatch, st)
    assert made and set(info.calls) <= READ_ONLY and "get_account_activities" in info.calls
    names = tab_names(st)
    assert names[0] == ["💵 Received", "📅 Coming up", "🏢 By company", "🔁 DRIP", "📈 Growth"] or names[1] == names[0]
    assert ["Bottom line", "Where it comes from", "What's coming", "Does DRIP pay?", "Worth knowing"] in names
    # received bars, expected stack, income-vs-weight, replay curves, what-if, growth bars
    assert st.plotly_chart.call_count == 6
    text = text_of(st)
    assert "Replaying" in text and "Holdings that pay" in text and "2 of 3" in text


def test_hide_mode_keeps_private_dollar_amounts_off_the_page(monkeypatch):
    st = make_streamlit(hide=True)
    run(monkeypatch, st)
    metrics = [str(c) for c in st.metric.call_args_list]
    assert any("••••" in m and "Expected" in m for m in metrics) and any("••••" in m and "Received" in m for m in metrics)
    bullets = [c.args[0] for c in st.markdown.call_args_list if c.args and str(c.args[0]).startswith("- ")]
    private = " ".join(b for b in bullets if "Replaying" not in b and "total gain" not in b)
    assert "\\$•••" in private and not re.search(r"\\\$\d", private)
    for c in st.dataframe.call_args_list:
        shown = set(c.args[0].columns)
        assert not shown & {"Annual income", "Received 12m", "Per payment", "Amount", "Value", "Per share", "Worth today"}


def test_dollar_signs_are_escaped_so_markdown_does_not_turn_them_into_math(monkeypatch):
    st = make_streamlit()
    run(monkeypatch, st)
    bullets = [c.args[0] for c in st.markdown.call_args_list if c.args and str(c.args[0]).startswith("- ")]
    assert bullets and all(not re.search(r"(?<!\\)\$", b) for b in bullets)
    assert any("\\$" in b for b in bullets)


def test_summary_is_the_first_thing_on_the_page(monkeypatch):
    st = make_streamlit()
    run(monkeypatch, st)
    assert [c.args[0] for c in st.subheader.call_args_list][0] == "Summary"
    assert st.container.called and "no AI" in text_of(st)


def test_locked_without_a_password_secret_or_before_unlock(monkeypatch):
    st = make_streamlit(secrets={})
    with pytest.raises(Stopped):
        run(monkeypatch, st)
    assert not st.plotly_chart.called
    st2 = make_streamlit(unlocked=False)
    with pytest.raises(Stopped):
        run(monkeypatch, st2)
    assert not st2.plotly_chart.called and not st2.dataframe.called


def test_never_reads_the_brokerage_while_locked(monkeypatch):
    st = make_streamlit(unlocked=False)
    made = []
    monkeypatch.setitem(sys.modules, "streamlit", st)
    monkeypatch.setattr(hl, "make_client", lambda *a: made.append(1))
    for m in ("dividend_charts", "holdings_charts", "portfolio_state"):
        sys.modules.pop(m, None)
    with pytest.raises(Stopped):
        runpy.run_path(str(ROOT / "pages" / "4_Dividends.py"), run_name="__main__")
    assert made == []


def test_needs_snaptrade_keys(monkeypatch):
    st = make_streamlit(secrets={"APP_PASSWORD": "pw"})
    with pytest.raises(Stopped):
        run(monkeypatch, st)


def test_page_survives_an_unreadable_activity_feed(monkeypatch):
    st = make_streamlit()
    run(monkeypatch, st, fail_activities=True)
    text = text_of(st)
    assert "Activity:" in text and "couldn't be read" in text            # said plainly, and still shows expected income
    assert "Expected, next 12 months" in text


def test_page_survives_an_empty_activity_feed(monkeypatch):
    st = make_streamlit()
    run(monkeypatch, st, rows=[])
    text = text_of(st)
    assert "No dividend payments came back" in text and st.plotly_chart.call_count >= 4


def test_page_survives_yahoo_failing_for_every_ticker(monkeypatch):
    st = make_streamlit()
    bad = lambda s: {"prices": pd.Series(dtype=float), "divs": pd.Series(dtype=float), "error": "Yahoo didn't answer (RuntimeError)."}
    run(monkeypatch, st, history=bad)
    assert "Couldn't load dividend history for" in text_of(st)


def test_non_payers_only_still_renders(monkeypatch):
    st = make_streamlit()
    nopay = lambda s: {**fake_history(s), "divs": pd.Series(dtype=float)}
    run(monkeypatch, st, rows=[], history=nopay)
    assert "None of your 3 holdings" in text_of(st)


def test_try_any_ticker_replays_that_ticker(monkeypatch):
    st = make_streamlit(other_ticker="schd")
    seen = []

    def hist(s):
        seen.append(s)
        return fake_history(s)

    run(monkeypatch, st, history=hist)
    assert "SCHD" in seen and "Replaying SCHD" in text_of(st)


def test_account_ids_and_values_never_reach_the_page(monkeypatch):
    st = make_streamlit()
    run(monkeypatch, st)
    assert "a1" not in flat(st, "json")
