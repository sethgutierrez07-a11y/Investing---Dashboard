"""
Strategy Lab charts (Plotly). Presentation only; numbers come from lab_lib.
Two series at most per chart, fixed colours (strategy = blue, benchmark = orange),
2px lines, end-of-line labels so identity never depends on colour alone.
"""

from __future__ import annotations

import numpy as np
import plotly.graph_objects as go

from holdings_charts import SANS, TOKENS, _base_layout


def _layout(mode: str, height: int, **overrides) -> dict:
    """Base layout with per-chart overrides merged in (passing a key twice to update_layout is a TypeError)."""
    d = _base_layout(mode, height)
    d.update(overrides)
    return d

SERIES = {"light": {"strategy": "#2a78d6", "benchmark": "#eb6834"}, "dark": {"strategy": "#3987e5", "benchmark": "#d95926"}}


def equity_chart(curves: dict, mode: str = "dark", split=None, height: int = 360) -> go.Figure:
    """curves: name -> equity Series ('strategy' first, benchmark second). Optional split date marks the held-out period."""
    t, c = TOKENS[mode], SERIES[mode]
    fig = go.Figure()
    for i, (name, eq) in enumerate(curves.items()):
        colour = c["strategy"] if i == 0 else c["benchmark"]
        fig.add_trace(go.Scatter(
            x=eq.index, y=eq.values, mode="lines", name=name, line=dict(color=colour, width=2),
            hovertemplate=f"<b>{name}</b><br>%{{x|%b %d, %Y}}<br>$%{{y:,.0f}}<extra></extra>",
        ))
        fig.add_annotation(x=eq.index[-1], y=float(eq.values[-1]), text=f" {name}", showarrow=False, xanchor="left",
                           font=dict(color=t["text2"], size=12))
    if split is not None:
        fig.add_vline(x=split, line=dict(color=t["muted"], width=1, dash="dot"))
        fig.add_annotation(x=split, y=1, yref="paper", text="held-out period starts →", showarrow=False,
                           xanchor="left", yanchor="top", font=dict(color=t["muted"], size=11))
    fig.update_layout(**_layout(mode, height, showlegend=False, margin=dict(l=4, r=110, t=8, b=8), hovermode="x unified"))
    fig.update_xaxes(showgrid=False, linecolor=t["grid"], tickfont=dict(color=t["muted"]))
    fig.update_yaxes(gridcolor=t["grid"], zeroline=False, tickprefix="$", tickformat=",.0f", tickfont=dict(color=t["muted"]))
    return fig


def drawdown_chart(dds: dict, mode: str = "dark", height: int = 200) -> go.Figure:
    """dds: name -> drawdown Series (0 to -1). Shows how deep and how long each fall lasted."""
    t, c = TOKENS[mode], SERIES[mode]
    fig = go.Figure()
    for i, (name, dd) in enumerate(dds.items()):
        colour = c["strategy"] if i == 0 else c["benchmark"]
        fig.add_trace(go.Scatter(
            x=dd.index, y=dd.values * 100, mode="lines", name=name, line=dict(color=colour, width=2),
            hovertemplate=f"<b>{name}</b><br>%{{x|%b %d, %Y}}<br>%{{y:.1f}}% below its peak<extra></extra>",
        ))
    fig.update_layout(**_layout(mode, height, showlegend=True, hovermode="x unified",
                                legend=dict(orientation="h", y=1.12, x=0, font=dict(color=t["text2"]))))
    fig.update_xaxes(showgrid=False, linecolor=t["grid"], tickfont=dict(color=t["muted"]))
    fig.update_yaxes(gridcolor=t["grid"], zeroline=False, ticksuffix="%", tickfont=dict(color=t["muted"]))
    return fig


def luck_chart(sims, observed: float, mode: str = "dark", height: int = 240) -> go.Figure:
    """Histogram of what random placements of the same in/out pattern earned (annualised), with the real result marked."""
    t, c = TOKENS[mode], SERIES[mode]
    vals = np.asarray(sims) * 100
    fig = go.Figure(go.Histogram(x=vals, nbinsx=40, marker=dict(color=c["benchmark"]), opacity=0.85,
                                 hovertemplate="%{x:.1f}% a year: %{y} random placements<extra></extra>"))
    fig.add_vline(x=observed * 100, line=dict(color=c["strategy"], width=3))
    fig.add_annotation(x=observed * 100, y=1, yref="paper", text=" your rule", showarrow=False, xanchor="left",
                       yanchor="top", font=dict(color=c["strategy"], size=12))
    fig.update_layout(**_layout(mode, height, showlegend=False, bargap=0.05))
    fig.update_xaxes(ticksuffix="%", title_text="Average yearly return of random placements (before costs)",
                     title_font=dict(size=12, color=t["muted"]), tickfont=dict(color=t["muted"]), linecolor=t["grid"])
    fig.update_yaxes(showgrid=False, showticklabels=False)
    return fig
