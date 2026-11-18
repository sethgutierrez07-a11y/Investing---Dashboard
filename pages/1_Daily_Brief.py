"""
Daily Brief — open it, see what changed.

Read-only. Needs FINNHUB_API_KEY in Streamlit Secrets (same as the main page).
Optional secrets:
  SEC_USER_AGENT     e.g. "Your Name your.email@example.com"  (turns on SEC filings)
  ANTHROPIC_API_KEY  turns on the "Write my brief" button (costs a few cents per click)
  ANTHROPIC_MODEL    override the default model
"""

import datetime as dt

import pandas as pd
import streamlit as st

import brief_lib as bl

st.set_page_config(page_title="Daily Brief", layout="wide")

DEFAULT_WATCHLIST = ["AAPL", "MSFT", "VOO"]
MAX_TICKERS = 15  # Finnhub free tier allows ~60 calls/minute


def secret(name: str):
    try:
        return st.secrets[name]
    except Exception:
        return None


# ---------- Cached fetchers ----------
@st.cache_data(ttl=60)
def c_quote(symbol, key):
    return bl.fetch_quote(symbol, key)


@st.cache_data(ttl=3600)
def c_recs(symbol, key):
    return bl.fetch_recommendations(symbol, key)


@st.cache_data(ttl=900)
def c_news(symbol, start, end, key):
    return bl.fetch_company_news(symbol, start, end, key)


@st.cache_data(ttl=6 * 3600)
def c_earnings(start, end, key):
    return bl.fetch_earnings_calendar(start, end, key)


@st.cache_data(ttl=24 * 3600)
def c_cik_map(user_agent):
    return bl.fetch_cik_map(user_agent)


@st.cache_data(ttl=3600)
def c_submissions(cik, user_agent):
    return bl.fetch_submissions(cik, user_agent)


@st.cache_data(ttl=3600, show_spinner=False)
def c_summary(digest, key, model):
    return bl.summarize_with_claude(digest, key, model)


# ---------- Page ----------
st.title("🗞️ Daily Brief")
st.caption(
    "What changed since yesterday on your watchlist. Informational only, not "
    "financial advice. This page is read-only and never places trades."
)

api_key = secret("FINNHUB_API_KEY")
if not api_key:
    st.error("No `FINNHUB_API_KEY` found. Add it under ⋮ → Settings → Secrets.")
    st.stop()

with st.sidebar:
    st.header("Brief settings")
    default_list = st.session_state.get("watchlist", DEFAULT_WATCHLIST)
    raw = st.text_area("Tickers (comma-separated)", value=", ".join(default_list), height=80)
    tickers = []
    for t in raw.split(","):
        t = t.strip().upper()
        if t and t not in tickers:
            tickers.append(t)
    if len(tickers) > MAX_TICKERS:
        st.warning(f"Using the first {MAX_TICKERS} tickers to stay inside free API limits.")
        tickers = tickers[:MAX_TICKERS]
    threshold = st.slider("Flag moves bigger than (%)", 0.5, 10.0, 2.0, 0.5)
    news_days = st.slider("News & filings lookback (days)", 1, 7, 3)
    earnings_days = st.slider("Earnings look-ahead (days)", 7, 30, 14)

if not tickers:
    st.info("Add at least one ticker in the sidebar.")
    st.stop()

today = dt.date.today()

# 1) Movers ------------------------------------------------------------
quotes = {}
for sym in tickers:
    try:
        quotes[sym] = c_quote(sym, api_key)
    except Exception:
        quotes[sym] = None
movers = bl.build_movers(quotes, threshold)

st.subheader("1 · Movers")
big = movers[movers["Flag"].str.contains("big move", na=False)]
if big.empty:
    st.success(f"No watchlist move bigger than {threshold:.1f}% today.")
else:
    st.warning(
        "Big movers: "
        + ", ".join(f"{row['Symbol']} ({row['Change %']:+.2f}%)" for _, row in big.iterrows())
    )
st.dataframe(
    movers,
    hide_index=True,
    use_container_width=True,
    column_config={
        "Price": st.column_config.NumberColumn(format="$%.2f"),
        "Change %": st.column_config.NumberColumn(format="%+.2f%%"),
    },
)

# 2) Earnings ----------------------------------------------------------
st.subheader("2 · Earnings coming up")
try:
    cal = c_earnings(today, today + dt.timedelta(days=earnings_days), api_key)
    earnings = bl.filter_earnings(cal, tickers, today)
    if earnings.empty:
        st.info(f"No earnings reports for your tickers in the next {earnings_days} days.")
    else:
        st.dataframe(earnings, hide_index=True, use_container_width=True)
except Exception as e:
    earnings = pd.DataFrame()
    st.warning(f"Couldn't load the earnings calendar: {e}")

# 3) Analyst shifts ----------------------------------------------------
st.subheader("3 · Analyst sentiment shifts")
shifts = {}
for sym in tickers:
    try:
        shifts[sym] = bl.analyst_shift(c_recs(sym, api_key))
    except Exception:
        shifts[sym] = None
rows = [
    {
        "Symbol": s,
        "Direction": v["direction"],
        "Score before": v["score_before"],
        "Score now": v["score_now"],
        "Change": v["delta"],
    }
    for s, v in shifts.items()
    if v
]
if rows:
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
    st.caption(
        "Score runs from -2 (all Strong Sell) to +2 (all Strong Buy), comparing the "
        "latest monthly analyst snapshot with the prior one. Analyst ratings skew "
        "bullish and often lag price."
    )
else:
    st.info("No analyst trend data available for these tickers.")

# 4) News --------------------------------------------------------------
st.subheader("4 · Headlines")
news = {}
start = today - dt.timedelta(days=news_days)
for sym in tickers:
    try:
        news[sym] = bl.select_news(c_news(sym, start, today, api_key), limit=3)
    except Exception:
        news[sym] = []
any_news = False
for sym, items in news.items():
    if not items:
        continue
    any_news = True
    with st.expander(f"{sym} — {len(items)} headline(s)", expanded=False):
        for it in items:
            # No raw HTML here: headlines come from outside sources.
            st.markdown(f"**[{it['headline']}]({it['url']})**")
            st.caption(f"{it['source']} · {it['published']:%b %d %H:%M} UTC")
if not any_news:
    st.info("No recent headlines (ETFs like VOO often have none).")

# 5) SEC filings -------------------------------------------------------
st.subheader("5 · SEC filings (8-K and insider Form 4)")
ua = secret("SEC_USER_AGENT")
filings = {}
if not ua:
    st.info(
        "To turn this on, add `SEC_USER_AGENT` to Secrets, e.g. "
        '`SEC_USER_AGENT = "Your Name your.email@example.com"`. The SEC asks every '
        "automated user to identify themselves."
    )
else:
    try:
        cik_map = c_cik_map(ua)
        for sym in tickers:
            cik = cik_map.get(sym)
            if not cik:
                continue  # ETFs/funds usually aren't in the SEC company list
            subs = c_submissions(cik, ua)
            found = bl.recent_filings(subs, cik, today - dt.timedelta(days=news_days + 4))
            if found:
                filings[sym] = found
        if not filings:
            st.info("No new 8-K or Form 4 filings for your stocks in this window.")
        for sym, fl in filings.items():
            with st.expander(f"{sym} — {len(fl)} filing(s)"):
                st.dataframe(
                    pd.DataFrame(fl),
                    hide_index=True,
                    use_container_width=True,
                    column_config={"Link": st.column_config.LinkColumn("Link", display_text="open")},
                )
    except Exception as e:
        st.warning(f"Couldn't load SEC filings: {e}")

# 6) Claude summary ----------------------------------------------------
st.subheader("6 · Written brief")
anth_key = secret("ANTHROPIC_API_KEY")
if not anth_key:
    st.info(
        "Optional: add `ANTHROPIC_API_KEY` to Secrets to get a plain-English summary of "
        "everything above. It only runs when you click the button."
    )
else:
    if st.button("Write my brief"):
        digest = bl.build_digest(movers, earnings, shifts, news, filings)
        try:
            with st.spinner("Writing…"):
                text = c_summary(digest, anth_key, secret("ANTHROPIC_MODEL") or "claude-haiku-5-5")
            st.markdown(text)
            st.caption(
                "AI-written from the data above. It can be wrong. Check the sections "
                "above before relying on it."
            )
        except Exception as e:
            st.warning(f"Couldn't write the brief: {e}")
