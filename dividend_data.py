"""
Data fetching for the Dividends page. READ-ONLY.

  - SnapTrade account activity (dividends and reinvestments): only `list_user_accounts`-style
    account ids that the Holdings read already produced, and only `get_account_activities`.
  - Yahoo Finance (yfinance): per-share dividend history and unadjusted closes, for projections
    and the DRIP replay. No key needed.

Anything that fails is reported, never raised into the page.
"""

from __future__ import annotations

from typing import Any, Callable

import pandas as pd

import holdings_lib as hl

ACTIVITY_TYPES = "DIVIDEND,REI,STOCK_DIVIDEND"
RANGES_DAYS = (3650, 1095, 365)  # try ten years of history, then fewer if the broker rejects it
PAGE = 1000
MAX_PAGES = 20


def _page_through(call: Callable[..., Any], account_id: str, start: str, end: str, types: str | None) -> list[dict]:
    items: list[dict] = []
    offset = 0
    for _ in range(MAX_PAGES):
        kwargs = dict(account_id=account_id, start_date=start, end_date=end, offset=offset, limit=PAGE)
        if types:
            kwargs["type"] = types
        body = hl.unwrap(call(**kwargs))
        rows = hl.as_list(body, ("data", "activities", "results"))
        items += [r for r in rows if isinstance(r, dict)]
        total = hl.dig(body, "pagination", "total")
        offset += len(rows)
        if len(rows) < PAGE or (isinstance(total, int) and offset >= total):
            break
    return items


def fetch_activities(client: Any, accounts: list[dict], today: Any,
                     on_error: Callable[[Exception], str] = lambda e: type(e).__name__) -> dict:
    """Dividend-related activity for each account. Returns plain, cacheable data:
    {"items": [...], "errors": [...], "shape": {...}, "range_days": int | None}."""
    today = pd.Timestamp(today).normalize()
    out: dict = {"items": [], "errors": [], "shape": {}, "range_days": None}
    for acct in accounts:
        if not isinstance(acct, dict) or not acct.get("id"):
            continue
        label = hl.account_label(acct)
        call = client.account_information.get_account_activities
        done = False
        last_err: Exception | None = None
        for days in RANGES_DAYS:
            start, end = (today - pd.Timedelta(days=days)).strftime("%Y-%m-%d"), today.strftime("%Y-%m-%d")
            for types in (ACTIVITY_TYPES, None):  # second try: no type filter, filter locally
                try:
                    items = _page_through(call, acct["id"], start, end, types)
                except Exception as e:  # noqa: BLE001
                    last_err = e
                    continue
                for it in items:
                    it["_account"] = label
                out["items"] += items
                out["range_days"] = max(out["range_days"] or 0, days)
                if items and not out["shape"]:
                    out["shape"] = {"activity": hl.describe_shape(items[0])}
                done = True
                break
            if done:
                break
        if not done:
            out["errors"].append(f"{label}: {on_error(last_err) if last_err else 'no response'}")
    return out


def fetch_history(symbol: str) -> dict:
    """{'prices': Series, 'divs': Series, 'error': str | None}. Closes are NOT dividend-adjusted
    (the DRIP replay adds dividends itself); both are split-adjusted by Yahoo."""
    empty = pd.Series(dtype=float)
    try:
        import yfinance as yf
    except ImportError:
        return {"prices": empty, "divs": empty, "error": "yfinance isn't installed."}
    try:
        h = yf.Ticker(symbol.replace(".", "-")).history(  # Yahoo writes BRK.B as BRK-B
            period="max", interval="1d", auto_adjust=False, actions=True)
    except Exception as e:  # noqa: BLE001 — Yahoo sometimes rate-limits cloud IPs
        return {"prices": empty, "divs": empty, "error": f"Yahoo didn't answer ({type(e).__name__})."}
    if h is None or h.empty or "Close" not in h:
        return {"prices": empty, "divs": empty, "error": "no history"}
    idx = pd.DatetimeIndex(h.index)
    if idx.tz is not None:
        idx = idx.tz_convert(None)
    h = h.set_axis(idx.normalize())
    divs = h["Dividends"][h["Dividends"] > 0] if "Dividends" in h else empty
    return {"prices": h["Close"].dropna().astype(float), "divs": divs.astype(float), "error": None}
