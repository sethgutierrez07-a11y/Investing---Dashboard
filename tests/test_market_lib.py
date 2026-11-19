"""Market overview calculations."""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import market_lib as ml  # noqa: E402


def ser(values, end="2026-11-19"):
    return pd.Series(values, index=pd.bdate_range(end=end, periods=len(values)), dtype=float)


def ramp(n=300, start=100.0, step=1.0, end="2026-11-19"):
    return ser([start + step * i for i in range(n)], end)


# ---------------------------------------------------------------- returns
def test_period_returns_exact_values():
    s = ramp(300)                                     # 100 ... 399
    r = ml.period_returns(s)
    last = 399.0
    assert r["1D"] == pytest.approx(last / 398 - 1)
    assert r["1W"] == pytest.approx(last / 394 - 1)
    assert r["1M"] == pytest.approx(last / 378 - 1)
    assert r["3M"] == pytest.approx(last / 336 - 1)
    assert r["1Y"] == pytest.approx(last / 147 - 1)


def test_ytd_uses_the_last_close_of_the_prior_year():
    s = pd.Series([100.0, 110.0, 121.0], index=pd.to_datetime(["2026-12-30", "2026-12-31", "2027-01-04"]))
    assert ml.period_returns(s)["YTD"] == pytest.approx(121 / 110 - 1)
    only_this_year = pd.Series([100.0, 105.0], index=pd.to_datetime(["2027-01-04", "2027-01-05"]))
    assert ml.period_returns(only_this_year)["YTD"] is None


def test_short_history_gives_none_not_garbage():
    r = ml.period_returns(ramp(10))
    assert r["1D"] is not None and r["1W"] is not None and r["1M"] is None and r["1Y"] is None
    assert all(v is None for v in ml.period_returns(None).values())
    assert all(v is None for v in ml.period_returns(ser([5.0])).values())
    assert all(v is None for v in ml.period_returns(pd.Series(dtype=float)).values())


def test_bad_values_are_ignored():
    s = ramp(60)
    s.iloc[10] = np.nan
    s.iloc[20] = -5.0
    s.iloc[30] = 0.0
    assert ml.period_returns(s)["1M"] is not None and np.isfinite(ml.period_returns(s)["1M"])


def test_unsorted_input_is_sorted():
    s = ramp(60)
    assert ml.period_returns(s.sample(frac=1, random_state=1)) == ml.period_returns(s)


# ---------------------------------------------------------------- yields
def test_level_changes_are_differences_not_percentages():
    s = ser([4.0] * 300)
    s.iloc[-1] = 4.25
    c = ml.level_changes(s)
    assert c["1D"] == pytest.approx(0.25) and c["1M"] == pytest.approx(0.25) and c["1Y"] == pytest.approx(0.25)
    assert ml.level_changes(ser([4.0]))["1D"] is None


def test_normalize_yield_only_rescales_tenfold_quotes():
    assert ml.normalize_yield(ser([42.5, 43.0])).iloc[-1] == pytest.approx(4.3)
    assert ml.normalize_yield(ser([4.2, 4.3])).iloc[-1] == pytest.approx(4.3)
    assert ml.normalize_yield(None).empty


def test_curve_points_with_lag_and_gaps():
    closes = {"^IRX": ser([5.0] * 30 + [4.0]), "^TNX": ser([4.0] * 30 + [4.5])}
    assert ml.curve_points(closes, ["^IRX", "^TNX"]) == [4.0, 4.5]
    assert ml.curve_points(closes, ["^IRX", "^TNX"], lag=1) == [5.0, 4.0]
    assert ml.curve_points(closes, ["^IRX", "^FVX", "^TNX"], lag=100) == [None, None, None]
    assert ml.curve_points(closes, ["^IRX", "^FVX", "^TNX"])[1] is None


@pytest.mark.parametrize("short,long,spread,label", [
    (5.0, 4.0, -1.0, "inverted"), (4.0, 4.2, 0.2, "flat"), (3.5, 4.5, 1.0, "upward-sloping"), (4.0, 4.5, 0.5, "upward-sloping"),
    (4.0, 4.0, 0.0, "flat")])
def test_curve_spread_and_label(short, long, spread, label):
    assert ml.curve_spread(short, long) == pytest.approx(spread)
    assert ml.curve_label(ml.curve_spread(short, long)) == label


def test_curve_missing_inputs():
    assert ml.curve_spread(None, 4.0) is None and ml.curve_spread(4.0, float("nan")) is None
    assert ml.curve_label(None) is None


# ---------------------------------------------------------------- trend
def test_trend_stats_uptrend():
    t = ml.trend_stats(ramp(300))
    assert t["trend"] == "up" and t["vs50"] > 0 and t["vs200"] > 0
    assert t["from_high"] == pytest.approx(0.0) and t["range_pos"] == pytest.approx(1.0)
    assert t["ma50"] == pytest.approx(np.mean(range(100 + 250, 400)))


def test_trend_stats_downtrend_and_mixed():
    down = ml.trend_stats(ramp(300, start=400, step=-1))
    assert down["trend"] == "down" and down["from_high"] < 0 and down["range_pos"] == pytest.approx(0.0)
    # long rise then a short dip: below the 50-day, still above the 200-day
    s = ser(list(np.linspace(100, 300, 280)) + list(np.linspace(300, 250, 20)))
    assert ml.trend_stats(s)["trend"] == "mixed"


def test_trend_stats_short_and_empty_history():
    t = ml.trend_stats(ramp(30))
    assert t["vs50"] is None and t["vs200"] is None and t["trend"] is None and t["last"] is not None
    assert ml.trend_stats(None)["last"] is None
    flat = ml.trend_stats(ser([5.0] * 300))
    assert flat["range_pos"] is None and flat["from_high"] == 0


# ---------------------------------------------------------------- VIX
@pytest.mark.parametrize("level,label", [(10, "Calm"), (14.99, "Calm"), (15, "Normal"), (19.9, "Normal"), (20, "Elevated"), (29.9, "Elevated"),
                                         (30, "Stressed"), (80, "Stressed")])
def test_vix_regimes(level, label):
    assert ml.vix_regime(level)[0] == label


def test_vix_regime_missing():
    assert ml.vix_regime(None) is None and ml.vix_regime(float("nan")) is None


# ---------------------------------------------------------------- tables
NAMES = {"XLK": "Technology", "XLY": "Consumer Discretionary", "XLC": "Communication", "XLP": "Consumer Staples", "XLU": "Utilities", "XLV": "Health Care"}


def sector_closes(**steps):
    return {s: ramp(300, step=steps.get(s, 0.5)) for s in NAMES}


def test_sector_table_sorted_best_first_and_skips_short_history():
    c = sector_closes(XLK=3.0, XLU=-0.2)
    c["XLC"] = ramp(10)                                               # too short for a 1-month return
    t = ml.sector_table(c, NAMES)
    assert t.iloc[0]["Symbol"] == "XLK" and t.iloc[-1]["Symbol"] == "XLU"
    assert "XLC" not in set(t["Symbol"]) and t["1M"].is_monotonic_decreasing
    assert ml.sector_table({}, NAMES).empty and list(ml.sector_table({}, NAMES).columns)[:2] == ["Symbol", "Sector"]


def test_breadth_counts_sectors_up():
    t = ml.sector_table(sector_closes(XLU=-0.3, XLP=-0.3), NAMES)
    assert ml.breadth(t) == (4, 6)
    assert ml.breadth(pd.DataFrame()) is None and ml.breadth(None) is None


def test_offense_vs_defense_gap_sign():
    t = ml.sector_table(sector_closes(XLK=3, XLY=3, XLC=3, XLP=0.2, XLU=0.2, XLV=0.2), NAMES)
    od = ml.offense_vs_defense(t)
    assert od["gap"] > 0 and od["gap"] == pytest.approx(od["offense"] - od["defense"])
    t2 = ml.sector_table(sector_closes(XLK=0.1, XLY=0.1, XLC=0.1, XLP=3, XLU=3, XLV=3), NAMES)
    assert ml.offense_vs_defense(t2)["gap"] < 0
    assert ml.offense_vs_defense(t.head(2)) is None and ml.offense_vs_defense(None) is None


def test_index_table_rows_and_missing_index():
    names = {"^GSPC": "S&P 500", "^IXIC": "Nasdaq", "^DJI": "Dow"}
    t = ml.index_table({"^GSPC": ramp(300), "^IXIC": ramp(300, step=2)}, names)
    assert list(t["Index"]) == ["S&P 500", "Nasdaq"]
    assert t.iloc[0]["Level"] == 399 and t.iloc[0]["1D"] == pytest.approx(399 / 398 - 1)
    assert ml.index_table({}, names).empty
