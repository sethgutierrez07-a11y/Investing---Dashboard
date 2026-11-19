"""
Plain-English write-up for the Stock Deep-Dive. Rules only, no AI: every sentence comes from a number on the page.
Returns [(section title, [bullets])]. Bullets may contain **bold** and "$" (the page escapes them for Markdown).
"""

from __future__ import annotations

import deep_lib as dlib


def pc(x: float | None, digits: int = 1, signed: bool = False) -> str:
    if x is None:
        return "n/a"
    return f"{x * 100:+.{digits}f}%" if signed else f"{x * 100:.{digits}f}%"


def _article(word: str) -> str:
    return "an" if word[:1].lower() in "aeiou" else "a"


def in_plain_words(symbol: str, profile: dict | None, quote: dict | None, metrics: dict | None, stats: dict | None) -> list[str]:
    out = []
    profile = profile or {}
    name = profile.get("name") or symbol
    mcap = profile.get("marketCapitalization") or dlib.metric(metrics, "mcap")
    size = dlib.size_bucket(mcap)
    words = dlib.money_words(mcap)
    industry = (profile.get("finnhubIndustry") or "").strip()
    first = f"**{name}** ({symbol})"
    if size:
        first += f" is {_article(size[0])} {size[0]} company"
    else:
        first += " is a company"
    if industry:
        first += f" in the {industry.lower()} industry"
    if words:
        first += f", valued by the market at {words}"
    out.append(first + (f" ({size[1]})." if size else "."))

    price = (quote or {}).get("c") or None
    if price:
        day = (quote or {}).get("dp")
        line = f"It last traded at ${price:,.2f}" + (f" ({day:+.2f}% today)" if day is not None else "")
        if stats and stats.get("from_high") is not None:
            fh = stats["from_high"]
            line += ", at its 52-week high" if fh > -0.005 else f", {pc(abs(fh), 0)} below its 52-week high"
        out.append(line + ".")

    pe = dlib.metric(metrics, "pe")
    if pe is not None and pe > 0:
        tone = "a modest price" if pe <= 20 else "a demanding price that assumes strong growth" if pe > 40 else "a middle-of-the-road price"
        out.append(f"At a P/E of {pe:.1f}, investors pay about ${pe:.0f} for each $1 of yearly profit: {tone} by common rules of thumb.")
    elif dlib.metric(metrics, "net_margin") is not None and dlib.metric(metrics, "net_margin") < 0:
        out.append("It is not profitable over the past 12 months, so there is no P/E to judge the price by.")

    g, nm = dlib.metric(metrics, "rev_growth"), dlib.metric(metrics, "net_margin")
    bits = []
    if g is not None:
        bits.append(f"sales {'grew' if g >= 0 else 'shrank'} {abs(g):.1f}% over the past year")
    if nm is not None:
        bits.append(f"it keeps about {nm:.0f}¢ of profit from each sales dollar" if nm >= 0 else f"it loses about {abs(nm):.0f}¢ on each sales dollar")
    if bits:
        out.append("The business: " + " and ".join(bits) + ".")

    if stats:
        parts = []
        if stats.get("1Y") is not None:
            parts.append(f"{pc(stats['1Y'], 0, True)} over the past year (dividends included)")
        if stats.get("volatility") is not None:
            parts.append(f"swinging about {pc(stats['volatility'], 0)} a year")
        if parts:
            line = "Its price has done " + ", ".join(parts)
            if stats.get("max_drawdown") is not None and stats.get("years_of_history", 0) >= 2:
                line += f". The worst fall from a peak in the past five years was {pc(abs(stats['max_drawdown']), 0)}"
            out.append(line + ".")
    return out


def analyst_line(trends: list[dict] | None) -> str | None:
    import brief_lib as bl
    import idea_lib as il
    if not trends:
        return None
    score = bl.analyst_score(trends[0])
    if score is None:
        return None
    n = sum((trends[0].get(k, 0) or 0) for k in ("strongBuy", "buy", "hold", "sell", "strongSell"))
    shift = bl.analyst_shift(trends)
    note = f", {shift['direction']} than last month" if shift and shift["direction"] != "little changed" else ""
    return f"Analyst consensus ({n} analysts): **{il.consensus_verdict(score)}** (score {score:+.2f} of ±2{note}). Analysts tend to skew bullish and lag the price."


def bottom_line(ev: dict, trends: list[dict] | None) -> list[str]:
    n_pro, n_con, cov = len(ev["pros"]), len(ev["cons"]), ev["covered"]
    if cov < 3:
        return ["There isn't enough data on this ticker for a meaningful read."]
    avg = ev["avg"] or 0
    lean = "lean positive" if avg >= 0.3 else "lean cautious" if avg <= -0.1 else "are mixed"
    pos = f"{n_pro} positive" + ("" if n_pro == 1 else "s")
    cau = f"{n_con} caution" + ("" if n_con == 1 else "s")
    out = [f"The screen found **{pos}** and **{cau}** across {cov} measures, so the numbers {lean}. "
           "That describes the past and says nothing about what the stock does next."]
    a = analyst_line(trends)
    if a:
        out.append(a)
    out.append("A reasonable next step is to read the company's latest earnings summary, compare it with a rival, and decide how much of your "
               "money one company should be. A diversified fund holds this company and hundreds of others.")
    return out


def fits_you(symbol: str, held: dict | None) -> list[str]:
    if held is None:
        return []
    if held["held"]:
        w = held["weight"]
        line = f"You already own {symbol}: it is about **{w:.0f}%** of your invested money."
        if w >= 20:
            line += " That is a big share for a single company: if it fell 30%, your total would fall roughly " f"{w * 0.3:.0f}%."
        return [line]
    return [f"You don't hold {symbol}. Adding it would diversify you further only if it behaves differently from what you own; the Risk tab shows how your holdings move together."]


def fund_summary(symbol: str, quote: dict | None, stats: dict | None, kind: str = "fund") -> list[str]:
    if kind == "fund":
        out = [f"**{symbol}** looks like a fund or ETF rather than a single company, so company measures (P/E, margins, debt) don't apply. "
               "Below: its price history, risk and dividends."]
    else:
        out = [f"Company numbers for **{symbol}** aren't available right now (no Finnhub key, an unknown ticker, or the free plan's per-minute limit). "
               "Price history and risk are still shown below."]
    price = (quote or {}).get("c")
    if price:
        out.append(f"It last traded at ${price:,.2f}.")
    if stats:
        bits = []
        if stats.get("1Y") is not None:
            bits.append(f"{pc(stats['1Y'], 1, True)} over the past year")
        if stats.get("3Y") is not None:
            bits.append(f"{pc(stats['3Y'], 1, True)} a year over three years")
        if bits:
            out.append("Returns with dividends reinvested: " + ", ".join(bits) + ".")
        if stats.get("max_drawdown") is not None:
            out.append(f"Its worst fall from a peak in the past five years was {pc(abs(stats['max_drawdown']), 0)}.")
    return out


def write_summary(symbol: str, *, profile=None, quote=None, metrics=None, ev=None, stats=None, trends=None, held=None, fund=False) -> list[tuple[str, list[str]]]:
    if fund or ev is None:
        return [("In plain words", fund_summary(symbol, quote, stats, "fund" if fund else "nodata")), ("Worth knowing", worth_knowing())]
    sections = [("In plain words", in_plain_words(symbol, profile, quote, metrics, stats))]
    sections.append(("What looks good", [f"**{lab}:** {t}" for lab, t in ev["pros"]] or ["Nothing stood out as a clear positive on these measures."]))
    sections.append(("What to watch", [f"**{lab}:** {t}" for lab, t in ev["cons"]] +
                     ["**Always:** one company can fall much further than a diversified fund, and these numbers look backward."]))
    sections.append(("Bottom line", bottom_line(ev, trends)))
    me = fits_you(symbol, held)
    if me:
        sections.append(("How it fits you", me))
    sections.append(("Worth knowing", worth_knowing()))
    return sections


def worth_knowing() -> list[str]:
    return [
        "Company numbers come from Finnhub's free data and price history from Yahoo Finance. Either can be delayed, incomplete, or occasionally wrong.",
        "Good/OK/Watch labels are rules of thumb. Fair levels differ by industry (a bank and a software firm are not comparable on debt or margins).",
        "This is research, not advice or a recommendation. No screen can tell you what a stock will do next.",
    ]
