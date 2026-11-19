"""
Holdings — your real Fidelity portfolio, read-only, via SnapTrade Personal.

Secrets needed (Streamlit → Settings → Secrets):
  APP_PASSWORD            a password you choose; this page shows nothing without it
  SNAPTRADE_CLIENT_ID     your SnapTrade *Personal* client ID
  SNAPTRADE_CONSUMER_KEY  your SnapTrade *Personal* consumer key
  FINNHUB_API_KEY         (already set) used for today's move

You connect Fidelity inside SnapTrade's own dashboard. This app never sees
your Fidelity login and never calls any trading endpoint.
"""

import time

import streamlit as st

import brief_lib as bl
import holdings_charts as hc
import holdings_lib as hl

st.set_page_config(page_title="Holdings", layout="wide")

GOOD, CRITICAL = "#0ca30c", "#d03b3b"
CHART_CFG = {"displayModeBar": False}


def secret(name: str):
    try:
        return st.secrets[name]
    except Exception:
        return None


def theme_mode() -> str:
    try:
        return "light" if st.context.theme.type == "light" else "dark"
    except Exception:
        return "dark"


def signed_span(text: str, value) -> str:
    """Coloured, arrow-prefixed delta. Only ever receives text we formatted ourselves."""
    if value is None:
        return f'<span style="opacity:.6">{text}</span>'
    up = value >= 0
    return f'<span style="color:{GOOD if up else CRITICAL};font-weight:600">{"▲" if up else "▼"} {text}</span>'


# ---------- Access gate (fails closed) ----------
expected = secret("APP_PASSWORD")
if not expected:
    st.title("💼 Holdings")
    st.error(
        "This page shows private account data, so it stays locked until you set a password. "
        'Add `APP_PASSWORD = "choose-something-long"` under ⋮ → Settings → Secrets, then reload.'
    )
    st.stop()

if not st.session_state.get("holdings_unlocked"):
    st.title("💼 Holdings")
    entered = st.text_input("Password", type="password")
    if st.button("Unlock"):
        if hl.password_ok(entered, expected):
            st.session_state["holdings_unlocked"] = True
            st.rerun()
        else:
            time.sleep(2)  # slows down password guessing
            st.error("Wrong password.")
    st.stop()

client_id = secret("SNAPTRADE_CLIENT_ID")
consumer_key = secret("SNAPTRADE_CONSUMER_KEY")
if not (client_id and consumer_key):
    st.title("💼 Holdings")
    st.info(
        "Not connected yet. Add `SNAPTRADE_CLIENT_ID` and `SNAPTRADE_CONSUMER_KEY` (your "
        "**Personal** keys from the SnapTrade dashboard) to Secrets."
    )
    st.stop()

with st.sidebar:
    st.header("Holdings settings")
    hide = st.toggle("Hide dollar amounts", value=False, help="Show only weights and percentages (good for screenshots).")
    combine = st.toggle("Combine accounts", value=True)
    if st.button("Refresh now"):
        st.cache_data.clear()
        st.rerun()
    if st.button("Lock"):
        st.session_state["holdings_unlocked"] = False
        st.rerun()


@st.cache_data(ttl=300, show_spinner="Reading your accounts…")
def load_holdings():
    client = hl.make_client(client_id, consumer_key)
    return hl.fetch_all(client)


try:
    raw = load_holdings()
except Exception as e:
    st.title("💼 Holdings")
    st.error(
        f"Couldn't read from SnapTrade ({type(e).__name__}). Check that both keys are the "
        "Personal ones, that 2-factor is on, and that a brokerage is connected in the SnapTrade dashboard."
    )
    with st.expander("Technical detail"):
        st.code(str(e)[:500])
    st.stop()

if not raw:
    st.title("💼 Holdings")
    st.info("SnapTrade is reachable, but no brokerage accounts are connected yet. Connect Fidelity in the SnapTrade dashboard.")
    st.stop()


def show_shape():
    """Field names and types only, never amounts. Safe to copy into a chat for debugging."""
    with st.expander("Data shape (field names only, no values)"):
        st.json([r.get("shape", {}) for r in raw])


try:
    pf = hl.build_portfolio(raw)
except Exception as e:
    st.title("💼 Holdings")
    st.error(f"Connected, but I couldn't read the data shape SnapTrade returned ({type(e).__name__}).")
    show_shape()
    st.stop()

df = pf["positions"]
if df.empty:
    st.title("💼 Holdings")
    for w in pf["warnings"]:
        st.warning(w)
    st.info("Connected, but no positions were found. If you only hold cash, that's expected.")
    show_shape()
    st.stop()

# ---------- Numbers ----------
mode = theme_mode()
# Cash-equivalent funds (e.g. a money-market core position) count as cash, not as holdings,
# so they don't distort concentration. They still appear in the table below.
holdings_df = df[df["Class"] != "Cash equiv."]
if holdings_df.empty:
    holdings_df = df
merged = hl.by_symbol(holdings_df)
table_merged = hl.by_symbol(df)
summary = hl.summarize(df, pf["cash"])
conc = hl.concentration(merged["Weight %"])
mix = hl.asset_mix(df, pf["cash"])

quotes = {}
fh_key = secret("FINNHUB_API_KEY")
if fh_key:

    @st.cache_data(ttl=60)
    def quote(sym, key):
        return bl.fetch_quote(sym, key)

    for sym in merged["Symbol"].head(15):  # stay inside the free API limit
        if sym == "?":
            continue
        try:
            quotes[sym] = quote(sym, fh_key)
        except Exception:
            quotes[sym] = None
move = hl.day_change(holdings_df, quotes) if quotes else {"pct": None, "coverage": 0.0}

# ---------- Header + hero ----------
st.title("💼 Holdings")
st.caption("Read-only view of your Fidelity account through SnapTrade. Informational only, not financial advice.")

hero_value = "••••••" if hide else hl.money(summary["total"])
parts = []
if move["pct"] is not None:
    parts.append(signed_span(f"{hl.pct(move['pct'], signed=False, digits=2)} today (est.)", move["pct"]))
if summary["gain_pct"] is not None:
    if hide:
        since = hl.pct(summary["gain_pct"], signed=False)
    else:
        since = f"{hl.money(summary['gain'])} ({hl.pct(summary['gain_pct'], signed=False)})"
    parts.append(signed_span(f"{since} since purchase", summary["gain"]))
st.markdown(
    f"""
<div style="margin:6px 0 2px 0;opacity:.65;font-size:13px;letter-spacing:.08em;text-transform:uppercase">Total portfolio value</div>
<div style="font-size:60px;line-height:1.05;font-weight:650;letter-spacing:-0.02em">{hero_value}</div>
<div style="font-size:15px;margin-top:8px">{'&nbsp;&nbsp;·&nbsp;&nbsp;'.join(parts)}</div>
""",
    unsafe_allow_html=True,
)
st.write("")
for w in pf["warnings"]:
    st.warning(w)

# ---------- KPI tiles ----------
k1, k2, k3, k4 = st.columns(4)
with k1.container(border=True):
    if hide:
        st.metric("Since purchase", hl.pct(summary["gain_pct"]) if summary["gain_pct"] is not None else "—")
    else:
        st.metric(
            "Since purchase",
            hl.money(summary["gain"], signed=True) if summary["gain"] is not None else "—",
            delta=hl.pct(summary["gain_pct"]) if summary["gain_pct"] is not None else None,
            help=f"Unrealized gain vs. average purchase price. Covers {summary['gain_coverage']*100:.0f}% of invested value.",
        )
with k2.container(border=True):
    st.metric(
        "Today (est.)",
        hl.pct(move["pct"], digits=2) if move["pct"] is not None else "—",
        help=f"Weighted from live quotes; covers {move['coverage']*100:.0f}% of invested value.",
    )
with k3.container(border=True):
    st.metric(
        "Cash",
        hl.pct(summary["cash_pct"], signed=False) if hide else hl.money(summary["cash"]),
        delta=None if hide or summary["cash_pct"] is None else f"{summary['cash_pct']:.1f}% of total",
        delta_color="off",
    )
with k4.container(border=True):
    st.metric(
        "Holdings",
        f"{summary['n_holdings']}",
        delta=f"acts like ~{conc['effective_n']:.1f} equal-sized" if conc.get("effective_n") else None,
        delta_color="off",
        help="Effective number of holdings: how many equal-sized positions your portfolio behaves like.",
    )

st.write("")

# ---------- Allocation + mix ----------
left, right = st.columns([3, 2], gap="large")
with left.container(border=True):
    st.markdown("**Where your money is**")
    st.caption("Share of total portfolio, largest first.")
    st.plotly_chart(hc.rank_bars(hl.top_for_bars(merged, 10), mode), width="stretch", config=CHART_CFG)

with right.container(border=True):
    st.markdown("**What it's made of**")
    st.caption("Asset class, as a share of the whole portfolio.")
    st.plotly_chart(hc.mix_bar(mix, mode), width="stretch", config=CHART_CFG)
    st.markdown("**Concentration**")
    if conc["largest"] is not None:
        st.progress(min(conc["largest"] / 100, 1.0), text=f"Largest holding: {conc['largest']:.0f}% of invested")
        st.progress(min(conc["top5"] / 100, 1.0), text=f"Top 5 holdings: {conc['top5']:.0f}% of invested")
        st.caption(
            "Measured per ticker. An ETF counts as one holding here even though it contains "
            "many companies, so a portfolio of broad ETFs looks more concentrated than it really is."
        )

# ---------- Gains ----------
gains = hl.gain_rows(merged)
st.write("")
with st.container(border=True):
    st.markdown("**What's working and what isn't**")
    st.caption("Gain or loss since purchase, per holding (uses SnapTrade's average purchase price).")
    if len(gains) >= 1:
        st.plotly_chart(hc.gain_bars(gains, mode), width="stretch", config=CHART_CFG)
    else:
        st.info("No cost-basis data came back, so gains can't be shown.")

# ---------- Insights ----------
notes = hl.insights(summary, conc, mix, merged)
if notes:
    st.write("")
    with st.container(border=True):
        st.markdown("**Observations**")
        for n in notes:
            st.markdown(f"- {n}")
        st.caption("Descriptive only. These are facts about your portfolio, not advice.")

# ---------- Table view ----------
st.write("")
st.subheader("All positions")
view = table_merged if combine else df
cols = (["Symbol", "Description", "Class"] if combine else ["Account", "Symbol", "Description", "Class"]) + [
    "Weight %", "Units", "Price", "Market value", "Cost basis", "Gain", "Gain %"
]
view = view[[c for c in cols if c in view.columns]]
show = hl.hide_dollars(view) if hide else view
fmt = {
    "Weight %": st.column_config.ProgressColumn("Weight", format="%.1f%%", min_value=0, max_value=100),
    "Gain %": st.column_config.NumberColumn("Gain %", format="%+.1f%%"),
    "Units": st.column_config.NumberColumn(format="%.4f"),
    "Price": st.column_config.NumberColumn(format="$%.2f"),
    "Market value": st.column_config.NumberColumn("Value", format="$%.0f"),
    "Cost basis": st.column_config.NumberColumn("Cost", format="$%.0f"),
    "Gain": st.column_config.NumberColumn("Gain", format="%+.0f"),
}
st.dataframe(
    show, hide_index=True, width="stretch",
    column_config={k: v for k, v in fmt.items() if k in show.columns},
)
st.caption("Cost basis can be incomplete for transferred or reinvested shares. The table has the exact figures behind every chart above.")
show_shape()
