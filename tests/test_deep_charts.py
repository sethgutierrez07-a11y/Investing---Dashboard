import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_lab_charts  # noqa: F401,E402  (installs a plotly stand-in if plotly is missing)

for m in ("deep_charts", "risk_charts", "holdings_charts"):
    sys.modules.pop(m, None)
import deep_charts as dc  # noqa: E402


def prices(n=1500):
    return pd.Series(100 * np.exp(np.cumsum(np.random.default_rng(0).normal(0.0004, 0.012, n))), index=pd.bdate_range(end="2026-11-19", periods=n))


@pytest.mark.parametrize("mode", ["light", "dark"])
@pytest.mark.parametrize("years", [1, 2, 5, 20])
def test_price_chart_builds_for_every_range(mode, years):
    dc.price_chart(prices(), mode, years=years)


def test_price_chart_survives_short_history():
    dc.price_chart(prices(120), "dark", years=2)             # moving averages are empty, the line still draws


@pytest.mark.parametrize("mode", ["light", "dark"])
def test_analyst_bars_build_with_missing_ratings(mode):
    dc.analyst_bars({"strongBuy": 5, "buy": 3, "hold": 2, "sell": 0, "strongSell": 1}, mode)
    dc.analyst_bars({"hold": 4}, mode)
    dc.analyst_bars({}, mode)
