"""
Investing Dashboard (home page): live quotes, your holdings, analyst consensus, stock of the day.
(app.py is the small entry point that lists the pages; this file is the home page itself.)

Runs on Streamlit Community Cloud. Reads your Finnhub API key from
Streamlit "Secrets" (never stored on your own computer).

Data source: Finnhub (https://finnhub.io). Free tier has rate limits —
if you add many tickers, prices may take a moment to load.
"""

import requests
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import ui

import datetime as dt

import holdings_lib as hl
import idea_lib as il
import portfolio_state as ps

st.set_page_config(page_title="Investing Dashboard", layout="wide")
ui.apply()

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


@st.cache_data(ttl=12 * 3600)  # fundamentals change quarterly
def fetch_metrics(symbol: str, api_key: str) -> dict:
    r = requests.get(
        f"{FINNHUB_BASE}/stock/metric",
        params={"symbol": symbol, "metric": "all", "token": api_key},
        timeout=10,
    )
    r.raise_for_status()
    return (r.json() or {}).get("metric") or {}


@st.cache_data(ttl=86400)
def fetch_profile(symbol: str, api_key: str) -> dict:
    r = requests.get(
        f"{FINNHUB_BASE}/stock/profile2",
        params={"symbol": symbol, "token": api_key},
        timeout=10,
    )
    r.raise_for_status()
    return r.json()


def render_consensus_donut(trend: dict):
    """Share of analysts per rating. Hover shows the head-count; the middle shows the consensus score."""
    slices = il.consensus_slices(trend)
    total = sum(n for _, n, _ in slices)
    score = il.bl.analyst_score(trend)
    fig = go.Figure(
        go.Pie(
            labels=[s[0] for s in slices],
            values=[s[1] for s in slices],
            marker=dict(colors=[s[2] for s in slices], line=dict(color="rgba(0,0,0,0)", width=3)),
            hole=0.6,
            sort=False,  # keep Strong Buy -> Strong Sell order
            direction="clockwise",
            textinfo="value",
            textposition="outside",
            hovertemplate="%{label}: %{value} analysts (%{percent})<extra></extra>",
        )
    )
    fig.update_layout(
        height=260,
        margin=dict(l=10, r=10, t=10, b=10),
        legend=dict(orientation="v", y=0.5),
        annotations=[
            dict(
                text=(f"<b>{il.consensus_verdict(score)}</b><br>{score:+.2f} · {total} analysts" if score is not None else "No ratings"),
                x=0.5, y=0.5, showarrow=False, font=dict(size=14),
            )
        ],
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


def render_analyst_section(df, portfolio, api_key):
    """Analysts rate companies, not funds: stocks get analyst tabs, ETFs/funds get their own table."""
    st.subheader("Analyst consensus & price targets")
    class_by = dict(zip(portfolio["merged"]["Symbol"], portfolio["merged"]["Class"])) if portfolio else {}
    names = dict(zip(df["Symbol"], df["Name"])) if "Name" in df else {}
    stocks, funds = il.split_stocks_funds(list(df["Symbol"]), class_by, names)

    st.markdown("**Stocks**")
    if not stocks:
        st.info("No individual stocks in this list. Add one in the sidebar to see analyst ratings.")
    else:
        tabs = st.tabs(stocks)
        for tab, symbol in zip(tabs, stocks):
            with tab:
                render_stock_tab(symbol, api_key)

    if funds:
        st.markdown("**ETFs & funds**")
        st.caption(
            "Analysts rate individual companies, not funds, so there are no analyst ratings or price targets for these. "
            "What matters for a fund is what it holds, what it costs and how big it is. Here is how yours are doing."
        )
        cols = ["Symbol", "Name", "Price", "Change %"] + [c for c in ("Weight %", "Impact (pp)", "Since purchase %") if c in df.columns]
        fdf = df[df["Symbol"].isin(funds)][cols].reset_index(drop=True)
        fdf["Type"] = [class_by.get(s, "ETF/fund") for s in fdf["Symbol"]]
        st.dataframe(
            fdf.style.format(
                {"Price": "${:.2f}", "Change %": "{:+.2f}%", "Weight %": "{:.1f}%", "Impact (pp)": "{:+.2f}", "Since purchase %": "{:+.1f}%"},
                na_rep="—",
            ),
            width="stretch", hide_index=True,
        )


def render_stock_tab(symbol, api_key):
    col1, col2 = st.columns([2, 1])
    try:
        trend_data = fetch_recommendation_trend(symbol, api_key)
    except Exception as e:
        col1.warning(f"Couldn't load analyst data for {symbol}: {e}")
        trend_data = []

    if trend_data:
        latest = trend_data[0]
        col1.plotly_chart(render_consensus_donut(latest), width="stretch")
        col1.caption(f"As of period ending {latest.get('period', 'unknown')}.")
    else:
        col1.info("No analyst recommendation data available for this ticker.")

    if st.session_state.get("price_targets_blocked"):
        col2.info("Price targets aren't included on the free Finnhub plan.")
        return
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
            st.session_state["price_targets_blocked"] = True  # skip the rest: saves API calls
            col2.info("Price targets aren't included on the free Finnhub plan.")
        else:
            col2.warning(f"Couldn't load price target: {e}")
    except Exception as e:
        col2.warning(f"Couldn't load price target: {e}")


def render_stock_of_the_day(api_key, exclude):
    """Screen a daily sample of large US companies and show the best one, with the numbers behind it."""
    st.subheader("💡 Stock of the day")
    st.caption(
        "An idea to research, not a recommendation. Each day a sample of large US companies you don't already follow is "
        "screened on valuation, growth, profitability, debt, price trend and analyst views; the best-scoring one is shown "
        "with the data behind every pro and con. It is a screen on past numbers and cannot see what happens next."
    )
    offset = st.session_state.get("idea_offset", 0)
    today = dt.date.today()
    candidates = il.pick_candidates(il.UNIVERSE, exclude, today.toordinal(), n=6, offset=offset)

    evals, failed = [], []
    with st.spinner("Screening today's candidates…"):
        for sym in candidates:
            try:
                evals.append(il.evaluate(sym, fetch_quote(sym, api_key), fetch_metrics(sym, api_key), fetch_recommendation_trend(sym, api_key)))
            except Exception:
                failed.append(sym)  # rate limit or a bad ticker: skip it, don't hide the rest
    best = il.choose(evals)

    if best is None:
        st.info(
            "Couldn't screen enough candidates right now"
            + (f" ({len(failed)} failed to load, probably the free API's per-minute limit)" if failed else "")
            + ". Try again in a minute."
        )
    else:
        sym = best["symbol"]
        try:
            name = fetch_profile(sym, api_key).get("name") or ""
        except Exception:
            name = ""
        with st.container(border=True):
            st.markdown(f"### {sym}" + (f" · {name}" if name else ""))
            m1, m2, m3, m4 = st.columns(4)
            facts = dict(best["facts"])
            m1.metric("Price", f"${best['price']:,.2f}" if best["price"] else "—", delta=f"{best['day_pct']:+.2f}% today" if best["day_pct"] is not None else None)
            m2.metric("P/E (TTM)", facts.get("P/E (TTM)", "—"))
            m3.metric("Below 52-wk high", facts.get("Below 52-week high", "—"))
            m4.metric("Analyst score", f"{best['analyst_score']:+.2f}" if best["analyst_score"] is not None else "—", help="−2 (all Strong Sell) to +2 (all Strong Buy).")
            pro_col, con_col = st.columns(2)
            with pro_col:
                st.markdown("**What looks good**")
                for label, text in best["pros"] or [("", "Nothing stood out as a clear positive on these measures.")]:
                    st.markdown(f"- **{label}:** {text}" if label else f"- {text}")
            with con_col:
                st.markdown("**What to watch**")
                for label, text in best["cons"] or [("", "No red flags on these measures.")]:
                    st.markdown(f"- **{label}:** {text}" if label else f"- {text}")
                st.markdown("- **Always:** one company can fall far more than a diversified fund, and these numbers look backward.")
            st.caption(f"Screened {len(evals)} candidates today; {sym} had the best score per measure with data ({best['covered']} measures had data).")

        with st.expander("All the numbers for " + sym):
            st.dataframe(pd.DataFrame(best["facts"], columns=["Measure", "Value"]), hide_index=True, width="stretch")
        with st.expander("Other candidates screened today"):
            st.dataframe(pd.DataFrame(il.comparison_rows(evals)), hide_index=True, width="stretch")
            if failed:
                st.caption(f"Didn't load (likely the API's per-minute limit): {', '.join(failed)}")

    with st.expander("How this is scored"):
        st.markdown("Each measure scores a **pro** or **con** only when it crosses these lines. A pick needs data on at least "
                    f"{il.MIN_FACTORS} measures, and the winner has the best net score per measure with data.")
        st.dataframe(pd.DataFrame(il.RULES, columns=["Measure", "What it looks at", "Rule"]), hide_index=True, width="stretch")
        st.caption("Thresholds are rules of thumb, not predictions. Data: Finnhub free tier.")
    if st.button("Show a different idea"):
        st.session_state["idea_offset"] = offset + 1
        st.rerun()


def main():
    ui.eyebrow("Personal research terminal")
    st.title("📊 Investing Dashboard")
    st.caption(
        "Live quotes and analyst consensus, built around your holdings once unlocked. Not financial advice — "
        "analyst ratings skew bullish and often lag price; use alongside "
        "your own research."
    )

    status_box = st.container()  # filled once the quotes below have loaded
    ui.nav_tiles()
    st.write("")

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

    with status_box:
        ui.status_strip(ui.data_status(quotes, ps.configured(), ps.is_unlocked(), portfolio is not None))

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
    render_analyst_section(df, portfolio, api_key)

    st.divider()
    render_stock_of_the_day(api_key, set(tickers) | held)

    st.divider()
    st.caption(
        "Data from Finnhub. Analyst ratings are informational, not a "
        "recommendation to buy or sell. This app does not place trades."
    )


if __name__ == "__main__":
    main()
