"""
Plain-English market summary, written by rules from the numbers (no AI). Returns [(title, [bullets])].
Percent only; describes what has happened, never predicts. Bullets are Markdown-safe (no dollar signs).
"""

from __future__ import annotations

import datetime as dt

import pandas as pd

import market_lib as ml


def pc(x: float | None, digits: int = 1, signed: bool = False) -> str:
    if x is None or pd.isna(x):
        return "n/a"
    v = x * 100
    if round(abs(v), digits) == 0:
        v = 0.0
    return f"{v:+.{digits}f}%" if signed else f"{v:.{digits}f}%"


def pp(x: float, digits: int = 2) -> str:
    """Percentage points, e.g. 'up 0.15 percentage points'."""
    word = "up" if x > 0 else "down"
    return f"{word} {abs(x):.{digits}f} percentage points"


def _move(name: str, r: float | None) -> str | None:
    if r is None or pd.isna(r):
        return None
    if abs(r) < 0.0005:
        return f"{name} was little changed"
    return f"{name} {'rose' if r > 0 else 'fell'} {pc(abs(r))}"


def _date(d) -> str:
    d = pd.Timestamp(d)
    return d.strftime("%b ") + str(d.day)


def short_version(idx: dict[str, float | None], latest, sp: dict | None, vix: float | None, ten: dict | None) -> list[str]:
    out = []
    names = list(idx)
    first = _move(names[0], idx[names[0]]) if names else None
    if first:
        rest = [f"{n} {pc(idx[n], signed=True)}" for n in names[1:] if idx.get(n) is not None and not pd.isna(idx[n])]
        out.append(f"In the latest session ({_date(latest)}), {first.replace(names[0], 'the ' + names[0], 1)}." + (f" {', '.join(rest[:-1])}{' and ' if len(rest) > 1 else ''}{rest[-1]}." if rest else ""))
    if sp and sp.get("vs200") is not None:
        v200 = sp["vs200"]
        where = f"{pc(abs(v200))} {'above' if v200 >= 0 else 'below'} its 200-day average"
        high = f" and {pc(abs(sp['from_high']))} below its 52-week high" if sp.get("from_high") is not None and sp["from_high"] <= -0.0005 else (
            " and at its 52-week high" if sp.get("from_high") is not None else "")
        desc = {"up": "It is above both its 50-day and 200-day averages, which is an uptrend.",
                "down": "It is below both its 50-day and 200-day averages, which is a downtrend.",
                "mixed": "It is on different sides of its 50-day and 200-day averages, which gives mixed signals."}.get(sp.get("trend"), "")
        out.append(f"The S&P 500 is {where}{high}. " + (desc + " " if desc else "") + "Averages lag, so this describes where it has been, not where it is going.")
    reg = ml.vix_regime(vix)
    if reg:
        out.append(f"The VIX, the market's expected-volatility gauge, is {vix:.1f}: **{reg[0].lower()}** ({reg[1]}; its long-run average is roughly 20).")
    if ten and ten.get("level") is not None:
        chg = ten.get("m1")
        tail = f", {pp(chg)} over the past month" if chg is not None and abs(chg) >= 0.005 else ", about unchanged over the past month" if chg is not None else ""
        out.append(f"The 10-year Treasury yield is {ten['level']:.2f}%{tail}. It is the base for many other interest rates.")
    return out or ["Not enough market data loaded to summarize."]


def under_the_surface(table: pd.DataFrame | None, br: tuple[int, int] | None, od: dict | None, spread: float | None,
                      y_short: float | None, y_long: float | None) -> list[str]:
    out = []
    if table is not None and not table.empty:
        best, worst = table.iloc[0], table.iloc[-1]
        line = f"Over the past month, **{best['Sector']}** led ({pc(best['1M'], signed=True)}) and **{worst['Sector']}** lagged ({pc(worst['1M'], signed=True)})."
        if br:
            line += f" {br[0]} of {br[1]} sectors rose."
        out.append(line)
    if od:
        gap = od["gap"] * 100
        if abs(gap) < 1:
            out.append("Growth-oriented sectors (technology, consumer discretionary, communication) and defensive ones (staples, utilities, health care) are moving about together over the past month.")
        else:
            lead, lag = ("Growth-oriented sectors (technology, consumer discretionary, communication)", "defensive ones (staples, utilities, health care)") if gap > 0 else (
                "Defensive sectors (staples, utilities, health care)", "growth-oriented ones (technology, consumer discretionary, communication)")
            out.append(f"{lead} are ahead of {lag} by {abs(gap):.1f} percentage points over the past month.")
    lab = ml.curve_label(spread)
    if lab:
        rel = "about the same as" if abs(spread) < 0.005 else "below" if spread < 0 else "above"
        base = f"The yield curve is **{lab}**: the 10-year yield ({y_long:.2f}%) is {rel} the 3-month ({y_short:.2f}%)."
        if lab == "inverted":
            base += " Inverted curves have often come before recessions, though the timing has varied widely."
        out.append(base)
    return out


def coming_up(events: list[dict], today: dt.date) -> list[str]:
    """First upcoming event of each kind, in plain words."""
    out = []
    labels = {"Fed": "Next Fed decision", "Earnings": "Next earnings report", "Ex-dividend": "Next ex-dividend date (estimated)", "Market closed": "Next market closure"}
    for kind in ("Fed", "Earnings", "Ex-dividend", "Market closed"):
        c = [e for e in events if e["type"] == kind and pd.Timestamp(e["date"]).date() >= today]
        if not c:
            continue
        e = min(c, key=lambda x: pd.Timestamp(x["date"]))
        n = (pd.Timestamp(e["date"]).date() - today).days
        when = "today" if n == 0 else "tomorrow" if n == 1 else f"in {n} days"
        title = e["title"].replace(" reports earnings", "").replace(" ex-dividend (estimated)", "").replace("FOMC interest-rate decision", "FOMC rate decision")
        out.append(f"{labels[kind]}: **{title}**, {_date(e['date'])} ({when}).")
    return out or ["Nothing from your watchlist or the built-in calendar falls in this window."]


def write_summary(*, idx, latest, sp, vix, ten, table=None, br=None, od=None, spread=None, y_short=None, y_long=None,
                  events=None, today=None) -> list[tuple[str, list[str]]]:
    sections = [("The short version", short_version(idx, latest, sp, vix, ten))]
    surface = under_the_surface(table, br, od, spread, y_short, y_long)
    if surface:
        sections.append(("Under the surface", surface))
    if events is not None and today is not None:
        sections.append(("Coming up", coming_up(events, today)))
    sections.append(("Worth knowing", [
        "Prices come from Yahoo Finance and can be delayed by about 15 minutes. Percent changes compare the latest close with earlier closes.",
        "This describes what has already happened. It says nothing about what happens next, and it is not financial advice.",
    ]))
    return sections
