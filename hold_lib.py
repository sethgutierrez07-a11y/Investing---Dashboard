"""
"How long to hold" for the Stock Deep-Dive. Pure functions: no Streamlit, no network.

Nobody can say how long a particular stock should be held. What the past CAN show is
  * how often holding it for 1, 3 and 5 years ended in a gain (rolling windows over its full Yahoo history),
  * how long its worst falls took to climb back (peak to recovery), and
  * how bumpy it is, which sets how long money should be able to sit in it.
From those we give a planning window ("money you won't need for at least N years"), what would make it worth a
re-check, and a size note. Everything is a rule of thumb on past numbers, not a prediction or advice.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

import deep_lib as dlib
import risk_lib as rl

YEARS = (1, 3, 5)
TIERS = [  # (volatility upper bound, name, base years)
    (0.20, "steady", 3),
    (0.30, "moderate", 5),
    (0.45, "bumpy", 5),
    (9.99, "very bumpy", 7),
]
MAX_YEARS = 10
SIZE_NOTE_PCT = 5            # a common rule of thumb: keep one bumpy stock to about this share of invested money
RULES = [
    ("Steadiness", "Yearly swings under 20% = steady (3-year base), 20-30% = moderate (5), 30-45% = bumpy (5), 45%+ = very bumpy (7). "
                   "Without swing data, the worst fall decides: milder than 20% steady, 20-35% moderate, 35-50% bumpy, deeper very bumpy."),
    ("Recovery", "If its past falls took longer than the base to climb back (peak to recovery), the window grows to cover that, up to 10 years."),
    ("Price tag", "+1 year when the P/E is above 40 or there are no earnings, since expensive stocks have more room to fall."),
    ("Funds", "At least 5 years for a fund or ETF: it is a basket, so the question is how long you can leave it alone."),
    ("Window shown", "The base-plus-adjustments number is the low end; the range runs two years past it. Anything over 10 years shows as 10+."),
    ("Size note", f"Bumpy or very bumpy single stocks: many people keep them to about {SIZE_NOTE_PCT}% of invested money."),
]


# ---------------------------------------------------------------- what history says
def history_windows(prices, divs=None, years=YEARS, min_samples: int = 120) -> list[dict]:
    """For each holding length: how many start dates were tested and how they ended (dividends reinvested)."""
    eq = dlib.equity_curve(prices, divs)
    out = []
    for y in years:
        n = int(y * 252)
        if len(eq) <= n + min_samples:
            continue
        tot = (eq.shift(-n) / eq - 1).dropna()
        if len(tot) < min_samples:
            continue
        med = float(tot.median())
        out.append({"years": y, "periods": int(len(tot)), "share_gain": float((tot > 0).mean()),
                    "median_total": med, "median_per_year": float((1 + med) ** (1 / y) - 1) if med > -1 else None,
                    "worst_total": float(tot.min()), "best_total": float(tot.max())})
    return out


def recoveries(prices, divs=None, min_depth: float = 0.15, n: int = 3, lookback_days: int = 2520) -> dict:
    """Deepest falls over the last ~10 years and how long each took from peak to being back (or 'still down')."""
    p = dlib._clean(prices)
    if len(p) < 120:
        return {"episodes": [], "longest_days": None, "still_down": None}
    ret = rl.total_returns(p, divs).iloc[-lookback_days:]
    eps = []
    for e in rl.drawdown_episodes(ret, n=n, min_depth=min_depth):
        total = (e["days_down"] + e["days_to_recover"]) if e["days_to_recover"] is not None else None
        eps.append({**e, "total_days": total})
    done = [e["total_days"] for e in eps if e["total_days"] is not None]
    still = next((e for e in eps if e["recovered"] is None), None)
    return {"episodes": eps, "longest_days": max(done) if done else None, "still_down": still}


# ---------------------------------------------------------------- the window
def tier_for(stats: dict | None) -> tuple[str, int] | None:
    if not stats:
        return None
    vol = stats.get("volatility")
    if vol is not None:
        for top, name, base in TIERS:
            if vol < top:
                return name, base
    md = stats.get("max_drawdown")
    if md is None:
        return None
    if md > -0.20:
        return "steady", 3
    if md > -0.35:
        return "moderate", 5
    if md > -0.50:
        return "bumpy", 5
    return "very bumpy", 7


def window_text(low: int) -> str:
    return "10+ years" if low >= MAX_YEARS else f"{low}–{min(low + 2, MAX_YEARS)} years"


def horizon(stats: dict | None, recov: dict | None, ev: dict | None = None, fund: bool = False,
            metrics: dict | None = None) -> dict | None:
    """The planning window, with every adjustment spelled out. None when there isn't enough history to say."""
    t = tier_for(stats)
    if t is None:
        return None
    tier, base = t
    years, why = base, [f"base {base} years for a {tier} stock"]
    if fund and years < 5:
        years = 5
        why.append("a fund is held for at least 5 years")
    longest = (recov or {}).get("longest_days")
    if longest:
        need = math.ceil(longest / 365)
        if need > years:
            years = min(need, MAX_YEARS)
            why.append(f"its past falls took up to about {need} years from peak to recovery")
    pe = dlib.metric(metrics, "pe")
    expensive = (not fund) and ((pe is not None and pe > 40) or any(lab == "Valuation" and "No positive" in t_ for lab, t_ in (ev or {}).get("cons", [])))
    if expensive and years < MAX_YEARS:
        years += 1
        why.append("priced for a lot of growth (+1 year)")
    years = min(years, MAX_YEARS)
    style = "Medium-term (a few years)" if years <= 3 else "Long-term" if years <= 6 else "Long-term, and keep it small"
    return {"tier": tier, "low": years, "text": window_text(years), "style": style, "why": why,
            "small_slice": tier in ("bumpy", "very bumpy") and not fund}


# ---------------------------------------------------------------- what to keep an eye on
def rechecks(stats: dict | None, ev: dict | None, div: dict | None, earn_days: int | None, fund: bool = False) -> list[dict]:
    """Things that would make a long hold worth a second look, each with its status today."""
    cons = {lab for lab, _t in (ev or {}).get("cons", [])}
    out = []

    def add(what, why, flagged, now_ok, now_flag):
        out.append({"what": what, "why": why, "flag": bool(flagged), "now": now_flag if flagged else now_ok})

    if not fund:
        soon = earn_days is not None and earn_days <= 14
        add("Each earnings report", "Four times a year: are sales and profit still growing as expected?", soon,
            "No report in the next two weeks.", f"A report is due in {earn_days} day{'s' if earn_days != 1 else ''}.")
        add("Sales and profit", "Shrinking sales or profit per share for several reports is the classic slow warning.",
            cons & {"Growth", "Profitability", "Growth over time", "Earnings over time", "Operating margin"},
            "Nothing flagged on growth or profit.", "Growth or profit is already flagged under What to watch.")
        add("Debt and cash", "Heavy debt turns a bad year into a crisis.",
            cons & {"Balance sheet", "Short-term cash", "Interest costs"},
            "Nothing flagged on debt or cash.", "Debt or cash is already flagged under What to watch.")
        if div and div.get("active"):
            add("The dividend", "A cut or skipped payment is a strong warning sign.", "Dividend safety" in cons,
                "Payout looks covered by profit.", "The payout is already a large share of profit.")
        if ev is not None:
            add("Analyst opinion", "A shift from buy toward sell across many analysts is worth noticing, not obeying.", "Analysts" in cons,
                "Analysts are not leaning negative.", "Analysts are already leaning negative.")
    trend = (stats or {}).get("trend")
    add("The long-term trend", "Staying below the 200-day average for months can mean the story has changed.", trend == "down",
        "Not in a downtrend right now.", "Below both its 50-day and 200-day averages right now.")
    add("Your own reason for buying", "If the reason you bought it no longer holds, that matters more than the price.", False,
        "Write your reason down now so you can check it later.", "")
    return out
