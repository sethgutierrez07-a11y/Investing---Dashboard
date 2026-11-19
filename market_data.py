"""
Market data for the Market page: daily closes for indexes, volatility, Treasury yields, sector ETFs and a
few other markets, from Yahoo Finance via yfinance (no key). Prices can be delayed about 15 minutes.

Only fetch_close() touches the network; everything else is plain data and tested without it.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pandas as pd

import price_data as pdata

INDEXES = [("^GSPC", "S&P 500"), ("^IXIC", "Nasdaq"), ("^DJI", "Dow"), ("^RUT", "Russell 2000")]
VIX = ("^VIX", "VIX")
RATES = [("^IRX", "3-month"), ("^FVX", "5-year"), ("^TNX", "10-year"), ("^TYX", "30-year")]
SECTORS = [
    ("XLK", "Technology"), ("XLF", "Financials"), ("XLV", "Health Care"), ("XLY", "Consumer Discretionary"),
    ("XLP", "Consumer Staples"), ("XLE", "Energy"), ("XLI", "Industrials"), ("XLU", "Utilities"),
    ("XLB", "Materials"), ("XLRE", "Real Estate"), ("XLC", "Communication"),
]
OTHER = [("GC=F", "Gold"), ("CL=F", "Oil (WTI)"), ("DX-Y.NYB", "US dollar index"), ("BTC-USD", "Bitcoin")]

CORE = [s for s, _ in INDEXES] + [VIX[0], "^TNX"]
EXTRA = [s for s, _ in SECTORS] + [s for s, _ in RATES if s != "^TNX"] + [s for s, _ in OTHER]


def fetch_close(symbol: str, period: str = "2y") -> dict:
    """{'close': Series, 'error': str | None}. Never raises: Yahoo sometimes rate-limits cloud servers."""
    empty = pd.Series(dtype=float)
    try:
        import yfinance as yf
    except ImportError:
        return {"close": empty, "error": "yfinance isn't installed."}
    try:
        h = yf.Ticker(symbol).history(period=period, interval="1d", auto_adjust=True, actions=False)
    except Exception as e:  # noqa: BLE001
        return {"close": empty, "error": f"Yahoo didn't answer ({type(e).__name__})."}
    if h is None or h.empty or "Close" not in h:
        return {"close": empty, "error": "no data"}
    return clean(h["Close"])


def clean(close: pd.Series | None) -> dict:
    """Wrap a raw close series: sorted, tz-naive, positive, one row per day."""
    if close is None or len(close) == 0:
        return {"close": pd.Series(dtype=float), "error": "no data"}
    s = pdata.clean_prices(pd.Series(close))
    if s.empty:
        return {"close": s, "error": "no data"}
    return {"close": s, "error": None}


def fetch_many(symbols: list[str], period: str = "2y", fetcher=fetch_close, workers: int = 6) -> dict[str, dict]:
    """Several symbols at once (network waits overlap). Order of the result follows `symbols`."""
    symbols = list(dict.fromkeys(symbols))
    if not symbols:
        return {}
    with ThreadPoolExecutor(max_workers=min(workers, len(symbols))) as ex:
        results = list(ex.map(lambda s: fetcher(s, period), symbols))
    return dict(zip(symbols, results))
