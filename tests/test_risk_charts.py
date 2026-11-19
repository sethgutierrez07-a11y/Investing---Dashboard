import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_lab_charts  # noqa: F401,E402  (installs a plotly stand-in if plotly is missing)

for m in ("risk_charts", "holdings_charts"):
    sys.modules.pop(m, None)
import risk_charts as rc  # noqa: E402


def corr(n=3):
    a = np.eye(n) + 0.3 * (1 - np.eye(n))
    names = [f"S{i}" for i in range(n)]
    return pd.DataFrame(a, index=names, columns=names)


@pytest.mark.parametrize("mode", ["light", "dark"])
@pytest.mark.parametrize("n", [2, 3, 8])
def test_heatmap_builds(mode, n):
    rc.corr_heatmap(corr(n), mode)


@pytest.mark.parametrize("mode", ["light", "dark"])
def test_bars_build(mode):
    rc.risk_vs_money(["A", "B", "C"], [50, 30, 20], [70, 20, 10], mode)
    rc.stress_bars(["Market -10%", "Market -20%"], [-9.0, -18.0], mode)
    rc.risk_vs_money(["A"], [100], [100], mode)


def test_layout_overrides_replace_base_values():
    d = rc._layout("dark", 300, margin=dict(l=1, r=2, t=3, b=4), showlegend=False)
    assert d["margin"] == dict(l=1, r=2, t=3, b=4) and d["height"] == 300
