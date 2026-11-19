"""
Written risk summary, by rules. No AI, no network: every sentence is chosen and filled in from the
numbers on the page. Percent-only, so nothing here is a private dollar amount.

write_summary(...) -> [(title, [bullet, ...]), ...]
"""

from __future__ import annotations

import pandas as pd

Section = tuple[str, list[str]]


def pct(x: float, d: int = 0) -> str:
    return f"{x * 100:.{d}f}%"


def month(ts) -> str:
    return pd.Timestamp(ts).strftime("%b %Y")


def join(items: list[str]) -> str:
    items = list(items)
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def relative_bumpiness(pm: dict, sm: dict) -> str:
    r = pm["volatility"] / sm["volatility"] if sm["volatility"] else 1.0
    return "calmer" if r < 0.85 else "bumpier" if r > 1.15 else "about as bumpy"


def bottom_line(pm, sm, years, n, rc, weights, beta_p) -> list[str]:
    rel = relative_bumpiness(pm, sm)
    rel_text = f"{rel} than the S&P 500" if rel != "about as bumpy" else "about as bumpy as the S&P 500"
    out = [
        f"**In short:** over the last {years:.0f} years, today's mix of {n} holding{'s' if n != 1 else ''} would have been {rel_text}. "
        f"Yearly swings were {pct(pm['volatility'])} against {pct(sm['volatility'])}, the worst fall from a peak was "
        f"{pct(-pm['max_drawdown'])} against {pct(-sm['max_drawdown'])}, and it grew {pct(pm['cagr'], 1)} a year against {pct(sm['cagr'], 1)}."
    ]
    if pm["sharpe"] is not None and sm["sharpe"] is not None:
        d = pm["sharpe"] - sm["sharpe"]
        out.append("**Reward for the risk:** " + (
            f"better than the market (Sharpe {pm['sharpe']:.2f} against {sm['sharpe']:.2f}): more return for each unit of risk taken." if d > 0.1 else
            f"worse than the market (Sharpe {pm['sharpe']:.2f} against {sm['sharpe']:.2f}): less return for each unit of risk taken." if d < -0.1 else
            f"about the same as the market (Sharpe {pm['sharpe']:.2f} against {sm['sharpe']:.2f})."))
    if n >= 2 and rc is not None and len(rc):
        gap = (rc - pd.Series(weights).reindex(rc.index).fillna(0)).sort_values(ascending=False)
        top = gap.index[0]
        if gap.iloc[0] >= 0.10:
            out.append(f"**Where the risk is:** {top} is {pct(weights[top])} of your money but {pct(rc[top])} of your risk, "
                       "so it drives how bumpy the whole mix feels.")
        else:
            out.append("**Where the risk is:** roughly in line with where the money is. No single holding is carrying much more "
                       "risk than its size.")
    if beta_p is not None:
        out.append(f"**Sensitivity:** a beta of {beta_p:.2f} means that for every 10% the market falls, this mix has typically fallen about {beta_p * 10:.0f}%.")
    return out


def diversification(avg_corr, div_ratio, hi, lo, n, excluded) -> list[str]:
    if n < 2:
        return ["You have a single holding in the window, so there is nothing to diversify across. Its risk is the whole portfolio's risk."]
    out = []
    level = "low" if avg_corr < 0.3 else "moderate" if avg_corr < 0.6 else "high"
    meaning = {"low": "they often move independently, which is what diversification needs.",
               "moderate": "they share some of the same ups and downs, but not all.",
               "high": "they mostly rise and fall together, so owning several gives less protection than it looks."}[level]
    out.append(f"**How alike your holdings are:** average correlation {avg_corr:.2f} ({level}). {meaning[0].upper() + meaning[1:]}")
    if div_ratio is not None:
        out.append(f"**Benefit of mixing:** the mix is {div_ratio:.2f}x calmer than its holdings are on their own"
                   + (" (1.00 would mean no benefit at all)." if div_ratio < 1.1 else "."))
    if hi:
        out.append(f"**Most alike:** {hi[0]} and {hi[1]} (correlation {hi[2]:.2f})."
                   + (f" **Least alike:** {lo[0]} and {lo[1]} ({lo[2]:.2f})." if lo and lo[:2] != hi[:2] else ""))
    out.append("Correlation is measured between tickers. An ETF already holds many companies inside it, so a mix of broad ETFs can look "
               "concentrated here and still be well spread underneath.")
    if excluded:
        out.append(f"Left out because their price history is too short for this window: {join(excluded)}.")
    return out


def bad_stretches(episodes, hist, pm, years) -> list[str]:
    out = []
    if episodes:
        e = episodes[0]
        rec = (f"and it took {e['days_to_recover'] / 30.4:.0f} months from the bottom to get back to that peak"
               if e["days_to_recover"] is not None else "and it had not yet gotten back to that peak at the end of the data")
        out.append(f"**Deepest fall:** {pct(-e['depth'])}, from {month(e['peak'])} to {month(e['trough'])}, {rec}.")
        if len(episodes) > 1:
            out.append("**Next ones:** " + "; ".join(f"{pct(-x['depth'])} ({month(x['peak'])} to {month(x['trough'])})" for x in episodes[1:]) + ".")
    else:
        out.append(f"No fall of 5% or more from a peak in these {years:.0f} years.")
    for h in hist:
        diff = h["mix"] - h["market"]
        if h["mix"] < 0:
            tail = ", a smaller loss." if diff > 0.01 else ", a bigger loss." if diff < -0.01 else "."
            out.append(f"**{h['label']}:** today's mix would have lost {pct(-h['mix'])} against {pct(-h['market'])} for the S&P 500{tail}")
        else:
            out.append(f"**{h['label']}:** today's mix would have gained {pct(h['mix'])} against {pct(h['market'])} for the S&P 500.")
    if pm.get("worst_day") is not None:
        out.append(f"**Single bad days:** the worst day was {pct(pm['worst_day'], 1)} on {pd.Timestamp(pm['worst_day_date']):%b %-d, %Y}. "
                   f"On 1 day in 20, it did worse than {pct(pm['bad_day_5pct'], 1)}."
                   + (f" The worst 21-day stretch lost {pct(-pm['worst_month'], 0)}." if pm.get("worst_month") is not None and pm["worst_month"] < 0 else ""))
    return out


def stress(stress_rows: list[dict], beta_p, biggest) -> list[str]:
    if beta_p is None or not stress_rows:
        return ["Not enough overlapping price history with the S&P 500 to estimate how your mix reacts to a market fall."]
    out = ["**If the market fell:** " + "; ".join(f"{r['market']:.0f}% → your mix about {r['mix']:.0f}%" for r in stress_rows) + "."]
    if biggest:
        out.append(f"**Biggest share of a fall:** {biggest[0]} would account for about {pct(biggest[1])} of the loss.")
    out.append("These are rough. They assume each holding keeps reacting the way it did on average, but in real crashes holdings tend to "
               "fall together more than usual, so actual losses can be larger. Not a forecast.")
    return out


def worth_knowing(n_days: int) -> list[str]:
    return [
        "This is a **backcast**: today's holdings at today's weights, replayed over past prices. It is how this mix would have behaved, "
        "not what your account actually did.",
        f"It uses {n_days:,} trading days of data, which is one slice of history. A calmer or rougher period would change every number.",
        "Volatility and drawdown measure bumpiness, not permanent loss. A single stock can fail for good in a way a broad index has not.",
        "Informational only, not financial advice.",
    ]


def write_summary(*, pm, sm, years, n, n_days, rc, weights, beta_p, avg_corr, div_ratio, hi, lo, excluded, episodes, hist,
                  stress_rows, biggest) -> list[Section]:
    sections = [
        ("Bottom line", bottom_line(pm, sm, years, n, rc, weights, beta_p)),
        ("Diversification", diversification(avg_corr, div_ratio, hi, lo, n, excluded)),
        ("Bad stretches", bad_stretches(episodes, hist, pm, years)),
        ("Stress test", stress(stress_rows, beta_p, biggest)),
        ("Worth knowing", worth_knowing(n_days)),
    ]
    return [(t, b) for t, b in sections if b]
