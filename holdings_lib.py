"""
Holdings — data + logic layer (no Streamlit imports, so it can be unit tested).

READ-ONLY. This module only ever calls SnapTrade's account-information
endpoints (list accounts, balances, positions). It never calls any trading
endpoint, and the SnapTrade connection to Fidelity is read-only on their side.

Auth model: SnapTrade *Personal* API key (your own client ID + consumer key).
Personal keys do NOT use userId / userSecret and must not call registerUser.
"""

from __future__ import annotations

import hmac
from collections.abc import Mapping
from typing import Any, Callable

import pandas as pd

POSITION_COLS = [
    "Account", "Symbol", "Description", "Units", "Price",
    "Market value", "Cost basis", "Gain", "Gain %",
]
# Columns that reveal how much you hold. Units are included because
# units x (public) price gives the dollar value right back.
DOLLAR_COLS = ["Units", "Price", "Market value", "Cost basis", "Gain"]


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------
def to_plain(obj: Any) -> Any:
    """Turn SDK response objects into plain dicts/lists (so they can be cached)."""
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, Mapping):  # dict, frozendict, and other dict-likes
        return {k: to_plain(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set, frozenset)):
        return [to_plain(v) for v in obj]
    for attr in ("to_dict", "model_dump", "dict"):
        fn = getattr(obj, attr, None)
        if callable(fn):
            try:
                return to_plain(fn())
            except Exception:
                pass
    if hasattr(obj, "__dict__"):
        return to_plain({k: v for k, v in vars(obj).items() if not k.startswith("_")})
    return str(obj)


def unwrap(resp: Any) -> Any:
    """SDK calls return a wrapper with `.body`; tests may pass the body directly."""
    return to_plain(getattr(resp, "body", resp))


def dig(obj: Any, *path: str, default: Any = None) -> Any:
    cur = obj
    for key in path:
        if isinstance(cur, dict) and key in cur:
            cur = cur[key]
        else:
            return default
    return cur if cur is not None else default


def first(obj: Any, *paths: tuple[str, ...], default: Any = None) -> Any:
    for p in paths:
        v = dig(obj, *p)
        if v is not None:
            return v
    return default


LIST_KEYS = ("positions", "balances", "accounts", "data", "items", "results")


def as_list(obj: Any, keys: tuple[str, ...] = LIST_KEYS) -> list:
    """Accept a list, or a dict that wraps one under a common key. Anything else -> []."""
    if isinstance(obj, (list, tuple)):
        return list(obj)
    if isinstance(obj, dict):
        for k in keys:
            if isinstance(obj.get(k), (list, tuple)):
                return list(obj[k])
        lists = [v for v in obj.values() if isinstance(v, (list, tuple))]
        if len(lists) == 1:  # a dict with exactly one list inside: that's the payload
            return list(lists[0])
    return []


def describe_shape(obj: Any, depth: int = 4) -> Any:
    """Outline of a payload: field names and types only, never values."""
    if isinstance(obj, dict):
        if depth <= 0:
            return "dict"
        return {str(k): describe_shape(v, depth - 1) for k, v in list(obj.items())[:30]}
    if isinstance(obj, (list, tuple)):
        if not obj:
            return "list (empty)"
        return [f"list of {len(obj)}", describe_shape(obj[0], depth - 1)] if depth > 0 else "list"
    return type(obj).__name__


def num(x: Any) -> float | None:
    try:
        if x is None or isinstance(x, bool):
            return None
        return float(x)
    except (TypeError, ValueError):
        return None


# --------------------------------------------------------------------------
# Normalizing SnapTrade payloads
# --------------------------------------------------------------------------
def account_label(account: dict) -> str:
    """'Fidelity · Individual' — never the account number."""
    inst = account.get("institution_name") or ""
    name = account.get("name") or "Account"
    return f"{inst} · {name}".strip(" ·")


def normalize_positions(account: dict, raw_positions: list[dict]) -> list[dict]:
    label = account_label(account)
    rows = []
    for p in as_list(raw_positions, ("positions",)):
        if not isinstance(p, dict):
            continue
        if "units" not in p and "fractional_units" not in p and isinstance(p.get("position"), dict):
            p = p["position"]  # some shapes nest each position one level down
        ticker = first(
            p,
            ("symbol", "symbol", "symbol"),
            ("symbol", "symbol", "raw_symbol"),
            ("symbol", "raw_symbol"),
            ("ticker",),
        )
        if ticker is None:
            inner = dig(p, "symbol", "symbol")  # some shapes put the ticker string here
            ticker = inner if isinstance(inner, str) else None
        if isinstance(ticker, dict) or not ticker:
            ticker = "?"
        desc = first(p, ("symbol", "symbol", "description"), ("symbol", "description"), default="")
        units = num(p.get("units"))
        if units is None:
            units = num(p.get("fractional_units"))
        price = num(p.get("price"))
        avg = num(p.get("average_purchase_price"))
        if not units:
            continue
        mv = units * price if price is not None else None
        cost = units * avg if avg else None
        if mv is not None and cost:
            gain = mv - cost
        else:
            gain = num(p.get("open_pnl"))
            cost = (mv - gain) if (mv is not None and gain is not None) else None
        gain_pct = (gain / cost * 100) if (gain is not None and cost) else None
        rows.append(
            {
                "Account": label, "Symbol": str(ticker).upper(), "Description": str(desc),
                "Units": units, "Price": price, "Market value": mv,
                "Cost basis": cost, "Gain": gain, "Gain %": gain_pct,
            }
        )
    return rows


def cash_from_balances(raw_balances: list[dict]) -> dict[str, float]:
    """{'USD': 123.45} — sums cash per currency code."""
    out: dict[str, float] = {}
    for b in as_list(raw_balances, ("balances",)):
        if not isinstance(b, dict):
            continue
        code = first(b, ("currency", "code"), default="USD")
        cash = num(b.get("cash"))
        if cash is not None:
            out[code] = out.get(code, 0.0) + cash
    return out


def account_total(account: dict) -> float | None:
    return num(first(account, ("balance", "total", "amount")))


def build_portfolio(per_account: list[dict]) -> dict:
    """Combine fetched per-account data into one portfolio view.

    per_account items: {"account": {...}, "positions": [...], "balances": [...], "error": str|None}
    Returns positions DataFrame (with weights), cash, warnings.
    """
    rows: list[dict] = []
    cash_total = 0.0
    warnings: list[str] = []
    for item in per_account:
        acct = item.get("account", {})
        label = account_label(acct)
        if item.get("error"):
            warnings.append(f"{label}: couldn't load ({item['error']})")
            continue
        acct_rows = normalize_positions(acct, item.get("positions"))
        cash = cash_from_balances(item.get("balances"))
        non_usd = {k: v for k, v in cash.items() if k != "USD" and v}
        if non_usd:
            warnings.append(f"{label}: non-USD cash ({', '.join(non_usd)}) is not included in totals.")
        acct_cash = cash.get("USD", 0.0)
        cash_total += acct_cash
        rows.extend(acct_rows)

        pos_mv = sum(r["Market value"] or 0 for r in acct_rows)
        reported = account_total(acct)
        if reported and abs((pos_mv + acct_cash) - reported) / reported > 0.02:
            warnings.append(
                f"{label}: positions + cash differ from the account total SnapTrade reports by more "
                f"than 2%. Treat these numbers as approximate."
            )
        if as_list(item.get("positions"), ("positions",)) and not acct_rows:
            warnings.append(f"{label}: positions came back but none could be read. Data shape may have changed.")

    df = pd.DataFrame(rows, columns=POSITION_COLS)
    total = float(df["Market value"].sum(skipna=True)) + cash_total if not df.empty else cash_total
    if not df.empty and total > 0:
        df["Weight %"] = df["Market value"] / total * 100
    else:
        df["Weight %"] = pd.Series(dtype=float)
    df = df.sort_values("Market value", ascending=False, na_position="last").reset_index(drop=True)
    return {"positions": df, "cash": cash_total, "total": total, "warnings": warnings}


def by_symbol(df: pd.DataFrame) -> pd.DataFrame:
    """Merge the same ticker held in several accounts."""
    if df.empty:
        return df
    g = df.groupby("Symbol", as_index=False).agg(
        {"Units": "sum", "Market value": "sum", "Cost basis": "sum", "Gain": "sum", "Weight %": "sum"}
    )
    g["Gain %"] = g.apply(lambda r: r["Gain"] / r["Cost basis"] * 100 if r["Cost basis"] else None, axis=1)
    return g.sort_values("Market value", ascending=False).reset_index(drop=True)


# --------------------------------------------------------------------------
# Analytics
# --------------------------------------------------------------------------
def concentration(weights_pct: pd.Series) -> dict:
    """How concentrated the invested part is. Weights are % of total portfolio."""
    w = weights_pct.dropna()
    w = w[w > 0] / 100
    if w.empty:
        return {"largest": None, "top5": None, "effective_n": None}
    invested = w / w.sum()  # re-base to the invested portion
    hhi = float((invested**2).sum())
    return {
        "largest": float(invested.max() * 100),
        "top5": float(invested.sort_values(ascending=False).head(5).sum() * 100),
        "effective_n": 1 / hhi if hhi else None,
    }


def day_change(df: pd.DataFrame, quotes: dict[str, dict | None]) -> dict:
    """Estimate today's % move of the invested part from watchlist-style quotes.

    Symbols with no quote are left out; `coverage` says how much of the value was priced.
    """
    agg = by_symbol(df)
    if agg.empty:
        return {"pct": None, "coverage": 0.0}
    priced_mv = 0.0
    move = 0.0
    total_mv = float(agg["Market value"].sum())
    for _, r in agg.iterrows():
        q = quotes.get(r["Symbol"])
        dp = num(q.get("dp")) if q else None
        if dp is None or not q.get("c"):
            continue
        priced_mv += r["Market value"]
        move += r["Market value"] * dp / 100
    if priced_mv <= 0:
        return {"pct": None, "coverage": 0.0}
    return {"pct": move / priced_mv * 100, "coverage": priced_mv / total_mv if total_mv else 0.0}


def hide_dollars(df: pd.DataFrame) -> pd.DataFrame:
    return df.drop(columns=[c for c in DOLLAR_COLS if c in df.columns])


# --------------------------------------------------------------------------
# Access control
# --------------------------------------------------------------------------
def password_ok(entered: str | None, expected: str | None) -> bool:
    """Constant-time compare. Fails closed if no password has been configured."""
    if not expected or not entered:
        return False
    return hmac.compare_digest(entered.encode(), expected.encode())


# --------------------------------------------------------------------------
# SnapTrade I/O (read-only calls only)
# --------------------------------------------------------------------------
def make_client(client_id: str, consumer_key: str):
    """Build a SnapTrade client using Personal API key auth."""
    from snaptrade_client import SnapTrade, SnapTradeAuth  # lazy: only needed when used

    factory = getattr(SnapTradeAuth, "personal_api_key", None)
    if factory is None:
        raise RuntimeError(
            "This version of snaptrade-python-sdk has no personal_api_key auth. "
            "Update the package (pip install -U snaptrade-python-sdk)."
        )
    return SnapTrade(auth=factory(consumer_key=consumer_key, client_id=client_id))


def fetch_all(client: Any, on_error: Callable[[Exception], str] = lambda e: type(e).__name__) -> list[dict]:
    """Read accounts, then balances and positions per account. One bad account
    never hides the others. Only read endpoints are called."""
    accounts = as_list(unwrap(client.account_information.list_user_accounts()), ("accounts",))
    out = []
    for acct in accounts:
        if not isinstance(acct, dict):
            continue
        item: dict = {"account": acct, "positions": [], "balances": [], "error": None, "shape": {}}
        aid = acct.get("id")
        try:
            item["balances"] = unwrap(client.account_information.get_user_account_balance(account_id=aid))
            item["positions"] = unwrap(client.account_information.get_all_account_positions(account_id=aid))
            item["shape"] = {
                "balances": describe_shape(item["balances"]),
                "positions": describe_shape(item["positions"]),
            }
        except Exception as e:  # noqa: BLE001 — report, don't crash the page
            item["error"] = on_error(e)
        out.append(item)
    return out
