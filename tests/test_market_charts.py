import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_lab_charts  # noqa: F401,E402  (installs a plotly stand-in if plotly is missing)

for m in ("market_charts", "risk_charts", "holdings_charts"):
    sys.modules.pop(m, None)
import market_charts as mc  # noqa: E402


@pytest.mark.parametrize("mode", ["light", "dark"])
def test_sector_bars_build_for_mixed_empty_and_single(mode):
    mc.sector_bars(["A", "B", "C"], [0.05, -0.02, 0.0], mode)
    mc.sector_bars(["A"], [0.01], mode)
    mc.sector_bars([], [], mode)
    assert mc.sector_bars(["A"] * 11, [0.01] * 11, mode, height=500) is not None


@pytest.mark.parametrize("mode", ["light", "dark"])
def test_yield_curve_builds_with_gaps_and_extra_lines(mode):
    mats = ["3-month", "5-year", "10-year", "30-year"]
    mc.yield_curve(mats, {"Now": [4.0, 4.1, 4.3, 4.6], "1 month ago": [4.1, None, 4.2, 4.5], "1 year ago": [5.0, 4.4, 4.3, 4.5]}, mode)
    mc.yield_curve(mats, {"Now": [4.0, 4.1, 4.3, 4.6]}, mode)


@pytest.mark.parametrize("mode", ["light", "dark"])
def test_vix_chart_builds(mode):
    idx = pd.bdate_range("2026-01-01", periods=100)
    mc.vix_chart(idx, [15 + (i % 7) for i in range(100)], mode)


def test_colors_are_the_apps_reserved_status_pair():
    import holdings_charts as hc
    assert mc.GOOD == hc.GOOD and mc.CRITICAL == hc.CRITICAL
