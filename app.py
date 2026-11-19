"""
Personal Investing Dashboard — Stage 1: Live Market Tracker + Analyst Consensus

Runs on Streamlit Community Cloud. Reads your Finnhub API key from
Streamlit "Secrets" (never stored on your own computer).

Data source: Finnhub (https://finnhub.io). Free tier has rate limits —
if you add many tickers, prices may take a moment to load.
"""

import requests
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import holdings_lib as hl
import portfolio_state as ps

st.set_page_config(page_title="Investing Dashboard", layout="wide")

# ---------- Config ----------
FINNHUB_BASE = "https://finnhub.io/api/v1"

DEFAULT_WATCHLIST = ["AAPL", "MSFT", "VOO"]

RATING_LABELS = {
    "strongBuy": "Strong Buy",
    "buy": "Buy",
    "hold": "Hold",
    "sell": "Sell",
    "strongSell": "Strong Sell",
}


def get_api_key() -> str | None:
    """Reads the Finnhub key from Streamlit secrets."""
    try:
        return st.secrets["FINNHUB_API_KEY"]
    except Exception:
        return None


@st.cache_data(ttl=60)  # refresh at most once a minute per ticker
def fetch_quote(symbol: str, api_key: str) -> dict:
    r = requests.get(
        f"{FINNHUB_BASE}/quote",
        params={"symbol": symbol, "token": api_key},
        timeout=10,
    )
    r.raise_for_status()
    return r.json()


@st.cache_data(ttl=3600)  # analyst consensus doesn't change minute to minute
def fetch_recommendation_trend(symbol: str, api_key: str) -> list[dict]:
    r = requests.get(
        f"{FINNHUB_BASE}/stock/recommendation",
        params={"symbol": symbol, "token": api_key},
        timeout=10,
    )
    r.raise_for_status()
    return r.json()


@st.cache_data(ttl=3600)
def fetch_price_target(symbol: str, api_key: str) -> dict:
    r = requests.get(
        f"{FINNHUB_BASE}/stock/price-target",
        params={"symbol": symbol, "token": api_key},
        timeout=10,
    )
    r.raise_for_status()
    return r.json()


@st.cache_data(ttl=86400)
def fetch_profile(symbol: str, api_key: str) -> dict:
    r = requests.get(
        f"{FINNHUB_BASE}/stock/profile2",
        params={"symbol": symbol, "token": api_key},
        timeout=10,
    )
    r.raise_for_status()
    return r.json()


def render_consensus_bar(trend: dict):
    labels = ["Strong Buy", "Buy", "Hold", "Sell", "Strong Sell"]
    values = [
        trend.get("strongBuy", 0),
        trend.get("buy", 0),
        trend.get("hold", 0),
        trend.get("sell", 0),
        trend.get("strongSell", 0),
    ]
    colors = ["#1a7f37", "#4caf50", "#ffb020", "#e05252", "#9b1c1c"]
    fig = go.Figure(
        go.Bar(
            x=values,
            y=labels,
            orientation="h",
            marker_color=colors,
            text=values,
            textposition="outside",
        )
    )
    fig.update_layout(
        height=220,
        margin=dict(l=10, r=10, t=10, b=10),
        xaxis_title="Number of analysts",
    )
    return fig


def render_portfolio_headline(portfolio, quotes):
    """Percent-only summary of how YOUR portfolio is moving today (no dollar amounts on this page)."""
    merged = portfolio["merged"]
    move = hl.day_change(portfolio["holdings_df"], {k: v for k, v in quotes.items() if v})
    contrib = hl.contributions(merged, quotes)
    c1, c2, c3 = st.columns(3)
    with c1.container(border=True):
        st.metric(
            "Your portfolio today (est.)",
            hl.pct(move["pct"], digits=2) if move["pct"] is not None else "—",
            help=f"Weighted from live quotes; covers {move['coverage']*100:.0f}% of your invested value.",
        )
    if not contrib.empty:
        best, worst = contrib.loc[contrib["Contribution pp"].idxmax()], contrib.loc[contrib["Contribution pp"].idxmin()]
        with c2.container(border=True):
            st.metric("Biggest help", str(best["Symbol"]), delta=f"{best['Contribution pp']:+.2f} pp")
        with c3.container(border=True):
            st.metric("Biggest drag", str(worst["Symbol"]), delta=f"{worst['Contribution pp']:+.2f} pp")
    st.write("")


def main():
    st.title("📊 Investing Dashboard")
    st.caption(
        "Live quotes and analyst consensus, built around your holdings once unlocked. Not financial advice — "
        "analyst ratings skew bullish and often lag price; use alongside "
        "your own research."
    )

    api_key = get_api_key()
    if not api_key:
        st.error(
            "No Finnhub API key found. Add `FINNHUB_API_KEY` to this app's "
            "Secrets in Streamlit Community Cloud (⋮ menu → Settings → Secrets)."
        )
        st.stop()

    ps.unlock_sidebar()
    portfolio = ps.get_portfolio()
    tickers, held = ps.watchlist_sidebar(portfolio)
    with st.sidebar:
        st.caption("Prices refresh automatically every 60 seconds you have the page open; reopen the page anytime for the latest.")
    if portfolio is None and ps.configured() and not ps.is_unlocked():
        st.info("Showing a sample watchlist. Unlock in the sidebar to see this page built around your real holdings.")

    if not tickers:
        st.info("Add at least one ticker in the sidebar to get started.")
        return

    weights = ps.weight_lookup(portfolio)
    gains = ps.gain_lookup(portfolio)
    rows, quotes = [], {}
    for symbol in tickers:
        try:
            quote = fetch_quote(symbol, api_key)
            profile = fetch_profile(symbol, api_key)
            quotes[symbol] = quote
            row = {
                "Symbol": symbol,
                "Name": profile.get("name", ""),
                "Price": quote.get("c"),
                "Change": quote.get("d"),
                "Change %": quote.get("dp"),
                "Prev Close": quote.get("pc"),
            }
            if portfolio:
                w = weights.get(symbol)
                row["Weight %"] = w
                row["Since purchase %"] = gains.get(symbol)
            rows.append(row)
        except Exception as e:
            quotes[symbol] = None
            rows.append({"Symbol": symbol, "Name": f"Error: {e}"})

    df = pd.DataFrame(rows)

    if portfolio:
        render_portfolio_headline(portfolio, quotes)
        contrib = hl.contributions(portfolio["merged"], quotes)
        df["Impact (pp)"] = df["Symbol"].map(dict(zip(contrib["Symbol"], contrib["Contribution pp"])))
        df = df.assign(_held=df["Symbol"].isin(held), _w=df.get("Weight %")).sort_values(
            ["_held", "_w"], ascending=[False, False], na_position="last"
        ).drop(columns=["_held", "_w"]).reset_index(drop=True)
        st.subheader("Your holdings" + (" + extras" if (set(tickers) - held) else ""))
        fmt = {"Price": "${:.2f}", "Change": "{:+.2f}", "Change %": "{:+.2f}%", "Prev Close": "${:.2f}",
               "Weight %": "{:.1f}%", "Impact (pp)": "{:+.2f}", "Since purchase %": "{:+.1f}%"}
        st.caption("Weight is share of your invested money. Impact is how many percentage points each holding added to or took from your portfolio today (weight × move).")
    else:
        st.subheader("Watchlist")
        fmt = {"Price": "${:.2f}", "Change": "{:+.2f}", "Change %": "{:+.2f}%", "Prev Close": "${:.2f}"}
    st.dataframe(df.style.format(fmt, na_rep="—"), width="stretch", hide_index=True)

    st.divider()
    st.subheader("Analyst consensus & price targets")

    ordered = [x for x in df["Symbol"]] or tickers
    tabs = st.tabs(ordered)
    for tab, symbol in zip(tabs, ordered):
        with tab:
            col1, col2 = st.columns([2, 1])
            try:
                trend_data = fetch_recommendation_trend(symbol, api_key)
            except Exception as e:
                col1.warning(f"Couldn't load analyst data for {symbol}: {e}")
                trend_data = []

            if trend_data:
                latest = trend_data[0]
                col1.plotly_chart(render_consensus_bar(latest), width="stretch")
                col1.caption(f"As of period ending {latest.get('period', 'unknown')}.")
            else:
                col1.info("No analyst recommendation data available for this ticker.")

            try:
                pt = fetch_price_target(symbol, api_key)
                if pt and pt.get("targetMean"):
                    col2.metric("Mean price target", f"${pt['targetMean']:.2f}")
                    col2.metric("High / Low target", f"${pt['targetHigh']:.2f} / ${pt['targetLow']:.2f}")
                    col2.caption(f"Based on {pt.get('lastUpdated', 'recent')} data.")
                else:
                    col2.info("No price target data available.")
            except requests.exceptions.HTTPError as e:
                if e.response is not None and e.response.status_code == 403:
                    col2.info("Price targets aren't included on the free Finnhub plan.")
                else:
                    col2.warning(f"Couldn't load price target: {e}")
            except Exception as e:
                col2.warning(f"Couldn't load price target: {e}")

    st.divider()
    st.caption(
        "Data from Finnhub. Analyst ratings are informational, not a "
        "recommendation to buy or sell. This app does not place trades."
    )


if __name__ == "__main__":
    main()
