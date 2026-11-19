"""
Market overview calculations. Pure functions: closes in, numbers out. No Streamlit, no network.

Returns are fractions (0.01 = 1%). Yield changes are in percentage points. "Trading days" windows:
1 week = 5, 1 month = 21, 3 months = 63, 1 year = 252.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

WINDOWS = {"1D": 1, "1W": 5, "1M": 21, "3M": 63, "1Y": 252}
OFFENSIVE = ["XLK", "XLY", "XLC"]
DEFENSIVE = ["XLP", "XLU", "XLV"]


def _clean(close: pd.Series | None) -> pd.Series:
    if close is None:
        return pd.Series(dtype=float)
    s = pd.to_numeric(pd.Series(close), errors="coerce").dropna()
    return s[s > 0].sort_index()


def period_returns(close: pd.Series | None) -> dict[str, float | None]:
    """1D, 1W, 1M, 3M, 1Y and YTD price returns; None where the history is too short."""
    s = _clean(close)
    out: dict[str, float | None] = {k: None for k in [*WINDOWS, "YTD"]}
    if len(s) < 2:
        return out
    last = float(s.iloc[-1])
    for k, n in WINDOWS.items():
        if len(s) > n:
            out[k] = last / float(s.iloc[-1 - n]) - 1
    prior = s[s.index.year < s.index[-1].year]
    if len(prior):
        out["YTD"] = last / float(prior.iloc[-1]) - 1
    return out


def level_changes(series: pd.Series | None) -> dict[str, float | None]:
    """Change in the level (for yields: percentage points) over 1 day, 1 month and 1 year."""
    s = _clean(series)
    out: dict[str, float | None] = {"1D": None, "1M": None, "1Y": None}
    if len(s) < 2:
        return out
    last = float(s.iloc[-1])
    for k, n in (("1D", 1), ("1M", 21), ("1Y", 252)):
        if len(s) > n:
            out[k] = last - float(s.iloc[-1 - n])
    return out


def normalize_yield(series: pd.Series | None) -> pd.Series:
    """Yahoo quotes Treasury yields in percent (4.25). Very old data used 10x that (42.5); undo it if seen."""
    s = _clean(series)
    return s / 10 if len(s) and float(s.iloc[-1]) > 25 else s


def trend_stats(close: pd.Series | None) -> dict:
    """Where the latest close sits versus its averages and its 52-week range."""
    s = _clean(close)
    out = {"last": None, "ma50": None, "ma200": None, "vs50": None, "vs200": None, "high52": None, "low52": None,
           "from_high": None, "range_pos": None, "trend": None}
    if s.empty:
        return out
    last = float(s.iloc[-1])
    out["last"] = last
    if len(s) >= 50:
        out["ma50"] = float(s.iloc[-50:].mean())
        out["vs50"] = last / out["ma50"] - 1
    if len(s) >= 200:
        out["ma200"] = float(s.iloc[-200:].mean())
        out["vs200"] = last / out["ma200"] - 1
    yr = s.iloc[-252:]
    out["high52"], out["low52"] = float(yr.max()), float(yr.min())
    out["from_high"] = last / out["high52"] - 1
    if out["high52"] > out["low52"]:
        out["range_pos"] = (last - out["low52"]) / (out["high52"] - out["low52"])
    if out["vs50"] is not None and out["vs200"] is not None:
        out["trend"] = "up" if (out["vs50"] > 0 and out["vs200"] > 0) else "down" if (out["vs50"] < 0 and out["vs200"] < 0) else "mixed"
    return out


def vix_regime(level: float | None) -> tuple[str, str] | None:
    """(label, plain-English meaning) from rough, commonly used bands. The long-run average is roughly 20."""
    if level is None or pd.isna(level):
        return None
    if level < 15:
        return "Calm", "markets are unusually relaxed"
    if level < 20:
        return "Normal", "about the usual level of worry"
    if level < 30:
        return "Elevated", "investors are nervous and swings are bigger than usual"
    return "Stressed", "fear is high and large daily swings are likely"


def curve_spread(y_short: float | None, y_long: float | None) -> float | None:
    """10-year minus 3-month yield, in percentage points (negative = inverted)."""
    if y_short is None or y_long is None or pd.isna(y_short) or pd.isna(y_long):
        return None
    return float(y_long) - float(y_short)


def curve_label(spread: float | None) -> str | None:
    if spread is None:
        return None
    return "inverted" if spread < 0 else "flat" if spread < 0.5 else "upward-sloping"


def curve_points(closes: dict[str, pd.Series], order: list[str], lag: int = 0) -> list[float | None]:
    """Yield for each maturity `lag` trading days ago (0 = latest). `order` lists the symbols short to long."""
    out = []
    for sym in order:
        s = normalize_yield(closes.get(sym))
        out.append(float(s.iloc[-1 - lag]) if len(s) > lag else None)
    return out


def sector_table(closes: dict[str, pd.Series], names: dict[str, str]) -> pd.DataFrame:
    """One row per sector ETF with 1D / 1M / 3M / YTD returns (fractions), best 1M first."""
    rows = []
    for sym, name in names.items():
        r = period_returns(closes.get(sym))
        if r["1M"] is None:
            continue
        rows.append({"Symbol": sym, "Sector": name, "1D": r["1D"], "1M": r["1M"], "3M": r["3M"], "YTD": r["YTD"]})
    cols = ["Symbol", "Sector", "1D", "1M", "3M", "YTD"]
    if not rows:
        return pd.DataFrame(columns=cols)
    return pd.DataFrame(rows, columns=cols).sort_values("1M", ascending=False).reset_index(drop=True)


def breadth(table: pd.DataFrame, col: str = "1M") -> tuple[int, int] | None:
    """(sectors up, sectors measured)."""
    if table is None or table.empty or col not in table:
        return None
    v = table[col].dropna()
    return int((v > 0).sum()), int(len(v))


def offense_vs_defense(table: pd.DataFrame, col: str = "1M") -> dict | None:
    """Average return of growth-oriented sectors minus defensive ones, in fractions."""
    if table is None or table.empty:
        return None
    t = table.set_index("Symbol")[col]
    off = [t[s] for s in OFFENSIVE if s in t.index and pd.notna(t[s])]
    de = [t[s] for s in DEFENSIVE if s in t.index and pd.notna(t[s])]
    if len(off) < 2 or len(de) < 2:
        return None
    return {"offense": float(np.mean(off)), "defense": float(np.mean(de)), "gap": float(np.mean(off) - np.mean(de))}


def index_table(closes: dict[str, pd.Series], names: dict[str, str]) -> pd.DataFrame:
    """Returns and trend position for each index (the 'advanced' detail table)."""
    rows = []
    for sym, name in names.items():
        s = closes.get(sym)
        if s is None or len(_clean(s)) < 2:
            continue
        r, t = period_returns(s), trend_stats(s)
        rows.append({"Index": name, "Level": t["last"], "1D": r["1D"], "1W": r["1W"], "1M": r["1M"], "3M": r["3M"], "YTD": r["YTD"], "1Y": r["1Y"],
                     "vs 50-day": t["vs50"], "vs 200-day": t["vs200"], "From 52-wk high": t["from_high"]})
    return pd.DataFrame(rows)
