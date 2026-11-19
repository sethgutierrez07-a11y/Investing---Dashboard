import re
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
import dividend_lib as dl  # noqa: E402
import dividend_text as dt  # noqa: E402
from test_dividend_lib import TODAY, act, flat_prices, merged_df, profiles_for_table, quarterly, sample_activity  # noqa: E402


def build(activity=None, merged=None, profiles=None, drip=True, hide=False, activity_ok=True, cash_apy=0.0, held_shares=None):
    activity = sample_activity() if activity is None else activity
    merged = merged_df() if merged is None else merged
    profiles = profiles_for_table() if profiles is None else profiles
    rec = dl.received_by_symbol(activity, TODAY)
    table = dl.company_table(merged, rec, profiles)
    shares = dict(zip(merged["Symbol"], merged["Units"]))
    proj = dl.project_payments(shares, profiles, TODAY, lags={"__default__": 10})
    sim = None
    if drip:
        ex = pd.DatetimeIndex([pd.Timestamp("2019-04-01") + pd.DateOffset(months=3 * i) for i in range(40)])
        sim = dl.simulate_drip(flat_prices(8), pd.Series(1.0, index=ex), years=5, cash_apy=cash_apy)
    return dt.write_summary(
        income=dl.income_summary(activity, TODAY), reinv=dl.reinvestment(activity), port=dl.portfolio_income(table),
        table=table, proj=proj, drip=sim, drip_symbol="VOO", cash_apy=cash_apy, activity_ok=activity_ok, hide=hide)


def section(s, title):
    return " ".join(dict(s)[title])


def test_sections_and_every_bullet_is_a_clean_sentence():
    s = build()
    assert [t for t, _ in s] == ["Bottom line", "Where it comes from", "What's coming", "Does DRIP pay?", "Worth knowing"]
    for _, bullets in s:
        for b in bullets:
            assert b.strip() and b[-1] in ".)" and not re.search(r"\bnan\b", b.lower()) and "None" not in b and "{" not in b


def test_bottom_line_numbers_match_the_table():
    s = build()
    table = dl.company_table(merged_df(), dl.received_by_symbol(sample_activity(), TODAY), profiles_for_table())
    annual = table["Annual income"].sum()
    text = section(s, "Bottom line")
    assert f"${annual:,.0f}" in text and "2 of your 3 holdings pay" in text
    assert "$66 of dividends actually arrived" in text and "up 57%" in text          # 66 vs 42 the year before


def test_hide_mode_never_prints_private_dollar_amounts():
    s = build(hide=True)
    private = " ".join(" ".join(b) for t, b in s if t != "Does DRIP pay?")
    assert not re.search(r"\$\d", private) and "$•••" in private
    assert re.search(r"\$\d", section(s, "Does DRIP pay?"))      # the replay is a made-up $10,000, not your money


def test_concentration_wording_follows_the_numbers():
    s = build()
    text = section(s, "Bottom line")
    assert "biggest dividend source" in text or "leans on it" in text or "only" in text
    m = merged_df()
    m.loc[m["Symbol"] == "AAPL", "Market value"] = 100.0           # tiny holding...
    pr = profiles_for_table()
    pr["AAPL"] = dl.dividend_profile(quarterly("2020-02-10", n=27, amount=5.0), TODAY)   # ...paying a lot
    assert "leans on it more than its size suggests" in section(build(merged=m, profiles=pr), "Bottom line")


def test_single_source_warning_and_non_payer_note():
    pr = profiles_for_table()
    pr["VOO"] = dl.dividend_profile(None, TODAY)
    s = build(profiles=pr)
    assert "Dividend-wise" not in section(s, "Bottom line")          # only one payer: concentration lines need >= 2
    m = merged_df()
    out = section(build(merged=m, profiles=pr), "Where it comes from")
    assert "VOO (50% of invested) and TSLA (10% of invested) pay no dividend" in out


def test_no_payers_gives_a_short_honest_summary():
    pr = {k: dl.dividend_profile(None, TODAY) for k in ("VOO", "AAPL", "TSLA")}
    s = build(activity=dl.parse_activities([]), profiles=pr, drip=False)
    assert [t for t, _ in s] == ["Bottom line", "Does DRIP pay?", "Worth knowing"]
    assert "None of your 3 holdings" in section(s, "Bottom line")


def test_short_or_missing_activity_feed_is_said_plainly():
    short = dl.parse_activities([act("DIVIDEND", "2026-09-01", amount=5.0, id_="x")])
    assert "only reaches back to Sep 1" in section(build(activity=short), "Bottom line")
    assert "No dividend payments came back" in section(build(activity=dl.parse_activities([])), "Bottom line")
    assert "couldn't be read" in section(build(activity=dl.parse_activities([]), activity_ok=False), "Bottom line")


def test_sold_and_stopped_payers_are_called_out():
    act_ = dl.parse_activities([act("DIVIDEND", "2026-06-01", sym="XOM", amount=40.0, id_="x")])
    pr = profiles_for_table()
    pr["TSLA"] = dl.dividend_profile(quarterly("2016-01-10", n=12), TODAY)       # paid long ago, stopped
    text = section(build(activity=act_, profiles=pr), "Where it comes from")
    assert "XOM ($40) paid you in the last year but is no longer held" in text
    assert "TSLA appears to have stopped paying" in text


def test_coming_up_lists_next_dates_busiest_month_and_assumptions():
    text = section(build(), "What's coming")
    assert text.startswith("Next up:") and "(ex-dividend date plus your usual delay)" in text
    assert "Busiest month:" in text and "no raises, no cuts" in text


def test_variable_and_special_payers_are_noted():
    pr = profiles_for_table()
    vals = [1.0, 1.4, 0.8, 1.6] * 3
    idx = pd.DatetimeIndex([pd.Timestamp("2024-02-20") + pd.DateOffset(months=3 * i) for i in range(12)])
    pr["VOO"] = dl.dividend_profile(pd.Series(vals, index=idx)[lambda s: s.index <= TODAY], TODAY)
    assert "different amount each time" in section(build(profiles=pr), "What's coming")


def test_drip_section_reports_replay_decomposition_and_account_behaviour():
    text = section(build(), "Does DRIP pay?")
    assert "Replaying VOO's real history over 5 years" in text
    m = re.search(r"Of the \$[\d,]+ total gain, (\d+)% came from the price, (\d+)% from the dividends themselves, and (\d+)%", text)
    assert m and abs(sum(map(int, m.groups())) - 100) <= 2
    assert "12% of the dividend cash" in text or "reinvested" in text
    assert "same as buying more shares" in text and "still taxed that year" in text
    assert "earning 4.0% a year" in section(build(cash_apy=0.04), "Does DRIP pay?")


def test_drip_section_when_dividends_land_as_cash():
    no_rei = dl.parse_activities([act("DIVIDEND", "2026-09-01", amount=5.0, id_="x")])
    assert "look to be landing as cash" in section(build(activity=no_rei), "Does DRIP pay?")


def test_worth_knowing_names_the_fastest_grower_and_flags_flat_ones():
    pr = profiles_for_table()
    out = section(build(profiles=pr), "Worth knowing")
    assert "AAPL's dividend per share has grown about 5.0% a year" in out and "total return" in out
    assert "not financial advice" in out
