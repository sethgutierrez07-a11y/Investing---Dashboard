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

import plotly.graph_objects as go
import streamlit as st

import brief_lib as bl
import holdings_lib as hl

st.set_page_config(page_title="Holdings", layout="wide")


def secret(name: str):
    try:
        return st.secrets[name]
    except Exception:
        return None


# ---------- Access gate (fails closed) ----------
st.title("💼 Holdings")

expected = secret("APP_PASSWORD")
if not expected:
    st.error(
        "This page shows private account data, so it stays locked until you set a password. "
        'Add `APP_PASSWORD = "choose-something-long"` under ⋮ → Settings → Secrets, then reload.'
    )
    st.stop()

if not st.session_state.get("holdings_unlocked"):
    entered = st.text_input("Password", type="password")
    if st.button("Unlock"):
        if hl.password_ok(entered, expected):
            st.session_state["holdings_unlocked"] = True
            st.rerun()
        else:
            time.sleep(2)  # slows down password guessing
            st.error("Wrong password.")
    st.stop()

st.caption(
    "Read-only view of your Fidelity account through SnapTrade. Informational only, not "
    "financial advice. This app cannot place trades."
)

client_id = secret("SNAPTRADE_CLIENT_ID")
consumer_key = secret("SNAPTRADE_CONSUMER_KEY")
if not (client_id and consumer_key):
    st.info(
        "Not connected yet. Add `SNAPTRADE_CLIENT_ID` and `SNAPTRADE_CONSUMER_KEY` (your "
        "**Personal** keys from the SnapTrade dashboard) to Secrets. Setup steps are in the chat."
    )
    st.stop()

with st.sidebar:
    st.header("Holdings settings")
    hide = st.toggle("Hide dollar amounts", value=False, help="Show only weights and percentages (good for screenshots).")
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
    st.error(
        f"Couldn't read from SnapTrade ({type(e).__name__}). Check that both keys are the "
        "Personal ones, that 2-factor is on, and that a brokerage is connected in the SnapTrade dashboard."
    )
    with st.expander("Technical detail"):
        st.code(str(e)[:500])
    st.stop()

if not raw:
    st.info("SnapTrade is reachable, but no brokerage accounts are connected yet. Connect Fidelity in the SnapTrade dashboard.")
    st.stop()

def show_shape():
    """Field names and types only, never amounts. Safe to copy into a chat for debugging."""
    with st.expander("Data shape (field names only, no values)"):
        st.json([r.get("shape", {}) for r in raw])


try:
    pf = hl.build_portfolio(raw)
except Exception as e:
    st.error(f"Connected, but I couldn't read the data shape SnapTrade returned ({type(e).__name__}).")
    show_shape()
    st.stop()

df = pf["positions"]
for w in pf["warnings"]:
    st.warning(w)

if df.empty:
    st.info("Connected, but no positions were found. If you only hold cash, that's expected.")
    show_shape()
    st.stop()

# ---------- Headline numbers ----------
merged = hl.by_symbol(df)
conc = hl.concentration(merged["Weight %"])  # per ticker, across accounts

quotes = {}
fh_key = secret("FINNHUB_API_KEY")
if fh_key:
    @st.cache_data(ttl=60)
    def quote(sym, key):
        return bl.fetch_quote(sym, key)

    for sym in merged["Symbol"].head(15):  # stay inside the free API limit
        try:
            quotes[sym] = quote(sym, fh_key)
        except Exception:
            quotes[sym] = None
move = hl.day_change(df, quotes) if quotes else {"pct": None, "coverage": 0.0}

c1, c2, c3, c4 = st.columns(4)
if hide:
    c1.metric("Positions", f"{len(merged)}")
    c2.metric("Cash", f"{pf['cash'] / pf['total'] * 100:.1f}% of total" if pf["total"] > 0 else "—")
else:
    c1.metric("Total value", f"${pf['total']:,.0f}")
    c2.metric("Cash", f"${pf['cash']:,.0f}")
c3.metric(
    "Today (est.)",
    f"{move['pct']:+.2f}%" if move["pct"] is not None else "—",
    help=f"Weighted from live quotes; covers {move['coverage']*100:.0f}% of invested value.",
)
c4.metric("Largest position", f"{conc['largest']:.1f}%" if conc["largest"] else "—", help="Share of the invested part of your portfolio.")

# ---------- Allocation ----------
st.subheader("Allocation")
left, right = st.columns([3, 2])
top = merged.head(12)
fig = go.Figure(go.Bar(x=top["Weight %"][::-1], y=top["Symbol"][::-1], orientation="h",
                       text=[f"{w:.1f}%" for w in top["Weight %"][::-1]], textposition="outside"))
fig.update_layout(height=max(260, 28 * len(top)), margin=dict(l=10, r=40, t=10, b=10), xaxis_title="% of total portfolio")
left.plotly_chart(fig, width="stretch")

with right:
    st.markdown("**Concentration**")
    if conc["top5"] is not None:
        st.write(f"Top 5 holdings = **{conc['top5']:.0f}%** of what you have invested.")
        st.write(f"Effective number of holdings: **{conc['effective_n']:.1f}**")
        st.caption(
            "Effective holdings shows how diversified you really are: 20 stocks where one is 60% "
            "of the portfolio behaves like only a few. A broad index fund counts as one holding "
            "here even though it contains hundreds of stocks."
        )

# ---------- Positions table ----------
st.subheader("Positions")
view = merged if st.toggle("Combine accounts", value=True) else df
show = hl.hide_dollars(view) if hide else view
fmt = {
    "Weight %": st.column_config.NumberColumn(format="%.1f%%"),
    "Gain %": st.column_config.NumberColumn(format="%+.1f%%"),
    "Units": st.column_config.NumberColumn(format="%.4f"),
}
if not hide:
    fmt["Price"] = st.column_config.NumberColumn(format="$%.2f")
    for c in ("Market value", "Cost basis"):
        fmt[c] = st.column_config.NumberColumn(format="$%.0f")
    fmt["Gain"] = st.column_config.NumberColumn(format="%+.0f")
st.dataframe(show, hide_index=True, width="stretch", column_config=fmt)
st.caption("Gain uses SnapTrade's average purchase price. Cost basis can be incomplete for transferred or reinvested shares.")

show_shape()
