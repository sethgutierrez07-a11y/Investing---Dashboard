"""
Stock of the day, shared by the dashboard, the Daily Brief and the Stock Deep-Dive so all three show the same pick
without repeating the screening. Cached Finnhub reads + one cached screen. Read-only; needs only the Finnhub key.
"""

import streamlit as st

import brief_lib as bl
import idea_lib as il
import portfolio_state as ps


@st.cache_data(ttl=60, show_spinner=False)
def quote(symbol: str, api_key: str) -> dict:
    return bl.fetch_quote(symbol, api_key)


@st.cache_data(ttl=3600, show_spinner=False)
def trends(symbol: str, api_key: str) -> list[dict]:
    return bl.fetch_recommendations(symbol, api_key)


@st.cache_data(ttl=12 * 3600, show_spinner=False)
def metrics(symbol: str, api_key: str) -> dict:
    return (bl.finnhub_get("stock/metric", {"symbol": symbol, "metric": "all"}, api_key) or {}).get("metric") or {}


@st.cache_data(ttl=86400, show_spinner=False)
def profile(symbol: str, api_key: str) -> dict:
    return bl.finnhub_get("stock/profile2", {"symbol": symbol}, api_key) or {}


def exclusions(held, tickers=None) -> set[str]:
    """What the pick should skip: what you hold, plus the sample list while locked (or your watchlist when given)."""
    return set(held or []) | set(tickers if tickers is not None else (ps.SAMPLE_WATCHLIST if not held else []))


@st.cache_data(ttl=300, show_spinner=False)
def screen_today(api_key: str, exclude: tuple, day_ordinal: int, offset: int = 0, n: int = 6) -> dict:
    """{'best': evaluation or None, 'evals': [...], 'failed': [...], 'name': str}. One failure never hides the others."""
    candidates = il.pick_candidates(il.UNIVERSE, set(exclude), day_ordinal, n=n, offset=offset)
    evals, failed = [], []
    for sym in candidates:
        try:
            evals.append(il.evaluate(sym, quote(sym, api_key), metrics(sym, api_key), trends(sym, api_key)))
        except Exception:  # noqa: BLE001 - rate limit or a bad ticker: skip it, keep the rest
            failed.append(sym)
    best = il.choose(evals)
    name = ""
    if best:
        try:
            name = profile(best["symbol"], api_key).get("name") or ""
        except Exception:  # noqa: BLE001
            name = ""
    return {"best": best, "evals": evals, "failed": failed, "name": name}
