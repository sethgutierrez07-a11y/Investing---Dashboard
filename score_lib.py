"""
Scorecard for the Stock Deep-Dive. Pure functions: no Streamlit, no network.

Turns the page's own Good / OK / Watch reads into one 0-100 number, in five areas:
  Value, Growth, Profit and Safety come from the company numbers (deep_lib.key_numbers); Price & trend comes from the price history.
Each measure is worth 100 (Good), 60 (OK) or 20 (Watch); an area is the average of its measures, the score is the average of the
areas that have data. It RANKS the numbers on this page against rules of thumb; it is not a forecast and not a recommendation.
"""

from __future__ import annotations

import deep_lib as dlib

POINTS = {"good": 100, "ok": 60, "watch": 20}
MIN_AREAS = 3                       # fewer areas than this and there is no honest score
LABELS = [(75, "Strong"), (60, "Solid"), (40, "Mixed"), (0, "Weak")]
# area -> (key_numbers group, extra labels borrowed from another group)
COMPANY_AREAS = [("Value", "Valuation", ()), ("Growth", "Growth", ()), ("Profit", "Profitability", ()),
                 ("Safety", "Financial health", ("Payout ratio",))]
PRICE_AREA = "Price & trend"
AREA_NOTES = {
    "Value": "Is the price reasonable for what the company earns?",
    "Growth": "Are sales and profit growing, and has it lasted?",
    "Profit": "How much of each sales dollar does it keep?",
    "Safety": "Could it handle a bad year: debt, cash on hand, payout?",
    PRICE_AREA: "Is the price trending up, steady, and keeping up with the market?",
}
RULES = [
    ("Points", "Good = 100, OK = 60, Watch = 20 for each measure. The same Good/OK/Watch lines as the Key numbers tab."),
    ("Areas", "Value = valuation measures. Growth = sales and earnings growth. Profit = margins and returns. "
              "Safety = debt, current ratio, interest cover and payout ratio. Price & trend = the four lines below."),
    ("Price & trend", "Trend: above both averages = Good, mixed = OK, below both = Watch. Versus the S&P 500 over 3 years (1 year if shorter): "
                      "+5 points a year or more = Good, -5 or worse = Watch. Yearly swings: 22% or less = Good, 45% or more = Watch. "
                      "Worst fall in five years (needs 2+ years of history): milder than 25% = Good, 50% or worse = Watch."),
    ("Score", "The average of the areas that have data (at least three needed). 75+ Strong, 60-74 Solid, 40-59 Mixed, under 40 Weak."),
]


def round_half_up(x: float) -> int:
    return int(x + 0.5)


def label_for(score: float) -> str:
    return next(name for floor, name in LABELS if score >= floor)


def price_items(stats: dict | None) -> list[dict]:
    """The price-history signals as graded items, using the same lines as the pros and cons."""
    if not stats:
        return []
    out = []

    def add(label, shown, grade):
        out.append({"label": label, "shown": shown, "grade": grade})

    t = stats.get("trend")
    if t:
        add("Trend", {"up": "above both averages", "down": "below both averages", "mixed": "mixed"}[t], {"up": "good", "down": "watch", "mixed": "ok"}[t])
    ex, span = (stats.get("excess_3y"), "3 years") if stats.get("excess_3y") is not None else (stats.get("excess_1y"), "1 year")
    if ex is not None:
        add(f"Versus the S&P 500, {span}", f"{ex * 100:+.1f} points a year" if span == "3 years" else f"{ex * 100:+.1f} points", "good" if ex >= 0.05 else "watch" if ex <= -0.05 else "ok")
    vol = stats.get("volatility")
    if vol is not None:
        add("Yearly swings", f"{vol * 100:.0f}%", "good" if vol <= 0.22 else "watch" if vol >= 0.45 else "ok")
    md = stats.get("max_drawdown")
    if md is not None and (stats.get("years_of_history") or 0) >= 2:
        add("Worst fall, 5 years", f"{md * 100:.0f}%", "good" if md > -0.25 else "watch" if md <= -0.50 else "ok")
    return out


def _area(name: str, items: list[dict]) -> dict | None:
    graded = [i for i in items if i.get("grade") in POINTS]
    if not graded:
        return None
    score = sum(POINTS[i["grade"]] for i in graded) / len(graded)
    best = [i for i in graded if i["grade"] == "good"]
    worst = [i for i in graded if i["grade"] == "watch"]
    return {"name": name, "score": score, "n": len(graded), "items": graded, "note": AREA_NOTES[name],
            "best": [i["label"] for i in best], "worst": [i["label"] for i in worst]}


def scorecard(metrics: dict | None, stats: dict | None, fund: bool = False) -> dict | None:
    """{score, label, areas, missing, n_measures} or None for funds and when fewer than three areas have data."""
    if fund:
        return None
    rows = dlib.key_numbers(metrics)
    areas = []
    for name, group, extra in COMPANY_AREAS:
        items = [{"label": r["label"], "shown": r["shown"], "grade": r["grade"]} for r in rows if r["group"] == group or r["label"] in extra]
        a = _area(name, items)
        if a:
            areas.append(a)
    p = _area(PRICE_AREA, price_items(stats))
    if p:
        areas.append(p)
    if len(areas) < MIN_AREAS:
        return None
    score = round_half_up(sum(a["score"] for a in areas) / len(areas))              # label what is shown, not the raw average
    have = {a["name"] for a in areas}
    return {"score": score, "label": label_for(score), "areas": areas,
            "missing": [n for n in [c[0] for c in COMPANY_AREAS] + [PRICE_AREA] if n not in have],
            "n_measures": sum(a["n"] for a in areas)}
