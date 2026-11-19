import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import dividend_lib as dl  # noqa: E402

TODAY = pd.Timestamp("2026-11-18")


def act(type_, date, sym="AAPL", amount=10.0, units=None, price=None, id_=None, desc=None, symbol_shape="nested"):
    if symbol_shape == "nested":
        symbol = {"id": "x", "symbol": sym, "raw_symbol": sym, "description": f"{sym} Corp"} if sym else None
    elif symbol_shape == "double":
        symbol = {"symbol": {"symbol": sym}}
    else:
        symbol = sym
    d = {"id": id_, "type": type_, "trade_date": date, "amount": amount, "units": units, "price": price,
         "symbol": symbol, "description": desc, "_account": "Fidelity · Individual"}
    return {k: v for k, v in d.items() if v is not None}


def quarterly(start="2020-02-10", n=27, amount=0.25, step=3, grow=0.0):
    idx = [pd.Timestamp(start) + pd.DateOffset(months=step * i) for i in range(n)]
    return pd.Series([amount * (1 + grow) ** (i // (12 // step)) for i in range(n)], index=pd.DatetimeIndex(idx))


# ---------------------------------------------------------------- parsing
def test_parse_keeps_dividend_and_reinvestment_rows_only():
    df = dl.parse_activities([
        act("DIVIDEND", "2026-08-14T00:00:00Z", amount=12.5, id_="1"),
        act("REI", "2026-08-14", amount=-12.5, units=0.06, price=200.0, id_="2"),
        act("BUY", "2026-08-01", amount=-500.0, units=2, price=250.0, id_="3"),
        act("INTEREST", "2026-08-01", sym=None, amount=1.2, id_="4"),
        "garbage", None, {"type": "DIVIDEND"},  # unreadable rows are skipped, not fatal
    ])
    assert list(df["Kind"]) == ["Dividend", "Reinvested"] or set(df["Kind"]) == {"Dividend", "Reinvested"}
    assert len(df) == 2
    rei = df[df["Kind"] == "Reinvested"].iloc[0]
    assert rei["Amount"] == 12.5 and rei["Units"] == pytest.approx(0.06)   # reinvestment is stored positive


def test_parse_reads_symbol_in_every_shape_and_from_description():
    rows = [act("DIVIDEND", "2026-01-05", sym="MSFT", symbol_shape=s, id_=s) for s in ("nested", "double", "plain")]
    rows.append(act("DIVIDEND", "2026-01-06", sym=None, desc="DIVIDEND RECEIVED COCA COLA CO (KO)", id_="d"))
    df = dl.parse_activities(rows)
    assert sorted(df["Symbol"]) == ["KO", "MSFT", "MSFT", "MSFT"]


def test_parse_dedupes_and_keeps_reversals_negative():
    rows = [act("DIVIDEND", "2026-05-01", amount=8.0, id_="a"), act("DIVIDEND", "2026-05-01", amount=8.0, id_="a"),
            act("DIVIDEND", "2026-05-03", amount=-8.0, id_="b")]
    df = dl.parse_activities(rows)
    assert len(df) == 2 and df["Amount"].sum() == 0.0


def test_parse_dedupes_rows_without_ids_by_content():
    r = act("DIVIDEND", "2026-05-01", amount=8.0)
    assert len(dl.parse_activities([r, dict(r)])) == 1


def test_parse_amount_falls_back_to_units_times_price_and_handles_empty():
    df = dl.parse_activities([{"type": "REI", "trade_date": "2026-02-02", "units": "2", "price": "50", "symbol": "VOO"}])
    assert df.iloc[0]["Amount"] == 100.0
    assert dl.parse_activities(None).empty and dl.parse_activities([]).empty
    assert list(dl.parse_activities([]).columns) == dl.ACTIVITY_COLS


def test_parse_unlabeled_rows_use_description_conservatively():
    df = dl.parse_activities([
        {"type": "", "trade_date": "2026-03-01", "amount": 5, "description": "DIVIDEND RECEIVED", "symbol": "KO", "id": "1"},
        {"type": "", "trade_date": "2026-03-01", "amount": 5, "description": "REINVESTMENT KO", "symbol": "KO", "id": "2"},
        {"type": "FEE", "trade_date": "2026-03-01", "amount": 5, "description": "DIVIDEND FEE", "symbol": "KO", "id": "3"},
    ])
    assert sorted(df["Kind"]) == ["Dividend", "Reinvested"]    # a typed FEE row is never mistaken for a dividend


# ---------------------------------------------------------------- income
def sample_activity():
    rows = []
    # quarterly AAPL dividends over ~2.3 years: 10 -> 12, plus a monthly VOO-like stream
    for i, d in enumerate(["2024-08-15", "2024-11-14", "2025-02-13", "2025-05-15", "2025-08-14", "2025-11-13",
                           "2026-02-12", "2026-05-14", "2026-08-13"]):
        rows.append(act("DIVIDEND", d, "AAPL", 10.0 if d < "2025-11-01" else 12.0, id_=f"a{i}"))
    rows.append(act("REI", "2026-08-13", "AAPL", -12.0, units=0.06, price=200.0, id_="r1"))
    rows.append(act("DIVIDEND", "2026-09-15", "VOO", 30.0, id_="v1"))
    return dl.parse_activities(rows)


def test_income_summary_windows_and_growth():
    a = sample_activity()
    s = dl.income_summary(a, TODAY)
    # last 365 days (after 2025-11-18): 2026-02-12, 05-14, 08-13 (12 each) + VOO 30
    assert s["ttm"] == pytest.approx(66.0)
    # previous 365 days: 2024-11-18 .. 2025-11-18 -> 2025-02-13 (10) 05-15 (10) 08-14 (10) 11-13 (12)
    assert s["prev_ttm"] == pytest.approx(42.0)
    assert s["growth_pct"] == pytest.approx((66 / 42 - 1) * 100)
    assert s["ytd"] == pytest.approx(66.0)
    assert s["full_year"] and s["n"] == 10 and s["first"] == pd.Timestamp("2024-08-15")


def test_income_summary_is_honest_when_the_feed_is_short():
    a = dl.parse_activities([act("DIVIDEND", "2026-09-01", amount=5.0, id_="x")])
    s = dl.income_summary(a, TODAY)
    assert s["ttm"] == 5.0 and not s["full_year"] and s["prev_ttm"] is None and s["growth_pct"] is None
    e = dl.income_summary(dl.parse_activities([]), TODAY)
    assert e["ttm"] == 0.0 and e["n"] == 0 and e["first"] is None


def test_by_month_fills_zeros_and_ends_this_month():
    m = dl.by_month(sample_activity(), TODAY, months=6)
    assert len(m) == 6 and m["Month"].iloc[-1] == pd.Timestamp("2026-11-01")
    assert dict(zip(m["Month"].dt.strftime("%Y-%m"), m["Amount"]))["2026-09"] == 30.0
    assert m["Amount"].iloc[-1] == 0.0


def test_by_year_and_received_by_symbol():
    a = sample_activity()
    y = dict(zip(dl.by_year(a)["Year"], dl.by_year(a)["Amount"]))
    assert y[2024] == 20.0 and y[2025] == 10 + 10 + 10 + 12 and y[2026] == 36 + 30
    r = dl.received_by_symbol(a, TODAY)
    assert list(r.index) == ["AAPL", "VOO"] and r["AAPL"] == 36.0


def test_reinvestment_rate_per_symbol_and_flag():
    r = dl.reinvestment(sample_activity())
    assert r["has_rei"] and r["reinvested"] == 12.0
    assert r["rate_by_symbol"]["AAPL"] == pytest.approx(12 / 98)
    assert r["rate_by_symbol"]["VOO"] == 0.0
    assert r["units_by_symbol"]["AAPL"] == pytest.approx(0.06)
    none = dl.reinvestment(dl.parse_activities([act("DIVIDEND", "2026-09-01", amount=5.0, id_="x")]))
    assert not none["has_rei"] and none["rate"] == 0.0
    assert dl.reinvestment(dl.parse_activities([]))["rate"] is None


# ---------------------------------------------------------------- history cleaning / profiles
def test_clean_history_handles_junk_and_tz():
    s = pd.Series([0.5, np.nan, -1, 0.5, 0.0], index=pd.DatetimeIndex(
        ["2025-01-02", "2025-02-02", "2025-03-02", "2025-01-02", "2025-04-02"], tz="America/New_York"))
    c = dl.clean_history(s)
    assert list(c.values) == [0.5] and c.index.tz is None
    assert dl.clean_history(None).empty and dl.clean_history(pd.Series(dtype=float)).empty


def test_profile_quarterly_payer_rate_next_date_and_growth():
    h = quarterly("2020-02-10", n=27, amount=0.25, grow=0.10)   # raises each year; last payment 2026-08-10
    p = dl.dividend_profile(h, TODAY)
    assert p["active"] and p["freq"] == 4 and p["freq_name"] == "Quarterly"
    assert p["last_ex"] == pd.Timestamp("2026-08-10")
    assert p["next_ex"] == pd.Timestamp("2026-11-10") or p["next_ex"] == pd.Timestamp("2027-02-10")
    assert p["next_ex"] > TODAY
    assert p["annual_rate"] == pytest.approx(p["last_amount"] * 4)
    assert p["cagr"] == pytest.approx(10.0, abs=0.5) and p["cagr_years"] >= 4
    assert p["streak"] >= 4


def test_profile_monthly_semiannual_annual_frequency():
    for step, name in ((1, "Monthly"), (6, "Semi-annual"), (12, "Annual")):
        h = quarterly("2022-01-05", n=200 // step, amount=1.0, step=step)
        h = h[h.index <= TODAY]
        p = dl.dividend_profile(h, TODAY)
        assert p["freq_name"] == name, (step, p)
        assert p["annual_rate"] == pytest.approx(12 / step)


def test_profile_inactive_when_payments_stopped_or_missing():
    old = quarterly("2018-01-10", n=12)
    p = dl.dividend_profile(old, TODAY)
    assert not p["active"] and "stopped" in p["reason"]
    assert dl.dividend_profile(None, TODAY)["reason"] == "no dividend history"
    assert dl.dividend_profile(pd.Series(dtype=float), TODAY)["active"] is False
    assert dl.status_of(dl.dividend_profile(None, TODAY)) == "No dividend"
    assert dl.status_of(p) == "Stopped" and dl.status_of(None) == "No data"


def test_profile_ignores_a_special_dividend_in_the_forward_rate():
    h = quarterly("2024-02-10", n=11, amount=0.50)       # last payment 2026-08-10
    h.iloc[-2] = 5.0                       # a one-off special
    h = h[h.index <= TODAY]
    p = dl.dividend_profile(h, TODAY)
    assert p["special"] and p["annual_rate"] == pytest.approx(0.50 * 4)
    assert p["ttm"] > 2.0                    # but trailing income still counts the cash that really arrived


def test_profile_variable_payer_uses_average_not_last_payment():
    vals = [1.0, 1.4, 0.8, 1.6, 1.0, 1.4, 0.8, 1.6]          # an ETF-like wobble
    idx = pd.DatetimeIndex([pd.Timestamp("2024-12-20") + pd.DateOffset(months=3 * i) for i in range(8)])
    p = dl.dividend_profile(pd.Series(vals, index=idx)[lambda s: s.index <= TODAY], TODAY)
    assert p["varies"]
    assert p["annual_rate"] == pytest.approx(np.mean(vals[len(vals) - 1 - 3:][:4]) * 4, rel=0.5)
    last4 = pd.Series(vals, index=idx)[lambda s: s.index <= TODAY].iloc[-4:]
    assert p["annual_rate"] == pytest.approx(last4.mean() * 4)


def test_profile_irregular_schedule_is_flagged_not_projected():
    idx = pd.DatetimeIndex(["2025-01-10", "2025-03-01", "2025-07-14", "2026-01-30", "2026-06-14", "2026-09-22"])
    p = dl.dividend_profile(pd.Series([1.0] * 6, index=idx), TODAY)    # gaps 50/135/200/135/100 days: no regular rhythm
    assert p["active"] and p["freq"] is None and "irregular" in p["reason"]
    assert dl.project_payments({"X": 10}, {"X": p}, TODAY).empty
    assert dl.status_of(p) == "Irregular"


def test_growth_requires_enough_complete_years_and_breaks_streak_on_a_cut():
    h = quarterly("2022-02-10", n=10, amount=1.0)            # only ~2 complete years
    assert dl.dividend_profile(h, TODAY)["cagr"] is None
    amounts = [1.0] * 4 + [1.1] * 4 + [1.2] * 4 + [1.0] * 4 + [1.0] * 4   # 2019..2023 then a cut in 2022-ish
    idx = pd.DatetimeIndex([pd.Timestamp("2021-02-10") + pd.DateOffset(months=3 * i) for i in range(20)])
    p = dl.dividend_profile(pd.Series(amounts, index=idx)[lambda s: s.index <= TODAY], TODAY)
    assert p["streak"] == 0                                   # most recent year is flat/lower, so the streak is broken


# ---------------------------------------------------------------- pay lag + projection
def test_pay_lags_learned_from_received_rows_with_default_fallback():
    h = {"AAPL": pd.Series([0.25] * 3, index=pd.DatetimeIndex(["2026-02-09", "2026-05-11", "2026-08-10"]))}
    rec = dl.parse_activities([act("DIVIDEND", "2026-02-12", id_="1"), act("DIVIDEND", "2026-05-14", id_="2"),
                               act("DIVIDEND", "2026-08-13", id_="3"), act("DIVIDEND", "2026-08-13", sym="KO", id_="4")])
    lags = dl.pay_lags(dl.cash_dividends(rec), h)
    assert lags["AAPL"] == 3 and lags["__default__"] == 3 and "KO" not in lags
    assert dl.pay_lags(pd.DataFrame(), {})["__default__"] == dl.DEFAULT_PAY_LAG_DAYS


def test_project_payments_schedule_amounts_and_window():
    h = quarterly("2020-02-10", n=27, amount=0.40)           # last ex 2026-08-10
    p = dl.dividend_profile(h, TODAY)
    proj = dl.project_payments({"AAPL": 50.0}, {"AAPL": p}, TODAY, months=12, lags={"AAPL": 10})
    assert len(proj) == 4
    assert proj["Amount"].tolist() == pytest.approx([20.0] * 4)
    assert proj["PayDate"].min() > TODAY and proj["PayDate"].max() <= TODAY + pd.DateOffset(months=12)
    assert proj["PayDate"].is_monotonic_increasing
    assert (proj["PayDate"] - proj["ExDate"]).dt.days.unique().tolist() == [10]


def test_project_includes_a_dividend_that_went_ex_but_has_not_been_paid_yet():
    idx = pd.DatetimeIndex([pd.Timestamp("2024-11-12") + pd.DateOffset(months=3 * i) for i in range(9)])
    p = dl.dividend_profile(pd.Series(0.4, index=idx), TODAY)
    assert p["last_ex"] == pd.Timestamp("2026-11-12")                       # went ex six days ago
    proj = dl.project_payments({"X": 10.0}, {"X": p}, TODAY, lags={"__default__": 14})
    assert proj.iloc[0]["ExDate"] == pd.Timestamp("2026-11-12") and proj.iloc[0]["PayDate"] == pd.Timestamp("2026-11-26")


def test_project_skips_inactive_unheld_and_zero_share_tickers():
    h = quarterly("2020-02-10", n=27)
    p = dl.dividend_profile(h, TODAY)
    out = dl.project_payments({"A": 0.0, "B": 5.0, "C": 5.0}, {"A": p, "C": dl.dividend_profile(None, TODAY)}, TODAY)
    assert out.empty


def test_projected_by_month_pivots_and_fills():
    h = quarterly("2020-02-10", n=27, amount=0.40)
    p = dl.dividend_profile(h, TODAY)
    proj = dl.project_payments({"AAPL": 10.0, "KO": 5.0}, {"AAPL": p, "KO": p}, TODAY)
    pv = dl.projected_by_month(proj, TODAY, months=12)
    assert len(pv) == 13 and set(pv.columns) == {"AAPL", "KO"}
    assert pv["AAPL"].sum() == pytest.approx(16.0) and pv["KO"].sum() == pytest.approx(8.0)
    assert dl.projected_by_month(dl.project_payments({}, {}, TODAY), TODAY).empty


# ---------------------------------------------------------------- company table
def merged_df():
    return pd.DataFrame([
        {"Symbol": "VOO", "Description": "Vanguard S&P 500", "Class": "ETF", "Units": 10.0, "Market value": 5000.0,
         "Cost basis": 4000.0, "Gain": 1000.0, "Weight %": 50.0},
        {"Symbol": "AAPL", "Description": "Apple", "Class": "Stock", "Units": 20.0, "Market value": 4000.0,
         "Cost basis": 2000.0, "Gain": 2000.0, "Weight %": 40.0},
        {"Symbol": "TSLA", "Description": "Tesla", "Class": "Stock", "Units": 2.0, "Market value": 1000.0,
         "Cost basis": None, "Gain": None, "Weight %": 10.0},
    ])


def profiles_for_table():
    return {
        "VOO": dl.dividend_profile(quarterly("2020-03-25", n=27, amount=1.80), TODAY),
        "AAPL": dl.dividend_profile(quarterly("2020-02-10", n=27, amount=0.25, grow=0.05), TODAY),
        "TSLA": dl.dividend_profile(None, TODAY),
    }


def test_company_table_income_yield_and_shares():
    pr = profiles_for_table()
    rec = pd.Series({"AAPL": 20.0, "XOM": 33.0})
    t = dl.company_table(merged_df(), rec, pr)
    row = t.set_index("Symbol")
    assert row.loc["VOO", "Annual income"] == pytest.approx(pr["VOO"]["annual_rate"] * 10)
    assert row.loc["AAPL", "Yield %"] == pytest.approx(row.loc["AAPL", "Annual income"] / 4000 * 100)
    assert row.loc["AAPL", "Yield on cost %"] == pytest.approx(row.loc["AAPL", "Annual income"] / 2000 * 100)
    assert pd.isna(row.loc["TSLA", "Yield on cost %"]) and row.loc["TSLA", "Status"] == "No dividend"
    assert row.loc["XOM", "Status"] == "Sold" and not row.loc["XOM", "Held"] and row.loc["XOM", "Received 12m"] == 33.0
    assert row["Income share %"].sum() == pytest.approx(100.0)
    assert row.loc["VOO", "Share of invested %"] == pytest.approx(50.0)
    assert list(t["Symbol"])[0] in ("VOO", "AAPL")                      # biggest income first


def test_portfolio_income_headlines_and_concentration():
    t = dl.company_table(merged_df(), pd.Series(dtype=float), profiles_for_table())
    p = dl.portfolio_income(t)
    voo, aapl = t.set_index("Symbol").loc["VOO", "Annual income"], t.set_index("Symbol").loc["AAPL", "Annual income"]
    assert p["annual"] == pytest.approx(voo + aapl) and p["monthly"] == pytest.approx(p["annual"] / 12)
    assert p["payers"] == 2 and p["holdings"] == 3
    assert p["yield_pct"] == pytest.approx(p["annual"] / 10000 * 100)
    assert p["top"] in ("VOO", "AAPL") and 50 <= p["top_share"] <= 100
    assert 1.0 <= p["effective_sources"] <= 2.0
    assert dl.portfolio_income(pd.DataFrame())["annual"] == 0.0


def test_portfolio_income_with_no_payers_is_safe():
    pr = {k: dl.dividend_profile(None, TODAY) for k in ("VOO", "AAPL", "TSLA")}
    p = dl.portfolio_income(dl.company_table(merged_df(), pd.Series(dtype=float), pr))
    assert p["annual"] == 0.0 and p["top"] is None and p["payers"] == 0


# ---------------------------------------------------------------- DRIP replay
def flat_prices(n_years=6, price=100.0):
    idx = pd.bdate_range("2019-01-02", periods=int(n_years * 261))
    return pd.Series(price, index=idx)


def test_drip_on_flat_price_matches_hand_calculation():
    prices = flat_prices(5, 100.0)
    ex = pd.DatetimeIndex([pd.Timestamp("2019-04-01") + pd.DateOffset(months=3 * i) for i in range(16)])
    divs = pd.Series(1.0, index=ex)                             # 4% a year on a flat $100 stock
    sim = dl.simulate_drip(prices, divs, years=None, start_value=10_000, pay_lag_days=5)
    n = int((divs.index <= sim["end"]).sum())
    # price never moves, so the cash route is 10,000 + 100 shares x $1 x n payments
    assert sim["cash_end"] == pytest.approx(10_000 + 100 * n)
    # reinvesting at $100 a share compounds: shares x (1 + 1/100) each quarter
    assert sim["drip_end"] == pytest.approx(100 * 1.01**n * 100, rel=1e-6)
    assert sim["advantage"] > 0 and sim["price_end"] == pytest.approx(10_000)
    assert sim["parts"]["price"] == pytest.approx(0) and sim["parts"]["dividends"] == pytest.approx(100 * n)
    assert sum(sim["parts"].values()) == pytest.approx(sim["drip_end"] - 10_000)
    assert sim["start_yield_pct"] == pytest.approx(4.0)


def test_drip_first_dividend_uses_original_shares_and_second_uses_the_extra_ones():
    prices = flat_prices(2, 50.0)
    divs = pd.Series([2.0, 2.0], index=pd.DatetimeIndex(["2019-03-01", "2019-06-03"]))
    sim = dl.simulate_drip(prices, divs, years=None, start_value=5000, pay_lag_days=3)
    s0 = 5000 / 50                                               # 100 shares
    s1 = s0 + s0 * 2 / 50                                        # 104
    s2 = s1 + s1 * 2 / 50                                        # 108.16
    assert sim["drip_end"] == pytest.approx(s2 * 50)


def test_drip_advantage_grows_with_time_and_yield():
    prices = flat_prices(12, 100.0)
    def run(amount, years):
        ex = pd.DatetimeIndex([pd.Timestamp("2019-04-01") + pd.DateOffset(months=3 * i) for i in range(48)])
        return dl.simulate_drip(prices, pd.Series(amount, index=ex), years=years, pay_lag_days=5)
    assert run(1.0, 10)["advantage"] > run(1.0, 5)["advantage"] > 0
    assert run(2.0, 10)["advantage"] > run(1.0, 10)["advantage"]


def test_cash_interest_narrows_the_drip_gap():
    prices = flat_prices(8, 100.0)
    ex = pd.DatetimeIndex([pd.Timestamp("2019-04-01") + pd.DateOffset(months=3 * i) for i in range(32)])
    divs = pd.Series(1.0, index=ex)
    plain = dl.simulate_drip(prices, divs, years=None, cash_apy=0.0)
    paid = dl.simulate_drip(prices, divs, years=None, cash_apy=0.04)
    assert paid["cash_end"] > plain["cash_end"] and paid["advantage"] < plain["advantage"]
    assert paid["drip_end"] == pytest.approx(plain["drip_end"])


def test_drip_returns_none_without_enough_data_or_dividends():
    prices = flat_prices(3)
    assert dl.simulate_drip(prices, pd.Series(dtype=float)) is None
    assert dl.simulate_drip(prices.iloc[:10], pd.Series([1.0], index=[prices.index[3]])) is None
    assert dl.simulate_drip(prices, pd.Series([1.0], index=[pd.Timestamp("2010-01-04")]), years=None) is None  # outside window


def test_drip_window_is_the_last_n_years():
    prices = flat_prices(12)
    ex = pd.DatetimeIndex([pd.Timestamp("2019-04-01") + pd.DateOffset(months=3 * i) for i in range(48)])
    sim = dl.simulate_drip(prices, pd.Series(1.0, index=ex), years=5)
    assert 4.9 < sim["years"] < 5.1


def test_project_growth_hand_checked_and_assumption_sensitivity():
    g = dl.project_growth(10_000, yield_pct=4, price_growth_pct=0, div_growth_pct=0, years=3)
    assert g["Year"].tolist() == [0, 1, 2, 3]
    assert g["DRIP"].tolist() == pytest.approx([10_000, 10_400, 10_816, 11_248.64])
    assert g["Cash"].tolist() == pytest.approx([10_000, 10_400, 10_800, 11_200])
    assert g["Price only"].tolist() == pytest.approx([10_000] * 4)
    hi = dl.project_growth(10_000, 4, 6, 5, 20)
    lo = dl.project_growth(10_000, 4, 6, 5, 10)
    assert hi["DRIP"].iloc[10] == pytest.approx(lo["DRIP"].iloc[-1]) and hi["DRIP"].iloc[-1] > hi["Cash"].iloc[-1]
    assert (dl.project_growth(10_000, 0, 5, 0, 10)["DRIP"] == dl.project_growth(10_000, 0, 5, 0, 10)["Price only"]).all()


def test_recent_payments_flags_reinvested_ones():
    r = dl.recent_payments(sample_activity(), n=5)
    assert list(r.columns) == ["Date", "Symbol", "Amount", "Reinvested"] and len(r) == 5
    flags = dict(zip(zip(r["Symbol"], r["Date"].dt.strftime("%Y-%m-%d")), r["Reinvested"]))
    assert flags[("AAPL", "2026-08-13")] is True and flags[("VOO", "2026-09-15")] is False
    assert dl.recent_payments(dl.parse_activities([]), 5).empty
