"""The Deep-Dive write-up: facts match the numbers, wording stays neutral."""

import re
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import deep_lib as dlib  # noqa: E402
import deep_text as dtx  # noqa: E402
from test_deep_lib import GOOD, QUOTE, TRENDS, px  # noqa: E402

PROFILE = {"name": "Acme Corp", "finnhubIndustry": "Technology", "marketCapitalization": 500_000, "exchange": "NASDAQ NMS"}
STATS = dlib.price_stats(px(0.0008))


def sections(**kw):
    ev = dlib.assess("ACME", QUOTE, GOOD, TRENDS, STATS)
    base = dict(profile=PROFILE, quote=QUOTE, metrics=GOOD, ev=ev, stats=STATS, trends=TRENDS)
    base.update(kw)
    return dict(dtx.write_summary("ACME", **base))


def flat(secs):
    return " ".join(b for bullets in secs.values() for b in bullets)


def test_section_order_and_contents():
    s = sections()
    assert list(s) == ["In plain words", "What looks good", "What to watch", "Bottom line", "Worth knowing"]
    plain = " ".join(s["In plain words"])
    assert "**Acme Corp** (ACME) is a mega-cap company in the technology industry" in plain and "about $500 billion" in plain
    assert "$100.00 (+1.00% today)" in plain and "P/E of 18.0" in plain and "modest price" in plain
    assert "sales grew 14.0%" in plain and "22¢ of profit" in plain


def test_pros_and_cons_text_is_the_assessment_verbatim():
    ev = dlib.assess("ACME", QUOTE, GOOD, TRENDS, STATS)
    s = sections()
    assert s["What looks good"] == [f"**{l}:** {t}" for l, t in ev["pros"]]
    assert s["What to watch"][-1].startswith("**Always:**") and len(s["What to watch"]) == len(ev["cons"]) + 1


def test_bottom_line_counts_and_wording():
    b = " ".join(sections()["Bottom line"])
    ev = dlib.assess("ACME", QUOTE, GOOD, TRENDS, STATS)
    assert f"**{len(ev['pros'])} positives**" in b and f"across {ev['covered']} measures" in b and "lean positive" in b
    assert "Analyst consensus (18 analysts): **Leans Buy**" in b
    one = dtx.bottom_line({"pros": [("a", "x")], "cons": [("b", "y")], "covered": 6, "avg": 0.0}, None)[0]
    assert "**1 positive**" in one and "**1 caution**" in one and "are mixed" in one
    assert "lean cautious" in dtx.bottom_line({"pros": [], "cons": [("b", "y")] * 3, "covered": 6, "avg": -0.5}, None)[0]
    assert dtx.bottom_line({"pros": [], "cons": [], "covered": 1, "avg": 0}, None) == ["There isn't enough data on this ticker for a meaningful read."]


def test_unprofitable_company_and_expensive_company_wording():
    m = dict(GOOD, netProfitMarginTTM=-8.0)
    m.pop("peTTM")
    plain = " ".join(dtx.in_plain_words("X", PROFILE, QUOTE, m, None))
    assert "not profitable" in plain and "loses about 8¢" in plain
    plain = " ".join(dtx.in_plain_words("X", PROFILE, QUOTE, dict(GOOD, peTTM=55.0), None))
    assert "demanding price" in plain
    plain = " ".join(dtx.in_plain_words("X", PROFILE, QUOTE, dict(GOOD, peTTM=30.0), None))
    assert "middle-of-the-road" in plain


def test_52_week_high_phrase():
    at_high = dict(STATS, from_high=0.0)
    assert "at its 52-week high" in " ".join(dtx.in_plain_words("X", PROFILE, QUOTE, GOOD, at_high))
    below = dict(STATS, from_high=-0.18)
    assert "18% below its 52-week high" in " ".join(dtx.in_plain_words("X", PROFILE, QUOTE, GOOD, below))


def test_how_it_fits_you_is_percent_only_and_warns_on_concentration():
    s = sections(held={"held": True, "weight": 25.0})
    t = " ".join(s["How it fits you"])
    assert "**25%**" in t and "roughly 8%" in t and "$" not in t
    small = " ".join(sections(held={"held": True, "weight": 5.0})["How it fits you"])
    assert "big share" not in small
    assert "don't hold ACME" in " ".join(sections(held={"held": False, "weight": None})["How it fits you"])
    assert "How it fits you" not in sections(held=None)


def test_fund_and_nodata_paths():
    f = dict(dtx.write_summary("VOO", quote=QUOTE, stats=STATS, fund=True))
    assert list(f) == ["In plain words", "Worth knowing"] and "fund or ETF" in f["In plain words"][0]
    assert any("worst fall" in b for b in f["In plain words"])
    n = dict(dtx.write_summary("XYZ", quote=None, stats=None, ev=None))
    assert "aren't available" in n["In plain words"][0] and "fund" not in n["In plain words"][0]


def test_no_hype_advice_or_certainty_in_any_path():
    texts = [flat(sections()), flat(sections(held={"held": True, "weight": 30.0})),
             flat(dict(dtx.write_summary("VOO", quote=QUOTE, stats=STATS, fund=True)))]
    for t in texts:
        low = t.lower()
        for w in (r"you should", r"\bbuy now\b", r"\bsell now\b", r"will rise", r"will fall", r"guaranteed", r"can't lose", r"sure thing", r"undervalued", r"overvalued"):
            assert not re.search(w, low), w
        assert "not advice" in low or "not a recommendation" in low or "no screen" in low or "describes the past" in low


def test_analyst_line_handles_missing_and_empty():
    assert dtx.analyst_line(None) is None and dtx.analyst_line([]) is None
    assert dtx.analyst_line([{"strongBuy": 0, "buy": 0, "hold": 0, "sell": 0, "strongSell": 0}]) is None
    assert "more bullish than last month" in dtx.analyst_line([dict(TRENDS[0], strongBuy=12), dict(TRENDS[1], strongBuy=2)])


def test_percent_helper():
    assert dtx.pc(0.123) == "12.3%" and dtx.pc(0.123, 0, True) == "+12%" and dtx.pc(None) == "n/a" and dtx.pc(-0.05, 1, True) == "-5.0%"
