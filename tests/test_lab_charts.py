"""
Run the REAL chart functions (not a fake module). Uses plotly if installed, otherwise a small
stand-in whose methods take **kwargs exactly like Plotly's, so a keyword passed twice
(the bug that broke the live page) raises the same TypeError.
"""

import sys
import types
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def install_stub_if_needed():
    try:
        import plotly.graph_objects  # noqa: F401
        return
    except ImportError:
        pass

    class Fig:
        def __init__(self, *traces):
            self.traces = list(traces)
            self.layout = {}
            self.annotations = []
            self.shapes = []

        def add_trace(self, t):
            self.traces.append(t)

        def add_annotation(self, **k):
            self.annotations.append(k)

        def add_vline(self, **k):
            self.shapes.append(k)

        def add_hline(self, **k):
            self.shapes.append(k)

        def update_layout(self, **k):
            self.layout.update(k)

        def update_xaxes(self, **k):
            pass

        def update_yaxes(self, **k):
            pass

        def update_traces(self, **k):
            pass

    go = types.ModuleType("plotly.graph_objects")
    go.Figure = Fig
    for name in ("Bar", "Pie", "Scatter", "Histogram", "Heatmap"):
        setattr(go, name, lambda **k: k)
    pkg = types.ModuleType("plotly")
    pkg.graph_objects = go
    sys.modules["plotly"], sys.modules["plotly.graph_objects"] = pkg, go


install_stub_if_needed()
for m in ("lab_charts", "holdings_charts"):
    sys.modules.pop(m, None)
import lab_charts as lc  # noqa: E402


def series(n=300, seed=0):
    rng = np.random.default_rng(seed)
    return pd.Series(10_000 * np.exp(np.cumsum(rng.normal(0.0003, 0.01, n))), index=pd.bdate_range("2020-01-01", periods=n))


@pytest.mark.parametrize("mode", ["light", "dark"])
def test_equity_chart_builds_with_and_without_split(mode):
    a, b = series(), series(seed=1)
    lc.equity_chart({"Rule": a, "Buy and hold": b}, mode)
    lc.equity_chart({"Rule": a, "Buy and hold": b}, mode, split=a.index[200], height=300)


@pytest.mark.parametrize("mode", ["light", "dark"])
def test_drawdown_and_luck_charts_build(mode):
    a = series()
    dd = a / a.cummax() - 1
    lc.drawdown_chart({"Rule": dd, "Buy and hold": dd * 1.5}, mode)
    lc.luck_chart(np.random.default_rng(0).normal(0.05, 0.03, 500), 0.08, mode)


def test_overrides_replace_base_values_instead_of_colliding():
    d = lc._layout("dark", 300, margin=dict(l=1, r=2, t=3, b=4), showlegend=False)
    assert d["margin"] == dict(l=1, r=2, t=3, b=4) and d["height"] == 300 and d["showlegend"] is False
