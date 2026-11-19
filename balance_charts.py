"""
Balance-check charts (Plotly). Presentation only; numbers come from balance_lib.
Two series in fixed colours (blue = you, orange = the reference), legend always shown, every bar labelled with its value.
"""

from __future__ import annotations

import plotly.graph_objects as go

from holdings_charts import TOKENS, _base_layout
from risk_charts import SERIES


def compare_bars(rows: list[dict], mode: str = "dark", ref_label: str = "Reference mix", height: int | None = None) -> go.Figure:
    """Grouped horizontal bars. rows: [{"label", "yours", "ref"}], first row at the top."""
    t, c = TOKENS[mode], SERIES[mode]
    rows = list(rows)[::-1]
    labels = [r["label"] for r in rows]
    h = height or max(180, 56 * len(rows) + 60)
    fig = go.Figure()
    fig.add_trace(go.Bar(y=labels, x=[r["ref"] for r in rows], orientation="h", name=ref_label, marker_color=c["b"],
                         text=[f"{r['ref']:.0f}%" for r in rows], textposition="outside", cliponaxis=False,
                         hovertemplate="%{y}: %{x:.1f}% " + f"({ref_label})<extra></extra>"))
    fig.add_trace(go.Bar(y=labels, x=[r["yours"] for r in rows], orientation="h", name="You", marker_color=c["a"],
                         text=[f"{r['yours']:.0f}%" for r in rows], textposition="outside", cliponaxis=False,
                         hovertemplate="%{y}: %{x:.1f}% (you)<extra></extra>"))
    top = max([r["ref"] for r in rows] + [r["yours"] for r in rows] + [1.0])
    fig.update_layout(**_base_layout(mode, h), barmode="group", bargap=0.35, bargroupgap=0.12, showlegend=True,
                      legend=dict(orientation="h", y=1.12, x=0, traceorder="reversed", font=dict(color=t["text2"])))
    fig.update_xaxes(range=[0, top * 1.18], showgrid=False, showticklabels=False)
    fig.update_yaxes(showgrid=False, tickfont=dict(color=t["text2"]))
    return fig
