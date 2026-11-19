"""
Stock of the day: a transparent screen, not a prediction.

Pure logic (no Streamlit, no network). Each factor looks at one number from
Finnhub's free data and scores +1 (pro), -1 (con) or 0 (no signal). The page
shows every number behind every pro and con, plus how the pick compares with
the other candidates screened that day.
"""

from __future__ import annotations

import random
from typing import Any

import brief_lib as bl

UNIVERSE = [
    # technology
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "AVGO", "ORCL", "ADBE", "CRM", "CSCO", "TXN", "QCOM", "AMD", "IBM",
    # financials
    "JPM", "BAC", "WFC", "GS", "MS", "V", "MA", "AXP", "BLK",
    # health care
    "UNH", "JNJ", "PFE", "MRK", "LLY", "ABBV", "TMO", "ABT", "AMGN", "GILD",
    # consumer
    "PG", "KO", "PEP", "WMT", "COST", "MCD", "NKE", "SBUX", "HD", "LOW", "TGT", "DIS", "NFLX",
    # communication
    "CMCSA", "T", "VZ",
    # energy, industrials, materials, utilities
    "XOM", "CVX", "COP", "CAT", "DE", "HON", "GE", "UPS", "LMT", "RTX", "LIN", "NEE", "DUK", "SO",
]

MIN_FACTORS = 5  # a pick needs at least this many factors with real data

ALIASES = {
    "pe": ("peTTM", "peBasicExclExtraTTM", "peExclExtraTTM", "peNormalizedAnnual"),
    "rev_growth": ("revenueGrowthTTMYoy", "revenueGrowthQuarterlyYoy"),
    "net_margin": ("netProfitMarginTTM", "netProfitMarginAnnual"),
    "roe": ("roeTTM", "roeRfy"),
    "debt_equity": ("totalDebt/totalEquityQuarterly", "totalDebt/totalEquityAnnual"),
    "high52": ("52WeekHigh",),
    "low52": ("52WeekLow",),
    "beta": ("beta",),
    "div_yield": ("dividendYieldIndicatedAnnual", "currentDividendYieldTTM"),
    "mcap": ("marketCapitalization",),
}

RULES = [
    ("Valuation", "P/E (trailing 12 months)", "Pro if 0 < P/E ≤ 20. Con if P/E > 40, or if earnings are negative."),
    ("Growth", "Revenue growth, year over year", "Pro if ≥ 10%. Con if shrinking (< 0%)."),
    ("Profitability", "Net profit margin", "Pro if ≥ 15%. Con if negative."),
    ("Returns", "Return on equity", "Pro if ≥ 15%. Con if negative."),
    ("Balance sheet", "Debt / equity", "Pro if ≤ 0.5. Con if ≥ 2."),
    ("Price vs 52-week high", "How far below its yearly high", "Pro if 10–30% below (a pullback). Con if within 3% of the high (little margin for error) or more than 45% below (may be broken for a reason)."),
    ("Analysts", "Analyst rating score, −2 to +2", "Pro if ≥ 1.0. Con if ≤ 0.0. Analysts skew bullish and lag price."),
    ("Dividend", "Indicated dividend yield", "Pro if ≥ 2%."),
    ("Volatility", "Beta vs the market", "Con if ≥ 1.5 (swings much more than the market)."),
]


def metric(metrics: dict | None, key: str) -> float | None:
    """First usable number for a logical metric, trying each known Finnhub field name."""
    for name in ALIASES.get(key, (key,)):
        v = (metrics or {}).get(name)
        if isinstance(v, bool):
            continue
        try:
            if v is not None:
                return float(v)
        except (TypeError, ValueError):
            continue
    return None


def pick_candidates(universe: list[str], exclude: set[str], day_ordinal: int, n: int = 8, offset: int = 0) -> list[str]:
    """Deterministic sample for the day (same all day), excluding what you already follow."""
    pool = [s for s in universe if s.upper() not in {e.upper() for e in exclude}]
    rng = random.Random(day_ordinal * 1000 + offset)
    return rng.sample(pool, min(n, len(pool)))


def evaluate(symbol: str, quote: dict | None, metrics: dict | None, trends: list[dict] | None) -> dict:
    """Score one stock. Returns pros/cons (each with the number behind it), facts, and coverage."""
    pros: list[tuple[str, str]] = []
    cons: list[tuple[str, str]] = []
    facts: list[tuple[str, str]] = []
    covered = 0

    def add(kind: str, label: str, text: str):
        (pros if kind == "pro" else cons if kind == "con" else []).append((label, text))

    price = (quote or {}).get("c") or None
    day = (quote or {}).get("dp") if price else None

    pe = metric(metrics, "pe")
    growth = metric(metrics, "rev_growth")
    margin = metric(metrics, "net_margin")
    roe = metric(metrics, "roe")
    de = metric(metrics, "debt_equity")
    high, low = metric(metrics, "high52"), metric(metrics, "low52")
    beta = metric(metrics, "beta")
    dy = metric(metrics, "div_yield")
    mcap = metric(metrics, "mcap")

    # Valuation
    if pe is not None:
        covered += 1
        facts.append(("P/E (TTM)", f"{pe:.1f}"))
        if 0 < pe <= 20:
            add("pro", "Valuation", f"P/E of {pe:.1f} is at or below 20, a modest price for each dollar of earnings.")
        elif pe > 40:
            add("con", "Valuation", f"P/E of {pe:.1f} is above 40: the price already assumes a lot of future growth.")
    elif margin is not None and margin < 0:
        covered += 1
        facts.append(("P/E (TTM)", "n/a (no positive earnings)"))
        add("con", "Valuation", "No positive trailing earnings, so there is no P/E to judge the price by.")

    # Growth
    if growth is not None:
        covered += 1
        facts.append(("Revenue growth (YoY)", f"{growth:.1f}%"))
        if growth >= 10:
            add("pro", "Growth", f"Revenue is growing {growth:.1f}% year over year.")
        elif growth < 0:
            add("con", "Growth", f"Revenue is shrinking ({growth:.1f}% year over year).")

    # Profitability
    if margin is not None:
        covered += 1
        facts.append(("Net profit margin", f"{margin:.1f}%"))
        if margin >= 15:
            add("pro", "Profitability", f"Keeps {margin:.0f}¢ of profit from every revenue dollar (net margin {margin:.1f}%).")
        elif margin < 0:
            add("con", "Profitability", f"Losing money: net margin is {margin:.1f}%.")

    if roe is not None:
        covered += 1
        facts.append(("Return on equity", f"{roe:.1f}%"))
        if roe >= 15:
            add("pro", "Returns", f"Return on equity of {roe:.1f}% shows it earns well on shareholders' capital.")
        elif roe < 0:
            add("con", "Returns", f"Negative return on equity ({roe:.1f}%).")

    # Balance sheet
    if de is not None:
        covered += 1
        facts.append(("Debt / equity", f"{de:.2f}"))
        if de <= 0.5:
            add("pro", "Balance sheet", f"Low debt: debt-to-equity is {de:.2f}.")
        elif de >= 2:
            add("con", "Balance sheet", f"Heavy debt: debt-to-equity is {de:.2f}.")

    # Price vs yearly high
    below = None
    if price and high:
        below = (high - price) / high * 100
        covered += 1
        facts.append(("52-week range", f"${low:.2f} – ${high:.2f}" if low else f"high ${high:.2f}"))
        facts.append(("Below 52-week high", f"{below:.1f}%"))
        if 10 <= below <= 30:
            add("pro", "Price", f"Trading {below:.0f}% below its 52-week high, so you would not be buying at the peak.")
        elif below < 3:
            add("con", "Price", f"Within {max(below, 0):.1f}% of its 52-week high: little cushion if sentiment turns.")
        elif below > 45:
            add("con", "Price", f"Down {below:.0f}% from its 52-week high. That can be a bargain or a warning; check why.")

    # Analysts
    score = shift = None
    if trends:
        score = bl.analyst_score(trends[0])
        shift = bl.analyst_shift(trends)
    if score is not None:
        covered += 1
        n = sum((trends[0].get(k, 0) or 0) for k in ("strongBuy", "buy", "hold", "sell", "strongSell"))
        facts.append(("Analyst score (−2…+2)", f"{score:+.2f} from {n} analysts"))
        trend_note = f" ({shift['direction']} than last month)" if shift and shift["direction"] != "little changed" else ""
        if score >= 1.0:
            add("pro", "Analysts", f"Analyst consensus leans bullish ({score:+.2f} of +2, {n} analysts){trend_note}.")
        elif score <= 0.0:
            add("con", "Analysts", f"Analyst consensus is not bullish ({score:+.2f}, {n} analysts){trend_note}.")

    # Dividend / volatility
    if dy is not None and dy > 0:
        facts.append(("Dividend yield", f"{dy:.2f}%"))
        if dy >= 2:
            add("pro", "Dividend", f"Pays an indicated {dy:.1f}% dividend yield.")
    if beta is not None:
        covered += 1
        facts.append(("Beta", f"{beta:.2f}"))
        if beta >= 1.5:
            add("con", "Volatility", f"Beta of {beta:.2f}: it tends to swing about {beta:.1f}× as much as the market.")

    if mcap:
        facts.append(("Market cap", f"${mcap / 1000:,.0f}B" if mcap >= 1000 else f"${mcap:,.0f}M"))
    if price:
        facts.insert(0, ("Price", f"${price:,.2f}" + (f" ({day:+.2f}% today)" if day is not None else "")))

    total = len(pros) - len(cons)
    return {
        "symbol": symbol.upper(), "price": price, "day_pct": day, "pros": pros, "cons": cons, "facts": facts,
        "covered": covered, "net": total, "avg": (total / covered) if covered else None,
        "eligible": covered >= MIN_FACTORS, "below_high": below, "analyst_score": score,
    }


def choose(evals: list[dict]) -> dict | None:
    """Best eligible candidate: highest net score per factor with data, then more pros, then more coverage."""
    ok = [e for e in evals if e["eligible"]]
    if not ok:
        return None
    return max(ok, key=lambda e: (e["avg"], len(e["pros"]), e["covered"], e["symbol"]))


def comparison_rows(evals: list[dict]) -> list[dict]:
    rows = []
    for e in sorted(evals, key=lambda e: (e["avg"] is None, -(e["avg"] or 0))):
        rows.append({
            "Symbol": e["symbol"], "Pros": len(e["pros"]), "Cons": len(e["cons"]),
            "Factors with data": e["covered"],
            "Screen score": None if e["avg"] is None else round(e["avg"], 2),
            "Eligible": "yes" if e["eligible"] else "not enough data",
        })
    return rows


def split_stocks_funds(symbols: list[str], class_by_symbol: dict[str, str], names: dict[str, str]) -> tuple[list[str], list[str]]:
    """Analysts rate companies, not funds. Held tickers use their asset class; others with no
    company name (Finnhub returns none for ETFs) are treated as funds; a failed lookup stays with stocks."""
    non_stock = {"ETF", "Fund", "Bond", "Crypto", "Cash equiv."}
    stocks, funds = [], []
    for s in symbols:
        cls = class_by_symbol.get(s)
        if cls is not None:
            (funds if cls in non_stock else stocks).append(s)
        else:
            n = (names.get(s) or "").strip()
            (stocks if n else funds).append(s)
    return stocks, funds
