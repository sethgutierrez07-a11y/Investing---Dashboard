"""
Portfolio risk, from price history. Pure logic: no Streamlit, no network.

Everything is a BACKCAST: today's holdings, at today's weights, replayed over past prices.
It says how this mix would have behaved, not what your account actually did.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import dividend_lib as dl

TRADING_DAYS = 252
MIN_DAYS = 250

# Named stretches for the "how would today's mix have fared" table. Dates are peak-to-trough of the S&P 500.
HISTORY_WINDOWS = [
    ("Late-2018 selloff", "2018-09-20", "2018-12-24"),
    ("COVID crash", "2020-02-19", "2020-03-23"),
    ("2022 bear market", "2022-01-03", "2022-10-12"),
]


def total_returns(prices: pd.Series, divs: pd.Series | None) -> pd.Series:
    """Daily total return: price change plus any dividend that went ex that day."""
    p = prices.dropna()
    p = p[p > 0]
    if len(p) < 2:
        return pd.Series(dtype=float, index=pd.DatetimeIndex([]))
    p.index = pd.DatetimeIndex(p.index)
    d = dl.clean_history(divs).reindex(p.index).fillna(0.0)
    r = ((p + d) / p.shift(1) - 1).dropna()
    return r[np.isfinite(r)]


def aligned_returns(rets: dict[str, pd.Series], years: float | None, min_days: int = MIN_DAYS) -> tuple[pd.DataFrame, list[str]]:
    """One column per ticker over a COMMON window. Tickers with too little history are dropped
    (shortest first) until the common window is long enough; the dropped ones are returned."""
    rets = {k: v for k, v in rets.items() if v is not None and len(v)}
    if not rets:
        return pd.DataFrame(), []
    df = pd.concat(rets, axis=1)
    if years:
        df = df[df.index >= df.index.max() - pd.DateOffset(years=int(years))]
    kept = list(df.columns)
    excluded: list[str] = []
    while kept:
        common = df[kept].dropna()
        if len(common) >= min_days or len(kept) == 1:
            break
        worst = min(kept, key=lambda c: df[c].notna().sum())
        kept.remove(worst)
        excluded.append(worst)
    if not kept:
        return pd.DataFrame(), list(rets)
    return df[kept].dropna(), excluded


def normalize_weights(weights: dict[str, float], cols) -> dict[str, float]:
    w = {c: max(float(weights.get(c, 0.0)), 0.0) for c in cols}
    tot = sum(w.values())
    return {c: v / tot for c, v in w.items()} if tot > 0 else {c: 1 / len(w) for c in w}


def portfolio_returns(df: pd.DataFrame, weights: dict[str, float]) -> pd.Series:
    """Constant-weight mix, rebalanced every day (a simple approximation of holding today's mix)."""
    w = normalize_weights(weights, df.columns)
    return (df * pd.Series(w)).sum(axis=1)


def risk_metrics(ret: pd.Series) -> dict | None:
    if ret is None or len(ret) < 30:
        return None
    eq = (1 + ret).cumprod()
    years = max((ret.index[-1] - ret.index[0]).days / 365.25, 1e-9)
    vol = float(ret.std() * np.sqrt(TRADING_DAYS))
    cagr = float(eq.iloc[-1] ** (1 / years) - 1) if eq.iloc[-1] > 0 else -1.0
    roll = (1 + ret).rolling(21).apply(np.prod, raw=True) - 1
    return {
        "cagr": cagr, "volatility": vol, "years": years, "total_return": float(eq.iloc[-1] - 1),
        "max_drawdown": float((eq / eq.cummax() - 1).min()),
        "sharpe": float(ret.mean() / ret.std() * np.sqrt(TRADING_DAYS)) if ret.std() > 0 else None,
        "worst_day": float(ret.min()), "worst_day_date": ret.idxmin(),
        "worst_month": float(roll.min()) if roll.notna().any() else None,
        "bad_day_5pct": float(ret.quantile(0.05)),
    }


def correlation(df: pd.DataFrame) -> pd.DataFrame:
    return df.corr()


def avg_pairwise_corr(corr: pd.DataFrame, weights: dict[str, float]) -> float | None:
    cols = list(corr.columns)
    if len(cols) < 2:
        return None
    w = normalize_weights(weights, cols)
    num = den = 0.0
    for i in cols:
        for j in cols:
            if i != j:
                num += w[i] * w[j] * float(corr.loc[i, j])
                den += w[i] * w[j]
    return num / den if den else None


def extreme_pairs(corr: pd.DataFrame) -> tuple[tuple[str, str, float] | None, tuple[str, str, float] | None]:
    """(most similar pair, least similar pair)."""
    cols = list(corr.columns)
    pairs = [(a, b, float(corr.loc[a, b])) for k, a in enumerate(cols) for b in cols[k + 1:]]
    if not pairs:
        return None, None
    return max(pairs, key=lambda x: x[2]), min(pairs, key=lambda x: x[2])


def diversification_ratio(df: pd.DataFrame, weights: dict[str, float]) -> float | None:
    """Weighted average of each holding's own volatility divided by the mix's volatility.
    1.0 = no benefit from mixing; higher = the holdings offset each other."""
    w = normalize_weights(weights, df.columns)
    pv = portfolio_returns(df, weights).std()
    if not pv or pv <= 0:
        return None
    return float(sum(w[c] * df[c].std() for c in df.columns) / pv)


def risk_contributions(df: pd.DataFrame, weights: dict[str, float]) -> pd.Series:
    """Each holding's share of the mix's total risk (they sum to 1)."""
    w = pd.Series(normalize_weights(weights, df.columns))
    cov = df.cov()
    marginal = cov.values @ w.values
    total = float(w.values @ marginal)
    if total <= 0:
        return pd.Series(w.values, index=w.index)
    return pd.Series(w.values * marginal / total, index=w.index)


def betas(df: pd.DataFrame, market: pd.Series) -> dict[str, float | None]:
    """Sensitivity of each holding to the market: a beta of 1.2 means about 12% down for a 10% market fall."""
    out: dict[str, float | None] = {}
    for c in df.columns:
        j = pd.concat([df[c], market], axis=1, join="inner").dropna()
        v = j.iloc[:, 1].var() if len(j) >= 60 else 0
        out[c] = float(j.iloc[:, 0].cov(j.iloc[:, 1]) / v) if v and v > 0 else None
    return out


def portfolio_beta(weights: dict[str, float], b: dict[str, float | None]) -> float | None:
    ok = {k: v for k, v in b.items() if v is not None}
    if not ok:
        return None
    w = normalize_weights(weights, ok.keys())
    return float(sum(w[k] * ok[k] for k in ok))


def stress_table(weights: dict[str, float], b: dict[str, float | None], shocks=(-10, -20, -30)) -> pd.DataFrame:
    """Estimated move of the mix for each market shock (%), plus each holding's contribution to it."""
    ok = {k: v for k, v in b.items() if v is not None}
    w = normalize_weights(weights, ok.keys()) if ok else {}
    rows = []
    for s in shocks:
        row = {"Market move %": float(s), "Your mix %": float(sum(w[k] * ok[k] for k in ok) * s) if ok else None}
        for k in ok:
            row[k] = float(w[k] * ok[k] * s)
        rows.append(row)
    return pd.DataFrame(rows)


def drawdown_episodes(ret: pd.Series, n: int = 3, min_depth: float = 0.05) -> list[dict]:
    """The n deepest falls from a peak: when it peaked, bottomed, and (if it did) got back."""
    if ret is None or len(ret) < 30:
        return []
    eq = (1 + ret).cumprod()
    peak = eq.cummax()
    dd = eq / peak - 1
    grp = (eq >= peak).cumsum()
    starts = list(dd.groupby(grp).head(1).index)
    out = []
    for k, (g, sub) in enumerate(dd.groupby(grp)):
        depth = float(sub.min())
        if depth > -min_depth:
            continue
        trough = sub.idxmin()
        recovered = starts[k + 1] if k + 1 < len(starts) else None
        out.append({"peak": sub.index[0], "trough": trough, "depth": depth, "recovered": recovered,
                    "days_down": int((trough - sub.index[0]).days),
                    "days_to_recover": int((recovered - trough).days) if recovered is not None else None})
    return sorted(out, key=lambda e: e["depth"])[:n]


def window_return(ret: pd.Series, start: str, end: str, slack_days: int = 7) -> float | None:
    """Compound return over a dated window, or None if the data doesn't cover it."""
    s, e = pd.Timestamp(start), pd.Timestamp(end)
    if ret is None or ret.empty or ret.index.min() > s + pd.Timedelta(days=slack_days) or ret.index.max() < e - pd.Timedelta(days=slack_days):
        return None
    w = ret[(ret.index > s) & (ret.index <= e)]
    return float((1 + w).prod() - 1) if len(w) else None


def history_table(port: pd.Series, market: pd.Series) -> list[dict]:
    rows = []
    for label, a, b in HISTORY_WINDOWS:
        p, m = window_return(port, a, b), window_return(market, a, b)
        if p is not None and m is not None:
            rows.append({"label": label, "start": a, "end": b, "mix": p, "market": m})
    return rows
