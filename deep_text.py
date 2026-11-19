"""
Plain-English write-up for the Stock Deep-Dive. Rules only, no AI: every sentence comes from a number on the page.
Returns [(section title, [bullets])]. Bullets may contain **bold** and "$" (the page escapes them for Markdown).
"""

from __future__ import annotations

import deep_lib as dlib
import fit_lib as fl
import hold_lib as hl
import score_lib as sl


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


def _length(days: int) -> str:
    months = round(days / 30.4)
    return f"{months} months" if months < 24 else f"{days / 365.25:.1f} years"


def holding_summary(symbol: str, h: dict | None, windows: list[dict] | None, recov: dict | None,
                    div: dict | None = None, held: dict | None = None, fund: bool = False) -> list[str]:
    """Plain-words bullets for the "How long to hold it" section. Percent-only for holdings."""
    if not h:
        return ["There isn't enough price history to say how long this has needed to be held. Newer companies and funds have a short record."]
    out = [f"**Planning window: {h['text']}** ({h['style'].lower()}). Think of it as money you won't need for at least {h['low']} years. "
           "It is not a prediction, and not a date to sell."]
    out.append(f"**Why:** {symbol} has been {h['tier']}" + (" (as a fund)" if fund else "") + ". " + "; ".join(h["why"]).capitalize() + ".")
    ws = windows or []
    if ws:
        bits = ", ".join(f"{w['years']} year{'s' if w['years'] > 1 else ''}: {w['share_gain'] * 100:.0f}%" for w in ws)
        out.append(f"**History:** how often holding it for a stretch ended in a gain (dividends included): {bits}.")
        long = ws[-1]
        out.append(f"The worst {long['years']}-year stretch ended {pc(long['worst_total'], 0, True)} overall; the typical one {pc(long['median_total'], 0, True)}. "
                   "The stretches overlap and come from one period, so treat them as a feel for the range.")
    else:
        out.append("**History:** not enough price history to test 1, 3 or 5-year holding periods yet.")
    eps = (recov or {}).get("episodes") or []
    if eps:
        e = eps[0]
        if e["recovered"] is not None:
            out.append(f"**Recovery:** its deepest fall ({pc(e['depth'], 0)}, from {e['peak']:%b %Y}) took about {_length(e['total_days'])} to get back to the old high.")
        else:
            out.append(f"**Recovery:** its deepest fall ({pc(e['depth'], 0)}, from {e['peak']:%b %Y}) has not been fully recovered yet. Waiting is not guaranteed to work.")
    elif recov and recov.get("longest_days") is None:
        out.append("**Recovery:** no fall deeper than 15% in the past ten years (or the record is too short to say).")
    if h.get("small_slice"):
        line = f"**Size:** because it swings this much, many people keep a single stock like this to about {hl.SIZE_NOTE_PCT}% of invested money, so one bad stretch doesn't decide the whole portfolio."
        if held and held.get("held") and held.get("weight") is not None and held["weight"] > hl.SIZE_NOTE_PCT:
            line += f" You hold {held['weight']:.0f}% of invested money in it."
        out.append(line)
    if not fund and div and div.get("active") and (div.get("streak") or 0) >= 5:
        out.append(f"**While you wait:** it has raised its dividend {div['streak']} years in a row, which pays you along the way (it can still be cut).")
    elif not fund and div is not None and not div.get("active"):
        out.append("**While you wait:** it pays no regular dividend, so the whole return depends on the price.")
    out.append("**Long is not forever:** a long hold only works while the business stays healthy. The list below says what to re-check.")
    return out


def score_summary(symbol: str, sc: dict | None, fund: bool = False) -> list[str]:
    """Plain-words bullets for the scorecard."""
    if fund:
        return ["Funds and ETFs aren't scored: the scorecard grades company numbers, and a fund is a basket of companies. See the price tab for how it has moved."]
    if not sc:
        return ["Not enough company data to score this one fairly (it needs at least three of the five areas). The Key numbers tab shows what is available."]
    out = [f"**Scorecard: {sc['score']} out of 100 ({sc['label']}).** An average of {len(sc['areas'])} areas built from {sc['n_measures']} measures."]
    top = max(sc["areas"], key=lambda a: a["score"])
    low = min(sc["areas"], key=lambda a: a["score"])
    if top is not low and top["score"] != low["score"]:
        out.append(f"**Strongest area: {top['name']}** ({top['score']:.0f}). **Weakest: {low['name']}** ({low['score']:.0f}).")
    else:
        out.append("All areas scored about the same.")
    worst = [f"{lab} ({a['name']})" for a in sc["areas"] for lab in a["worst"]]
    if worst:
        out.append("Marked Watch: " + ", ".join(worst[:5]) + (f" and {len(worst) - 5} more" if len(worst) > 5 else "") + ".")
    if sc["missing"]:
        out.append("Not scored (no data): " + ", ".join(sc["missing"]) + ". The score is an average of what was available.")
    out.append("It ranks these numbers against rules of thumb. It is not a forecast and not a recommendation.")
    return out


def fit_summary(symbol: str, rows: list[dict], summ: dict) -> list[str]:
    """Plain-words bullets for the fit check, using YOUR rules."""
    if not rows:
        return ["Turn on at least one rule in the Fit for you tab."]
    if summ["checked"] == 0:
        return ["None of your rules could be checked with the data available for this ticker."]
    out = [f"**{summ['verdict']}:** {symbol} meets {summ['pass']} of the {summ['checked']} rules that could be checked"
           + (f" ({summ['unknown']} couldn't be checked)." if summ["unknown"] else ".")]
    fails = [r for r in rows if r["result"] == "fail"]
    if fails:
        out.append("**Doesn't meet:** " + "; ".join(f"{r['rule'].lower()} (yours: {r['yours']}, this stock: {r['stock']})" for r in fails) + ".")
    unk = [r for r in rows if r["result"] == "unknown"]
    if unk:
        out.append("**Couldn't check:** " + ", ".join(r["rule"].lower() for r in unk) + ".")
    out.append("These are your own rules, so this describes the match. It is not a recommendation, and a stock can miss a rule and still be right for someone else.")
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
