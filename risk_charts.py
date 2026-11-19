"""
Risk charts (Plotly). Presentation only; numbers come from risk_lib.
Correlation is a single-hue scale (alike = darker); the paired bars reuse the app's fixed blue/orange;
falls use the reserved red with a ▼ in the label. Growth and drawdown charts come from lab_charts.
"""

from __future__ import annotations

import plotly.graph_objects as go

from holdings_charts import CRITICAL, TOKENS, _base_layout

SERIES = {"light": {"a": "#2a78d6", "b": "#eb6834"}, "dark": {"a": "#3987e5", "b": "#d95926"}}


def _layout(mode: str, height: int, **overrides) -> dict:
    d = _base_layout(mode, height)
    d.update(overrides)
    return d


def corr_heatmap(corr, mode: str = "dark", height: int | None = None) -> go.Figure:
    """Correlation between holdings, 0 (unrelated) to 1 (move together). Values are written in the cells."""
    t, c = TOKENS[mode], SERIES[mode]
    labels = list(corr.columns)
    z = [[float(corr.loc[a, b]) for b in labels] for a in labels]
    text = [[f"{v:.2f}" for v in row] for row in z]
    fig = go.Figure(go.Heatmap(
        z=z, x=labels, y=labels, zmin=0, zmax=1, text=text, texttemplate="%{text}", textfont=dict(color=t["text2"], size=12),
        colorscale=[[0, t["surface"]], [1, c["a"]]], showscale=False, xgap=2, ygap=2,
        hovertemplate="<b>%{y}</b> and <b>%{x}</b><br>correlation %{z:.2f}<extra></extra>",
    ))
    fig.update_layout(**_layout(mode, height or max(260, 52 * len(labels) + 80)))
    fig.update_xaxes(showgrid=False, side="top", tickfont=dict(color=t["text2"]))
    fig.update_yaxes(showgrid=False, autorange="reversed", tickfont=dict(color=t["text2"]))
    return fig


def risk_vs_money(symbols: list[str], money_share: list[float], risk_share: list[float], mode: str = "dark",
                  height: int | None = None) -> go.Figure:
    """Each holding's share of your money next to its share of the mix's risk (both in %)."""
    t, c = TOKENS[mode], SERIES[mode]
    syms = symbols[::-1]
    fig = go.Figure()
    fig.add_trace(go.Bar(y=syms, x=money_share[::-1], orientation="h", name="Share of your money", marker_color=c["b"],
                         text=[f"{v:.0f}%" for v in money_share[::-1]], textposition="outside", cliponaxis=False,
                         hovertemplate="<b>%{y}</b><br>%{x:.1f}% of your money<extra></extra>"))
    fig.add_trace(go.Bar(y=syms, x=risk_share[::-1], orientation="h", name="Share of the risk", marker_color=c["a"],
                         text=[f"{v:.0f}%" for v in risk_share[::-1]], textposition="outside", cliponaxis=False,
                         hovertemplate="<b>%{y}</b><br>%{x:.1f}% of the mix's risk<extra></extra>"))
    fig.update_layout(**_layout(mode, height or max(220, 62 * len(syms) + 60), barmode="group", bargap=0.35, showlegend=True,
                                legend=dict(orientation="h", y=1.12, x=0, font=dict(color=t["text2"])),
                                margin=dict(l=4, r=40, t=8, b=8)))
    fig.update_xaxes(showgrid=False, showticklabels=False)
    fig.update_yaxes(showgrid=False, tickfont=dict(color=t["text2"]))
    return fig


def stress_bars(labels: list[str], values: list[float], mode: str = "dark", height: int = 230) -> go.Figure:
    """Estimated fall of the mix (negative %) for each market shock."""
    t = TOKENS[mode]
    fig = go.Figure(go.Bar(
        y=labels[::-1], x=values[::-1], orientation="h", marker_color=CRITICAL,
        text=[f"▼ {abs(v):.1f}%" for v in values[::-1]], textposition="outside", cliponaxis=False,
        hovertemplate="<b>%{y}</b><br>about %{x:.1f}%<extra></extra>",
    ))
    fig.update_layout(**_layout(mode, height, showlegend=False, margin=dict(l=4, r=60, t=8, b=8)))
    fig.update_xaxes(showgrid=False, showticklabels=False)
    fig.update_yaxes(showgrid=False, tickfont=dict(color=t["text2"]))
    return fig
