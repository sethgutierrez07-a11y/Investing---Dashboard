import sys
import types
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import dividend_data as dd  # noqa: E402

TODAY = pd.Timestamp("2026-11-18")
ACCTS = [{"id": "a1", "name": "Individual", "institution_name": "Fidelity"},
         {"id": "a2", "name": "Roth IRA", "institution_name": "Fidelity"}]


class Resp:
    def __init__(self, body):
        self.body = body


def row(i, kind="DIVIDEND"):
    return {"id": f"id{i}", "type": kind, "trade_date": "2026-01-02", "amount": 1.0, "symbol": {"symbol": "AAPL"}}


class FakeAcctInfo:
    def __init__(self, rows_by_acct=None, reject_type=False, reject_ranges_over=None, fail_accts=(), total_key=True):
        self.rows = rows_by_acct or {}
        self.reject_type, self.reject_over, self.fail = reject_type, reject_ranges_over, fail_accts
        self.calls = []
        self.total_key = total_key

    def get_account_activities(self, account_id, start_date, end_date, offset=0, limit=1000, type=None):
        self.calls.append({"account_id": account_id, "start": start_date, "offset": offset, "type": type})
        if account_id in self.fail:
            raise TimeoutError("slow")
        if type and self.reject_type:
            raise ValueError("bad type filter")
        if self.reject_over:
            days = (pd.Timestamp(end_date) - pd.Timestamp(start_date)).days
            if days > self.reject_over:
                raise ValueError("range too long")
        rows = self.rows.get(account_id, [])
        if type:
            rows = [r for r in rows if r["type"] in type.split(",")]
        page = rows[offset: offset + limit]
        body = {"data": page}
        if self.total_key:
            body["pagination"] = {"offset": offset, "limit": limit, "total": len(rows)}
        return Resp(body)


class FakeClient:
    def __init__(self, **kw):
        self.account_information = FakeAcctInfo(**kw)

    def __getattr__(self, name):
        raise AssertionError(f"read-only violation: client.{name} was accessed")


def test_reads_each_account_with_only_the_activity_endpoint():
    c = FakeClient(rows_by_acct={"a1": [row(1), row(2, "REI")], "a2": [row(3)]})
    out = dd.fetch_activities(c, ACCTS, TODAY)
    assert sorted(i["id"] for i in out["items"]) == ["id1", "id2", "id3"]
    assert {i["_account"] for i in out["items"]} == {"Fidelity · Individual", "Fidelity · Roth IRA"}
    assert {k["type"] for k in c.account_information.calls} == {dd.ACTIVITY_TYPES}
    assert out["errors"] == [] and out["range_days"] == 3650
    assert "activity" in out["shape"] and "id" in out["shape"]["activity"]
    assert "AAPL" not in str(out["shape"])                       # field names and types only, never values


def test_paging_collects_every_page(monkeypatch):
    monkeypatch.setattr(dd, "PAGE", 2)
    c = FakeClient(rows_by_acct={"a1": [row(i) for i in range(5)]})
    out = dd.fetch_activities(c, ACCTS[:1], TODAY)
    assert len(out["items"]) == 5
    assert [k["offset"] for k in c.account_information.calls] == [0, 2, 4]


def test_paging_stops_without_pagination_info(monkeypatch):
    monkeypatch.setattr(dd, "PAGE", 2)
    c = FakeClient(rows_by_acct={"a1": [row(i) for i in range(3)]}, total_key=False)
    assert len(dd.fetch_activities(c, ACCTS[:1], TODAY)["items"]) == 3


def test_falls_back_to_unfiltered_then_filters_locally_in_the_parser():
    c = FakeClient(rows_by_acct={"a1": [row(1), row(2, "BUY")]}, reject_type=True)
    out = dd.fetch_activities(c, ACCTS[:1], TODAY)
    assert len(out["items"]) == 2 and c.account_information.calls[-1]["type"] is None


def test_shortens_the_date_range_when_the_broker_rejects_a_long_one():
    c = FakeClient(rows_by_acct={"a1": [row(1)]}, reject_ranges_over=400)
    out = dd.fetch_activities(c, ACCTS[:1], TODAY)
    assert len(out["items"]) == 1 and out["range_days"] == 365


def test_one_failing_account_does_not_hide_the_others():
    c = FakeClient(rows_by_acct={"a1": [row(1)], "a2": [row(2)]}, fail_accts=("a2",))
    out = dd.fetch_activities(c, ACCTS, TODAY)
    assert [i["id"] for i in out["items"]] == ["id1"]
    assert len(out["errors"]) == 1 and "Roth IRA" in out["errors"][0] and "TimeoutError" in out["errors"][0]
    assert "a2" not in str(out["errors"])                          # never the raw account id


def test_no_accounts_and_malformed_accounts():
    assert dd.fetch_activities(FakeClient(), [], TODAY)["items"] == []
    assert dd.fetch_activities(FakeClient(), [None, {"name": "no id"}], TODAY)["items"] == []


def test_any_other_client_area_is_never_touched():
    c = FakeClient(rows_by_acct={"a1": [row(1)]})
    dd.fetch_activities(c, ACCTS[:1], TODAY)
    with pytest.raises(AssertionError):
        c.trading


# ---------------------------------------------------------------- Yahoo wrapper
def install_fake_yf(monkeypatch, hist=None, boom=None):
    class T:
        def __init__(self, sym):
            self.sym = sym

        def history(self, **kw):
            assert kw.get("auto_adjust") is False and kw.get("actions") is True     # unadjusted closes + dividends
            if boom:
                raise boom
            return hist

    mod = types.ModuleType("yfinance")
    mod.Ticker = T
    monkeypatch.setitem(sys.modules, "yfinance", mod)


def test_fetch_history_splits_prices_and_dividends(monkeypatch):
    idx = pd.DatetimeIndex(["2026-01-02", "2026-01-05", "2026-01-06"], tz="America/New_York")
    h = pd.DataFrame({"Close": [100.0, 101.0, 99.0], "Dividends": [0.0, 0.5, 0.0]}, index=idx)
    install_fake_yf(monkeypatch, hist=h)
    r = dd.fetch_history("AAPL")
    assert r["error"] is None and len(r["prices"]) == 3 and list(r["divs"]) == [0.5]
    assert r["prices"].index.tz is None and r["divs"].index[0] == pd.Timestamp("2026-01-05")


def test_fetch_history_reports_problems_instead_of_raising(monkeypatch):
    install_fake_yf(monkeypatch, boom=RuntimeError("429"))
    assert "didn't answer" in dd.fetch_history("AAPL")["error"]
    install_fake_yf(monkeypatch, hist=pd.DataFrame())
    assert dd.fetch_history("AAPL")["error"] == "no history"
    monkeypatch.setitem(sys.modules, "yfinance", None)
    assert "isn't installed" in dd.fetch_history("AAPL")["error"]


def test_class_share_tickers_use_yahoos_dash_spelling(monkeypatch):
    seen = []

    class T:
        def __init__(self, sym):
            seen.append(sym)

        def history(self, **kw):
            return pd.DataFrame()

    mod = types.ModuleType("yfinance")
    mod.Ticker = T
    monkeypatch.setitem(sys.modules, "yfinance", mod)
    dd.fetch_history("BRK.B")
    assert seen == ["BRK-B"]
