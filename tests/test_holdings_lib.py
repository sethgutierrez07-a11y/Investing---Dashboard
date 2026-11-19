import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import holdings_lib as hl  # noqa: E402


def pos(ticker, units, price, avg=None, pnl=None, desc="", fractional=None):
    return {
        "symbol": {"symbol": {"symbol": ticker, "description": desc, "currency": {"code": "USD"}}},
        "units": units,
        "fractional_units": fractional,
        "price": price,
        "average_purchase_price": avg,
        "open_pnl": pnl,
        "currency": {"code": "USD"},
    }


ACCT = {"id": "a1", "name": "Individual", "institution_name": "Fidelity", "number": "Z12345678",
        "balance": {"total": {"amount": 1500.0, "currency": "USD"}}}


# ---- normalization ----
def test_normalize_basic_gain_and_label_hides_number():
    rows = hl.normalize_positions(ACCT, [pos("aapl", 10, 150.0, avg=100.0, desc="Apple")])
    r = rows[0]
    assert r["Symbol"] == "AAPL"
    assert r["Market value"] == 1500.0
    assert r["Cost basis"] == 1000.0
    assert r["Gain"] == 500.0
    assert r["Gain %"] == pytest.approx(50.0)
    assert r["Account"] == "Fidelity · Individual"
    assert "Z12345678" not in str(r)


def test_normalize_falls_back_to_open_pnl_without_avg_price():
    r = hl.normalize_positions(ACCT, [pos("VOO", 2, 500.0, avg=None, pnl=100.0)])[0]
    assert r["Gain"] == 100.0
    assert r["Cost basis"] == 900.0
    assert r["Gain %"] == pytest.approx(100 / 900 * 100)


def test_normalize_no_cost_info_leaves_gain_empty():
    r = hl.normalize_positions(ACCT, [pos("VOO", 2, 500.0)])[0]
    assert r["Gain"] is None and r["Gain %"] is None and r["Market value"] == 1000.0


def test_normalize_skips_zero_units_and_uses_fractional():
    rows = hl.normalize_positions(ACCT, [pos("A", 0, 10.0), pos("B", None, 10.0, fractional=2.5)])
    assert [r["Symbol"] for r in rows] == ["B"]
    assert rows[0]["Units"] == 2.5


def test_normalize_alternate_ticker_shapes():
    p1 = {"symbol": {"raw_symbol": "MSFT"}, "units": 1, "price": 1.0}
    p2 = {"symbol": {"symbol": "TSLA"}, "units": 1, "price": 1.0}  # ticker string one level up
    p3 = {"units": 1, "price": 1.0}  # nothing usable
    syms = [r["Symbol"] for r in hl.normalize_positions(ACCT, [p1, p2, p3])]
    assert syms == ["MSFT", "TSLA", "?"]


def test_normalize_handles_junk():
    assert hl.normalize_positions(ACCT, None) == []
    bad = {"units": "abc", "price": "x", "symbol": {"symbol": {"symbol": "ZZ"}}}
    assert hl.normalize_positions(ACCT, [bad]) == []  # unreadable units -> skipped


def test_cash_from_balances():
    bal = [{"currency": {"code": "USD"}, "cash": 100.5}, {"currency": {"code": "USD"}, "cash": 10},
           {"currency": {"code": "CAD"}, "cash": 5}, {"cash": None}]
    assert hl.cash_from_balances(bal) == {"USD": 110.5, "CAD": 5.0}
    assert hl.cash_from_balances(None) == {}


# ---- portfolio build ----
def item(positions, cash=0.0, acct=ACCT, error=None):
    return {"account": acct, "positions": positions, "balances": [{"currency": {"code": "USD"}, "cash": cash}], "error": error}


def test_build_portfolio_weights_sum_to_100_with_cash():
    pf = hl.build_portfolio([item([pos("A", 10, 100.0), pos("B", 5, 100.0)], cash=500.0)])
    assert pf["total"] == 2000.0 and pf["cash"] == 500.0
    assert pf["positions"]["Weight %"].sum() + 500 / 2000 * 100 == pytest.approx(100)
    assert pf["positions"].iloc[0]["Symbol"] == "A"  # sorted by value


def test_build_portfolio_isolates_failed_account():
    acct2 = dict(ACCT, id="a2", name="Roth", balance={})
    pf = hl.build_portfolio([item([pos("A", 1, 100.0)], acct=ACCT), item([], acct=acct2, error="Timeout")])
    assert len(pf["positions"]) == 1
    assert any("Roth" in w and "Timeout" in w for w in pf["warnings"])


def test_build_portfolio_reconciliation_warning():
    acct = dict(ACCT, balance={"total": {"amount": 5000.0}})
    pf = hl.build_portfolio([item([pos("A", 10, 100.0)], acct=acct)])
    assert any("differ" in w for w in pf["warnings"])
    ok = hl.build_portfolio([item([pos("A", 10, 100.0)], cash=500.0)])
    assert not any("differ" in w for w in ok["warnings"])


def test_build_portfolio_warns_when_positions_unreadable_and_non_usd():
    junk = [{"units": "abc"}]
    pf = hl.build_portfolio([item(junk)])
    assert any("none could be read" in w for w in pf["warnings"])
    cad = {"account": ACCT, "positions": [], "balances": [{"currency": {"code": "CAD"}, "cash": 50}], "error": None}
    assert any("non-USD" in w for w in hl.build_portfolio([cad])["warnings"])


def test_build_portfolio_empty():
    pf = hl.build_portfolio([])
    assert pf["positions"].empty and pf["total"] == 0


def test_by_symbol_merges_accounts():
    acct2 = dict(ACCT, id="a2", name="Roth")
    pf = hl.build_portfolio([item([pos("A", 10, 100.0, avg=50.0)]), item([pos("A", 5, 100.0, avg=100.0)], acct=acct2)])
    m = hl.by_symbol(pf["positions"])
    assert len(m) == 1
    assert m.iloc[0]["Units"] == 15 and m.iloc[0]["Market value"] == 1500
    assert m.iloc[0]["Gain"] == pytest.approx(500) and m.iloc[0]["Gain %"] == pytest.approx(500 / 1000 * 100)
    assert hl.by_symbol(pd.DataFrame()).empty


# ---- analytics ----
def test_concentration_known_values():
    c = hl.concentration(pd.Series([50.0, 50.0]))
    assert c["largest"] == pytest.approx(50) and c["effective_n"] == pytest.approx(2)
    c = hl.concentration(pd.Series([25.0] * 4))
    assert c["effective_n"] == pytest.approx(4) and c["top5"] == pytest.approx(100)
    c = hl.concentration(pd.Series([90.0, 5.0, 5.0]))
    assert c["largest"] == pytest.approx(90) and c["effective_n"] < 1.25
    assert hl.concentration(pd.Series([], dtype=float))["largest"] is None


def test_concentration_rebases_to_invested_part():
    # 20% cash: the two stocks are 40%/40% of total = 50%/50% of invested
    assert hl.concentration(pd.Series([40.0, 40.0]))["largest"] == pytest.approx(50)


def test_day_change_weighted_and_coverage():
    pf = hl.build_portfolio([item([pos("A", 10, 100.0), pos("B", 10, 100.0), pos("C", 10, 100.0)])])
    quotes = {"A": {"c": 100, "dp": 2.0}, "B": {"c": 100, "dp": -1.0}, "C": None}
    d = hl.day_change(pf["positions"], quotes)
    assert d["pct"] == pytest.approx(0.5)  # (2 - 1)/2 over the priced part
    assert d["coverage"] == pytest.approx(2 / 3)
    assert hl.day_change(pf["positions"], {})["pct"] is None
    assert hl.day_change(pd.DataFrame(columns=hl.POSITION_COLS), {})["pct"] is None


def test_hide_dollars_removes_everything_that_reveals_size():
    pf = hl.build_portfolio([item([pos("A", 10, 100.0, avg=50.0)], cash=100.0)])
    h = hl.hide_dollars(pf["positions"])
    for col in ("Units", "Price", "Market value", "Cost basis", "Gain"):
        assert col not in h.columns
    assert {"Symbol", "Weight %", "Gain %"} <= set(h.columns)


# ---- access gate ----
def test_password_ok_fails_closed():
    assert hl.password_ok("secret", "secret")
    assert not hl.password_ok("wrong", "secret")
    assert not hl.password_ok("", "secret")
    assert not hl.password_ok(None, "secret")
    assert not hl.password_ok("anything", None)  # no password configured -> locked
    assert not hl.password_ok("", "")
    assert hl.password_ok("pässwörd", "pässwörd")  # non-ASCII must not crash


# ---- SnapTrade I/O ----
class FakeResp:
    def __init__(self, body):
        self.body = body


class FakeAccountInfo:
    def __init__(self, fail_on=None):
        self.fail_on = fail_on
        self.calls = []

    def list_user_accounts(self):
        self.calls.append("list_user_accounts")
        return FakeResp([ACCT, dict(ACCT, id="a2", name="Roth")])

    def get_user_account_balance(self, account_id):
        self.calls.append("get_user_account_balance")
        if account_id == self.fail_on:
            raise TimeoutError("slow")
        return FakeResp([{"currency": {"code": "USD"}, "cash": 10.0}])

    def get_all_account_positions(self, account_id):
        self.calls.append("get_all_account_positions")
        return FakeResp([pos("A", 1, 10.0)])


class FakeClient:
    def __init__(self, **kw):
        self.account_information = FakeAccountInfo(**kw)

    def __getattr__(self, name):  # any other area (trading, etc.) must never be touched
        raise AssertionError(f"read-only violation: client.{name} was accessed")


def test_fetch_all_only_uses_read_calls_and_isolates_errors():
    c = FakeClient(fail_on="a2")
    out = hl.fetch_all(c)
    assert [o["error"] for o in out] == [None, "TimeoutError"]
    assert set(c.account_information.calls) <= {"list_user_accounts", "get_user_account_balance", "get_all_account_positions"}
    pf = hl.build_portfolio(out)
    assert len(pf["positions"]) == 1 and any("Roth" in w for w in pf["warnings"])


def test_fetch_all_no_accounts():
    class Empty(FakeAccountInfo):
        def list_user_accounts(self):
            return FakeResp([])

    c = FakeClient()
    c.account_information = Empty()
    assert hl.fetch_all(c) == []


def test_to_plain_handles_sdk_like_objects():
    class Obj:
        def __init__(self):
            self.units = 3
            self._private = "no"

    class WithDict:
        def to_dict(self):
            return {"a": Obj()}

    assert hl.to_plain(WithDict()) == {"a": {"units": 3}}
    assert hl.to_plain([None, 1, "x"]) == [None, 1, "x"]


def test_make_client_clear_error_without_sdk():
    # SDK isn't installed here; the failure must be an ImportError we can show, not a crash elsewhere
    with pytest.raises((ImportError, RuntimeError)):
        hl.make_client("id", "key")
