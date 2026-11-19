import datetime as dt
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import brief_text as bt  # noqa: E402

TODAY = dt.date(2026, 11, 18)
WEIGHTS = {"VOO": 60.0, "AAPL": 25.0, "MSFT": 15.0}
QUOTES = {"VOO": {"c": 500, "dp": 0.4}, "AAPL": {"c": 200, "dp": -4.0}, "MSFT": {"c": 400, "dp": 0.2}}


def contrib_df(quotes=QUOTES, weights=WEIGHTS):
    rows = [{"Symbol": s, "Share %": w, "Move %": quotes[s]["dp"], "Contribution pp": w * quotes[s]["dp"] / 100} for s, w in weights.items()]
    df = pd.DataFrame(rows)
    return df.reindex(df["Contribution pp"].abs().sort_values(ascending=False).index).reset_index(drop=True)


def brief(**over):
    base = dict(quotes=QUOTES, weights=WEIGHTS, contrib=contrib_df(), move_pct=-0.73, coverage=1.0, benchmark_pct=0.5,
                earnings=pd.DataFrame(), earnings_days=14, shifts={}, news={}, filings={}, threshold=2.0,
                conc={"largest": 60.0, "top5": 100.0}, held=True)
    base.update(over)
    return dict(bt.write_brief(**base))


def text(sections):
    return " ".join(" ".join(b) for b in sections.values())


def test_bottom_line_compares_with_market_and_names_the_driver():
    s = brief()
    t = " ".join(s["Bottom line"])
    assert "down 0.73%" in t and "behind it by 1.23 pp" in t
    assert "1 up" not in t and "2 up, 1 down" in t
    assert "AAPL did most of the work" in t          # -1.00 pp of ~1.4 gross movement
    assert "Winners added +0.27 pp while decliners took -1.00 pp" in t.replace("−", "-")


def test_roughly_in_line_and_big_holding_that_just_follows_its_weight():
    q = {"VOO": {"c": 1, "dp": 0.5}, "AAPL": {"c": 1, "dp": 0.5}, "MSFT": {"c": 1, "dp": 0.5}}
    s = brief(quotes=q, contrib=contrib_df(q), move_pct=0.5, benchmark_pct=0.45)
    t = " ".join(s["Bottom line"])
    assert "roughly in line" in t
    assert "mostly follows **VOO**" in t and "did most of the work" not in t   # 60% of money, 60% of movement: nothing surprising


def test_spread_out_when_no_holding_dominates():
    w = {"A": 34.0, "B": 33.0, "C": 33.0}
    q = {"A": {"c": 1, "dp": 1.0}, "B": {"c": 1, "dp": -1.0}, "C": {"c": 1, "dp": 0.9}}
    s = brief(quotes=q, weights=w, contrib=contrib_df(q, w), move_pct=0.3, benchmark_pct=0.3)
    assert "spread out" in " ".join(s["Bottom line"])


def test_big_mover_without_news_says_so_and_with_news_quotes_sanitized_headline():
    t = " ".join(brief()["What drove it"])
    assert "AAPL" in t and "-4.00%" in t.replace("−", "-") and "no headlines or filings" in t
    assert "company- or sector-specific" in t          # -4.0 vs market +0.5
    news = {"AAPL": [{"headline": "Big [click here](http://evil.example) <b>news</b> **now**", "source": "Wire", "url": "u",
                      "published": dt.datetime(2026, 11, 18)}]}
    t2 = " ".join(brief(news=news)["What drove it"])
    assert "click here" in t2 and "http" not in t2 and "[" not in t2 and "<" not in t2 and "**now**" not in t2
    assert "no headlines" not in t2


def test_mover_that_tracks_the_market_is_called_market_driven():
    q = {"VOO": {"c": 1, "dp": -2.5}, "AAPL": {"c": 1, "dp": -2.6}, "MSFT": {"c": 1, "dp": 0.0}}
    t = " ".join(brief(quotes=q, contrib=contrib_df(q), benchmark_pct=-2.4)["What drove it"])
    assert "mostly market-driven" in t


def test_filing_is_used_when_no_news():
    fl = {"AAPL": [{"Form": "8-K", "Filed": dt.date(2026, 11, 17), "What": "Earnings results", "Link": "x"}]}
    assert "filed a 8-K on Nov 17: Earnings results" in " ".join(brief(filings=fl)["What drove it"])


def test_quiet_day():
    q = {"VOO": {"c": 1, "dp": 0.1}, "AAPL": {"c": 1, "dp": -0.3}, "MSFT": {"c": 1, "dp": 0.2}}
    assert "A quiet day" in " ".join(brief(quotes=q, contrib=contrib_df(q))["What drove it"])


def test_price_vs_analysts_divergence_weighted_by_ownership():
    shifts = {"AAPL": {"direction": "more bullish", "score_before": 0.8, "score_now": 1.1},
              "MSFT": {"direction": "little changed", "score_before": 1, "score_now": 1}}
    t = " ".join(brief(shifts=shifts)["Price vs. analysts"])
    assert "AAPL" in t and "25%" in t and "yet the stock is -4.0%" in t.replace("−", "-") and "MSFT" not in t


def test_earnings_exposure_and_illustration():
    e = pd.DataFrame([
        {"Symbol": "AAPL", "Date": dt.date(2026, 11, 20), "In (days)": 2, "Timing": "After close"},
        {"Symbol": "MSFT", "Date": dt.date(2026, 11, 25), "In (days)": 7, "Timing": ""},
    ])
    t = " ".join(brief(earnings=e)["Coming up"])
    assert "40% of your invested money" in t and "AAPL" in t and "after close" in t
    assert "about 1.25 pp" in t                        # 25% x 5% move
    assert "MSFT (Nov 25)" in t
    assert "No earnings" in " ".join(brief()["Coming up"])


def test_filings_section_warns_form4_direction_unknown():
    fl = {"AAPL": [{"Form": "4", "Filed": TODAY, "What": "Insider", "Link": ""}, {"Form": "4", "Filed": TODAY, "What": "Insider", "Link": ""}]}
    t = " ".join(brief(filings=fl)["Paper trail"])
    assert "2 insider Form 4" in t and "cannot tell which" in t


def test_worth_a_look_flags_unexplained_move_concentration_and_missing_quotes():
    q = dict(QUOTES, XYZ=None)
    w = dict(WEIGHTS, **{f"S{i}": 1.0 for i in range(4)})   # 7 holdings, top 5 hold most of the money
    t = " ".join(brief(quotes=q, weights=w, conc={"largest": 60.0, "top5": 98.0})["Worth a closer look"])
    assert "Why did **AAPL** move" in t and "top 5 holdings are 98%" in t and "No live price for XYZ" in t
    # five or fewer holdings: "top 5 = 100%" would be meaningless, so it stays quiet
    assert "top 5" not in " ".join(brief(quotes=q)["Worth a closer look"])


def test_not_held_mode_uses_simple_average_and_no_weights():
    s = brief(held=False, weights={}, contrib=None, move_pct=None, conc=None)
    t = " ".join(s["Bottom line"])
    assert "simple average" in t and "did most of the work" not in t
    assert "of your invested money" not in " ".join(s.get("What drove it", []))


def test_no_quotes():
    s = brief(quotes={}, contrib=None)
    assert s["Bottom line"] == ["No live quotes came back, so there is nothing to summarize yet."]


def test_no_dollar_amounts_anywhere():
    assert "$" not in text(brief())


def test_low_coverage_warning():
    assert "only 55%" in " ".join(brief(coverage=0.55)["Bottom line"])
