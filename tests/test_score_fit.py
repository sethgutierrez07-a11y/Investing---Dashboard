"""Scorecard and Fit for you: grading maths, boundaries, plain-words text, chart."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_lab_charts  # noqa: F401,E402  (installs a plotly stand-in if plotly is missing)

for m in ("deep_charts", "risk_charts", "holdings_charts"):
    sys.modules.pop(m, None)
import deep_charts as dc  # noqa: E402
import deep_lib as dlib  # noqa: E402
import deep_text as dtx  # noqa: E402
import fit_lib as fl  # noqa: E402
import score_lib as sl  # noqa: E402
from test_deep_lib import GOOD, px  # noqa: E402

STATS_UP = dlib.price_stats(px(0.0008))


# ---------------------------------------------------------------- labels
@pytest.mark.parametrize("score,label", [(100, "Strong"), (75, "Strong"), (74, "Solid"), (60, "Solid"), (59, "Mixed"), (40, "Mixed"), (39, "Weak"), (0, "Weak")])
def test_label_boundaries(score, label):
    assert sl.label_for(score) == label


@pytest.mark.parametrize("x,r", [(73.49, 73), (73.5, 74), (73.6, 74), (74.0, 74), (0.0, 0), (99.5, 100)])
def test_scores_round_half_up(x, r):
    assert sl.round_half_up(x) == r


# ---------------------------------------------------------------- price signals
def stats(**kw):
    base = {"trend": None, "excess_3y": None, "excess_1y": None, "volatility": None, "max_drawdown": None, "years_of_history": 5}
    base.update(kw)
    return base


def grade_of(label_start, s):
    return next((i["grade"] for i in sl.price_items(s) if i["label"].startswith(label_start)), None)


@pytest.mark.parametrize("vol,g", [(0.10, "good"), (0.22, "good"), (0.2201, "ok"), (0.4499, "ok"), (0.45, "watch"), (0.9, "watch")])
def test_swings_use_the_same_lines_as_the_pros_and_cons(vol, g):
    assert grade_of("Yearly swings", stats(volatility=vol)) == g


@pytest.mark.parametrize("md,g", [(-0.05, "good"), (-0.2499, "good"), (-0.25, "ok"), (-0.4999, "ok"), (-0.50, "watch"), (-0.8, "watch")])
def test_worst_fall_lines(md, g):
    assert grade_of("Worst fall", stats(max_drawdown=md)) == g


def test_worst_fall_needs_two_years_of_history():
    assert grade_of("Worst fall", stats(max_drawdown=-0.6, years_of_history=1.9)) is None
    assert grade_of("Worst fall", stats(max_drawdown=-0.6, years_of_history=2.0)) == "watch"


@pytest.mark.parametrize("ex,g", [(0.05, "good"), (0.0499, "ok"), (0.0, "ok"), (-0.0499, "ok"), (-0.05, "watch")])
def test_versus_the_market_lines_and_fallback_to_one_year(ex, g):
    assert grade_of("Versus the S&P 500, 3 years", stats(excess_3y=ex)) == g
    one = [i for i in sl.price_items(stats(excess_1y=ex)) if i["label"].startswith("Versus")][0]
    assert one["label"].endswith("1 year") and one["grade"] == g
    assert grade_of("Versus", stats(excess_3y=0.2, excess_1y=-0.2)) == "good"                 # 3 years wins when both exist


@pytest.mark.parametrize("t,g", [("up", "good"), ("mixed", "ok"), ("down", "watch")])
def test_trend_grades(t, g):
    assert grade_of("Trend", stats(trend=t)) == g


def test_no_stats_means_no_price_items():
    assert sl.price_items(None) == [] and sl.price_items({}) == []


# ---------------------------------------------------------------- scorecard
def test_a_strong_company_with_a_steady_climb_scores_100():
    sc = sl.scorecard(GOOD, STATS_UP)
    assert sc["score"] == 100 and sc["label"] == "Strong" and sc["missing"] == []
    assert [a["name"] for a in sc["areas"]] == ["Value", "Growth", "Profit", "Safety", "Price & trend"]
    assert sc["n_measures"] == sum(a["n"] for a in sc["areas"])


def test_points_are_100_60_20_and_areas_average_their_measures():
    m = {"peTTM": 30.0, "revenueGrowthTTMYoy": 5.0, "netProfitMarginTTM": -3.0, "roeTTM": 20.0, "totalDebt/totalEquityQuarterly": 3.0}
    sc = sl.scorecard(m, None)
    a = {x["name"]: x for x in sc["areas"]}
    assert a["Value"]["score"] == 60 and a["Growth"]["score"] == 60                        # P/E 30 = OK; revenue growth 5% = OK
    assert a["Profit"]["score"] == (20 + 100) / 2                                         # net margin -3 = Watch, ROE 20 = Good
    assert a["Safety"]["score"] == 20 and a["Safety"]["worst"] == ["Debt / equity"]
    assert sc["score"] == int((60 + 60 + 60 + 20) / 4 + 0.5) and sc["missing"] == ["Price & trend"]


def test_payout_ratio_counts_toward_safety():
    sc = sl.scorecard({**GOOD, "payoutRatioTTM": 95.0}, STATS_UP)
    safety = next(a for a in sc["areas"] if a["name"] == "Safety")
    assert "Payout ratio" in [i["label"] for i in safety["items"]] and safety["score"] == (100 + 20) / 2


def test_the_shown_score_and_label_always_agree():
    for pe in (10, 22, 35, 45, 70):
        for growth in (-5, 3, 12):
            sc = sl.scorecard({"peTTM": pe, "revenueGrowthTTMYoy": growth, "netProfitMarginTTM": 12.0, "totalDebt/totalEquityQuarterly": 1.0}, STATS_UP)
            assert sc["label"] == sl.label_for(sc["score"]) and 0 <= sc["score"] <= 100


def test_too_little_data_or_a_fund_gives_no_score():
    assert sl.scorecard({"peTTM": 15.0, "revenueGrowthTTMYoy": 12.0}, None) is None           # two areas
    assert sl.scorecard({"peTTM": 15.0, "revenueGrowthTTMYoy": 12.0}, STATS_UP) is not None   # price history makes it three
    assert sl.scorecard(GOOD, STATS_UP, fund=True) is None and sl.scorecard(None, None) is None and sl.scorecard({}, STATS_UP) is None


def test_area_with_no_graded_measure_is_missing_not_zero():
    sc = sl.scorecard({"peTTM": 15.0, "revenueGrowthTTMYoy": 12.0, "netProfitMarginTTM": 20.0, "beta": 1.1}, None)
    assert sc["missing"] == ["Safety", "Price & trend"] and all(a["score"] == 100 for a in sc["areas"])


# ---------------------------------------------------------------- fit: your rules
def ctx(**kw):
    base = {"hz": {"low": 5, "text": "5–7 years"}, "stats": {"volatility": 0.30, "max_drawdown": -0.30, "years_of_history": 5}, "div": None,
            "pe": 25.0, "net_margin": 12.0, "rev_growth": 8.0, "div_yield": None, "size": "large-cap", "weight": None}
    base.update(kw)
    return base


def prefs(**kw):
    p = dict(fl.DEFAULTS)
    p.update(kw)
    return p


def res(rows, rule):
    return next(r for r in rows if r["rule"] == rule)["result"]


def test_prefs_start_from_defaults_and_take_valid_session_values():
    assert fl.prefs_from({}) == fl.DEFAULTS
    p = fl.prefs_from({"fit_years": 8, "fit_profit": False, "fit_dividend": "I want a dividend", "fit_pe": 25})
    assert (p["years"], p["profit"], p["dividend"], p["pe"]) == (8, False, "I want a dividend", 25)
    bad = fl.prefs_from({"fit_swings": "???", "fit_dividend": "x", "fit_size": "x", "fit_growth": "x", "fit_pe": 7})
    assert bad == fl.DEFAULTS
    assert fl.prefs_from({"fit_years": None}) == fl.DEFAULTS


def test_default_rules_and_the_account_rule_only_when_unlocked():
    rows = fl.check(fl.DEFAULTS, ctx())
    assert [r["rule"] for r in rows] == ["Time I can leave it", "Price swings", "Worst fall I could sit through", "Price tag (P/E)", "Makes a profit"]
    unlocked = fl.check(fl.DEFAULTS, ctx(weight=0.0))
    assert unlocked[-1]["rule"] == "Most I'd put in one stock" and unlocked[-1]["stock"] == "you don't hold it" and unlocked[-1]["result"] == "pass"


@pytest.mark.parametrize("low,years,r", [(5, 5, "pass"), (5, 4, "fail"), (3, 15, "pass"), (10, 9, "fail")])
def test_time_rule(low, years, r):
    assert res(fl.check(prefs(years=years), ctx(hz={"low": low, "text": "x"})), "Time I can leave it") == r


def test_time_rule_is_unknown_without_a_window():
    assert res(fl.check(fl.DEFAULTS, ctx(hz=None)), "Time I can leave it") == "unknown"


@pytest.mark.parametrize("vol,r", [(0.45, "pass"), (0.4501, "fail"), (0.10, "pass")])
def test_swings_rule_boundary(vol, r):
    assert res(fl.check(prefs(swings="Big (up to 45%)"), ctx(stats={"volatility": vol, "max_drawdown": -0.1, "years_of_history": 5})), "Price swings") == r


def test_swings_rule_caps_unknown_and_off_switch():
    rows = lambda **k: fl.check(prefs(**k), ctx(stats={"volatility": 0.25, "max_drawdown": -0.1, "years_of_history": 5}))   # noqa: E731
    assert res(rows(swings="Small (under 20% a year)"), "Price swings") == "fail" and res(rows(swings="Moderate (up to 30%)"), "Price swings") == "pass"
    assert "Price swings" not in [r["rule"] for r in rows(swings="Any")]
    assert res(fl.check(prefs(), ctx(stats={"volatility": None, "max_drawdown": -0.1, "years_of_history": 5})), "Price swings") == "unknown"


@pytest.mark.parametrize("md,fall,r", [(-0.50, 50, "pass"), (-0.501, 50, "fail"), (-0.10, 10, "pass"), (-0.11, 10, "fail")])
def test_fall_rule_boundary(md, fall, r):
    assert res(fl.check(prefs(fall=fall), ctx(stats={"volatility": 0.2, "max_drawdown": md, "years_of_history": 5})), "Worst fall I could sit through") == r


def test_fall_rule_needs_history():
    short = ctx(stats={"volatility": 0.2, "max_drawdown": -0.1, "years_of_history": 1.5})
    assert res(fl.check(prefs(), short), "Worst fall I could sit through") == "unknown"
    assert res(fl.check(prefs(), ctx(stats={})), "Worst fall I could sit through") == "unknown"


def test_dividend_rule_both_directions_and_unknown():
    pays, none = {"active": True}, {"active": False}
    want, skip = "I want a dividend", "I'd rather have none (growth)"
    assert res(fl.check(prefs(dividend=want), ctx(div=pays)), "Dividend") == "pass" and res(fl.check(prefs(dividend=want), ctx(div=none)), "Dividend") == "fail"
    assert res(fl.check(prefs(dividend=skip), ctx(div=none)), "Dividend") == "pass" and res(fl.check(prefs(dividend=skip), ctx(div=pays)), "Dividend") == "fail"
    assert res(fl.check(prefs(dividend=want), ctx(div=None, div_yield=1.5)), "Dividend") == "pass"          # yield from company numbers
    assert res(fl.check(prefs(dividend=want), ctx(div=None, div_yield=None)), "Dividend") == "unknown"
    assert res(fl.check(prefs(dividend=want), ctx(div=None, div_yield=0.0)), "Dividend") == "fail"
    assert "Dividend" not in [r["rule"] for r in fl.check(prefs(dividend="Either"), ctx(div=pays))]


@pytest.mark.parametrize("pe,cap,r", [(40.0, 40, "pass"), (40.1, 40, "fail"), (0.0, 40, "fail"), (-3.0, 40, "fail"), (10.0, 15, "pass")])
def test_pe_rule(pe, cap, r):
    assert res(fl.check(prefs(pe=cap), ctx(pe=pe)), "Price tag (P/E)") == r


def test_pe_rule_unknown_off_and_explains_missing_earnings():
    assert res(fl.check(prefs(), ctx(pe=None)), "Price tag (P/E)") == "unknown"
    assert "Price tag (P/E)" not in [r["rule"] for r in fl.check(prefs(pe="Any"), ctx())]
    row = next(r for r in fl.check(prefs(), ctx(pe=-1.0)) if r["rule"] == "Price tag (P/E)")
    assert row["stock"] == "no earnings" and "No positive earnings" in row["why"]


def test_profit_rule_prefers_margin_then_falls_back_to_earnings():
    p = lambda **k: res(fl.check(prefs(), ctx(**k)), "Makes a profit")                           # noqa: E731
    assert p(net_margin=0.1) == "pass" and p(net_margin=0.0) == "fail" and p(net_margin=-4.0) == "fail"
    assert p(net_margin=None, pe=12.0) == "pass" and p(net_margin=None, pe=-2.0) == "fail" and p(net_margin=None, pe=None) == "unknown"
    assert p(net_margin=5.0, pe=-2.0) == "pass"                                                  # the margin is what counts when we have it
    assert "Makes a profit" not in [r["rule"] for r in fl.check(prefs(profit=False), ctx())]


@pytest.mark.parametrize("size,want,r", [("small-cap", "Mid-cap and up", "fail"), ("mid-cap", "Mid-cap and up", "pass"), ("mega-cap", "Large-cap and up", "pass"),
                                         ("large-cap", "Large-cap and up", "pass"), ("micro-cap", "Small-cap and up", "fail"), ("small-cap", "Small-cap and up", "pass"),
                                         (None, "Mid-cap and up", "unknown")])
def test_size_rule(size, want, r):
    assert res(fl.check(prefs(size=want), ctx(size=size)), "Company size") == r


@pytest.mark.parametrize("g,want,r", [(0.0, "Growing (above 0%)", "fail"), (0.1, "Growing (above 0%)", "pass"), (5.0, "5% a year or more", "pass"),
                                      (4.99, "5% a year or more", "fail"), (10.0, "10% a year or more", "pass"), (9.99, "10% a year or more", "fail"),
                                      (None, "10% a year or more", "unknown")])
def test_growth_rule(g, want, r):
    assert res(fl.check(prefs(growth=want), ctx(rev_growth=g)), "Sales growth") == r


@pytest.mark.parametrize("w,share,r", [(10.0, 10, "pass"), (10.1, 10, "fail"), (0.0, 10, "pass"), (25.0, 30, "pass")])
def test_one_stock_limit_is_percent_only(w, share, r):
    row = next(x for x in fl.check(prefs(max_share=share), ctx(weight=w)) if x["rule"] == "Most I'd put in one stock")
    assert row["result"] == r and "$" not in str(row)
    assert (row["stock"] == "you don't hold it") == (w == 0)


def test_every_row_has_a_known_result_and_unique_rule_names():
    rows = fl.check(prefs(dividend="I want a dividend", size="Mid-cap and up", growth="5% a year or more"), ctx(weight=3.0, div={"active": True}))
    assert len(rows) == 9 and len({r["rule"] for r in rows}) == 9 and {r["result"] for r in rows} <= {"pass", "fail", "unknown"}


@pytest.mark.parametrize("p,f,u,verdict", [(5, 0, 0, "Fits your rules"), (4, 0, 2, "Fits your rules"), (3, 1, 0, "Mostly fits"), (4, 1, 0, "Mostly fits"), (5, 2, 0, "Partly fits"), (6, 2, 0, "Mostly fits"),
                                           (2, 2, 0, "Partly fits"), (3, 2, 0, "Partly fits"), (1, 2, 0, "Doesn't fit"), (0, 3, 0, "Doesn't fit")])
def test_verdict_bands(p, f, u, verdict):
    rows = [{"result": "pass"}] * p + [{"result": "fail"}] * f + [{"result": "unknown"}] * u
    s = fl.summary(rows)
    assert s["verdict"] == verdict and (s["pass"], s["fail"], s["unknown"], s["checked"], s["total"]) == (p, f, u, p + f, p + f + u)


def test_nothing_checkable_gives_no_verdict():
    assert fl.summary([{"result": "unknown"}] * 3)["verdict"] is None and fl.summary([])["verdict"] is None


# ---------------------------------------------------------------- wording
def test_score_text_names_strongest_weakest_and_what_is_missing():
    m = {"peTTM": 60.0, "revenueGrowthTTMYoy": 25.0, "netProfitMarginTTM": 30.0, "roeTTM": 40.0}
    sc = sl.scorecard(m, STATS_UP)
    t = " ".join(dtx.score_summary("ACME", sc))
    assert f"Scorecard: {sc['score']} out of 100 ({sc['label']})" in t
    assert "**Weakest: Value** (20)" in t and "Strongest area: " in t
    assert "Marked Watch: P/E (trailing 12 months) (Value)" in t
    assert "Not scored (no data): Safety" in t and "not a forecast and not a recommendation" in t


def test_score_text_for_funds_missing_data_and_a_flat_profile():
    assert "Funds and ETFs aren't scored" in dtx.score_summary("VOO", None, fund=True)[0]
    assert "at least three of the five areas" in dtx.score_summary("X", None)[0]
    flat = dtx.score_summary("ACME", sl.scorecard(GOOD, STATS_UP))
    assert "All areas scored about the same." in flat and not any(b.startswith("Marked Watch") for b in flat)


def test_watch_list_is_capped_at_five_with_a_count():
    m = {"peTTM": -1.0, "psTTM": 20.0, "pbQuarterly": 30.0, "pfcfShareTTM": -5.0, "revenueGrowthTTMYoy": -2.0, "netProfitMarginTTM": -9.0, "totalDebt/totalEquityQuarterly": 5.0}
    sc = sl.scorecard(m, STATS_UP)
    watch = sum(len(a["worst"]) for a in sc["areas"])
    assert watch > 5
    t = " ".join(dtx.score_summary("X", sc))
    assert f"and {watch - 5} more." in t


def test_fit_text_lists_misses_with_both_numbers_and_stays_neutral():
    rows = fl.check(prefs(swings="Small (under 20% a year)", years=3), ctx())
    summ = fl.summary(rows)
    t = " ".join(dtx.fit_summary("ACME", rows, summ))
    assert f"meets {summ['pass']} of the {summ['checked']} rules" in t
    assert "price swings (yours: up to 20% a year, this stock: 30% a year)" in t and "time i can leave it (yours: 3 years" in t
    assert "not a recommendation" in t and "$" not in t
    t2 = " ".join(dtx.fit_summary("ACME", fl.check(prefs(), ctx(hz=None)), fl.summary(fl.check(prefs(), ctx(hz=None)))))
    assert "couldn't be checked" in t2 and "**Couldn't check:** time i can leave it" in t2


def test_fit_text_edge_cases():
    assert "Turn on at least one rule" in dtx.fit_summary("X", [], fl.summary([]))[0]
    nothing = [{"rule": "A", "yours": "1", "stock": "n/a", "result": "unknown"}]
    assert "None of your rules could be checked" in dtx.fit_summary("X", nothing, fl.summary(nothing))[0]


# ---------------------------------------------------------------- chart
@pytest.mark.parametrize("mode", ["light", "dark"])
def test_score_bars_build(mode):
    sc = sl.scorecard(GOOD, STATS_UP)
    assert dc.score_bars(sc["areas"], mode) is not None
    dc.score_bars(sc["areas"][:1], mode)
