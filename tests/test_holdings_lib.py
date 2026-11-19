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


# ---- tolerance for unexpected response shapes (the real-world crash) ----
def test_positions_wrapped_in_a_dict_are_read():
    wrapped = {"positions": [pos("AAPL", 2, 100.0)], "option_positions": []}
    rows = hl.normalize_positions(ACCT, wrapped)
    assert [r["Symbol"] for r in rows] == ["AAPL"]


def test_dict_with_single_list_inside_is_read_even_with_unknown_key():
    rows = hl.normalize_positions(ACCT, {"holdings_list": [pos("MSFT", 1, 10.0)], "count": 1})
    assert [r["Symbol"] for r in rows] == ["MSFT"]


def test_non_dict_items_are_skipped_not_fatal():
    # iterating a dict yields strings; strings/ints/lists inside a list must not crash
    junk = ["positions", 5, None, ["x"], pos("VOO", 1, 10.0)]
    assert [r["Symbol"] for r in hl.normalize_positions(ACCT, junk)] == ["VOO"]
    assert hl.normalize_positions(ACCT, {"a": 1, "b": 2}) == []
    assert hl.normalize_positions(ACCT, "oops") == []


def test_each_position_nested_one_level_down():
    nested = [{"position": pos("TSLA", 3, 10.0)}]
    assert [r["Symbol"] for r in hl.normalize_positions(ACCT, nested)] == ["TSLA"]


def test_balances_tolerate_wrapper_and_junk():
    assert hl.cash_from_balances({"balances": [{"currency": {"code": "USD"}, "cash": 7}]}) == {"USD": 7.0}
    assert hl.cash_from_balances(["x", None, {"cash": 3}]) == {"USD": 3.0}
    assert hl.cash_from_balances("nope") == {}


def test_to_plain_handles_dict_likes_that_are_not_dict_subclasses():
    from collections.abc import Mapping

    class FrozenLike(Mapping):
        def __init__(self, d): self._d = d
        def __getitem__(self, k): return self._d[k]
        def __iter__(self): return iter(self._d)
        def __len__(self): return len(self._d)

    plain = hl.to_plain(FrozenLike({"units": 2, "symbol": FrozenLike({"symbol": "A"})}))
    assert plain == {"units": 2, "symbol": {"symbol": "A"}}


def test_build_portfolio_survives_wrapped_and_junk_payloads():
    item_ = {"account": ACCT, "positions": {"positions": [pos("A", 1, 10.0), "junk"]},
             "balances": {"balances": [{"currency": {"code": "USD"}, "cash": 5}]}, "error": None}
    pf = hl.build_portfolio([item_])
    assert len(pf["positions"]) == 1 and pf["cash"] == 5


def test_describe_shape_has_names_and_types_but_never_values():
    payload = [{"symbol": {"symbol": {"symbol": "SECRETTICKER"}}, "units": 123456.789, "price": 99.5,
                "currency": {"code": "USD"}, "tags": []}]
    shape = hl.describe_shape(payload)
    text = str(shape)
    assert "SECRETTICKER" not in text and "123456" not in text and "99.5" not in text
    assert "units" in text and "float" in text and "list of 1" in text
    assert hl.describe_shape([]) == "list (empty)"
    assert hl.describe_shape("x") == "str"


def test_fetch_all_records_shape_without_values_and_tolerates_wrapped_accounts():
    class Wrapped(FakeAccountInfo):
        def list_user_accounts(self):
            return FakeResp({"accounts": [ACCT, "junk"]})

    c = FakeClient()
    c.account_information = Wrapped()
    out = hl.fetch_all(c)
    assert len(out) == 1
    assert "units" in str(out[0]["shape"]["positions"])
    assert "Z12345678" not in str(out[0]["shape"])


# ---- ticker/class detection (the "100% in one holding" bug) ----
def real_pos(ticker, units, price, type_code="cs", type_desc="Common Stock", currency_symbol="$", cash_eq=False):
    """Roughly SnapTrade's real nesting, including a currency block that ALSO has a 'symbol' string."""
    return {
        "symbol": {
            "id": "pos-sym-id",
            "symbol": {
                "id": "u-id", "symbol": ticker, "raw_symbol": ticker, "description": f"{ticker} Inc",
                "currency": {"id": "c", "code": "USD", "name": "US Dollar", "symbol": currency_symbol},
                "exchange": {"code": "NYSE", "name": "NYSE", "symbol": "XNYS"},
                "type": {"id": "t", "code": type_code, "description": type_desc},
            },
        },
        "units": units, "price": price, "average_purchase_price": price * 0.8,
        "cash_equivalent": cash_eq, "currency": {"code": "USD", "symbol": "$"},
    }


def test_real_shape_ticker_not_confused_by_currency_or_exchange_symbols():
    rows = hl.normalize_positions(ACCT, [real_pos("AAPL", 1, 10.0), real_pos("VOO", 1, 10.0)])
    assert [r["Symbol"] for r in rows] == ["AAPL", "VOO"]  # not '$' or 'XNYS'
    assert rows[0]["Description"] == "AAPL Inc"


def test_different_tickers_are_not_merged_into_one():
    pf = hl.build_portfolio([item([real_pos("AAA", 1, 100.0), real_pos("BBB", 1, 100.0)])])
    merged = hl.by_symbol(pf["positions"])
    assert set(merged["Symbol"]) == {"AAA", "BBB"}
    assert hl.concentration(merged["Weight %"])["largest"] == pytest.approx(50)


def test_classify():
    assert hl.classify(real_pos("A", 1, 1, "cs", "Common Stock")) == "Stock"
    assert hl.classify(real_pos("V", 1, 1, "et", "ETF")) == "ETF"
    assert hl.classify(real_pos("M", 1, 1, "xx", "Money Market Fund")) == "Fund"
    assert hl.classify(real_pos("Z", 1, 1, "xx", "Something odd")) == "Other"
    assert hl.classify(real_pos("S", 1, 1, "et", "ETF", cash_eq=True)) == "Cash equiv."
    assert hl.classify({"units": 1}) == "Other"
    assert hl.classify({"symbol": {"symbol": {"type": {"description": "Exchange Traded Fund"}}}}) == "ETF"


# ---- summary / mix / bars / insights ----
def sample_pf():
    return hl.build_portfolio([item([
        real_pos("VOO", 10, 100.0, "et", "ETF"), real_pos("AAPL", 5, 100.0, "cs", "Common Stock"),
        real_pos("MSFT", 5, 100.0, "cs", "Common Stock"),
    ], cash=500.0)])  # 1000 + 500 + 500 + 500 cash = 2500


def test_summarize_numbers():
    pf = sample_pf()
    s = hl.summarize(pf["positions"], pf["cash"])
    assert s["total"] == 2500 and s["invested"] == 2000 and s["n_holdings"] == 3
    assert s["cash_pct"] == pytest.approx(20)
    assert s["gain"] == pytest.approx(400)            # 2000 value vs 1600 cost (bought at 80% of price)
    assert s["gain_pct"] == pytest.approx(25.0)
    assert s["gain_coverage"] == pytest.approx(1.0)


def test_summarize_empty_and_missing_cost():
    s = hl.summarize(pd.DataFrame(columns=hl.POSITION_COLS), 0.0)
    assert s["total"] == 0 and s["gain"] is None and s["cash_pct"] is None
    pf = hl.build_portfolio([item([pos("A", 1, 100.0)])])  # no cost info
    s = hl.summarize(pf["positions"], pf["cash"])
    assert s["gain"] is None and s["gain_pct"] is None and s["gain_coverage"] == 0.0


def test_asset_mix_includes_cash_and_sums_to_100():
    pf = sample_pf()
    mix = hl.asset_mix(pf["positions"], pf["cash"])
    assert mix["Share %"].sum() == pytest.approx(100)
    by = dict(zip(mix["Class"], mix["Share %"]))
    assert by["ETF"] == pytest.approx(40) and by["Stock"] == pytest.approx(40) and by["Cash"] == pytest.approx(20)
    assert hl.asset_mix(pd.DataFrame(columns=hl.POSITION_COLS), 0).empty


def test_top_for_bars_folds_tail():
    rows = [real_pos(f"T{i}", 1, 100.0 - i) for i in range(14)]
    merged = hl.by_symbol(hl.build_portfolio([item(rows)])["positions"])
    top = hl.top_for_bars(merged, n=10)
    assert len(top) == 11 and top.iloc[-1]["Symbol"] == "Other (4)"
    assert top["Weight %"].sum() == pytest.approx(100)
    assert len(hl.top_for_bars(merged.head(3), n=10)) == 3


def test_gain_rows_sorted_and_limited():
    rows = [real_pos(f"T{i}", 1, 100.0) for i in range(5)]
    for i, r in enumerate(rows):
        r["average_purchase_price"] = 100.0 / (1 + (i - 2) * 0.1)  # varied gains incl. losses
    merged = hl.by_symbol(hl.build_portfolio([item(rows)])["positions"])
    g = hl.gain_rows(merged, limit=3)
    assert len(g) == 3 and list(g["Gain %"]) == sorted(g["Gain %"], reverse=True)


def test_formatters():
    assert hl.money(10366.4) == "$10,366" and hl.money(-5.6) == "−$6" and hl.money(None) == "—"
    assert hl.money(1234, signed=True) == "+$1,234" and hl.money(-1234, signed=True) == "−$1,234"
    assert hl.pct(3.14159) == "+3.1%" and hl.pct(-2.0) == "-2.0%" and hl.pct(None) == "—"
    assert hl.pct(12.34, signed=False) == "12.3%"


def test_insights_are_descriptive_and_handle_single_holding():
    pf = sample_pf()
    merged = hl.by_symbol(pf["positions"])
    s = hl.summarize(pf["positions"], pf["cash"])
    mix = hl.asset_mix(pf["positions"], pf["cash"])
    text = " ".join(hl.insights(s, hl.concentration(merged["Weight %"]), mix, merged))
    assert "VOO" in text and "ETFs are 40%" in text and "Cash is 20%" in text
    for banned in ("should", "buy", "sell", "recommend"):
        assert banned not in text.lower().replace("buying", "")
    one = hl.by_symbol(hl.build_portfolio([item([real_pos("VOO", 1, 100.0)])])["positions"])
    s1 = hl.summarize(one.assign(**{"Market value": one["Market value"]}), 0.0)
    assert any("single position" in t for t in hl.insights(s1, hl.concentration(one["Weight %"]), pd.DataFrame(), one))
    assert hl.insights(s, {}, mix, pd.DataFrame()) == []


def test_asset_mix_folds_cash_equivalents_into_cash():
    pf = hl.build_portfolio([item([real_pos("SPAXX", 100, 1.0, "et", "ETF", cash_eq=True),
                                   real_pos("VOO", 1, 100.0, "et", "ETF")], cash=100.0)])
    mix = hl.asset_mix(pf["positions"], pf["cash"])
    by = dict(zip(mix["Class"], mix["Value"]))
    assert by["Cash"] == pytest.approx(200) and by["ETF"] == pytest.approx(100)
    assert "Cash equiv." not in by


def test_summarize_excludes_cash_equivalents_from_holding_count():
    pf = hl.build_portfolio([item([real_pos("VOO", 1, 100.0, "et", "ETF"),
                                   real_pos("SPAXX", 100, 1.0, "oef", "Money Market", cash_eq=True)])])
    assert hl.summarize(pf["positions"], pf["cash"])["n_holdings"] == 1
