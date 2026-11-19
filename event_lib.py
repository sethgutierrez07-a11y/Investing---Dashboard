"""
Calendar and market-clock logic for the Market page. Pure functions, no Streamlit, no network.

Built-in dates (as of Nov 2026), checked against the Federal Reserve's published meeting calendar and
the NYSE holiday calendar:
  * FOMC rate decisions from Dec 2026 through Sep 2027. Later 2027 meetings are left out on purpose:
    the Fed re-published its 2027 schedule in Nov 2026 and sources disagreed about the last ones.
  * NYSE/Nasdaq full-day closures and early closes through 2027.
The page says how far the built-in list reaches, and drops dates once they pass.

Earnings dates come from Finnhub and ex-dividend dates are estimated from each company's own payment
history; this module only merges them into one timeline.
"""

from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

import pandas as pd

ET = ZoneInfo("America/New_York")
COVERS_THROUGH = dt.date(2027, 12, 31)       # holiday list
FED_COVERS_THROUGH = dt.date(2027, 9, 30)    # FOMC list
OPEN_T, CLOSE_T, EARLY_CLOSE_T = dt.time(9, 30), dt.time(16, 0), dt.time(13, 0)

# (decision day, meeting days, has new projections)
FOMC = [
    (dt.date(2026, 12, 9), "Dec 8–9", True),
    (dt.date(2027, 1, 27), "Jan 26–27", False),
    (dt.date(2027, 3, 17), "Mar 16–17", True),
    (dt.date(2027, 4, 28), "Apr 27–28", False),
    (dt.date(2027, 6, 9), "Jun 8–9", True),
    (dt.date(2027, 7, 28), "Jul 27–28", False),
    (dt.date(2027, 9, 15), "Sep 14–15", True),
]

# date -> (name, kind) where kind is "closed" or "early" (1:00 PM ET close)
CLOSURES = {d: v for d, v in [
    (dt.date(2026, 11, 26), ("Thanksgiving Day", "closed")),
    (dt.date(2026, 11, 27), ("Day after Thanksgiving", "early")),
    (dt.date(2026, 12, 24), ("Christmas Eve", "early")),
    (dt.date(2026, 12, 25), ("Christmas Day", "closed")),
    (dt.date(2027, 1, 1), ("New Year's Day", "closed")),
    (dt.date(2027, 1, 18), ("Martin Luther King Jr. Day", "closed")),
    (dt.date(2027, 2, 15), ("Presidents' Day", "closed")),
    (dt.date(2027, 3, 26), ("Good Friday", "closed")),
    (dt.date(2027, 5, 31), ("Memorial Day", "closed")),
    (dt.date(2027, 6, 18), ("Juneteenth (observed)", "closed")),
    (dt.date(2027, 7, 5), ("Independence Day (observed)", "closed")),
    (dt.date(2027, 9, 6), ("Labor Day", "closed")),
    (dt.date(2027, 11, 25), ("Thanksgiving Day", "closed")),
    (dt.date(2027, 11, 26), ("Day after Thanksgiving", "early")),
    (dt.date(2027, 12, 24), ("Christmas Day (observed)", "closed")),
]}

TYPES = ["Earnings", "Ex-dividend", "Fed", "Market closed"]
TYPE_ICON = {"Earnings": "📣", "Ex-dividend": "💵", "Fed": "🏛️", "Market closed": "🔔"}


def _t(t: dt.time) -> str:
    return f"{t.strftime('%I:%M %p').lstrip('0')} ET"


def is_trading_day(d: dt.date) -> bool:
    c = CLOSURES.get(d)
    return d.weekday() < 5 and not (c and c[1] == "closed")


def next_trading_day(d: dt.date) -> dt.date:
    d += dt.timedelta(days=1)
    for _ in range(14):
        if is_trading_day(d):
            return d
        d += dt.timedelta(days=1)
    return d


def market_status(now: dt.datetime | None = None) -> dict:
    """{state: open|pre|after|closed, label, tone}. Regular hours only; extended hours are not modelled."""
    now = (now or dt.datetime.now(dt.timezone.utc)).astimezone(ET)
    d, t = now.date(), now.time()
    covered = d <= COVERS_THROUGH
    closure = CLOSURES.get(d)

    def nxt() -> str:
        n = next_trading_day(d)
        when = "tomorrow" if (n - d).days == 1 else n.strftime("%a %b %d").replace(" 0", " ")
        return f"opens {when} at {_t(OPEN_T)}"

    if d.weekday() >= 5:
        return {"state": "closed", "label": f"US market closed (weekend) · {nxt()}", "tone": "off", "covered": covered}
    if closure and closure[1] == "closed":
        return {"state": "closed", "label": f"US market closed for {closure[0]} · {nxt()}", "tone": "off", "covered": covered}
    close_t = EARLY_CLOSE_T if (closure and closure[1] == "early") else CLOSE_T
    if t < OPEN_T:
        return {"state": "pre", "label": f"US market not open yet · opens {_t(OPEN_T)}", "tone": "warn", "covered": covered}
    if t < close_t:
        extra = " (early close)" if close_t == EARLY_CLOSE_T else ""
        return {"state": "open", "label": f"US market open · closes {_t(close_t)}{extra}", "tone": "ok", "covered": covered}
    return {"state": "after", "label": f"US market closed for the day · {nxt()}", "tone": "off", "covered": covered}


# ---------------------------------------------------------------- events
def _event(date, kind, title, detail="") -> dict:
    return {"date": date, "type": kind, "title": title, "detail": detail}


def builtin_events(today: dt.date, days: int) -> list[dict]:
    end = today + dt.timedelta(days=days)
    out = []
    for decision, meeting, sep in FOMC:
        if today <= decision <= end:
            out.append(_event(decision, "Fed", "FOMC interest-rate decision",
                              f"Meeting {meeting}, announced 2:00 PM ET" + (" · with new projections" if sep else "")))
    for d, (name, kind) in CLOSURES.items():
        if today <= d <= end:
            out.append(_event(d, "Market closed", f"{name}: " + ("US markets closed" if kind == "closed" else "US markets close early"),
                              "" if kind == "closed" else "1:00 PM ET close"))
    return out


def earnings_events(df: pd.DataFrame | None) -> list[dict]:
    """From brief_lib.filter_earnings(): Symbol, Date, Timing, EPS est."""
    out = []
    if df is None or df.empty:
        return out
    for _, r in df.iterrows():
        bits = [str(r.get("Timing") or "").strip()]
        eps = r.get("EPS est.")
        if eps is not None and not pd.isna(eps):
            bits.append(f"EPS est. {float(eps):.2f}")
        out.append(_event(r["Date"], "Earnings", f"{r['Symbol']} reports earnings", " · ".join(b for b in bits if b)))
    return out


def exdividend_events(proj: pd.DataFrame | None, today: dt.date, days: int) -> list[dict]:
    """From dividend_lib.project_payments(): estimated ex-dividend dates inside the window."""
    out = []
    if proj is None or proj.empty:
        return out
    end = today + dt.timedelta(days=days)
    for _, r in proj.iterrows():
        d = pd.Timestamp(r["ExDate"]).date()
        if today <= d <= end:
            out.append(_event(d, "Ex-dividend", f"{r['Symbol']} ex-dividend (estimated)", f"about ${float(r['PerShare']):.2f} per share"))
    return out


def build_timeline(events: list[dict], today: dt.date, days: int, kinds: list[str] | None = None) -> pd.DataFrame:
    """One chronological table. Dates outside [today, today+days] and unwanted types are dropped."""
    end = today + dt.timedelta(days=days)
    rows = []
    for e in events:
        d = pd.Timestamp(e["date"]).date()
        if not (today <= d <= end) or (kinds is not None and e["type"] not in kinds):
            continue
        rows.append({"Date": d, "Day": d.strftime("%a"), "In (days)": (d - today).days, "Type": f"{TYPE_ICON.get(e['type'], '')} {e['type']}".strip(),
                     "Event": e["title"], "Details": e["detail"], "_o": TYPES.index(e["type"]) if e["type"] in TYPES else 9})
    cols = ["Date", "Day", "In (days)", "Type", "Event", "Details"]
    if not rows:
        return pd.DataFrame(columns=cols)
    df = pd.DataFrame(rows).sort_values(["Date", "_o", "Event"]).drop(columns="_o").reset_index(drop=True)
    return df[cols]


def next_event(events: list[dict], today: dt.date, kind: str) -> dict | None:
    c = [e for e in events if e["type"] == kind and pd.Timestamp(e["date"]).date() >= today]
    return min(c, key=lambda e: pd.Timestamp(e["date"])) if c else None
