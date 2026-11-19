"""
Dividend analysis. Pure logic: no Streamlit, no network, fully testable.

Three jobs:
  1. What you RECEIVED   - parse SnapTrade account activity (DIVIDEND / REI rows) into a clean table.
  2. What to EXPECT      - per-share dividend history -> payment schedule -> projected income.
                           Projections assume today's per-share amount and no raises; they are
                           estimates, never promises.
  3. DRIP efficiency     - replay real price + dividend history with and without reinvesting,
                           and a clearly hypothetical forward what-if.
"""

from __future__ import annotations

import re
from typing import Any

import numpy as np
import pandas as pd

import holdings_lib as hl

FREQ_NAMES = {12: "Monthly", 4: "Quarterly", 2: "Semi-annual", 1: "Annual"}
FREQ_DAYS = {12: 30.4, 4: 91.3, 2: 182.6, 1: 365.0}
DEFAULT_PAY_LAG_DAYS = 14
ACTIVITY_COLS = ["Date", "Symbol", "Kind", "Amount", "Units", "Price", "Account", "Id"]
KIND_BY_TYPE = {"DIVIDEND": "Dividend", "REI": "Reinvested", "STOCK_DIVIDEND": "Stock dividend"}


def to_day(x: Any) -> pd.Timestamp:
    ts = pd.Timestamp(x)
    if ts.tzinfo is not None:
        ts = ts.tz_convert(None)
    return ts.normalize()


# --------------------------------------------------------------------------
# 1. What you received (SnapTrade activity)
# --------------------------------------------------------------------------
def _symbol_of(a: dict) -> str | None:
    s: Any = a.get("symbol")
    for _ in range(3):  # {'symbol': {'symbol': 'AAPL', ...}} or {'symbol': 'AAPL'}
        if isinstance(s, dict):
            s = s.get("symbol") or s.get("raw_symbol")
        else:
            break
    if isinstance(s, str) and s.strip():
        return s.strip().upper()
    m = re.search(r"\(([A-Z][A-Z0-9.\-]{0,5})\)", str(a.get("description") or ""))
    return m.group(1) if m else None


def _type_code(a: dict) -> str:
    t = a.get("type")
    if isinstance(t, dict):
        t = t.get("code") or t.get("type")
    return str(t or "").strip().upper()


def _kind_of(a: dict) -> str | None:
    code = _type_code(a)
    if code in KIND_BY_TYPE:
        return KIND_BY_TYPE[code]
    if code in ("", "OTHER"):  # unlabeled rows: fall back to the description, conservatively
        desc = str(a.get("description") or "").upper()
        if "REINVEST" in desc:
            return "Reinvested"
        if "DIVIDEND" in desc:
            return "Dividend"
    return None


def parse_activities(items: list[dict] | None) -> pd.DataFrame:
    """Dividend-related rows only, one row each. Cash dividends keep their sign (a reversal is
    negative); reinvestments are positive amounts. Unreadable rows are skipped, never fatal."""
    rows = []
    for a in items or []:
        if not isinstance(a, dict):
            continue
        kind = _kind_of(a)
        if kind is None:
            continue
        date = pd.to_datetime(a.get("trade_date") or a.get("settlement_date"), errors="coerce", utc=True)
        if pd.isna(date):
            continue
        units, price, amount = hl.num(a.get("units")), hl.num(a.get("price")), hl.num(a.get("amount"))
        if amount is None and units is not None and price is not None:
            amount = units * price
        if amount is None:
            continue
        if kind == "Reinvested":
            amount = abs(amount)
            units = abs(units) if units is not None else None
        day = to_day(date)
        sym = _symbol_of(a) or "?"
        acct = a.get("_account") or ""
        uid = a.get("id") or f"{day.date()}|{sym}|{kind}|{round(amount, 4)}|{acct}"
        rows.append({"Date": day, "Symbol": sym, "Kind": kind, "Amount": float(amount), "Units": units,
                     "Price": price, "Account": acct, "Id": str(uid)})
    df = pd.DataFrame(rows, columns=ACTIVITY_COLS)
    if df.empty:
        return df
    df = df.drop_duplicates(subset=["Id"]).sort_values("Date", ascending=False).reset_index(drop=True)
    return df


def cash_dividends(act: pd.DataFrame) -> pd.DataFrame:
    return act[act["Kind"] == "Dividend"] if not act.empty else act


def income_summary(act: pd.DataFrame, today: Any) -> dict:
    """Totals from the cash-dividend rows. `covered_days` says how much history the feed really had,
    so a short feed is never presented as a full year."""
    today = to_day(today)
    d = cash_dividends(act)
    out = {"ttm": 0.0, "prev_ttm": None, "ytd": 0.0, "n": 0, "first": None, "last": None,
           "covered_days": 0, "full_year": False, "growth_pct": None}
    if act.empty:
        return out
    out["first"] = act["Date"].min()
    out["covered_days"] = int((today - out["first"]).days)
    out["full_year"] = out["covered_days"] >= 365
    if d.empty:
        return out
    out["n"] = int(len(d))
    out["last"] = d["Date"].max()
    ttm_mask = (d["Date"] > today - pd.Timedelta(days=365)) & (d["Date"] <= today)
    out["ttm"] = float(d.loc[ttm_mask, "Amount"].sum())
    out["ytd"] = float(d.loc[(d["Date"] >= pd.Timestamp(today.year, 1, 1)) & (d["Date"] <= today), "Amount"].sum())
    if out["covered_days"] >= 730:
        prev = (d["Date"] > today - pd.Timedelta(days=730)) & (d["Date"] <= today - pd.Timedelta(days=365))
        out["prev_ttm"] = float(d.loc[prev, "Amount"].sum())
        if out["prev_ttm"] > 0:
            out["growth_pct"] = (out["ttm"] / out["prev_ttm"] - 1) * 100
    return out


def by_month(act: pd.DataFrame, today: Any, months: int = 24) -> pd.DataFrame:
    """Cash dividends per calendar month for the last `months` months (zeros filled in)."""
    today = to_day(today)
    idx = pd.period_range(end=today.to_period("M"), periods=months, freq="M")
    d = cash_dividends(act)
    s = pd.Series(0.0, index=idx)
    if not d.empty:
        g = d.groupby(d["Date"].dt.to_period("M"))["Amount"].sum()
        for p, v in g.items():
            if p in s.index:
                s[p] = float(v)
    return pd.DataFrame({"Month": [p.to_timestamp() for p in s.index], "Amount": s.values})


def by_year(act: pd.DataFrame) -> pd.DataFrame:
    d = cash_dividends(act)
    if d.empty:
        return pd.DataFrame({"Year": [], "Amount": []})
    g = d.groupby(d["Date"].dt.year)["Amount"].sum().sort_index()
    return pd.DataFrame({"Year": g.index.astype(int), "Amount": g.values})


def received_by_symbol(act: pd.DataFrame, today: Any, days: int = 365) -> pd.Series:
    today = to_day(today)
    d = cash_dividends(act)
    if d.empty:
        return pd.Series(dtype=float)
    d = d[(d["Date"] > today - pd.Timedelta(days=days)) & (d["Date"] <= today)]
    return d.groupby("Symbol")["Amount"].sum().sort_values(ascending=False)


def recent_payments(act: pd.DataFrame, n: int = 15) -> pd.DataFrame:
    """Latest cash dividends, each flagged if a reinvestment of that ticker followed within a week."""
    cols = ["Date", "Symbol", "Amount", "Reinvested"]
    d = cash_dividends(act).head(n)
    if d.empty:
        return pd.DataFrame(columns=cols)
    rei = act[act["Kind"] == "Reinvested"]
    rows = []
    for _, r in d.iterrows():
        m = rei[(rei["Symbol"] == r["Symbol"]) & (rei["Date"] >= r["Date"] - pd.Timedelta(days=1))
                & (rei["Date"] <= r["Date"] + pd.Timedelta(days=7))]
        rows.append({"Date": r["Date"], "Symbol": r["Symbol"], "Amount": r["Amount"], "Reinvested": bool(len(m))})
    return pd.DataFrame(rows, columns=cols)


def reinvestment(act: pd.DataFrame) -> dict:
    """How much of the cash dividends was put back to work (from the REI rows), per ticker and overall."""
    d = cash_dividends(act)
    r = act[act["Kind"] == "Reinvested"] if not act.empty else act
    cash = float(d["Amount"].sum()) if not d.empty else 0.0
    rei = float(r["Amount"].sum()) if not r.empty else 0.0
    cash_by = d.groupby("Symbol")["Amount"].sum() if not d.empty else pd.Series(dtype=float)
    rei_by = r.groupby("Symbol")["Amount"].sum() if not r.empty else pd.Series(dtype=float)
    units_by = r.groupby("Symbol")["Units"].sum() if not r.empty else pd.Series(dtype=float)
    rate_by = {}
    for sym, c in cash_by.items():
        if c > 0:
            rate_by[sym] = min(float(rei_by.get(sym, 0.0)) / float(c), 1.0)
    return {
        "has_rei": not r.empty,
        "cash": cash, "reinvested": rei,
        "rate": (min(rei / cash, 1.0) if cash > 0 else None),
        "rate_by_symbol": rate_by,
        "units_by_symbol": {k: float(v) for k, v in units_by.items() if pd.notna(v)},
    }


# --------------------------------------------------------------------------
# 2. What to expect (per-share history -> schedule -> projection)
# --------------------------------------------------------------------------
def clean_history(s: pd.Series | None) -> pd.Series:
    """Per-share dividends by ex-date: floats > 0, tz-naive dates, sorted, one row per date."""
    if s is None or len(s) == 0:
        return pd.Series(dtype=float, index=pd.DatetimeIndex([]))
    out = pd.Series(pd.to_numeric(s.values, errors="coerce"), index=pd.DatetimeIndex(s.index))
    if out.index.tz is not None:
        out.index = out.index.tz_convert(None)
    out.index = out.index.normalize()
    out = out[out.notna() & (out > 0)]
    out = out[~out.index.duplicated(keep="last")]
    return out.sort_index().astype(float)


def strip_specials(s: pd.Series) -> tuple[pd.Series, pd.Series]:
    """Split (regular, special): a payment over 2.5x the median of the previous 8 is a one-off."""
    if len(s) < 5:
        return s, s.iloc[0:0]
    flags = []
    vals = s.values
    for i, v in enumerate(vals):
        prior = vals[max(0, i - 8):i]
        flags.append(len(prior) >= 4 and v > 2.5 * float(np.median(prior)))
    mask = pd.Series(flags, index=s.index)
    return s[~mask], s[mask]


def _frequency(gap_days: float) -> int | None:
    best, err = None, 1.0
    for f, days in FREQ_DAYS.items():
        e = abs(gap_days - days) / days
        if e < err:
            best, err = f, e
    return best if err <= 0.25 else None


def dividend_profile(hist: pd.Series | None, today: Any) -> dict:
    """Schedule and rate for one ticker, from its own payment history."""
    today = to_day(today)
    s = clean_history(hist)
    p: dict = {"active": False, "reason": None, "freq": None, "freq_name": None, "last_ex": None,
               "last_amount": None, "ttm": 0.0, "annual_rate": None, "varies": False, "special": False,
               "next_ex": None, "cagr": None, "cagr_years": 0, "streak": 0, "n_payments": int(len(s)),
               "first_ex": None}
    if s.empty:
        p["reason"] = "no dividend history"
        return p
    s = s[s.index <= today]
    if s.empty:
        p["reason"] = "no dividend history"
        return p
    p["first_ex"], p["last_ex"] = s.index[0], s.index[-1]
    reg, special = strip_specials(s)
    p["special"] = bool(len(special[special.index > today - pd.Timedelta(days=365)]))
    p["ttm"] = float(s[s.index > today - pd.Timedelta(days=365)].sum())

    gaps = np.diff(reg.index.values[-9:]).astype("timedelta64[D]").astype(float) if len(reg) >= 2 else np.array([])
    median_gap = float(np.median(gaps)) if len(gaps) else None
    freq = _frequency(median_gap) if median_gap else None
    p["freq"], p["freq_name"] = freq, FREQ_NAMES.get(freq)

    limit = 1.5 * (365 / freq) + 45 if freq else 400
    if (today - p["last_ex"]).days > limit:
        p["reason"] = "payments appear to have stopped"
        return p
    p["active"] = True
    p["last_amount"] = float(reg.iloc[-1]) if len(reg) else float(s.iloc[-1])
    if freq:
        recent = reg.iloc[-min(freq, len(reg)):]
        cv = float(recent.std(ddof=0) / recent.mean()) if len(recent) >= 2 and recent.mean() > 0 else 0.0
        p["varies"] = cv > 0.15
        per = float(recent.mean()) if p["varies"] else p["last_amount"]
        p["annual_rate"] = per * freq
        step = 12 // freq
        nxt = p["last_ex"]
        for _ in range(60):
            if nxt > today:
                break
            nxt = nxt + pd.DateOffset(months=step)
        p["next_ex"] = nxt
    else:
        p["annual_rate"] = float(reg[reg.index > today - pd.Timedelta(days=365)].sum()) or None
        p["reason"] = "irregular schedule (not projected)"
    _growth(p, reg, today)
    return p


def _growth(p: dict, reg: pd.Series, today: pd.Timestamp) -> None:
    """Dividend growth from complete calendar years that have the usual number of payments."""
    by = reg[reg.index.year < today.year].groupby(reg[reg.index.year < today.year].index.year).agg(["sum", "count"])
    if len(by) < 3:
        return
    mode_count = int(by["count"].tail(5).mode().iloc[0])
    years = []
    for y in sorted(by.index, reverse=True):
        if int(by.loc[y, "count"]) != mode_count:
            break
        years.append(y)
        if len(years) == 6:
            break
    years = years[::-1]
    if len(years) < 3:
        return
    tot = [float(by.loc[y, "sum"]) for y in years]
    if tot[0] > 0 and tot[-1] > 0:
        p["cagr"] = ((tot[-1] / tot[0]) ** (1 / (len(tot) - 1)) - 1) * 100
        p["cagr_years"] = len(tot) - 1
    streak = 0
    for a, b in zip(tot[-2::-1], tot[::-1]):
        if b > a * 1.0001:
            streak += 1
        else:
            break
    p["streak"] = streak


def pay_lags(received: pd.DataFrame, histories: dict[str, pd.Series]) -> dict:
    """Typical days from ex-dividend date to the day cash lands, learned from your own payments.
    Falls back to two weeks when there is nothing to learn from."""
    per: dict[str, list[int]] = {}
    for _, r in (received if received is not None else pd.DataFrame()).iterrows():
        h = histories.get(r["Symbol"])
        if h is None or len(h) == 0:
            continue
        h = clean_history(h)
        prior = h[h.index <= r["Date"]]
        if prior.empty:
            continue
        lag = int((r["Date"] - prior.index[-1]).days)
        if 0 <= lag <= 60:
            per.setdefault(r["Symbol"], []).append(lag)
    out = {k: int(np.median(v)) for k, v in per.items()}
    allv = [x for v in per.values() for x in v]
    out["__default__"] = int(np.median(allv)) if len(allv) >= 3 else DEFAULT_PAY_LAG_DAYS
    return out


def project_payments(shares: dict[str, float], profiles: dict[str, dict], today: Any, months: int = 12,
                     lags: dict | None = None) -> pd.DataFrame:
    """Expected payments over the next `months`, at today's per-share amount (no raises assumed).
    Includes a dividend whose ex-date just passed but whose cash hasn't arrived yet."""
    today = to_day(today)
    end = today + pd.DateOffset(months=months)
    lags = lags or {}
    rows = []
    for sym, sh in shares.items():
        p = profiles.get(sym)
        if not p or not p.get("active") or not p.get("freq") or not sh or sh <= 0:
            continue
        per_share = p["annual_rate"] / p["freq"]
        lag = int(lags.get(sym, lags.get("__default__", DEFAULT_PAY_LAG_DAYS)))
        step = 12 // p["freq"]
        ex = p["last_ex"]
        for _ in range(200):
            if ex > end:
                break
            pay = ex + pd.Timedelta(days=lag)
            if today < pay <= end:
                rows.append({"Symbol": sym, "ExDate": ex, "PayDate": pay, "PerShare": per_share,
                             "Shares": float(sh), "Amount": per_share * float(sh)})
            ex = ex + pd.DateOffset(months=step)
    df = pd.DataFrame(rows, columns=["Symbol", "ExDate", "PayDate", "PerShare", "Shares", "Amount"])
    return df.sort_values("PayDate").reset_index(drop=True)


def projected_by_month(proj: pd.DataFrame, today: Any, months: int = 12) -> pd.DataFrame:
    """Month x symbol table of expected income (zeros filled in)."""
    today = to_day(today)
    idx = pd.period_range(start=today.to_period("M"), periods=months + 1, freq="M")
    if proj.empty:
        return pd.DataFrame(index=[p.to_timestamp() for p in idx])
    pv = proj.assign(M=proj["PayDate"].dt.to_period("M")).pivot_table(
        index="M", columns="Symbol", values="Amount", aggfunc="sum", fill_value=0.0)
    pv = pv.reindex(idx, fill_value=0.0)
    pv.index = [p.to_timestamp() for p in pv.index]
    return pv


# --------------------------------------------------------------------------
# Company table and portfolio-level numbers
# --------------------------------------------------------------------------
def status_of(p: dict | None, is_etf_or_fund: bool = False) -> str:
    if p is None:
        return "No data"
    if p["active"] and p["freq"]:
        return "Pays"
    if p["active"]:
        return "Irregular"
    if p["reason"] == "no dividend history":
        return "No dividend"
    return "Stopped"


def company_table(merged: pd.DataFrame, received_ttm: pd.Series, profiles: dict[str, dict]) -> pd.DataFrame:
    """One row per ticker you hold (plus tickers that paid you but are no longer held)."""
    rows = []
    total_mv = float(merged["Market value"].sum(skipna=True)) if not merged.empty else 0.0
    held = set()
    for _, r in merged.iterrows():
        sym = r["Symbol"]
        held.add(sym)
        p = profiles.get(sym)
        shares = float(r["Units"]) if pd.notna(r["Units"]) else 0.0
        mv = float(r["Market value"]) if pd.notna(r["Market value"]) else None
        cost = float(r["Cost basis"]) if pd.notna(r["Cost basis"]) else None
        income = (p["annual_rate"] * shares) if (p and p["active"] and p["annual_rate"]) else 0.0
        rows.append({
            "Symbol": sym, "Company": r.get("Description") or sym, "Class": r.get("Class", ""), "Held": True,
            "Shares": shares, "Value": mv,
            "Share of invested %": (mv / total_mv * 100) if (mv is not None and total_mv > 0) else None,
            "Status": status_of(p), "Pays": (p or {}).get("freq_name") or "—",
            "Per payment": ((p["annual_rate"] / p["freq"]) if (p and p["active"] and p["freq"]) else None),
            "Next ex-date": (p or {}).get("next_ex"),
            "Annual income": income,
            "Received 12m": float(received_ttm.get(sym, 0.0)),
            "Yield %": (income / mv * 100) if (mv and income) else None,
            "Yield on cost %": (income / cost * 100) if (cost and income) else None,
            "Growth %": (p or {}).get("cagr"), "Growth years": (p or {}).get("cagr_years", 0),
            "Streak": (p or {}).get("streak", 0), "Varies": bool((p or {}).get("varies")),
            "Special": bool((p or {}).get("special")),
        })
    for sym, v in received_ttm.items():  # paid you in the last year but no longer held
        if sym not in held and sym != "?":
            rows.append({"Symbol": sym, "Company": sym, "Class": "", "Held": False, "Shares": 0.0, "Value": None,
                         "Share of invested %": None, "Status": "Sold", "Pays": "—", "Per payment": None,
                         "Next ex-date": None, "Annual income": 0.0, "Received 12m": float(v), "Yield %": None,
                         "Yield on cost %": None, "Growth %": None, "Growth years": 0, "Streak": 0,
                         "Varies": False, "Special": False})
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    tot = float(df["Annual income"].sum())
    df["Income share %"] = df["Annual income"] / tot * 100 if tot > 0 else 0.0
    return df.sort_values(["Annual income", "Value"], ascending=False, na_position="last").reset_index(drop=True)


def portfolio_income(table: pd.DataFrame) -> dict:
    """Headline numbers for the dividend side of the portfolio."""
    out = {"annual": 0.0, "monthly": 0.0, "yield_pct": None, "yoc_pct": None, "payers": 0, "holdings": 0,
           "top": None, "top_share": None, "top_weight": None, "effective_sources": None, "growth_pct": None}
    h = table[table["Held"]] if not table.empty else table
    if h.empty:
        return out
    out["holdings"] = int(len(h))
    payers = h[h["Annual income"] > 0]
    out["payers"] = int(len(payers))
    out["annual"] = float(payers["Annual income"].sum())
    out["monthly"] = out["annual"] / 12
    mv = float(h["Value"].sum(skipna=True))
    if mv > 0:
        out["yield_pct"] = out["annual"] / mv * 100
    cb = payers.dropna(subset=["Yield on cost %"])
    if not cb.empty:
        cost = float((cb["Annual income"] / cb["Yield on cost %"] * 100).sum())
        out["yoc_pct"] = float(cb["Annual income"].sum()) / cost * 100 if cost > 0 else None
    if out["annual"] > 0:
        top = payers.sort_values("Annual income", ascending=False).iloc[0]
        out["top"], out["top_share"] = top["Symbol"], float(top["Income share %"])
        out["top_weight"] = None if pd.isna(top["Share of invested %"]) else float(top["Share of invested %"])
        sh = (payers["Annual income"] / out["annual"]).values
        out["effective_sources"] = float(1 / np.sum(sh**2))
        g = payers.dropna(subset=["Growth %"])
        if not g.empty and g["Annual income"].sum() > 0:
            out["growth_pct"] = float(np.average(g["Growth %"], weights=g["Annual income"]))
    return out


# --------------------------------------------------------------------------
# 3. DRIP efficiency
# --------------------------------------------------------------------------
def simulate_drip(prices: pd.Series, divs: pd.Series, years: float | None = 10, start_value: float = 10_000.0,
                  pay_lag_days: int = 10, cash_apy: float = 0.0) -> dict | None:
    """Replay real history for one ticker: reinvest every dividend vs. take it as cash.

    `prices` are daily closes that are NOT dividend-adjusted (split-adjusted only), `divs` are
    per-share dividends by ex-date. Reinvestment buys at the first close on/after ex-date + lag.
    Cash earns `cash_apy` (0 by default, a deliberately plain baseline). Returns None when there
    is not enough history or the ticker paid nothing in the window."""
    p = prices.dropna()
    p = p[p > 0]
    if len(p) < 30:
        return None
    p.index = pd.DatetimeIndex(p.index).tz_localize(None) if p.index.tz is not None else pd.DatetimeIndex(p.index)
    end = p.index[-1]
    if years:
        p = p[p.index >= end - pd.DateOffset(years=int(years))]
    if len(p) < 30:
        return None
    d = clean_history(divs)
    d = d[(d.index > p.index[0]) & (d.index <= end)]
    if d.empty:
        return None
    shares0 = start_value / float(p.iloc[0])
    n = len(p)
    px = p.values
    add_drip, add_cash = np.zeros(n), np.zeros(n)
    for ex, per in d.items():  # in date order, so earlier reinvestments are already counted
        j = min(int(p.index.searchsorted(ex)), n - 1)
        held = shares0 + float(add_drip[: j + 1].sum())  # shares owned on the ex-date
        i = min(int(p.index.searchsorted(ex + pd.Timedelta(days=pay_lag_days))), n - 1)
        add_drip[i] += held * per / px[i]
        add_cash[i] += shares0 * per
    shares_curve = shares0 + np.cumsum(add_drip)
    daily = (1 + cash_apy) ** (1 / 365) - 1
    gaps = np.diff(p.index.values).astype("timedelta64[D]").astype(float)
    cash = np.zeros(n)
    cash[0] = add_cash[0]
    for i in range(1, n):
        cash[i] = cash[i - 1] * (1 + daily) ** gaps[i - 1] + add_cash[i]
    drip = pd.Series(shares_curve * px, index=p.index)
    price_only = pd.Series(shares0 * px, index=p.index)
    cashc = pd.Series(shares0 * px + cash, index=p.index)
    yrs = max((p.index[-1] - p.index[0]).days / 365.25, 1e-9)
    cagr = lambda end_v: (end_v / start_value) ** (1 / yrs) - 1  # noqa: E731
    first_year_divs = float(d[d.index <= p.index[0] + pd.Timedelta(days=365)].sum())
    return {
        "symbol": None, "start": p.index[0], "end": end, "years": yrs, "start_value": start_value,
        "drip": drip, "cash": cashc, "price_only": price_only,
        "drip_end": float(drip.iloc[-1]), "cash_end": float(cashc.iloc[-1]), "price_end": float(price_only.iloc[-1]),
        "advantage": float(drip.iloc[-1] - cashc.iloc[-1]),
        "advantage_pct": float(drip.iloc[-1] / cashc.iloc[-1] - 1) * 100,
        "extra_shares_pct": float(shares_curve[-1] / shares0 - 1) * 100,
        "drip_cagr": cagr(float(drip.iloc[-1])) * 100, "cash_cagr": cagr(float(cashc.iloc[-1])) * 100,
        "price_cagr": cagr(float(price_only.iloc[-1])) * 100,
        "dividends_cash": float(add_cash.sum()),
        "n_dividends": int(len(d)), "start_yield_pct": first_year_divs / float(p.iloc[0]) * 100,
        "parts": {
            "price": float(price_only.iloc[-1] - start_value),
            "dividends": float(cashc.iloc[-1] - price_only.iloc[-1]),
            "compounding": float(drip.iloc[-1] - cashc.iloc[-1]),
        },
    }


def project_growth(start_value: float, yield_pct: float, price_growth_pct: float, div_growth_pct: float,
                   years: int, cash_apy_pct: float = 0.0) -> pd.DataFrame:
    """Hypothetical what-if in yearly steps. Dividends are paid at each year-end; the first year's
    dividend is `yield_pct` of the starting price and then grows at `div_growth_pct` a year.
    Nothing here is a forecast; it just shows how the assumptions you pick compound."""
    g, dg, y, r = price_growth_pct / 100, div_growth_pct / 100, yield_pct / 100, cash_apy_pct / 100
    price0 = 1.0
    shares0 = start_value / price0
    shares, cash = shares0, 0.0
    rows = [{"Year": 0, "DRIP": start_value, "Cash": start_value, "Price only": start_value}]
    for t in range(1, int(years) + 1):
        price = price0 * (1 + g) ** t
        dps = y * price0 * (1 + dg) ** (t - 1)
        shares += shares * dps / price
        cash = cash * (1 + r) + shares0 * dps
        rows.append({"Year": t, "DRIP": shares * price, "Cash": shares0 * price + cash, "Price only": shares0 * price})
    return pd.DataFrame(rows)
