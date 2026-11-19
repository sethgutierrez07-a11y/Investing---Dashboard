"""
Market charts (Plotly). Presentation only; numbers come from market_lib.
Sector bars use the app's reserved green/red, always with a +/- sign in the label (never color alone).
Yield-curve lines use the fixed blue/orange pair plus a muted gray for the oldest line.
"""

from __future__ import annotations

import plotly.graph_objects as go

from holdings_charts import CRITICAL, GOOD, TOKENS, _base_layout
from risk_charts import SERIES


def _layout(mode: str, height: int, **overrides) -> dict:
    d = _base_layout(mode, height)
    d.update(overrides)
    return d


def sector_bars(labels: list[str], values: list[float], mode: str = "dark", height: int | None = None) -> go.Figure:
    """Horizontal bars of sector returns (fractions), best at the top."""
    t = TOKENS[mode]
    labs, vals = labels[::-1], [v * 100 for v in values[::-1]]
    fig = go.Figure(go.Bar(
        y=labs, x=vals, orientation="h", marker_color=[GOOD if v >= 0 else CRITICAL for v in vals],
        text=[f"{v:+.1f}%" for v in vals], textposition="outside", cliponaxis=False,
        hovertemplate="<b>%{y}</b><br>%{x:+.2f}%<extra></extra>"))
    fig.update_layout(**_layout(mode, height or max(240, 34 * len(labs) + 40), showlegend=False, margin=dict(l=4, r=50, t=8, b=8), bargap=0.3))
    fig.update_xaxes(showgrid=False, showticklabels=False, zeroline=True, zerolinecolor=t["grid"])
    fig.update_yaxes(showgrid=False, tickfont=dict(color=t["text2"]))
    return fig


def yield_curve(maturities: list[str], lines: dict[str, list[float | None]], mode: str = "dark", height: int = 300) -> go.Figure:
    """Treasury yields by maturity: the latest curve against a month ago and a year ago (values in %)."""
    t, c = TOKENS[mode], SERIES[mode]
    colors = [c["a"], c["b"], t["muted"]]
    fig = go.Figure()
    for i, (name, vals) in enumerate(lines.items()):
        fig.add_trace(go.Scatter(x=maturities, y=vals, name=name, mode="lines+markers", connectgaps=True,
                                 line=dict(color=colors[i % 3], width=3 if i == 0 else 2, dash="solid" if i == 0 else "dot"),
                                 marker=dict(size=8, line=dict(color=t["surface"], width=2)),
                                 hovertemplate="%{x}: %{y:.2f}%<extra>" + name + "</extra>"))
    fig.update_layout(**_layout(mode, height, showlegend=True, legend=dict(orientation="h", y=1.14, x=0, font=dict(color=t["text2"])), hovermode="x unified"))
    fig.update_xaxes(showgrid=False, tickfont=dict(color=t["text2"]))
    fig.update_yaxes(gridcolor=t["grid"], ticksuffix="%", tickfont=dict(color=t["text2"]), zeroline=False)
    return fig


def vix_chart(dates, values, mode: str = "dark", height: int = 260) -> go.Figure:
    """The VIX over the past year with its typical (20) and stressed (30) levels marked."""
    t, c = TOKENS[mode], SERIES[mode]
    fig = go.Figure(go.Scatter(x=list(dates), y=list(values), mode="lines", name="VIX", line=dict(color=c["a"], width=2),
                               hovertemplate="%{x|%b %d, %Y}: %{y:.1f}<extra></extra>"))
    for level, text in ((20, "20: about typical"), (30, "30: stressed")):
        fig.add_hline(y=level, line=dict(color=t["muted"], width=1, dash="dash"), annotation_text=text, annotation_position="top left",
                      annotation_font=dict(color=t["text2"], size=11))
    fig.update_layout(**_layout(mode, height, showlegend=False))
    fig.update_xaxes(showgrid=False, tickfont=dict(color=t["text2"]))
    fig.update_yaxes(gridcolor=t["grid"], tickfont=dict(color=t["text2"]), rangemode="tozero")
    return fig
