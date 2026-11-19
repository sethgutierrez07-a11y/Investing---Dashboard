"""
Daily price history for the Strategy Lab.

Order of attempts (the page tells you which one was used):
  1. Yahoo Finance via yfinance: no key, dividend-adjusted prices (what a backtest needs).
  2. Twelve Data (free key in Secrets as TWELVEDATA_API_KEY): split-adjusted only, so dividends are missing.
  3. A CSV you upload (Date + Close / Adj Close columns), e.g. downloaded from Yahoo or Stooq.

Parsing and cleaning are pure functions and tested; only the two fetch functions touch the network.
"""

from __future__ import annotations

import io
from typing import Any

import pandas as pd
import requests

MIN_DAYS = 250  # a year of data; less than that can't say anything useful


class PriceDataError(Exception):
    pass


def clean_prices(s: pd.Series) -> pd.Series:
    """Sorted, tz-naive, de-duplicated, positive prices only."""
    s = pd.to_numeric(s, errors="coerce")
    idx = pd.to_datetime(s.index, errors="coerce", utc=True)
    s.index = idx.tz_convert(None).normalize()
    s = s[~s.index.isna()]
    s = s[s.notna() & (s > 0)]
    s = s[~s.index.duplicated(keep="last")].sort_index()
    s.name = "price"
    return s.astype(float)


def parse_twelvedata(payload: Any) -> pd.Series:
    """Twelve Data time_series JSON -> price series. Raises PriceDataError with the provider's message."""
    if not isinstance(payload, dict):
        raise PriceDataError("Unexpected response from Twelve Data.")
    if payload.get("status") == "error" or "values" not in payload:
        raise PriceDataError(str(payload.get("message") or "Twelve Data returned no prices.")[:200])
    rows = [(v.get("datetime"), v.get("close")) for v in payload["values"] if isinstance(v, dict)]
    if not rows:
        raise PriceDataError("Twelve Data returned no prices.")
    s = pd.Series([r[1] for r in rows], index=[r[0] for r in rows])
    return clean_prices(s)


def parse_csv(data: bytes) -> pd.Series:
    """CSV with a Date column and an 'Adj Close' (preferred) or 'Close' column."""
    try:
        df = pd.read_csv(io.BytesIO(data))
    except Exception as e:  # noqa: BLE001
        raise PriceDataError(f"Couldn't read that file as a CSV ({type(e).__name__}).") from e
    cols = {str(c).strip().lower(): c for c in df.columns}
    date_col = cols.get("date") or cols.get("datetime") or cols.get("time")
    price_col = cols.get("adj close") or cols.get("adj_close") or cols.get("adjusted close") or cols.get("close")
    if not date_col or not price_col:
        raise PriceDataError("The CSV needs a Date column and a Close (or Adj Close) column.")
    return clean_prices(pd.Series(df[price_col].values, index=df[date_col].values))


def require_enough(s: pd.Series, symbol: str) -> pd.Series:
    if len(s) < MIN_DAYS:
        raise PriceDataError(f"Only {len(s)} days of prices found for {symbol}; need at least {MIN_DAYS} (about a year).")
    return s


def fetch_yahoo(symbol: str) -> pd.Series:
    """Dividend- and split-adjusted daily closes, as far back as Yahoo has them."""
    try:
        import yfinance as yf
    except ImportError as e:
        raise PriceDataError("yfinance isn't installed.") from e
    try:
        hist = yf.Ticker(symbol).history(period="max", interval="1d", auto_adjust=True)
    except Exception as e:  # noqa: BLE001 — Yahoo rate-limits or blocks cloud IPs at times
        raise PriceDataError(f"Yahoo Finance didn't answer ({type(e).__name__}).") from e
    if hist is None or hist.empty or "Close" not in hist:
        raise PriceDataError(f"Yahoo Finance has no history for {symbol}.")
    return clean_prices(hist["Close"])


def fetch_twelvedata(symbol: str, api_key: str) -> pd.Series:
    r = requests.get(
        "https://api.twelvedata.com/time_series",
        params={"symbol": symbol, "interval": "1day", "outputsize": 5000, "apikey": api_key},
        timeout=20,
    )
    r.raise_for_status()
    return parse_twelvedata(r.json())


def load_history(symbol: str, twelve_key: str | None = None) -> tuple[pd.Series, str, list[str]]:
    """(prices, source description, problems met on the way). Raises PriceDataError if nothing worked."""
    symbol = symbol.strip().upper()
    problems: list[str] = []
    try:
        return require_enough(fetch_yahoo(symbol), symbol), "Yahoo Finance (dividend-adjusted)", problems
    except PriceDataError as e:
        problems.append(str(e))
    if twelve_key:
        try:
            s = require_enough(fetch_twelvedata(symbol, twelve_key), symbol)
            return s, "Twelve Data (split-adjusted; dividends not included)", problems
        except (PriceDataError, requests.RequestException) as e:
            problems.append(f"Twelve Data: {e}" if isinstance(e, PriceDataError) else f"Twelve Data didn't answer ({type(e).__name__}).")
    raise PriceDataError(" ".join(problems) or "No price source worked.")
