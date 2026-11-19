"""
Stock Deep-Dive calculations. Pure functions: no Streamlit, no network.

Three inputs, all optional (every section degrades on its own):
  * Finnhub numbers  (basic financials, quote, analyst ratings)  -> key_numbers(), assess()
  * Yahoo price history (and dividends)                          -> price_stats()
  * the earnings calendar                                        -> assess()

The pros and cons START from the same screen as the dashboard's Stock of the Day (idea_lib.evaluate),
so the two never disagree, then add more signals. Everything is a rule of thumb on past numbers.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

import numpy as np
import pandas as pd

import idea_lib as il
import risk_lib as rl

TD = {"1M": 21, "3M": 63, "6M": 126, "1Y": 252}
EXTRA_ALIASES = {
    "ps": ("psTTM", "psAnnual"),
    "pb": ("pbQuarterly", "pbAnnual"),
    "pfcf": ("pfcfShareTTM", "pfcfShareAnnual"),
    "gross_margin": ("grossMarginTTM", "grossMarginAnnual"),
    "op_margin": ("operatingMarginTTM", "operatingMarginAnnual"),
    "roa": ("roaTTM", "roaRfy"),
    "current_ratio": ("currentRatioQuarterly", "currentRatioAnnual"),
    "interest_cov": ("netInterestCoverageTTM", "netInterestCoverageAnnual"),
    "eps_growth_ttm": ("epsGrowthTTMYoy",),
    "eps_growth_5y": ("epsGrowth5Y",),
    "rev_growth_5y": ("revenueGrowth5Y",),
    "payout": ("payoutRatioTTM", "payoutRatioAnnual"),
    "eps": ("epsTTM", "epsBasicExclExtraItemsTTM"),
    "avg_volume": ("3MonthAverageTradingVolume", "10DayAverageTradingVolume"),
}
ALL_ALIASES = {**il.ALIASES, **EXTRA_ALIASES}


def metric(metrics: dict | None, key: str) -> float | None:
    """First usable number for a logical metric, trying each known Finnhub field name."""
    for name in ALL_ALIASES.get(key, (key,)):
        v = (metrics or {}).get(name)
        if isinstance(v, bool):
            continue
        try:
            if v is not None and np.isfinite(float(v)):
                return float(v)
        except (TypeError, ValueError):
            continue
    return None


# ---------------------------------------------------------------- size and plain facts
def size_bucket(mcap_millions: float | None) -> tuple[str, str] | None:
    """(label, plain meaning) from market value in millions of dollars."""
    if not mcap_millions or mcap_millions <= 0:
        return None
    if mcap_millions >= 200_000:
        return "mega-cap", "one of the largest companies in the market"
    if mcap_millions >= 10_000:
        return "large-cap", "a large, established company"
    if mcap_millions >= 2_000:
        return "mid-cap", "a mid-sized company"
    if mcap_millions >= 300:
        return "small-cap", "a small company, which tends to swing more"
    return "micro-cap", "a very small company, which can be hard to trade and very volatile"


def money_words(mcap_millions: float | None) -> str | None:
    if not mcap_millions or mcap_millions <= 0:
        return None
    if mcap_millions >= 1_000_000:
        return f"about ${mcap_millions / 1_000_000:.1f} trillion"
    if mcap_millions >= 1_000:
        return f"about ${mcap_millions / 1_000:,.0f} billion"
    return f"about ${mcap_millions:,.0f} million"


def is_fund(profile: dict | None, metrics: dict | None) -> bool:
    """Funds and ETFs have no company profile, so company measures don't apply."""
    return not (profile or {}).get("name") and metric(metrics, "pe") is None and metric(metrics, "net_margin") is None


# ---------------------------------------------------------------- key numbers table
# (group, label, key, format, rule, plain meaning). Rules: ("pe", good, watch) ("low", good, watch)
# ("high", good, watch) ("flag", watch) or None for facts without a good/bad direction.
KEYS = [
    ("Valuation", "P/E (trailing 12 months)", "pe", "x", ("pe", 20, 40),
     "What you pay for each dollar of yearly profit. Higher means investors expect more growth."),
    ("Valuation", "Price / sales", "ps", "x", ("low", 2, 8),
     "What you pay for each dollar of yearly revenue. Fair levels vary a lot by industry."),
    ("Valuation", "Price / book", "pb", "x", ("low", 3, 10),
     "Price compared with the accounting value of what the company owns, after debts."),
    ("Valuation", "Price / free cash flow", "pfcf", "x", ("pe", 20, 40),
     "What you pay for each dollar of cash left after running and investing in the business."),
    ("Growth", "Revenue growth, 1 year", "rev_growth", "pct", ("high", 10, 0),
     "How much sales grew versus a year ago."),
    ("Growth", "Revenue growth, 5-year average", "rev_growth_5y", "pct", ("high", 8, 0),
     "Sales growth per year, averaged over five years. Shows whether growth lasts."),
    ("Growth", "Earnings growth, 1 year", "eps_growth_ttm", "pct", ("high", 10, 0),
     "How much profit per share grew versus a year ago."),
    ("Growth", "Earnings growth, 5-year average", "eps_growth_5y", "pct", ("high", 8, 0),
     "Profit-per-share growth per year over five years."),
    ("Profitability", "Gross margin", "gross_margin", "pct", ("high", 40, 20),
     "Share of each sales dollar left after the direct cost of the product. Varies by industry."),
    ("Profitability", "Operating margin", "op_margin", "pct", ("high", 15, 5),
     "Share of each sales dollar left after running costs. A measure of how good the core business is."),
    ("Profitability", "Net profit margin", "net_margin", "pct", ("high", 15, 0),
     "Share of each sales dollar that ends up as profit after everything."),
    ("Profitability", "Return on equity", "roe", "pct", ("high", 15, 0),
     "Profit earned per dollar shareholders have invested. Debt can inflate it."),
    ("Profitability", "Return on assets", "roa", "pct", ("high", 8, 2),
     "Profit earned per dollar of everything the company owns."),
    ("Financial health", "Debt / equity", "debt_equity", "ratio", ("low", 0.5, 2),
     "Borrowed money compared with shareholders' money. Lower means less risk if business slows."),
    ("Financial health", "Current ratio", "current_ratio", "ratio", ("high", 1.5, 1),
     "Short-term assets compared with bills due within a year. Below 1 can mean a cash squeeze."),
    ("Financial health", "Interest coverage", "interest_cov", "x", ("high", 8, 3),
     "How many times over profit covers interest payments. Higher is safer."),
    ("Dividend", "Dividend yield", "div_yield", "pct", None,
     "Yearly dividend as a share of the price. Not guaranteed, and it can be cut."),
    ("Dividend", "Payout ratio", "payout", "pct", ("low", 60, 90),
     "Share of profit paid out as dividends. Very high leaves little room if profit dips."),
    ("Trading", "Beta", "beta", "ratio", ("flag", 1.5),
     "How much it tends to move compared with the market. 1.0 moves with it; 1.5 swings about half again as much."),
    ("Trading", "Average daily volume (3 months)", "avg_volume", "mshares", None,
     "Shares traded per day, in millions. Higher volume usually means it is easier to buy and sell."),
]
READS = {"good": "Good", "ok": "OK", "watch": "Watch"}


def grade(rule: tuple | None, v: float | None) -> str | None:
    if rule is None or v is None:
        return None
    kind = rule[0]
    if kind == "pe":
        return "watch" if v <= 0 or v > rule[2] else "good" if v <= rule[1] else "ok"
    if kind == "low":
        return "good" if v <= rule[1] else "watch" if v >= rule[2] else "ok"
    if kind == "high":
        return "good" if v >= rule[1] else "watch" if v < rule[2] else "ok"
    if kind == "flag":
        return "watch" if v >= rule[1] else "ok"
    return None


def fmt(kind: str, v: float | None) -> str:
    if v is None:
        return "n/a"
    return {"x": f"{v:.1f}×", "pct": f"{v:.1f}%", "ratio": f"{v:.2f}", "mshares": f"{v:,.1f}M"}.get(kind, f"{v:.2f}")


def key_numbers(metrics: dict | None) -> list[dict]:
    """Every measure with a value, plus its group, a plain-English meaning and a Good/OK/Watch read."""
    rows = []
    for group, label, key, kind, rule, meaning in KEYS:
        v = metric(metrics, key)
        if v is None:
            continue
        g = grade(rule, v)
        rows.append({"group": group, "label": label, "key": key, "value": v, "shown": fmt(kind, v), "grade": g,
                     "read": READS.get(g, ""), "meaning": meaning})
    return rows


# ---------------------------------------------------------------- price history
def _clean(s: pd.Series | None) -> pd.Series:
    if s is None or len(s) == 0:
        return pd.Series(dtype=float)
    s = pd.to_numeric(pd.Series(s), errors="coerce").dropna()
    s = s[s > 0]
    s = s[~s.index.duplicated(keep="last")].sort_index()
    s.index = pd.DatetimeIndex(s.index)
    return s


def equity_curve(prices: pd.Series | None, divs: pd.Series | None = None, years: float | None = None) -> pd.Series:
    """Growth of 1.0 with dividends reinvested, optionally over the last `years` only."""
    p = _clean(prices)
    if len(p) < 2:
        return pd.Series(dtype=float)
    eq = (1 + rl.total_returns(p, divs)).cumprod()
    if years:
        eq = eq[eq.index >= eq.index[-1] - pd.Timedelta(days=int(years * 365.25))]
        if len(eq):
            eq = eq / eq.iloc[0]
    return eq


def _window(eq: pd.Series, n: int) -> float | None:
    return float(eq.iloc[-1] / eq.iloc[-1 - n] - 1) if len(eq) > n else None


def _annualized(eq: pd.Series, years: int) -> float | None:
    n = int(years * 252)
    if len(eq) <= n:
        return None
    return float((eq.iloc[-1] / eq.iloc[-1 - n]) ** (1 / years) - 1)


def price_stats(prices: pd.Series | None, divs: pd.Series | None = None, bench: pd.Series | None = None,
                bench_divs: pd.Series | None = None) -> dict | None:
    """Returns, risk and trend from price history. Returns include dividends. None if under ~3 months of data."""
    p = _clean(prices)
    if len(p) < 60:
        return None
    ret = rl.total_returns(p, divs)
    eq = (1 + ret).cumprod()
    out: dict[str, Any] = {"last": float(p.iloc[-1]), "last_date": p.index[-1], "years_of_history": len(p) / 252}
    for k, n in TD.items():
        out[k] = _window(eq, n)
    out["3Y"], out["5Y"] = _annualized(eq, 3), _annualized(eq, 5)

    r1 = ret.iloc[-252:]
    out["volatility"] = float(r1.std() * np.sqrt(252)) if len(r1) >= 120 else None

    eq5 = eq.iloc[-1260:]
    dd = eq5 / eq5.cummax() - 1
    out["max_drawdown"], out["max_drawdown_date"] = float(dd.min()), dd.idxmin()
    out["current_drawdown"] = float(dd.iloc[-1])
    rr = ret.iloc[-1260:]
    out["worst_day"], out["worst_day_date"] = float(rr.min()), rr.idxmin()
    out["best_day"], out["best_day_date"] = float(rr.max()), rr.idxmax()

    last = out["last"]
    out["vs50"] = last / float(p.iloc[-50:].mean()) - 1 if len(p) >= 50 else None
    out["vs200"] = last / float(p.iloc[-200:].mean()) - 1 if len(p) >= 200 else None
    out["trend"] = None
    if out["vs50"] is not None and out["vs200"] is not None:
        out["trend"] = "up" if out["vs50"] > 0 and out["vs200"] > 0 else "down" if out["vs50"] < 0 and out["vs200"] < 0 else "mixed"
    yr = p.iloc[-252:]
    out["high52"], out["low52"] = float(yr.max()), float(yr.min())
    out["from_high"] = last / out["high52"] - 1
    out["range_pos"] = (last - out["low52"]) / (out["high52"] - out["low52"]) if out["high52"] > out["low52"] else None

    out["beta"] = out["excess_1y"] = out["excess_3y"] = None
    out["bench_1y"] = out["bench_3y"] = None
    b = _clean(bench)
    if len(b) >= 60:
        br = rl.total_returns(b, bench_divs)
        j = pd.concat([ret, br], axis=1, join="inner").dropna().iloc[-756:]
        if len(j) >= 120 and j.iloc[:, 1].var() > 0:
            out["beta"] = float(j.iloc[:, 0].cov(j.iloc[:, 1]) / j.iloc[:, 1].var())
        beq = (1 + br).cumprod()
        out["bench_1y"], out["bench_3y"] = _window(beq, 252), _annualized(beq, 3)
        if out["1Y"] is not None and out["bench_1y"] is not None:
            out["excess_1y"] = out["1Y"] - out["bench_1y"]
        if out["3Y"] is not None and out["bench_3y"] is not None:
            out["excess_3y"] = out["3Y"] - out["bench_3y"]
    return out


# ---------------------------------------------------------------- pros and cons
def assess(symbol: str, quote: dict | None, metrics: dict | None, trends: list[dict] | None, stats: dict | None = None,
           div: dict | None = None, earnings_in_days: int | None = None) -> dict:
    """The screen's pros and cons plus extra signals. Same structure as idea_lib.evaluate, with `extra` counts."""
    base = il.evaluate(symbol, quote, metrics, trends)
    pros, cons = list(base["pros"]), list(base["cons"])
    covered = base["covered"]

    def add(kind, label, text):
        (pros if kind == "pro" else cons).append((label, text))

    def m(key):
        return metric(metrics, key)

    # cash-based valuation and longer-term growth
    pf = m("pfcf")
    if pf is not None:
        covered += 1
        if 0 < pf <= 20:
            add("pro", "Valuation (cash)", f"Price is {pf:.1f}× its yearly free cash flow, a modest multiple.")
        elif pf <= 0 or pf > 40:
            add("con", "Valuation (cash)", "No positive free cash flow to judge the price by." if pf <= 0 else f"Price is {pf:.0f}× its yearly free cash flow: a lot of growth is already expected.")
    r5, e5 = m("rev_growth_5y"), m("eps_growth_5y")
    if r5 is not None:
        covered += 1
        if r5 >= 8:
            add("pro", "Growth over time", f"Sales have grown about {r5:.1f}% a year on average over five years, so growth has lasted.")
        elif r5 < 0:
            add("con", "Growth over time", f"Sales have shrunk about {abs(r5):.1f}% a year on average over five years.")
    if e5 is not None:
        covered += 1
        if e5 >= 8:
            add("pro", "Earnings over time", f"Profit per share has grown about {e5:.1f}% a year over five years.")
        elif e5 < 0:
            add("con", "Earnings over time", f"Profit per share has fallen about {abs(e5):.1f}% a year over five years.")

    # profitability and health
    om = m("op_margin")
    if om is not None:
        covered += 1
        if om >= 15:
            add("pro", "Operating margin", f"Operating margin of {om:.1f}%: the core business is solidly profitable.")
        elif om < 5:
            add("con", "Operating margin", f"Thin operating margin ({om:.1f}%): little room if costs rise or sales slip.")
    cr, ic, po = m("current_ratio"), m("interest_cov"), m("payout")
    if cr is not None:
        covered += 1
        if cr < 1:
            add("con", "Short-term cash", f"Current ratio of {cr:.2f}: short-term bills exceed short-term assets.")
    if ic is not None:
        covered += 1
        if ic >= 8:
            add("pro", "Interest costs", f"Profit covers interest payments {ic:.0f} times over.")
        elif ic < 3:
            add("con", "Interest costs", f"Profit covers interest only {ic:.1f} times: debt could get heavy if profit drops.")
    if po is not None and po > 90 and (m("div_yield") or 0) > 0:
        add("con", "Dividend safety", f"Pays out {po:.0f}% of profit as dividends, leaving little room if profit dips.")

    # price behaviour
    if stats:
        if stats.get("trend") == "up":
            covered += 1
            add("pro", "Trend", "The price is above both its 50-day and 200-day averages: an uptrend (it describes the past, not the future).")
        elif stats.get("trend") == "down":
            covered += 1
            add("con", "Trend", "The price is below both its 50-day and 200-day averages: a downtrend.")
        vol = stats.get("volatility")
        if vol is not None:
            covered += 1
            if vol >= 0.45:
                add("con", "Swings", f"Its price swings a lot: about {vol * 100:.0f}% a year (the broad market is roughly 15–20%).")
            elif vol <= 0.22:
                add("pro", "Swings", f"Steadier than most stocks: about {vol * 100:.0f}% yearly swings.")
        md = stats.get("max_drawdown")
        if md is not None and stats.get("years_of_history", 0) >= 2:
            covered += 1
            if md <= -0.5:
                add("con", "Worst fall", f"At its worst it lost {abs(md) * 100:.0f}% from a peak (to {stats['max_drawdown_date']:%b %Y}). Could you hold through that?")
            elif md >= -0.25:
                add("pro", "Worst fall", f"Its worst fall in the past five years was a milder {abs(md) * 100:.0f}%.")
        ex = stats.get("excess_3y")
        if ex is not None:
            covered += 1
            if ex >= 0.05:
                add("pro", "Versus the market", f"Beat the S&P 500 by about {ex * 100:.0f} points a year over three years (past results don't carry forward).")
            elif ex <= -0.05:
                add("con", "Versus the market", f"Trailed the S&P 500 by about {abs(ex) * 100:.0f} points a year over three years.")

    # dividend record
    if div and div.get("active") and (div.get("streak") or 0) >= 5:
        add("pro", "Dividend record", f"Has raised its dividend {div['streak']} years in a row.")

    # event risk
    if earnings_in_days is not None and 0 <= earnings_in_days <= 14:
        when = "today" if earnings_in_days == 0 else "tomorrow" if earnings_in_days == 1 else f"in {earnings_in_days} days"
        add("con", "Earnings soon", f"Reports earnings {when}. Prices often move sharply on the news, either way.")

    net = len(pros) - len(cons)
    return {**base, "pros": pros, "cons": cons, "covered": covered, "net": net, "avg": net / covered if covered else None,
            "eligible": covered >= il.MIN_FACTORS, "base_pros": len(base["pros"]), "base_cons": len(base["cons"])}


def earnings_in_days(calendar: dict | None, symbol: str, today: dt.date, max_days: int = 200) -> tuple[int, dt.date] | None:
    """(days until, date) of this company's next report inside `max_days`, from Finnhub's calendar response."""
    best = None
    for item in (calendar or {}).get("earningsCalendar", []) or []:
        if (item.get("symbol") or "").upper() != symbol.upper() or not item.get("date"):
            continue
        try:
            d = dt.date.fromisoformat(item["date"])
        except ValueError:
            continue
        if today <= d <= today + dt.timedelta(days=max_days) and (best is None or d < best):
            best = d
    return ((best - today).days, best) if best else None


def held_context(symbol: str, weights: dict[str, float] | None) -> dict | None:
    """Percent-only: how big this ticker already is in your invested money (None when locked)."""
    if not weights:
        return None
    w = weights.get(symbol.upper())
    return {"held": w is not None, "weight": float(w) if w is not None else None}


# ---------------------------------------------------------------- rules shown on the page
EXTRA_RULES = [
    ("Trend", "Pro if above both its 50-day and 200-day averages; con if below both."),
    ("Swings", "Con if yearly price swings are 45% or more; pro if 22% or less."),
    ("Worst fall", "Con if it lost 50% or more from a peak in five years; pro if the worst fall was under 25%."),
    ("Versus the market", "Pro/con if it beat/trailed the S&P 500 by 5+ points a year over three years."),
    ("Dividend record", "Pro if the dividend has risen five or more years in a row."),
    ("Earnings soon", "Con (a heads-up) if it reports within 14 days."),
]


def rules_table() -> list[tuple[str, str, str, str]]:
    """(group, measure, 'Good when', 'Watch when') for every graded measure."""
    rows = []
    for group, label, _key, _kind, rule, _meaning in KEYS:
        if not rule:
            continue
        k = rule[0]
        if k == "pe":
            good, watch = f"above 0 and up to {rule[1]:g}", f"0 or below, or above {rule[2]:g}"
        elif k == "low":
            good, watch = f"{rule[1]:g} or lower", f"{rule[2]:g} or higher"
        elif k == "high":
            good, watch = f"{rule[1]:g} or higher", f"below {rule[2]:g}"
        else:
            good, watch = "-", f"{rule[1]:g} or higher"
        rows.append((group, label, good, watch))
    return rows


def returns_table(prices, divs=None, bench=None, bench_divs=None) -> pd.DataFrame:
    """Stock vs the S&P 500 (or whatever benchmark) over 1M…5Y, dividends included. Fractions; 3Y and 5Y are per year."""
    def curve(p, d):
        p = _clean(p)
        return (1 + rl.total_returns(p, d)).cumprod() if len(p) > 2 else pd.Series(dtype=float)

    eq, beq = curve(prices, divs), curve(bench, bench_divs)
    rows = []
    for label, n in TD.items():
        rows.append({"Period": label, "Stock": _window(eq, n), "S&P 500": _window(beq, n)})
    for y in (3, 5):
        rows.append({"Period": f"{y}Y per year", "Stock": _annualized(eq, y), "S&P 500": _annualized(beq, y)})
    df = pd.DataFrame(rows)
    df["Difference"] = df["Stock"] - df["S&P 500"]
    return df.dropna(subset=["Stock"]).reset_index(drop=True)


def compare_curves(prices, divs, bench, bench_divs, years: float = 5, start: float = 10_000.0) -> dict[str, pd.Series]:
    """Both growth curves from the same starting day and the same starting amount (dividends reinvested)."""
    a = equity_curve(prices, divs, years)
    out = {"Stock": a}
    b = equity_curve(bench, bench_divs, years)
    if len(a) and len(b):
        s = max(a.index[0], b.index[0])
        a, b = a[a.index >= s], b[b.index >= s]
        out = {"Stock": a / a.iloc[0], "S&P 500": b / b.iloc[0]}
    return {k: v * start for k, v in out.items() if len(v)}
