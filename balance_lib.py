"""
Balance check for the Holdings page. Pure functions: no Streamlit, no network.

Turns your positions (as % of the whole portfolio) into
  * an asset mix: US stocks / international stocks / bonds / cash / other,
  * a sector mix of the stock part (funds are looked through using balance_data.FUNDS; single stocks use their industry),
  * a growth-sector share,
and compares them with a reference mix you pick and with the S&P 500's own sector weights.
Percent-only: nothing here ever sees or returns a dollar amount. A holding it can't classify is listed, not guessed.
Rules of thumb on past data, not advice. The suggestions name AREAS to look at, never a particular stock or fund to buy.
"""

from __future__ import annotations

from typing import Any

import balance_data as bd

HEAVY_PTS = 8.0                  # a sector this far above the S&P 500's weight is "heavy"
LIGHT_MIN_GAP = 2.0              # ...and light needs to be at least this many points under, and under half the market weight
ASSET_TOL = 5.0                  # points either side of the reference mix that still counts as on target
INTL_TOL = 8.0
UNCLASSIFIED_NOTE = 5.0          # mention unclassified holdings once they are this much of the portfolio
ASSET_ORDER = ["Stocks", "Bonds", "Cash", "Other"]


# ---------------------------------------------------------------- classifying
def sector_from_industry(industry: str | None) -> str | None:
    s = (industry or "").strip().lower()
    if not s:
        return None
    for sector, words in bd.INDUSTRY_WORDS:
        if any(w in s for w in words):
            return sector
    return None


def sector_for_stock(symbol: str, industry: str | None = None) -> str | None:
    return bd.STOCK_SECTORS.get(symbol.upper()) or sector_from_industry(industry)


def needs_profile(symbol: str, cls: str) -> bool:
    """Single stocks we can't place from the built-in table need Finnhub's profile (one cached call each)."""
    return cls == "Stock" and symbol.upper() not in bd.STOCK_SECTORS


def _normalize(d: dict[str, float]) -> dict[str, float]:
    tot = sum(v for v in d.values() if v and v > 0)
    return {k: v / tot for k, v in d.items() if v and v > 0} if tot > 0 else {}


def classify(symbol: str, cls: str, profile: dict | None = None) -> dict | None:
    """What one holding is made of: {"asset": {category: fraction}, "sectors": {sector: fraction} | None, "kind": str}.
    None when we can't tell (an unknown fund, or a class we don't handle)."""
    sym = symbol.upper()
    profile = profile or {}
    if cls == "Cash equiv.":
        return {"asset": {bd.CASH: 1.0}, "sectors": None, "kind": "Cash-like"}
    if cls == "Bond":
        return {"asset": {bd.BOND: 1.0}, "sectors": None, "kind": "Bond"}
    if cls == "Crypto":
        return {"asset": {bd.OTHER: 1.0}, "sectors": None, "kind": "Crypto"}
    if cls == "Stock":
        country = (profile.get("country") or "US").upper()
        asset = bd.US if country in ("US", "USA", "UNITED STATES") else bd.INTL
        sector = sector_for_stock(sym, profile.get("finnhubIndustry"))
        return {"asset": {asset: 1.0}, "sectors": {sector: 1.0} if sector else None, "kind": "Single stock"}
    fund = bd.FUNDS.get(sym)
    if fund:
        return {"asset": _normalize(fund["asset"]), "sectors": _normalize(fund["sectors"]) if fund["sectors"] else None, "kind": fund["kind"]}
    return None


# ---------------------------------------------------------------- the picture
def build(holdings: list[dict], profiles: dict[str, dict] | None = None) -> dict:
    """holdings: [{"symbol", "class", "weight"}], weight = % of the WHOLE portfolio (cash included elsewhere via class).
    profiles: symbol -> Finnhub profile (only needed for single stocks missing from the built-in table).
    Returns the asset mix (% of portfolio), the sector mix (% of the stock money we could place), and where each sector comes from."""
    profiles = profiles or {}
    asset = {bd.US: 0.0, bd.INTL: 0.0, bd.BOND: 0.0, bd.CASH: 0.0, bd.OTHER: 0.0}
    sector_pts: dict[str, float] = {}
    sources: dict[str, dict[str, float]] = {}
    unclassified: dict[str, float] = {}
    stock_money = placed_stock = 0.0
    total = 0.0
    for h in holdings:
        w = float(h.get("weight") or 0.0)
        if w <= 0:
            continue
        total += w
        sym = str(h["symbol"]).upper()
        c = classify(sym, h.get("class") or "", profiles.get(sym))
        if c is None:
            unclassified[sym] = unclassified.get(sym, 0.0) + w
            continue
        stock_frac = 0.0
        for cat, frac in c["asset"].items():
            asset[cat] += w * frac
            if cat in (bd.US, bd.INTL):
                stock_frac += frac
        if stock_frac <= 0:
            continue
        stock_money += w * stock_frac
        if c["sectors"]:
            placed_stock += w * stock_frac
            for sec, frac in c["sectors"].items():
                pts = w * stock_frac * frac
                sector_pts[sec] = sector_pts.get(sec, 0.0) + pts
                sources.setdefault(sec, {})
                sources[sec][sym] = sources[sec].get(sym, 0.0) + pts
        else:
            unclassified[sym] = unclassified.get(sym, 0.0) + w * stock_frac
    sectors = {s: v / placed_stock * 100 for s, v in sector_pts.items()} if placed_stock > 0 else {}
    src = {s: sorted(((k, v / sector_pts[s] * 100) for k, v in d.items()), key=lambda kv: -kv[1]) for s, d in sources.items()}
    stocks = asset[bd.US] + asset[bd.INTL]
    return {
        "total": total, "asset": asset, "stocks": stocks,
        "intl_share": asset[bd.INTL] / stocks * 100 if stocks > 0 else None,
        "sectors": dict(sorted(sectors.items(), key=lambda kv: -kv[1])), "sources": src,
        "growth_share": sum(sectors.get(s, 0.0) for s in bd.GROWTH_SECTORS) if sectors else None,
        "coverage": placed_stock / stock_money if stock_money > 0 else None,
        "unclassified": sorted(unclassified.items(), key=lambda kv: -kv[1]),
        "unclassified_pct": sum(unclassified.values()),
    }


# ---------------------------------------------------------------- compare with a reference mix
def _status(diff: float, tol: float) -> str:
    return "On target" if abs(diff) <= tol else "Light" if diff < 0 else "Heavy"


def compare_assets(ex: dict, preset: str) -> list[dict]:
    """Your asset mix next to the reference mix, in points of the whole portfolio. Unclassified holdings are shown, not hidden."""
    p = bd.PRESETS[preset]
    a = ex["asset"]
    yours = {"Stocks": ex["stocks"], "Bonds": a[bd.BOND], "Cash": a[bd.CASH], "Other": a[bd.OTHER]}
    rows = []
    for name in ASSET_ORDER:
        tgt = float(p[name.lower() if name != "Stocks" else "stocks"])
        d = yours[name] - tgt
        rows.append({"name": name, "yours": yours[name], "target": tgt, "diff": d, "status": _status(d, ASSET_TOL)})
    return rows


def compare_region(ex: dict, preset: str) -> dict | None:
    if ex["intl_share"] is None:
        return None
    tgt = float(bd.PRESETS[preset]["intl"])
    d = ex["intl_share"] - tgt
    return {"yours": ex["intl_share"], "target": tgt, "diff": d, "status": _status(d, INTL_TOL)}


def compare_growth(ex: dict, preset: str) -> dict | None:
    g = ex["growth_share"]
    if g is None:
        return None
    lo, hi = bd.PRESETS[preset]["growth"]
    return {"yours": g, "low": float(lo), "high": float(hi), "market": sum(bd.MARKET[s] for s in bd.GROWTH_SECTORS),
            "status": "Light" if g < lo else "Heavy" if g > hi else "On target"}


def compare_sectors(ex: dict) -> list[dict]:
    """Every sector's weight in your stock money against the S&P 500's, biggest gap first."""
    rows = []
    for sec in bd.SECTORS:
        y, m = ex["sectors"].get(sec, 0.0), bd.MARKET[sec]
        d = y - m
        status = "Heavy" if d >= HEAVY_PTS else "Light" if (d <= -LIGHT_MIN_GAP and y < m * 0.5) else "Near market"
        rows.append({"sector": sec, "yours": y, "market": m, "diff": d, "status": status,
                     "from": (ex["sources"].get(sec) or [])[:3]})
    return sorted(rows, key=lambda r: -abs(r["diff"]))


# ---------------------------------------------------------------- plain words
def _src(r: dict) -> str:
    top = [(s, p) for s, p in r["from"] if p >= 25]
    if not top:
        return ""
    return " Mostly from " + " and ".join(f"{s} ({p:.0f}%)" for s, p in top[:2]) + "."


def suggestions(ex: dict, preset: str, pick: dict | None = None) -> list[dict]:
    """[{kind, text}] in the order worth reading. pick = {"symbol", "sector"} for today's stock idea, if there is one."""
    out: list[dict] = []
    if ex["total"] <= 0:
        return out
    p = bd.PRESETS[preset]
    for r in compare_assets(ex, preset):
        if r["status"] == "On target":
            continue
        word = "more" if r["diff"] < 0 else "less"
        out.append({"kind": "asset", "text": f"**{r['name']}:** {r['yours']:.0f}% of your portfolio against about {r['target']:.0f}% in the "
                    f"“{preset.lower()}” reference mix. That mix would have {abs(r['diff']):.0f} points {word} here."
                    + (" That isn't wrong for a long time horizon; it just means more ups and downs." if r["name"] == "Stocks" and r["diff"] > 0 else "")})
    reg = compare_region(ex, preset)
    if reg and reg["status"] != "On target":
        out.append({"kind": "region", "text": f"**Outside the US:** {reg['yours']:.0f}% of your stock money against about {reg['target']:.0f}% in the reference mix. "
                    + ("Funds that hold companies outside the US would fill that gap." if reg["diff"] < 0 else "That is more international than the reference mix.")})
    gr = compare_growth(ex, preset)
    if gr and gr["status"] != "On target":
        rng = f"{gr['low']:.0f}–{gr['high']:.0f}%"
        out.append({"kind": "growth", "text": f"**Growth tilt:** {gr['yours']:.0f}% of your stock money is in technology, communication and consumer discretionary "
                    f"(the S&P 500 is about {gr['market']:.0f}%). The “{preset.lower()}” reference range is {rng}, so you're "
                    + ("below it: the growth sectors are the light spot." if gr["status"] == "Light" else "above it: a very strong growth tilt.")})
    rows = compare_sectors(ex)
    for r in [r for r in rows if r["status"] == "Heavy"][:3]:
        out.append({"kind": "heavy", "sector": r["sector"], "text": f"**{r['sector']} is heavy:** {r['yours']:.0f}% of your stock money against about {r['market']:.0f}% in the S&P 500." + _src(r)})
    growth_pref = p["growth"][0] >= 50
    light = [r for r in rows if r["status"] == "Light"]
    light.sort(key=lambda r: (not (growth_pref and r["sector"] in bd.GROWTH_SECTORS), -abs(r["diff"])))
    for r in light[:3]:
        out.append({"kind": "light", "sector": r["sector"], "text": f"**{r['sector']} is light:** {r['yours']:.0f}% of your stock money against about {r['market']:.0f}% in the S&P 500. "
                    f"About {abs(r['diff']):.0f} more points would bring it to the market's weight. A good area to browse."})
    if pick and pick.get("sector"):
        row = next((r for r in rows if r["sector"] == pick["sector"]), None)
        if row:
            fits = {"Light": "a sector you're light in, so it would add balance",
                    "Heavy": "a sector you're already heavy in, so it would add to the tilt",
                    "Near market": "a sector where you're close to the market's weight"}[row["status"]]
            out.append({"kind": "pick", "text": f"**Today's stock idea ({pick['symbol']})** is in {pick['sector']}: {fits}."})
    if ex["unclassified_pct"] >= UNCLASSIFIED_NOTE:
        names = ", ".join(f"{s} ({v:.0f}%)" for s, v in ex["unclassified"][:5])
        out.append({"kind": "gap", "text": f"**Not classified:** {ex['unclassified_pct']:.0f}% of your portfolio ({names}) isn't in the built-in fund table or has no sector, "
                    "so it is left out of the sector view rather than guessed."})
    return out


def how_it_works() -> list[tuple[str, str]]:
    return [
        ("Reference mixes", "Common starting points, not a recommendation: Balanced 60/35/5, Balanced leaning growth 80/15/5, Growth 90/7/3, "
                            "Aggressive growth 100/0/0 (stocks/bonds/cash). On target means within 5 points."),
        ("Outside the US", "Share of stock money in non-US companies, against about 25% (20% for Aggressive growth). On target means within 8 points."),
        ("Growth tilt", "Share of stock money in technology, communication services and consumer discretionary, against a range per mix. "
                        f"The S&P 500 is about {sum(bd.MARKET[s] for s in bd.GROWTH_SECTORS):.0f}%."),
        ("Heavy / light sectors", f"Heavy: {HEAVY_PTS:.0f}+ points above the S&P 500's weight. Light: at least {LIGHT_MIN_GAP:.0f} points below and under half of it."),
        ("Funds", f"A fund is split into its sectors using a built-in table (checked {bd.AS_OF}, approximate). Funds not in the table are listed as not classified."),
        ("Single stocks", "Placed by a short built-in list of well-known companies, otherwise by the industry Finnhub reports."),
    ]
