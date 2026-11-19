"""
"Fit for you" for the Stock Deep-Dive. Pure functions: no Streamlit, no network.

YOU set the rules (how long you can leave the money, how big a swing you can sit through, dividend or not, ...);
this checks one stock against them and says which it meets and which it doesn't. The rules are yours, so the answer is a
description of the match, never a recommendation. Anything it can't check is marked unknown, not passed.
"""

from __future__ import annotations

SWINGS = {"Any": None, "Small (under 20% a year)": 0.20, "Moderate (up to 30%)": 0.30, "Big (up to 45%)": 0.45}
DIVIDENDS = ["Either", "I want a dividend", "I'd rather have none (growth)"]
PE_CAPS = ["Any", 15, 20, 25, 30, 40, 50, 60, 80]
SIZES = ["Any", "Small-cap and up", "Mid-cap and up", "Large-cap and up"]
GROWTHS = {"Any": None, "Growing (above 0%)": 0.0, "5% a year or more": 5.0, "10% a year or more": 10.0}
SIZE_RANK = {"micro-cap": 0, "small-cap": 1, "mid-cap": 2, "large-cap": 3, "mega-cap": 4}
SIZE_MIN = {"Small-cap and up": 1, "Mid-cap and up": 2, "Large-cap and up": 3}

DEFAULTS = {"years": 5, "swings": "Big (up to 45%)", "fall": 50, "dividend": "Either", "pe": 40, "profit": True,
            "size": "Any", "growth": "Any", "max_share": 10}
KEYS = {k: f"fit_{k}" for k in DEFAULTS}          # st.session_state keys the page uses


def prefs_from(state) -> dict:
    """Your rules from session state, with starting values for anything not set yet (and bad values replaced)."""
    out = dict(DEFAULTS)
    for k, sk in KEYS.items():
        v = state.get(sk, None)
        if v is not None:
            out[k] = v
    if out["swings"] not in SWINGS:
        out["swings"] = DEFAULTS["swings"]
    if out["dividend"] not in DIVIDENDS:
        out["dividend"] = DEFAULTS["dividend"]
    if out["size"] not in SIZES:
        out["size"] = DEFAULTS["size"]
    if out["growth"] not in GROWTHS:
        out["growth"] = DEFAULTS["growth"]
    if out["pe"] not in PE_CAPS:
        out["pe"] = DEFAULTS["pe"]
    return out


def _r(rule, yours, stock, result, why=""):
    return {"rule": rule, "yours": yours, "stock": stock, "result": result, "why": why}


def check(prefs: dict, ctx: dict) -> list[dict]:
    """One row per ACTIVE rule: {rule, yours, stock, result: pass|fail|unknown, why}.
    ctx: hz (hold_lib.horizon or None), stats, div, metrics-derived numbers: pe, net_margin, rev_growth, div_yield,
         size (bucket name or None), weight (% of invested if you hold it, 0 if you don't, None if the account is locked)."""
    rows = []
    hz, stats, div = ctx.get("hz"), ctx.get("stats") or {}, ctx.get("div")

    # 1. how long you can leave it
    years = int(prefs["years"])
    if hz:
        rows.append(_r("Time I can leave it", f"{years} years", f"needs about {hz['low']}+ years ({hz['text']})", "pass" if hz["low"] <= years else "fail",
                       "" if hz["low"] <= years else f"Its usual window starts at {hz['low']} years."))
    else:
        rows.append(_r("Time I can leave it", f"{years} years", "not enough history", "unknown"))

    # 2. swings
    cap = SWINGS[prefs["swings"]]
    if cap is not None:
        vol = stats.get("volatility")
        rows.append(_r("Price swings", f"up to {cap * 100:.0f}% a year", f"{vol * 100:.0f}% a year" if vol is not None else "n/a",
                       "unknown" if vol is None else "pass" if vol <= cap else "fail"))

    # 3. worst fall
    fall = int(prefs["fall"])
    md = stats.get("max_drawdown")
    ok_history = (stats.get("years_of_history") or 0) >= 2
    if md is None or not ok_history:
        rows.append(_r("Worst fall I could sit through", f"{fall}%", "not enough history", "unknown"))
    else:
        rows.append(_r("Worst fall I could sit through", f"{fall}%", f"{abs(md) * 100:.0f}% at its worst", "pass" if abs(md) * 100 <= fall else "fail"))

    # 4. dividend
    if prefs["dividend"] != DIVIDENDS[0]:
        active = bool(div and div.get("active"))
        yld = ctx.get("div_yield")
        known = div is not None or yld is not None
        pays = active or bool(yld and yld > 0)
        want = prefs["dividend"] == DIVIDENDS[1]
        rows.append(_r("Dividend", "wanted" if want else "none (growth)", "pays one" if pays else "pays none" if known else "n/a",
                       "unknown" if not known else "pass" if pays == want else "fail"))

    # 5. valuation
    if prefs["pe"] != "Any":
        pe = ctx.get("pe")
        if pe is None:
            rows.append(_r("Price tag (P/E)", f"up to {prefs['pe']}", "n/a", "unknown"))
        elif pe <= 0:
            rows.append(_r("Price tag (P/E)", f"up to {prefs['pe']}", "no earnings", "fail", "No positive earnings, so no P/E."))
        else:
            rows.append(_r("Price tag (P/E)", f"up to {prefs['pe']}", f"{pe:.1f}", "pass" if pe <= prefs["pe"] else "fail"))

    # 6. profitable
    if prefs["profit"]:
        m, pe = ctx.get("net_margin"), ctx.get("pe")
        gain = m if m is not None else (None if pe is None else (1 if pe > 0 else -1))
        rows.append(_r("Makes a profit", "yes", f"net margin {m:.1f}%" if m is not None else ("positive earnings" if gain and gain > 0 else "no profit" if gain else "n/a"),
                       "unknown" if gain is None else "pass" if gain > 0 else "fail"))

    # 7. size
    if prefs["size"] != "Any":
        size = ctx.get("size")
        rows.append(_r("Company size", prefs["size"].lower(), size or "n/a", "unknown" if size not in SIZE_RANK else "pass" if SIZE_RANK[size] >= SIZE_MIN[prefs["size"]] else "fail"))

    # 8. growth
    floor = GROWTHS[prefs["growth"]]
    if floor is not None:
        g = ctx.get("rev_growth")
        rows.append(_r("Sales growth", prefs["growth"].lower(), f"{g:.1f}% last year" if g is not None else "n/a",
                       "unknown" if g is None else "pass" if (g > floor if floor == 0 else g >= floor) else "fail"))

    # 9. how much of your money
    w = ctx.get("weight")
    if w is not None:
        share = int(prefs["max_share"])
        rows.append(_r("Most I'd put in one stock", f"{share}% of invested", f"you hold {w:.0f}%" if w > 0 else "you don't hold it", "pass" if w <= share else "fail",
                       "" if w <= share else "You already hold more than your limit."))
    return rows


def summary(rows: list[dict]) -> dict:
    """Counts and a plain verdict over the rules that could be checked."""
    p = sum(r["result"] == "pass" for r in rows)
    f = sum(r["result"] == "fail" for r in rows)
    u = sum(r["result"] == "unknown" for r in rows)
    checked = p + f
    ratio = p / checked if checked else None
    verdict = None if ratio is None else "Fits your rules" if f == 0 else "Mostly fits" if ratio >= 0.75 else "Partly fits" if ratio >= 0.5 else "Doesn't fit"
    return {"pass": p, "fail": f, "unknown": u, "checked": checked, "total": len(rows), "verdict": verdict}


def build_context(*, hz, stats, div, metrics_get, size, weight) -> dict:
    """metrics_get(key) -> number or None (deep_lib.metric bound to the company's numbers)."""
    return {"hz": hz, "stats": stats, "div": div, "pe": metrics_get("pe"), "net_margin": metrics_get("net_margin"),
            "rev_growth": metrics_get("rev_growth"), "div_yield": metrics_get("div_yield"), "size": size, "weight": weight}
