"""
Deep-Dive charts (Plotly). Presentation only; numbers come from deep_lib.
Growth-of-$10,000 and drawdown charts come from lab_charts (blue = this stock, orange = the S&P 500).
Analyst ratings use the same fixed green→gray→red ramp as the dashboard, always with a count on every bar.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

import idea_lib as il
from holdings_charts import TOKENS, _base_layout
from risk_charts import SERIES


def _layout(mode: str, height: int, **overrides) -> dict:
    d = _base_layout(mode, height)
    d.update(overrides)
    return d


def price_chart(prices, mode: str = "dark", height: int = 340, years: float = 2) -> go.Figure:
    """Closing price with its 50-day and 200-day averages over the last `years` (averages computed on the full history)."""
    t, c = TOKENS[mode], SERIES[mode]
    p = prices.dropna()
    ma50, ma200 = p.rolling(50).mean(), p.rolling(200).mean()
    start = p.index[-1] - pd.Timedelta(days=int(years * 365.25))
    p, ma50, ma200 = p[p.index >= start], ma50[ma50.index >= start], ma200[ma200.index >= start]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=p.index, y=p.values, mode="lines", name="Price", line=dict(color=c["a"], width=2),
                             hovertemplate="%{x|%b %d, %Y}<br>$%{y:,.2f}<extra>Price</extra>"))
    fig.add_trace(go.Scatter(x=ma50.index, y=ma50.values, mode="lines", name="50-day average", line=dict(color=c["b"], width=1.5, dash="dot"),
                             hovertemplate="$%{y:,.2f}<extra>50-day</extra>"))
    fig.add_trace(go.Scatter(x=ma200.index, y=ma200.values, mode="lines", name="200-day average", line=dict(color=t["muted"], width=1.5, dash="dash"),
                             hovertemplate="$%{y:,.2f}<extra>200-day</extra>"))
    fig.update_layout(**_layout(mode, height, showlegend=True, hovermode="x unified",
                                legend=dict(orientation="h", y=1.12, x=0, font=dict(color=t["text2"]))))
    fig.update_xaxes(showgrid=False, tickfont=dict(color=t["muted"]))
    fig.update_yaxes(gridcolor=t["grid"], zeroline=False, tickprefix="$", tickfont=dict(color=t["muted"]))
    return fig


def analyst_bars(trend: dict, mode: str = "dark", height: int = 230) -> go.Figure:
    """Counts of analysts per rating, best at the top, every bar labelled."""
    t = TOKENS[mode]
    rows = [(label, n, colour) for label, n, colour in il.consensus_slices(trend)][::-1]
    fig = go.Figure(go.Bar(y=[r[0] for r in rows], x=[r[1] for r in rows], orientation="h", marker_color=[r[2] for r in rows],
                           text=[str(r[1]) for r in rows], textposition="outside", cliponaxis=False,
                           hovertemplate="%{y}: %{x} analysts<extra></extra>"))
    fig.update_layout(**_layout(mode, height, showlegend=False, margin=dict(l=4, r=40, t=8, b=8), bargap=0.3))
    fig.update_xaxes(showgrid=False, showticklabels=False)
    fig.update_yaxes(showgrid=False, tickfont=dict(color=t["text2"]))
    return fig


def hold_chart(windows: list[dict], mode: str = "dark", height: int = 240) -> go.Figure:
    """Share of past holding periods that ended in a gain, one bar per length, every bar labelled."""
    t, c = TOKENS[mode], SERIES[mode]
    labels = [f"{w['years']} year" + ("s" if w["years"] > 1 else "") for w in windows]
    vals = [w["share_gain"] * 100 for w in windows]
    fig = go.Figure(go.Bar(x=labels, y=vals, marker_color=c["a"], text=[f"{v:.0f}%" for v in vals], textposition="outside", cliponaxis=False,
                           customdata=[w["periods"] for w in windows],
                           hovertemplate="Held %{x}: gain in %{y:.0f}% of %{customdata:,} tested periods<extra></extra>"))
    fig.update_layout(**_layout(mode, height, showlegend=False, margin=dict(l=4, r=4, t=24, b=8), bargap=0.45))
    fig.update_xaxes(showgrid=False, tickfont=dict(color=t["text2"]))
    fig.update_yaxes(range=[0, 115], showgrid=True, gridcolor=t["grid"], zeroline=False, ticksuffix="%", tickfont=dict(color=t["muted"]))
    return fig
