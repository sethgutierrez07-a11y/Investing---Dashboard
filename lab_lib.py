"""
Strategy Lab engine. Pure pandas/numpy: no Streamlit, no network.

Design rules that keep a backtest honest:
  * No look-ahead: a signal is computed from data up to today's close, and the trade
    happens at the NEXT close (lag_days=1), so a rule never trades on a price it
    could not have seen yet.
  * Costs are charged on every position change, in basis points of the amount traded.
  * Indicators use the full history (they are causal), but results are always
    reported on a window, so a training period and a held-out period can be compared.
  * "Is it luck?" asks whether the rule's *timing* beat the same exposure placed at
    random times, not whether the market went up.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np
import pandas as pd

TRADING_DAYS = 252
START_CAPITAL = 10_000.0


# --------------------------------------------------------------------------
# Signals -> positions
# --------------------------------------------------------------------------
def trend_signal(prices: pd.Series, window: int = 200) -> pd.Series:
    """1 when the price is above its `window`-day average, else 0 (cash)."""
    sma = prices.rolling(window).mean()
    return (prices > sma).astype(float).where(sma.notna(), 0.0)


def momentum_signal(prices: pd.Series, lookback: int = 126) -> pd.Series:
    """1 when the price is higher than it was `lookback` days ago, else 0."""
    past = prices.shift(lookback)
    return (prices > past).astype(float).where(past.notna(), 0.0)


def to_positions(signal: pd.Series, lag_days: int = 1) -> pd.Series:
    """Position held on each day. Signal known after day t's close, traded at day t+lag's close,
    so it first earns the return of day t+lag+1."""
    return signal.shift(1 + lag_days).fillna(0.0)


# --------------------------------------------------------------------------
# Running a strategy
# --------------------------------------------------------------------------
@dataclass
class Run:
    name: str
    returns: pd.Series      # daily strategy returns, net of costs
    positions: pd.Series | None   # None for strategies that aren't in/out (DCA)
    equity: pd.Series       # growth of START_CAPITAL


def _equity(ret: pd.Series) -> pd.Series:
    return START_CAPITAL * (1 + ret).cumprod()


def run_positions(prices: pd.Series, positions: pd.Series, cost_bps: float, name: str) -> Run:
    ret = prices.pct_change().fillna(0.0)
    turnover = positions.diff().abs()
    turnover.iloc[0] = abs(positions.iloc[0])
    net = positions * ret - turnover * cost_bps / 10_000
    return Run(name, net, positions, _equity(net))


def run_buy_hold(prices: pd.Series, cost_bps: float = 0.0) -> Run:
    return run_positions(prices, pd.Series(1.0, index=prices.index), cost_bps, "Buy and hold")


def run_trend(prices, window=200, cost_bps=10.0, lag_days=1) -> Run:
    return run_positions(prices, to_positions(trend_signal(prices, window), lag_days), cost_bps, f"Trend ({window}-day average)")


def run_momentum(prices, lookback=126, cost_bps=10.0, lag_days=1) -> Run:
    return run_positions(prices, to_positions(momentum_signal(prices, lookback), lag_days), cost_bps, f"Momentum ({lookback}-day)")


def run_lump_sum(prices: pd.Series, cost_bps: float = 0.0) -> Run:
    """All the money in on day one (the baseline DCA is compared against)."""
    r = run_buy_hold(prices, cost_bps)
    return Run("Lump sum on day one", r.returns, None, r.equity)


def run_dca(prices: pd.Series, cost_bps: float = 10.0) -> Run:
    """Same total money, but invested in equal parts on the first trading day of each month.
    Money not yet invested sits in cash earning 0 (the usual simple assumption)."""
    months = prices.index.to_period("M")
    buy_days = prices.groupby(months).head(1).index
    n = len(buy_days)
    part = START_CAPITAL / n
    shares = 0.0
    cash = START_CAPITAL
    values = []
    buy_set = set(buy_days)
    for day, px in prices.items():
        if day in buy_set:
            spend = min(part, cash)
            shares += spend * (1 - cost_bps / 10_000) / px
            cash -= spend
        values.append(cash + shares * px)
    eq = pd.Series(values, index=prices.index)
    return Run("Dollar-cost averaging", eq.pct_change().fillna(0.0), None, eq)


# --------------------------------------------------------------------------
# Metrics
# --------------------------------------------------------------------------
def window_returns(ret: pd.Series, start=None, end=None) -> pd.Series:
    r = ret
    if start is not None:
        r = r[r.index >= pd.Timestamp(start)]
    if end is not None:
        r = r[r.index < pd.Timestamp(end)]
    return r


def metrics(ret: pd.Series, positions: pd.Series | None = None) -> dict | None:
    """Headline stats for a window of daily returns (None if too short to mean anything)."""
    if ret is None or len(ret) < 30:
        return None
    eq = (1 + ret).cumprod()
    years = max((ret.index[-1] - ret.index[0]).days / 365.25, 1e-9)
    total = float(eq.iloc[-1] - 1)
    cagr = float(eq.iloc[-1] ** (1 / years) - 1) if eq.iloc[-1] > 0 else -1.0
    vol = float(ret.std() * np.sqrt(TRADING_DAYS))
    sharpe = float(ret.mean() / ret.std() * np.sqrt(TRADING_DAYS)) if ret.std() > 0 else None
    dd = eq / eq.cummax() - 1
    out = {
        "total_return": total, "cagr": cagr, "volatility": vol, "sharpe": sharpe,
        "max_drawdown": float(dd.min()), "years": years,
    }
    if positions is not None:
        p = positions.reindex(ret.index).fillna(0.0)
        out["time_invested"] = float(p.mean())
        out["trades"] = int((p.diff().abs().fillna(0) > 0).sum())
    return out


def stock_profile(ret: pd.Series | None) -> dict | None:
    """How the stock itself behaved over a window of daily returns: calendar-year record and
    how long it spent below an earlier high. Only years with ~a full year of data count."""
    if ret is None or len(ret) < 120:
        return None
    eq = (1 + ret).cumprod()
    dd = eq / eq.cummax() - 1
    yearly = {}
    for y, r in ret.groupby(ret.index.year):
        if len(r) >= 200:
            yearly[int(y)] = float((1 + r).prod() - 1)
    below = dd < 0
    longest, longest_open = 0.0, False
    if below.any():
        grp = (~below).cumsum()
        days = pd.Series(ret.index, index=ret.index)[below]
        for _, d in days.groupby(grp[below]):
            span = (d.iloc[-1] - d.iloc[0]).days / 365.25
            if span >= longest:
                longest, longest_open = span, bool(d.iloc[-1] == ret.index[-1])
    out = {"years_total": len(yearly), "years_up": sum(1 for v in yearly.values() if v > 0),
           "best_year": None, "worst_year": None, "longest_underwater_years": float(longest),
           "still_underwater": bool(longest_open), "from_peak": float(dd.iloc[-1])}
    if yearly:
        out["best_year"] = max(yearly.items(), key=lambda kv: kv[1])
        out["worst_year"] = min(yearly.items(), key=lambda kv: kv[1])
    return out


def drawdown(ret: pd.Series) -> pd.Series:
    eq = (1 + ret).cumprod()
    return eq / eq.cummax() - 1


def split_date(index: pd.DatetimeIndex, train_frac: float) -> pd.Timestamp:
    """First day of the held-out period."""
    k = int(len(index) * min(max(train_frac, 0.1), 0.95))
    return index[min(k, len(index) - 1)]


# --------------------------------------------------------------------------
# "Is it luck?"
# --------------------------------------------------------------------------
def timing_luck_test(positions: pd.Series, returns: pd.Series, n_sims: int = 2000, seed: int = 0, min_shift: int = 21) -> dict | None:
    """Did the rule's TIMING beat the same pattern of in/out days placed at random?

    The in/out pattern is circularly shifted against the returns (keeps how long and how
    clustered the rule was invested) and the average daily gross return is recomputed each
    time. p = share of random placements that did at least as well as the real one.
    """
    pos = positions.reindex(returns.index).fillna(0.0).to_numpy()
    ret = returns.to_numpy()
    n = len(ret)
    if n < 4 * min_shift or pos.std() == 0:
        return {"p_value": None, "reason": "no_timing" if n >= 4 * min_shift else "too_short"}
    observed = float((pos * ret).mean() * TRADING_DAYS)
    rng = np.random.default_rng(seed)
    shifts = rng.integers(min_shift, n - min_shift, size=n_sims)
    sims = np.array([(np.roll(pos, int(s)) * ret).mean() * TRADING_DAYS for s in shifts])
    p = float((1 + (sims >= observed).sum()) / (1 + n_sims))
    return {"p_value": p, "observed": observed, "sims": sims, "percentile": float((sims < observed).mean() * 100),
            "median_random": float(np.median(sims)), "reason": None}


def chance_of_false_hit(trials: int, alpha: float = 0.05) -> float:
    """If you try `trials` independent ideas that are all pure luck, the chance at least one looks significant."""
    return 1 - (1 - alpha) ** max(trials, 1)


def adjusted_threshold(trials: int, alpha: float = 0.05) -> float:
    """Bonferroni: the p-value a result must beat after `trials` tries."""
    return alpha / max(trials, 1)


def luck_verdict(p: float | None, trials: int, reason: str | None = None) -> tuple[str, str]:
    """(level, plain-English sentence). level is one of good / warn / neutral."""
    if p is None:
        if reason == "no_timing":
            return "neutral", "This rule was invested the whole time (or never), so there is no timing to test."
        return "neutral", "Not enough history in this window to run the test."
    thr = adjusted_threshold(trials)
    if p <= thr and p <= 0.05:
        return "good", (f"Only {p * 100:.1f}% of random placements did as well, which clears the bar even after counting your "
                        f"{trials} tr{'y' if trials == 1 else 'ies'}. That is evidence the timing helped, not proof it will keep working.")
    if p <= 0.05:
        return "warn", (f"{p * 100:.1f}% of random placements did as well. That looks significant on its own, but you have tried "
                        f"{trials} variations, so you need p ≤ {thr * 100:.2f}% to take it seriously.")
    if p <= 0.2:
        return "warn", f"{p * 100:.0f}% of random placements did as well. Suggestive, but that is well within what luck produces."
    return "neutral", f"{p * 100:.0f}% of random placements did as well or better. Nothing here beats luck."


# --------------------------------------------------------------------------
# Strategy registry (the page builds its controls from this)
# --------------------------------------------------------------------------
@dataclass
class Strategy:
    key: str
    label: str
    blurb: str
    params: list[tuple[str, str, int, int, int, int]]  # key, label, min, max, default, step
    run: Callable[..., Run]
    has_timing: bool = True


STRATEGIES = {
    "trend": Strategy(
        "trend", "Trend following",
        "Hold while the price is above its long-term average; sit in cash when it is below. Aims to dodge big drawdowns.",
        [("window", "Average length (days)", 20, 300, 200, 10)], lambda p, window, cost_bps: run_trend(p, window, cost_bps)),
    "momentum": Strategy(
        "momentum", "Momentum",
        "Hold while the price is higher than it was N days ago; otherwise cash. Bets that recent winners keep winning.",
        [("lookback", "Look-back (days)", 20, 300, 126, 10)], lambda p, lookback, cost_bps: run_momentum(p, lookback, cost_bps)),
    "dca": Strategy(
        "dca", "Dollar-cost averaging",
        "Invest equal amounts on the first trading day of every month, compared with investing everything on day one.",
        [], lambda p, cost_bps: run_dca(p, cost_bps), has_timing=False),
}


def run_strategy(key: str, prices: pd.Series, params: dict, cost_bps: float) -> Run:
    s = STRATEGIES[key]
    return s.run(prices, cost_bps=cost_bps, **{k: params[k] for k, *_ in s.params})


# --------------------------------------------------------------------------
# Presentation helpers (pure, tested)
# --------------------------------------------------------------------------
def rebased_equity(ret: pd.Series) -> pd.Series:
    """Growth of START_CAPITAL over just this window of returns."""
    return START_CAPITAL * (1 + ret).cumprod()


def _p(x, d=1):
    return "n/a" if x is None else f"{x * 100:+.{d}f}%"


def metrics_table(cols: dict[str, dict | None]) -> pd.DataFrame:
    """One column per series, one row per measure, everything pre-formatted for display."""
    rows = [
        ("Yearly return (CAGR)", lambda m: _p(m["cagr"])),
        ("Total return", lambda m: _p(m["total_return"], 0)),
        ("Worst drop from a peak", lambda m: f"{m['max_drawdown'] * 100:.1f}%"),
        ("Yearly volatility", lambda m: f"{m['volatility'] * 100:.1f}%"),
        ("Return per unit of risk (Sharpe)", lambda m: "n/a" if m["sharpe"] is None else f"{m['sharpe']:.2f}"),
        ("Time invested", lambda m: f"{m['time_invested'] * 100:.0f}%" if "time_invested" in m else "—"),
        ("Trades", lambda m: f"{m['trades']}" if "trades" in m else "—"),
    ]
    data = {name: [(fn(m) if m else "too short") for _, fn in rows] for name, m in cols.items()}
    return pd.DataFrame(data, index=[r[0] for r in rows])


def overfit_note(train_s: dict | None, train_b: dict | None, test_s: dict | None, test_b: dict | None) -> tuple[str, str]:
    """Compare the rule's edge over buy-and-hold before and after the held-out date. Returns (level, text)."""
    if not all([train_s, train_b, test_s, test_b]):
        return "neutral", "The held-out period is too short to judge."
    e_train = train_s["cagr"] - train_b["cagr"]
    e_test = test_s["cagr"] - test_b["cagr"]
    dd_better = test_s["max_drawdown"] > test_b["max_drawdown"] + 0.02
    head = f"Edge over buy-and-hold: {e_train * 100:+.1f} points a year in training, {e_test * 100:+.1f} in the held-out period."
    if e_train <= 0:
        return "neutral", head + " There was no edge in training to confirm, so this is a rule that did not help even on the data it was tuned on."
    if e_test <= 0:
        extra = " It did make the worst drop shallower, which may be all it was ever good for." if dd_better else ""
        return "warn", head + " The edge disappeared on data the rule never saw, the classic sign of fitting the past." + extra
    if e_test < e_train * 0.5:
        return "warn", head + " Most of the edge faded on fresh data. Treat the training result as flattering."
    return "good", head + " It held up on fresh data, which is encouraging. One held-out period is still only one test, not a guarantee."
