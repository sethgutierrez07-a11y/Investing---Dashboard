"""
Written dividend summary, by rules. No AI and no network: every sentence is picked and filled in
from the numbers computed on the page, so it only says what the data supports.

write_summary(...) -> [(title, [bullet, ...]), ...]  (rendered as tabs)
"""

from __future__ import annotations

from typing import Any

import pandas as pd

HIDDEN = "$•••"


def money(x: float | None, hide: bool = False) -> str:
    if x is None or pd.isna(x):
        return "—"
    return HIDDEN if hide else f"${x:,.0f}"


def md(text: str) -> str:
    """Streamlit renders $...$ as math, so dollar signs are escaped before going into markdown."""
    return text.replace("$", "\\$")


def usd(x: float) -> str:
    """For hypothetical replays (a made-up $10,000), which are not your private numbers."""
    return f"${x:,.0f}"


def day(ts: Any) -> str:
    return pd.Timestamp(ts).strftime("%b %-d")


def join(items: list[str]) -> str:
    items = list(items)
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


# --------------------------------------------------------------------------
def bottom_line(income: dict, port: dict, table: pd.DataFrame, activity_ok: bool, hide: bool) -> list[str]:
    out: list[str] = []
    if port["payers"] == 0:
        out.append(
            f"None of your {port['holdings']} holdings shows a regular dividend in its payment history, so there is no "
            "dividend income to project. For these holdings, all the return comes from the price."
        )
    else:
        line = (f"Your holdings are set up to pay about {money(port['annual'], hide)} over the next 12 months "
                f"(roughly {money(port['monthly'], hide)} a month), a {port['yield_pct']:.1f}% yield on what you have invested. "
                f"{port['payers']} of your {port['holdings']} holdings pay.")
        if port["yoc_pct"] is not None and abs(port["yoc_pct"] - port["yield_pct"]) >= 0.3:
            line += (f" Measured against what you originally paid for the payers, the yield is {port['yoc_pct']:.1f}% "
                     "(yield on cost).")
        out.append(line)

    if income["full_year"] and income["n"]:
        line = f"Over the last 12 months, {money(income['ttm'], hide)} of dividends actually arrived."
        if income["growth_pct"] is not None:
            way = "up" if income["growth_pct"] >= 0 else "down"
            line += f" That is {way} {abs(income['growth_pct']):.0f}% from the 12 months before."
        if port["annual"] > 0 and income["ttm"] > 0 and port["annual"] > income["ttm"] * 1.15:
            line += (" The forward figure is higher because it uses today's share counts and the latest payouts; "
                     "it is an estimate, not a forecast.")
        out.append(line)
    elif income["n"]:
        out.append(
            f"SnapTrade's activity feed only reaches back to {day(income['first'])}, so just {income['covered_days']} days of "
            f"history were counted ({money(income['ttm'], hide)} received). Trailing-year and growth figures need a full year."
        )
    elif not activity_ok:
        out.append("The activity feed couldn't be read, so received amounts are missing. Everything shown as expected "
                   "comes from each ticker's own payment history, not from your statements.")
    else:
        out.append("No dividend payments came back from SnapTrade's activity feed. Expected income below comes from each "
                   "ticker's own payment history, not from your statements.")

    if port["top"] and port["payers"] >= 2 and port["top_weight"] is not None:
        t, s, w = port["top"], port["top_share"], port["top_weight"]
        if s >= w + 10:
            out.append(f"{t} supplies {s:.0f}% of your dividend income while being {w:.0f}% of what you have invested, "
                       "so your income leans on it more than its size suggests.")
        elif s <= w - 10:
            out.append(f"{t} is {w:.0f}% of what you have invested but only {s:.0f}% of your dividend income, so more of "
                       "its return is coming from the price.")
        else:
            out.append(f"{t} is your biggest dividend source at {s:.0f}% of income, in line with its {w:.0f}% share of "
                       "what you have invested.")
        if port["effective_sources"] and port["effective_sources"] < 1.5:
            out.append("Dividend-wise your income is close to a single source, so a cut there would move the whole total.")
    return out


def where_from(table: pd.DataFrame, hide: bool) -> list[str]:
    out: list[str] = []
    if table.empty:
        return out
    held = table[table["Held"]]
    payers = held[held["Annual income"] > 0].sort_values("Annual income", ascending=False)
    if not payers.empty:
        parts = []
        for _, r in payers.head(3).iterrows():
            y = f", {r['Yield %']:.1f}% yield" if pd.notna(r["Yield %"]) else ""
            parts.append(f"{r['Symbol']} {money(r['Annual income'], hide)} a year ({r['Income share %']:.0f}% of income{y})")
        out.append("Biggest sources: " + "; ".join(parts) + ".")
        classes = payers.groupby("Class")["Annual income"].sum()
        tot = float(classes.sum())
        etf = float(classes.get("ETF", 0.0) + classes.get("Fund", 0.0))
        stock = float(classes.get("Stock", 0.0))
        if tot > 0 and etf > 0 and stock > 0:
            out.append(f"{etf / tot * 100:.0f}% of the income comes from ETFs and funds, {stock / tot * 100:.0f}% from "
                       "individual stocks.")
        high = payers.dropna(subset=["Yield %"]).sort_values("Yield %", ascending=False)
        if not high.empty:
            r = high.iloc[0]
            if r["Yield %"] >= 4 and r["Yield %"] >= 2 * max(table.attrs.get("port_yield", 0.0), 0.1):
                out.append(f"{r['Symbol']}'s {r['Yield %']:.1f}% yield is far above the rest. A yield that high can mean the "
                           "price has fallen, so look at why before counting on it.")
    nonpay = held[(held["Status"] == "No dividend") & (held["Share of invested %"].fillna(0) >= 10)]
    if not nonpay.empty:
        out.append(join([f"{r['Symbol']} ({r['Share of invested %']:.0f}% of invested)" for _, r in nonpay.iterrows()])
                   + (" pays no dividend: its return is all price." if len(nonpay) == 1 else " pay no dividend: their return is all price."))
    stopped = held[held["Status"] == "Stopped"]
    if not stopped.empty:
        out.append(join(list(stopped["Symbol"])) + (" appears" if len(stopped) == 1 else " appear")
                   + " to have stopped paying, so nothing is projected from it.")
    sold = table[table["Status"] == "Sold"]
    if not sold.empty:
        out.append(join([f"{r['Symbol']} ({money(r['Received 12m'], hide)})" for _, r in sold.iterrows()])
                   + " paid you in the last year but is no longer held, so that income won't repeat.")
    return out


def coming_up(proj: pd.DataFrame, table: pd.DataFrame, hide: bool) -> list[str]:
    out: list[str] = []
    if proj.empty:
        return ["No upcoming dividends could be projected. Either nothing you hold pays on a regular schedule, "
                "or the payment histories couldn't be loaded."]
    nxt = proj.head(3)
    out.append("Next up: " + "; ".join(f"{r['Symbol']} about {money(r['Amount'], hide)} around {day(r['PayDate'])}"
                                       for _, r in nxt.iterrows()) + ". Dates are estimates (ex-dividend date plus your usual delay).")
    by_m = proj.groupby(proj["PayDate"].dt.to_period("M"))["Amount"].sum()
    if len(by_m) >= 2:
        best, worst = by_m.idxmax(), by_m.idxmin()
        out.append(f"Busiest month: {best.strftime('%B')} (about {money(by_m.max(), hide)}). Lightest month with a payment: "
                   f"{worst.strftime('%B')} (about {money(by_m.min(), hide)}). Income lands in {len(by_m)} of the next 12 months.")
    out.append("These use each ticker's latest per-share payout and today's share counts. They assume no raises, no cuts "
               "and no new purchases.")
    held = table[table["Held"]] if not table.empty else table
    varies = list(held.loc[held["Varies"], "Symbol"]) if not held.empty else []
    special = list(held.loc[held["Special"], "Symbol"]) if not held.empty else []
    if varies:
        out.append(join(varies) + (" pays" if len(varies) == 1 else " pay") + " a different amount each time, so I used the recent average.")
    if special:
        out.append(join(special) + " paid a one-off special dividend in the last year. I left it out of the projection.")
    return out


def drip_section(reinv: dict, income: dict, drip: dict | None, drip_symbol: str | None, cash_apy: float) -> list[str]:
    out: list[str] = []
    if income["n"]:
        if reinv["has_rei"] and reinv["rate"] is not None:
            low = [s for s, r in reinv["rate_by_symbol"].items() if r < 0.5]
            line = f"In your account, {reinv['rate'] * 100:.0f}% of the dividend cash in the feed was reinvested."
            if low and reinv["rate"] >= 0.5:
                line += f" {join(low)} did not appear to be reinvested."
            out.append(line)
        else:
            out.append("No reinvestment rows showed up next to your dividends, so they look to be landing as cash. "
                       "(Or DRIP is on and the feed leaves those rows out. The reinvestment setting on each position in "
                       "Fidelity is the source of truth.)")
    if drip:
        yrs = f"{drip['years']:.0f}" if drip["years"] >= 2 else f"{drip['years']:.1f}"
        out.append(
            f"Replaying {drip_symbol}'s real history over {yrs} years: {usd(drip['start_value'])} with dividends reinvested "
            f"became {usd(drip['drip_end'])}, versus {usd(drip['cash_end'])} if the dividends were taken as cash"
            + (f" earning {cash_apy * 100:.1f}% a year" if cash_apy > 0 else "")
            + f". That gap is {drip['advantage_pct']:.1f}%."
        )
        p = drip["parts"]
        gain = p["price"] + p["dividends"] + p["compounding"]
        if gain > 0:
            out.append(
                f"Of the {usd(gain)} total gain, {p['price'] / gain * 100:.0f}% came from the price, "
                f"{p['dividends'] / gain * 100:.0f}% from the dividends themselves, and {p['compounding'] / gain * 100:.0f}% "
                "from reinvesting them. Only that last slice is what DRIP adds; you would collect the other two either way."
            )
        small = drip["advantage_pct"] < 3
        out.append(
            ("Reinvesting made a small difference here: " if small else "Reinvesting made a real difference here: ")
            + f"your share count grew {drip['extra_shares_pct']:.0f}% with no new money, from a starting yield of about {drip['start_yield_pct']:.1f}%. "
            + ("DRIP matters most for higher yields held a long time." if small else "That is the compounding of higher yield and a long hold.")
        )
    elif drip_symbol:
        out.append(f"{drip_symbol} has no usable dividend and price history in this window, so there is nothing to replay.")
    out.append("DRIP is the same as buying more shares with the dividend yourself. What it adds is automation, whole and "
               "fractional shares with no commission, and no cash left sitting idle. It doesn't change taxes: in a taxable "
               "account reinvested dividends are still taxed that year. It also keeps adding to what you already own, so check "
               "whether new money should go somewhere else.")
    return out


def worth_knowing(table: pd.DataFrame, income: dict) -> list[str]:
    out = ["Dividends are not extra return. On the ex-dividend date a stock's price falls by about the dividend, so what "
           "matters is total return (price plus dividends), not the cash alone."]
    out.append("Yield is income divided by today's value. Yield on cost divides by what you paid, so it keeps rising for "
               "winners you bought long ago while telling you nothing about whether they are still a good use of the money.")
    held = table[table["Held"]] if not table.empty else table
    if not held.empty:
        g = held.dropna(subset=["Growth %"]).sort_values("Growth %", ascending=False)
        if not g.empty:
            top = g.iloc[0]
            line = (f"{top['Symbol']}'s dividend per share has grown about {top['Growth %']:.1f}% a year over the last "
                    f"{int(top['Growth years'])} years")
            line += f", with {int(top['Streak'])} higher years in a row." if top["Streak"] >= 2 else "."
            out.append(line)
            weak = g[g["Growth %"] <= 0]
            if not weak.empty:
                out.append(join(list(weak["Symbol"])) + (" has" if len(weak) == 1 else " have") + " had flat or falling dividends per share over the span measured.")
    out.append("Expected amounts come from Yahoo Finance's dividend history and your current share counts. Companies can "
               "raise, cut or skip a dividend at any time, so treat them as estimates. Informational only, not financial advice.")
    return out


def write_summary(*, income: dict, reinv: dict, port: dict, table: pd.DataFrame, proj: pd.DataFrame,
                  drip: dict | None, drip_symbol: str | None = None, cash_apy: float = 0.0,
                  activity_ok: bool = True, hide: bool = False) -> list[tuple[str, list[str]]]:
    table = table.copy() if table is not None else pd.DataFrame()
    table.attrs["port_yield"] = port.get("yield_pct") or 0.0
    sections = [("Bottom line", bottom_line(income, port, table, activity_ok, hide))]
    if port["payers"] > 0:
        sections += [("Where it comes from", where_from(table, hide)), ("What's coming", coming_up(proj, table, hide))]
    sections += [("Does DRIP pay?", drip_section(reinv, income, drip, drip_symbol, cash_apy)),
                 ("Worth knowing", worth_knowing(table, income))]
    return [(t, b) for t, b in sections if b]
