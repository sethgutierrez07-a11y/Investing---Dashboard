"""Run the REAL dividend chart functions (plotly if installed, else the kwargs-faithful stand-in from test_lab_charts)."""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
import test_lab_charts  # noqa: F401,E402  (installs the plotly stand-in if plotly is missing)

for m in ("dividend_charts", "holdings_charts"):
    sys.modules.pop(m, None)
import dividend_charts as dc  # noqa: E402
import dividend_lib as dl  # noqa: E402


def traces(fig):
    return list(getattr(fig, "data", None) or fig.traces)


def val(t, key):
    return t[key] if isinstance(t, dict) else getattr(t, key)


def colours_of(t):
    if isinstance(t, dict):
        c = t.get("marker_color")
        return c if c is not None else t["marker"]["color"]
    return t.marker.color


MONTHS = ["Jan", "Feb", "Mar"]


@pytest.mark.parametrize("mode", ["light", "dark"])
@pytest.mark.parametrize("unit", ["$", "%"])
def test_month_and_stacked_bars_build(mode, unit):
    fig = dc.month_bars(MONTHS, [10.0, 0.0, 25.5], mode, unit)
    assert list(val(traces(fig)[0], "y")) == [10.0, 0.0, 25.5]
    st = dc.stacked_months(MONTHS, {"VOO": [5, 0, 9], "AAPL": [1, 2, 3], "Other": [0, 1, 0]}, mode, unit)
    assert [val(t, "name") for t in traces(st)] == ["VOO", "AAPL", "Other"]


def test_stack_colours_follow_the_ticker_and_other_is_grey():
    fig = dc.stacked_months(MONTHS, {"A": [1, 1, 1], "B": [1, 1, 1], "Other": [1, 1, 1]}, "dark")
    cols = [colours_of(t) for t in traces(fig)]
    assert cols[0] == dc.STACK["dark"][0] and cols[1] == dc.STACK["dark"][1] and cols[2] == dc.TOKENS["dark"]["muted"]
    assert len(set(dc.STACK["dark"])) == 5 and len(set(dc.STACK["light"])) == 5


def test_share_vs_weight_and_growth_bars_build_and_flag_negative_growth():
    dc.share_vs_weight(["VOO", "AAPL"], [73.0, 27.0], [50.0, 40.0], "light")
    fig = dc.growth_bars(["AAPL", "KO", "XYZ"], [7.5, 3.0, -2.0], "dark")
    t = traces(fig)[0]
    text = list(val(t, "text"))
    assert text == ["▼-2.0%", "+3.0%", "+7.5%"]                      # reversed for a top-down ranked chart; red ones carry ▼
    colours = list(colours_of(t))
    assert colours == [dc.CRITICAL, dc.SERIES["dark"]["a"], dc.SERIES["dark"]["a"]]


@pytest.mark.parametrize("unit", ["$", "x"])
def test_drip_and_whatif_charts_build(unit):
    idx = pd.bdate_range("2020-01-01", periods=300)
    s = pd.Series(np.linspace(10_000, 14_000, 300), index=idx)
    dc.drip_chart({"Reinvested": s * 1.05, "Dividends as cash": s, "Price only": s * 0.9}, "dark", unit)
    dc.whatif_chart(dl.project_growth(10_000, 3, 6, 5, 15), "light", unit)


def test_overrides_replace_base_values_instead_of_colliding():
    d = dc._layout("dark", 300, margin=dict(l=1, r=2, t=3, b=4), showlegend=True)
    assert d["margin"] == dict(l=1, r=2, t=3, b=4) and d["height"] == 300
