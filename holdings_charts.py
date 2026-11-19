"""
Holdings charts (Plotly). Thin presentation layer: all numbers come from
holdings_lib. Colors follow a validated categorical palette (fixed order,
colour follows the *entity*, never its rank), a single hue for ranked bars,
and reserved good/critical colours for gains and losses (always paired with
a ▲/▼ sign and a label, never colour alone).
"""

from __future__ import annotations

import plotly.graph_objects as go

SANS = "system-ui, -apple-system, 'Segoe UI', sans-serif"

TOKENS = {
    "light": {"surface": "#ffffff", "grid": "#e1e0d9", "muted": "#898781", "text2": "#52514e", "blue": "#2a78d6"},
    "dark": {"surface": "#0e1117", "grid": "#2c2c2a", "muted": "#898781", "text2": "#c3c2b7", "blue": "#3987e5"},
}
# Entity -> colour (fixed order slots 1-6; the same class is always the same colour)
CLASS_COLORS = {
    "light": {"ETF": "#2a78d6", "Stock": "#eb6834", "Cash": "#1baf7a", "Fund": "#eda100",
              "Bond": "#e87ba4", "Crypto": "#008300", "Other": "#898781"},
    "dark": {"ETF": "#3987e5", "Stock": "#d95926", "Cash": "#199e70", "Fund": "#c98500",
             "Bond": "#d55181", "Crypto": "#0ca30c", "Other": "#898781"},
}
GOOD, CRITICAL = "#0ca30c", "#d03b3b"
DARK_TEXT_ON = {"Fund"}  # yellow fills take dark label ink, everything else white


def _base_layout(mode: str, height: int) -> dict:
    t = TOKENS[mode]
    return dict(
        height=height,
        margin=dict(l=4, r=4, t=8, b=8),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family=SANS, size=13, color=t["text2"]),
        hoverlabel=dict(font=dict(family=SANS)),
    )


def _round_bars(fig: go.Figure) -> None:
    try:  # needs a recent plotly; purely cosmetic
        fig.update_traces(marker_cornerradius=4)
    except Exception:
        pass


def rank_bars(top, mode: str = "dark") -> go.Figure:
    """Ranked horizontal bars of portfolio weight, one hue, largest first."""
    t = TOKENS[mode]
    labels = list(top["Symbol"])[::-1]
    values = [float(v) for v in top["Weight %"]][::-1]
    names = list(top["Description"])[::-1]
    fig = go.Figure(
        go.Bar(
            x=values, y=labels, orientation="h", marker_color=t["blue"],
            text=[f"{v:.1f}%" for v in values], textposition="outside", cliponaxis=False,
            customdata=names, hovertemplate="<b>%{y}</b><br>%{customdata}<br>%{x:.1f}% of portfolio<extra></extra>",
        )
    )
    fig.update_layout(**_base_layout(mode, 64 + 36 * len(labels)), bargap=0.42, showlegend=False)
    fig.update_xaxes(range=[0, max(values) * 1.2 if values else 1], ticksuffix="%", showgrid=True,
                     gridcolor=t["grid"], gridwidth=1, zeroline=False, tickfont=dict(color=t["muted"]))
    fig.update_yaxes(showgrid=False, automargin=True, tickfont=dict(color=t["text2"], size=13))
    _round_bars(fig)
    return fig


def mix_bar(mix, mode: str = "dark") -> go.Figure:
    """One tall segmented bar: how the whole splits across asset classes."""
    t = TOKENS[mode]
    colors = CLASS_COLORS[mode]
    fig = go.Figure()
    for _, r in mix.iterrows():
        cls, share = r["Class"], float(r["Share %"])
        fig.add_trace(
            go.Bar(
                x=[share], y=[""], orientation="h", name=cls,
                marker=dict(color=colors.get(cls, colors["Other"]), line=dict(color=t["surface"], width=2)),
                text=[f"{share:.0f}%" if share >= 7 else ""], textposition="inside", insidetextanchor="middle",
                textfont=dict(color="#0b0b0b" if cls in DARK_TEXT_ON else "#ffffff", size=15, family=SANS),
                hovertemplate=f"<b>{cls}</b><br>{share:.1f}% of portfolio<extra></extra>",
            )
        )
    fig.update_layout(
        **_base_layout(mode, 150), barmode="stack", bargap=0,
        legend=dict(orientation="h", yanchor="top", y=-0.08, x=0, font=dict(size=13, color=t["text2"])),
    )
    fig.update_xaxes(range=[0, 100], visible=False)
    fig.update_yaxes(visible=False)
    _round_bars(fig)
    return fig


def gain_bars(g, mode: str = "dark") -> go.Figure:
    """Gain/loss since purchase per holding, centred on zero. Sign shown as ▲/▼ plus text."""
    t = TOKENS[mode]
    labels = list(g["Symbol"])[::-1]
    values = [float(v) for v in g["Gain %"]][::-1]
    fig = go.Figure(
        go.Bar(
            x=values, y=labels, orientation="h",
            marker_color=[GOOD if v >= 0 else CRITICAL for v in values],
            text=[f"{'▲' if v >= 0 else '▼'} {v:+.1f}%" for v in values],
            textposition="outside", cliponaxis=False,
            hovertemplate="<b>%{y}</b><br>%{x:+.1f}% since purchase<extra></extra>",
        )
    )
    span = max([abs(v) for v in values] + [1.0])
    fig.update_layout(**_base_layout(mode, 64 + 34 * len(labels)), bargap=0.42, showlegend=False)
    fig.update_xaxes(range=[-span * 1.35 if min(values) < 0 else -span * 0.05, span * 1.35], ticksuffix="%",
                     showgrid=True, gridcolor=t["grid"], zeroline=True, zerolinecolor=t["muted"], zerolinewidth=1,
                     tickfont=dict(color=t["muted"]))
    fig.update_yaxes(showgrid=False, automargin=True, tickfont=dict(color=t["text2"], size=13))
    _round_bars(fig)
    return fig
