"""
Free, rule-based "written brief". No AI, no network, no Streamlit.

It reads the same numbers the Daily Brief page already shows and turns them into
plain sentences that answer "so what?": how you did against the market, what
actually drove it, whether price and analysts disagree, where earnings risk sits,
and what has no explanation yet. Every sentence is built from a number on the page;
nothing here predicts anything.
"""

from __future__ import annotations

import re
from typing import Any

import pandas as pd

Section = tuple[str, list[str]]


def clean(text: str, limit: int = 110) -> str:
    """External text (headlines) goes into markdown: strip anything that could format or link."""
    t = re.sub(r"<[^>]*>", " ", str(text or ""))
    t = re.sub(r"(https?://|www\.)\S+", "", t)
    t = re.sub(r"[\[\]()<>*_`~|#\\]", "", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t if len(t) <= limit else t[: limit - 1].rstrip() + "…"


def _pp(x: float) -> str:
    return f"{x:+.2f} pp"


def _pct(x: float, d: int = 1) -> str:
    return f"{x:+.{d}f}%"


def _nonnull(x: Any) -> bool:
    return x is not None and not pd.isna(x)


def bottom_line(quotes, weights, contrib, move_pct, coverage, benchmark_pct, held) -> list[str]:
    out: list[str] = []
    priced = {s: q for s, q in quotes.items() if q and q.get("c") and _nonnull(q.get("dp"))}
    if not priced:
        return ["No live quotes came back, so there is nothing to summarize yet."]

    if held and move_pct is not None:
        word = "up" if move_pct >= 0 else "down"
        line = f"Your portfolio is **{word} {abs(move_pct):.2f}%** today (estimate from live quotes)."
        if benchmark_pct is not None:
            diff = move_pct - benchmark_pct
            mkt = f"The S&P 500 (via SPY) is {_pct(benchmark_pct, 2)}"
            if abs(diff) < 0.15:
                line += f" {mkt}, so you are roughly in line with the market."
            else:
                line += f" {mkt}, so you are **{'ahead of' if diff > 0 else 'behind'} it by {abs(diff):.2f} pp**."
        out.append(line)
        if coverage is not None and coverage < 0.8:
            out.append(f"Heads up: only {coverage * 100:.0f}% of your invested value had a live quote, so treat that figure as rough.")
    else:
        avg = sum(q["dp"] for q in priced.values()) / len(priced)
        line = f"Your {len(priced)} tickers moved **{_pct(avg, 2)}** on average today (simple average, not weighted by what you own)."
        if benchmark_pct is not None:
            line += f" The S&P 500 (via SPY) is {_pct(benchmark_pct, 2)}."
        out.append(line)

    ups = sum(1 for q in priced.values() if q["dp"] > 0)
    downs = sum(1 for q in priced.values() if q["dp"] < 0)
    out.append(f"Breadth: **{ups} up, {downs} down**" + (f", {len(priced) - ups - downs} flat." if len(priced) - ups - downs else "."))

    if held and contrib is not None and not contrib.empty:
        c = contrib["Contribution pp"]
        gross = float(c.abs().sum())
        gain, loss = float(c[c > 0].sum()), float(c[c < 0].sum())
        top = contrib.loc[c.abs().idxmax()]
        if gross > 0:
            share = abs(float(top["Contribution pp"])) / gross * 100
            if share >= 50 and len(contrib) > 1 and share >= float(top["Share %"]) + 10:
                out.append(
                    f"**{top['Symbol']} did most of the work:** it is {top['Share %']:.0f}% of your invested money but produced "
                    f"{share:.0f}% of today's movement, because it moved {_pct(top['Move %'], 2)} ({_pp(top['Contribution pp'])} to your portfolio)."
                )
            elif float(top["Share %"]) >= 50 and len(contrib) > 1:
                out.append(
                    f"Your portfolio mostly follows **{top['Symbol']}**, which is {top['Share %']:.0f}% of your invested money. "
                    "What it does each day largely sets your day."
                )
            else:
                out.append(f"The move is spread out: no single holding accounts for more than {share:.0f}% of today's movement.")
        if gain >= 0.1 and loss <= -0.1:
            out.append(
                f"Winners added {_pp(gain)} while decliners took {_pp(loss)}. The net number hides how much was moving underneath."
            )
    return out


def movers_section(quotes, weights, contrib, benchmark_pct, threshold, news, filings, held) -> list[str]:
    priced = {s: q for s, q in quotes.items() if q and q.get("c") and _nonnull(q.get("dp"))}
    if not priced:
        return []
    impact = dict(zip(contrib["Symbol"], contrib["Contribution pp"])) if (held and contrib is not None and not contrib.empty) else {}
    big = [s for s, q in priced.items() if abs(q["dp"]) >= threshold]
    key = (lambda s: -abs(impact.get(s, 0.0))) if impact else (lambda s: -abs(priced[s]["dp"]))
    big.sort(key=key)
    if not big:
        s = max(priced, key=lambda s: abs(priced[s]["dp"]))
        return [f"A quiet day: nothing moved more than {threshold:.1f}%. The biggest mover was **{s}** at {_pct(priced[s]['dp'], 2)}."]

    out = []
    for s in big[:3]:
        mv = priced[s]["dp"]
        head = f"**{s}** {_pct(mv, 2)}"
        if weights.get(s) is not None:
            head += f" (you hold {weights[s]:.0f}% of your invested money" + (f"; {_pp(impact[s])} to your portfolio" if s in impact else "") + ")"
        why = []
        if benchmark_pct is not None:
            rel = mv - benchmark_pct
            if abs(rel) < 1.0 and (mv >= 0) == (benchmark_pct >= 0):
                why.append(f"it moved close to the market ({_pct(benchmark_pct, 2)}), so this looks mostly market-driven rather than company-specific")
            else:
                why.append(f"it {'beat' if rel > 0 else 'lagged'} the market by {abs(rel):.1f} pp, which points to something company- or sector-specific")
        items = news.get(s) or []
        fl = filings.get(s) or []
        if items:
            why.append(f"latest headline: “{clean(items[0]['headline'])}” ({clean(items[0].get('source', ''), 30)})")
        elif fl:
            why.append(f"it filed a {fl[0]['Form']} on {fl[0]['Filed']:%b %d}: {clean(fl[0]['What'], 70)}")
        else:
            why.append("no headlines or filings turned up in your lookback window, so check whether similar companies moved too before assuming it is about this company")
        out.append(head + ": " + "; ".join(why) + ".")
    if len(big) > 3:
        out.append(f"Also past your {threshold:.1f}% line: {', '.join(big[3:])}.")
    return out


def price_vs_analysts(quotes, weights, shifts, held) -> list[str]:
    out = []
    rows = []
    for s, v in (shifts or {}).items():
        if not v or v["direction"] == "little changed":
            continue
        q = quotes.get(s) or {}
        mv = q.get("dp") if q.get("c") else None
        rows.append((weights.get(s, 0.0) or 0.0, s, v, mv))
    rows.sort(key=lambda r: -r[0])
    for w, s, v, mv in rows[:3]:
        own = f", {w:.0f}% of your invested money" if held and w else ""
        base = f"Analysts turned **{v['direction']}** on **{s}** (score {v['score_before']:+.2f} → {v['score_now']:+.2f}{own})"
        if mv is not None and mv <= -1 and v["direction"] == "more bullish":
            base += f", yet the stock is {_pct(mv, 1)} today. Either the market sees something analysts do not, or this is a dip analysts are leaning into. Ratings tend to lag price."
        elif mv is not None and mv >= 1 and v["direction"] == "more bearish":
            base += f", yet the stock is {_pct(mv, 1)} today: price and analysts disagree."
        else:
            base += "."
        out.append(base)
    return out


def calendar_section(earnings: pd.DataFrame | None, weights, earnings_days, held) -> list[str]:
    if earnings is None:
        return []
    if earnings.empty:
        return [f"No earnings reports are scheduled for your tickers in the next {earnings_days} days, so fewer scheduled surprises."]
    rows = []
    for _, r in earnings.iterrows():
        rows.append((weights.get(r["Symbol"], 0.0) or 0.0, r))
    rows.sort(key=lambda x: (-x[0], x[1]["Date"]))
    out = []
    if held:
        exposed = sum(w for w, _ in rows)
        out.append(f"**{exposed:.0f}% of your invested money** reports earnings within {earnings_days} days.")
        w, r = rows[0]
        if w > 0:
            when = f"{r['Date']:%a %b %d}" + (f", {r['Timing'].lower()}" if r.get("Timing") else "") + f" (in {int(r['In (days)'])} days)"
            out.append(
                f"Biggest exposure: **{r['Symbol']}** ({w:.0f}% of your money) on {when}. Illustration only: if it moved 5% on the report, "
                f"your portfolio would move about {w * 5 / 100:.2f} pp."
            )
        rest = [f"{r['Symbol']} ({r['Date']:%b %d})" for _, r in rows[1:4]]
        if rest:
            out.append("Also coming: " + ", ".join(rest) + ".")
    else:
        out.append("Reporting soon: " + ", ".join(f"{r['Symbol']} ({r['Date']:%b %d})" for _, r in rows[:5]) + ".")
    return out


def filings_section(filings, weights) -> list[str]:
    out = []
    for s, fl in sorted((filings or {}).items(), key=lambda kv: -(weights.get(kv[0], 0.0) or 0.0)):
        eightk = [f for f in fl if f["Form"] == "8-K"]
        f4 = [f for f in fl if f["Form"] == "4"]
        bits = []
        if eightk:
            bits.append("8-K: " + "; ".join(dict.fromkeys(clean(f["What"], 60) for f in eightk[:2])))
        if f4:
            bits.append(f"{len(f4)} insider Form 4 report(s)")
        if bits:
            out.append(f"**{s}**: " + ", ".join(bits) + ".")
    if out:
        out.append("A Form 4 can be a sale, a purchase, or a routine stock award; this summary cannot tell which, so open the filing before reading anything into it.")
    return out[:5]


def worth_a_look(quotes, weights, contrib, conc, threshold, news, filings, held) -> list[str]:
    out = []
    priced = {s: q for s, q in quotes.items() if q and q.get("c") and _nonnull(q.get("dp"))}
    for s, q in sorted(priced.items(), key=lambda kv: -abs(kv[1]["dp"])):
        if abs(q["dp"]) >= threshold and not news.get(s) and not (filings or {}).get(s):
            out.append(f"Why did **{s}** move {_pct(q['dp'], 1)} with no headline or filing behind it?")
            break
    if held and conc and len(weights) > 5 and conc.get("top5") is not None and conc["top5"] >= 60 and conc.get("largest") is not None:
        out.append(
            f"Your top 5 holdings are {conc['top5']:.0f}% of your invested money (largest {conc['largest']:.0f}%). "
            "Are you comfortable with a few names, or funds that hold many, setting your results?"
        )
    missing = [s for s, q in quotes.items() if not q or not q.get("c")]
    if missing:
        out.append(f"No live price for {', '.join(missing[:5])}; those are missing from every number above.")
    return out[:3]


def write_brief(
    *, quotes, weights, contrib, move_pct, coverage, benchmark_pct, earnings, earnings_days,
    shifts, news, filings, threshold, conc, held: bool,
) -> list[Section]:
    """Sections of (title, bullets). Empty sections are dropped."""
    weights = weights or {}
    news = news or {}
    filings = filings or {}
    sections: list[Section] = [
        ("Bottom line", bottom_line(quotes, weights, contrib, move_pct, coverage, benchmark_pct, held)),
        ("What drove it", movers_section(quotes, weights, contrib, benchmark_pct, threshold, news, filings, held)),
        ("Price vs. analysts", price_vs_analysts(quotes, weights, shifts, held)),
        ("Coming up", calendar_section(earnings, weights, earnings_days, held)),
        ("Paper trail", filings_section(filings, weights)),
        ("Worth a closer look", worth_a_look(quotes, weights, contrib, conc, threshold, news, filings, held)),
    ]
    return [(t, b) for t, b in sections if b]
