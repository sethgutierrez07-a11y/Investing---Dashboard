"""
Dividend charts (Plotly). Presentation only; numbers come from dividend_lib.
Same conventions as the other pages: one hue for a single measure, fixed colours per entity,
2px lines, a 2px surface gap between stacked segments, direct end labels, reserved
green/red only for good/bad. `unit` is "$" or "%" so the page can hide dollar amounts.
"""

from __future__ import annotations

import plotly.graph_objects as go

from holdings_charts import CRITICAL, TOKENS, _base_layout

SERIES = {"light": {"a": "#2a78d6", "b": "#eb6834"}, "dark": {"a": "#3987e5", "b": "#d95926"}}
# fixed slots for up to five tickers, then grey for everything else
STACK = {"light": ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"],
         "dark": ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181"]}


def _layout(mode: str, height: int, **overrides) -> dict:
    d = _base_layout(mode, height)
    d.update(overrides)
    return d


def _fmt(unit: str) -> dict:
    return dict(tickprefix="$", tickformat=",.0f") if unit == "$" else dict(ticksuffix="%", tickformat=".0f")


def _hover(unit: str, decimals: int = 0) -> str:
    return f"$%{{y:,.{decimals}f}}" if unit == "$" else f"%{{y:.{decimals}f}}%"


def month_bars(labels: list[str], values: list[float], mode: str = "dark", unit: str = "$", name: str = "Dividends",
               height: int = 280, hover_extra: list[str] | None = None) -> go.Figure:
    """One bar per month, one hue. Zero months stay visible as gaps."""
    t, c = TOKENS[mode], SERIES[mode]
    fig = go.Figure(go.Bar(
        x=labels, y=values, marker_color=c["a"], name=name,
        customdata=hover_extra or [""] * len(values),
        hovertemplate=f"<b>%{{x}}</b><br>{name}: {_hover(unit, 2 if unit == '$' else 1)}%{{customdata}}<extra></extra>",
    ))
    try:
        fig.update_traces(marker_cornerradius=4)
    except Exception:
        pass
    fig.update_layout(**_layout(mode, height, showlegend=False, bargap=0.25))
    fig.update_xaxes(showgrid=False, linecolor=t["grid"], tickfont=dict(color=t["muted"]))
    fig.update_yaxes(gridcolor=t["grid"], zeroline=False, tickfont=dict(color=t["muted"]), **_fmt(unit))
    return fig


def stacked_months(labels: list[str], series: dict[str, list[float]], mode: str = "dark", unit: str = "$",
                   height: int = 320) -> go.Figure:
    """Expected income by month, stacked by ticker. Series are drawn in the order given
    (largest first); anything after the fifth is the caller's 'Other', drawn grey."""
    t = TOKENS[mode]
    fig = go.Figure()
    for i, (name, vals) in enumerate(series.items()):
        colour = STACK[mode][i] if (i < len(STACK[mode]) and name != "Other") else t["muted"]
        fig.add_trace(go.Bar(
            x=labels, y=vals, name=name, marker=dict(color=colour, line=dict(color=t["surface"], width=2)),
            hovertemplate=f"<b>{name}</b> %{{x}}<br>{_hover(unit, 2 if unit == '$' else 1)}<extra></extra>",
        ))
    fig.update_layout(**_layout(mode, height, barmode="stack", bargap=0.25, showlegend=True,
                                legend=dict(orientation="h", y=1.14, x=0, font=dict(color=t["text2"]))))
    fig.update_xaxes(showgrid=False, linecolor=t["grid"], tickfont=dict(color=t["muted"]))
    fig.update_yaxes(gridcolor=t["grid"], zeroline=False, tickfont=dict(color=t["muted"]), **_fmt(unit))
    return fig


def share_vs_weight(symbols: list[str], income_share: list[float], invested_share: list[float], mode: str = "dark",
                    height: int | None = None) -> go.Figure:
    """For each payer: its share of dividend income next to its share of what you've invested."""
    t, c = TOKENS[mode], SERIES[mode]
    syms = symbols[::-1]
    fig = go.Figure()
    fig.add_trace(go.Bar(y=syms, x=invested_share[::-1], orientation="h", name="Share of what you've invested",
                         marker_color=c["b"], text=[f"{v:.0f}%" for v in invested_share[::-1]], textposition="outside",
                         cliponaxis=False, hovertemplate="<b>%{y}</b><br>%{x:.1f}% of invested money<extra></extra>"))
    fig.add_trace(go.Bar(y=syms, x=income_share[::-1], orientation="h", name="Share of dividend income",
                         marker_color=c["a"], text=[f"{v:.0f}%" for v in income_share[::-1]], textposition="outside",
                         cliponaxis=False, hovertemplate="<b>%{y}</b><br>%{x:.1f}% of dividend income<extra></extra>"))
    fig.update_layout(**_layout(mode, height or max(220, 62 * len(syms) + 60), barmode="group", bargap=0.35,
                                showlegend=True, legend=dict(orientation="h", y=1.12, x=0, font=dict(color=t["text2"])),
                                margin=dict(l=4, r=40, t=8, b=8)))
    fig.update_xaxes(showgrid=False, showticklabels=False)
    fig.update_yaxes(showgrid=False, tickfont=dict(color=t["text2"]))
    return fig


def growth_bars(symbols: list[str], growth: list[float], mode: str = "dark", height: int | None = None) -> go.Figure:
    """Dividend-per-share growth per year (CAGR). Negative bars use the reserved red, with a ▼ in the label."""
    t, c = TOKENS[mode], SERIES[mode]
    syms, vals = symbols[::-1], growth[::-1]
    fig = go.Figure(go.Bar(
        y=syms, x=vals, orientation="h", marker_color=[c["a"] if v >= 0 else CRITICAL for v in vals],
        text=[f"{'▼' if v < 0 else ''}{v:+.1f}%" for v in vals], textposition="outside", cliponaxis=False,
        hovertemplate="<b>%{y}</b><br>%{x:+.1f}% a year<extra></extra>",
    ))
    fig.update_layout(**_layout(mode, height or max(180, 44 * len(syms) + 50), showlegend=False, margin=dict(l=4, r=50, t=8, b=8)))
    fig.update_xaxes(showgrid=False, showticklabels=False, zeroline=True, zerolinecolor=t["grid"])
    fig.update_yaxes(showgrid=False, tickfont=dict(color=t["text2"]))
    return fig


def drip_chart(curves: dict, mode: str = "dark", unit: str = "$", height: int = 340) -> go.Figure:
    """curves: {'Reinvested': Series, 'Dividends as cash': Series, 'Price only': Series}. Values in $ (hypothetical)
    or as a multiple of the start when unit == 'x'."""
    t, c = TOKENS[mode], SERIES[mode]
    colours = {0: c["a"], 1: c["b"], 2: t["muted"]}
    fig = go.Figure()
    for i, (name, s) in enumerate(curves.items()):
        fig.add_trace(go.Scatter(
            x=s.index, y=s.values, mode="lines", name=name,
            line=dict(color=colours.get(i, t["muted"]), width=2 if i < 2 else 1.5, dash="solid" if i < 2 else "dot"),
            hovertemplate=f"<b>{name}</b><br>%{{x|%b %d, %Y}}<br>" + ("$%{y:,.0f}" if unit == "$" else "%{y:.2f}×") + "<extra></extra>",
        ))
        fig.add_annotation(x=s.index[-1], y=float(s.values[-1]), text=f" {name}", showarrow=False, xanchor="left",
                           font=dict(color=t["text2"], size=12))
    fig.update_layout(**_layout(mode, height, showlegend=True, hovermode="x unified", margin=dict(l=4, r=150, t=8, b=8),
                                legend=dict(orientation="h", y=1.12, x=0, font=dict(color=t["text2"]))))
    fig.update_xaxes(showgrid=False, linecolor=t["grid"], tickfont=dict(color=t["muted"]))
    ax = dict(tickprefix="$", tickformat=",.0f") if unit == "$" else dict(ticksuffix="×", tickformat=".1f")
    fig.update_yaxes(gridcolor=t["grid"], zeroline=False, tickfont=dict(color=t["muted"]), **ax)
    return fig


def whatif_chart(df, mode: str = "dark", unit: str = "$", height: int = 320) -> go.Figure:
    """Forward what-if table (Year, DRIP, Cash, Price only) as three lines."""
    t, c = TOKENS[mode], SERIES[mode]
    fig = go.Figure()
    for name, colour, width, dash in (("DRIP", c["a"], 2, "solid"), ("Cash", c["b"], 2, "solid"), ("Price only", t["muted"], 1.5, "dot")):
        label = {"DRIP": "Reinvested", "Cash": "Dividends as cash", "Price only": "Price only"}[name]
        fig.add_trace(go.Scatter(
            x=df["Year"], y=df[name], mode="lines", name=label, line=dict(color=colour, width=width, dash=dash),
            hovertemplate=f"<b>{label}</b><br>Year %{{x}}<br>" + ("$%{y:,.0f}" if unit == "$" else "%{y:.2f}×") + "<extra></extra>",
        ))
        fig.add_annotation(x=float(df["Year"].iloc[-1]), y=float(df[name].iloc[-1]), text=f" {label}", showarrow=False,
                           xanchor="left", font=dict(color=t["text2"], size=12))
    fig.update_layout(**_layout(mode, height, showlegend=True, hovermode="x unified", margin=dict(l=4, r=150, t=8, b=8),
                                legend=dict(orientation="h", y=1.12, x=0, font=dict(color=t["text2"]))))
    fig.update_xaxes(showgrid=False, linecolor=t["grid"], tickfont=dict(color=t["muted"]), title_text="Years from now",
                     title_font=dict(size=12, color=t["muted"]))
    ax = dict(tickprefix="$", tickformat=",.0f") if unit == "$" else dict(ticksuffix="×", tickformat=".1f")
    fig.update_yaxes(gridcolor=t["grid"], zeroline=False, tickfont=dict(color=t["muted"]), **ax)
    return fig
