"""
Shared, read-only access to your portfolio for every page.

Nothing here shows account data unless the visitor has entered APP_PASSWORD
(the same unlock the Holdings page uses). Pages that import this get:

  - load_raw():          one cached SnapTrade read, shared by all pages
  - get_portfolio():     the parsed portfolio, or None when locked / not connected
  - unlock_sidebar():    a small password box for the sidebar
  - watchlist_sidebar(): "my holdings + extra tickers" watchlist controls
"""

import time

import pandas as pd
import streamlit as st

import dividend_data as dd
import holdings_lib as hl

MAX_TICKERS = 15  # Finnhub free tier allows ~60 calls/minute
SAMPLE_WATCHLIST = ["AAPL", "MSFT", "VOO"]


def secret(name: str):
    try:
        return st.secrets[name]
    except Exception:
        return None


def configured() -> bool:
    return bool(secret("APP_PASSWORD") and secret("SNAPTRADE_CLIENT_ID") and secret("SNAPTRADE_CONSUMER_KEY"))


def is_unlocked() -> bool:
    return bool(secret("APP_PASSWORD")) and bool(st.session_state.get("holdings_unlocked"))


def unlock_sidebar() -> None:
    """Small unlock box for pages that work without the portfolio but get better with it."""
    expected = secret("APP_PASSWORD")
    if not expected or is_unlocked():
        return
    with st.sidebar:
        st.subheader("🔒 Personalize")
        entered = st.text_input("Password", type="password", key="sidebar_pw", help="Unlocks your real holdings on this page.")
        if st.button("Unlock", key="sidebar_unlock"):
            if hl.password_ok(entered, expected):
                st.session_state["holdings_unlocked"] = True
                st.rerun()
            else:
                time.sleep(2)  # slows down password guessing
                st.error("Wrong password.")


@st.cache_data(ttl=300, show_spinner="Reading your accounts…")
def load_raw():
    client = hl.make_client(secret("SNAPTRADE_CLIENT_ID"), secret("SNAPTRADE_CONSUMER_KEY"))
    return hl.fetch_all(client)


@st.cache_data(ttl=43200, show_spinner=False)
def load_history(symbol: str) -> dict:
    """Yahoo price + dividend history for one ticker, cached 12h and shared by the Dividends and Risk pages."""
    return dd.fetch_history(symbol)


def get_portfolio():
    """Parsed portfolio, or None (locked, not connected, empty, or unreadable).

    Never raises: personalization is a bonus, the page must still work without it.
    """
    if not (is_unlocked() and configured()):
        return None
    try:
        raw = load_raw()
        if not raw:
            return None
        pf = hl.build_portfolio(raw)
    except Exception:  # noqa: BLE001
        return None
    df = pf["positions"]
    if df.empty:
        return None
    # Cash-equivalent funds (a money-market core position) are cash, not holdings.
    holdings_df = df[df["Class"] != "Cash equiv."]
    if holdings_df.empty:
        holdings_df = df
    merged = hl.by_symbol(holdings_df)
    return {"raw": raw, "pf": pf, "df": df, "holdings_df": holdings_df, "merged": merged}


def held_symbols(portfolio, limit: int = MAX_TICKERS) -> list[str]:
    """Held tickers, biggest first, skipping unparsed ('?') symbols."""
    if not portfolio:
        return []
    syms = [s for s in portfolio["merged"]["Symbol"] if s and s != "?"]
    return syms[:limit]


def parse_tickers(text: str) -> list[str]:
    out: list[str] = []
    for t in text.replace("\n", ",").split(","):
        t = t.strip().upper()
        if t and t not in out:
            out.append(t)
    return out


def watchlist_sidebar(portfolio):
    """Sidebar controls. Returns (tickers, held) where held is the set of portfolio tickers.

    With a portfolio: your holdings are the watchlist by default; extras go in the box.
    Without one: the old editable sample list.
    """
    held = held_symbols(portfolio)
    with st.sidebar:
        st.header("Watchlist")
        if held:
            use_mine = st.toggle("Include my holdings", value=True, help="Your real tickers from Fidelity, biggest first.")
            extra_text = st.text_area("Extra tickers to watch (comma-separated)", value="", height=70)
            extras = parse_tickers(extra_text)
            tickers = (held if use_mine else []) + [t for t in extras if t not in held or not use_mine]
        else:
            text = st.text_area("Tickers (comma-separated)", value=", ".join(SAMPLE_WATCHLIST), height=80)
            tickers = parse_tickers(text)
        if len(tickers) > MAX_TICKERS:
            st.warning(f"Using the first {MAX_TICKERS} tickers to stay inside free API limits.")
            tickers = tickers[:MAX_TICKERS]
        st.session_state["watchlist"] = tickers
        st.caption(f"Tracking {len(tickers)} ticker(s)." + (" Includes your holdings." if held else ""))
    return tickers, set(held)


def weight_lookup(portfolio) -> dict[str, float]:
    """Ticker -> % of invested value (for Weight columns)."""
    return hl.shares_of_invested(portfolio["merged"]) if portfolio else {}


def gain_lookup(portfolio) -> dict[str, float | None]:
    """Ticker -> gain since purchase, in % (None if cost basis unknown)."""
    if not portfolio:
        return {}
    m = portfolio["merged"]
    return {s: (None if pd.isna(g) else float(g)) for s, g in zip(m["Symbol"], m["Gain %"])}
