"""
Free, rule-based written summary for the Strategy Lab. No AI, no network, no Streamlit.

Turns the numbers on the page into plain sentences about THIS ticker and THIS rule:
what the rule does, what happened, the risk/return trade-off, what costs did, whether
luck can explain it, how the held-out period compared, and what to try next.
"""

from __future__ import annotations

Section = tuple[str, list[str]]


def pts(x: float, d: int = 1) -> str:
    return f"{x * 100:+.{d}f} points"


def pct(x: float, d: int = 1) -> str:
    return f"{x * 100:.{d}f}%"


def describe_rule(key: str, symbol: str, params: dict, cost_bps: float) -> str:
    if key == "trend":
        w = params["window"]
        return (f"Hold {symbol} only while its price is above its {w}-day average (about {w / 21:.0f} months of trading). "
                f"When it falls below, sit in cash. The signal is read after each close and acted on at the next close.")
    if key == "momentum":
        n = params["lookback"]
        return (f"Hold {symbol} only while its price is higher than it was {n} trading days (about {n / 21:.0f} months) ago; "
                f"otherwise sit in cash. The signal is read after each close and acted on at the next close.")
    return (f"Split the same money into equal parts and buy {symbol} on the first trading day of every month, "
            f"compared with buying it all on day one. Money waiting to be invested sits in cash earning nothing.")


def setup_section(symbol, key, params, cost_bps, source, start, end, split, train_pct, benchmark_name) -> list[str]:
    return [
        f"**The rule:** {describe_rule(key, symbol, params, cost_bps)}",
        f"**The yardstick:** {benchmark_name.lower()}. Every number is shown next to it, because a rule only matters if it beats doing nothing clever.",
        f"**The data:** {symbol}, {start:%b %Y} to {end:%b %Y}, from {source}. Only the first {train_pct}% (to {split:%b %Y}) is used below; "
        f"the rest is held out for the final test.",
        f"**Costs:** {cost_bps:g} basis points ({cost_bps / 100:.2f}%) charged on each buy or sell.",
    ]


def what_happened(symbol, key, ms: dict, mb: dict, benchmark_name) -> list[str]:
    out = []
    d_ret = ms["cagr"] - mb["cagr"]
    d_dd = ms["max_drawdown"] - mb["max_drawdown"]          # positive = shallower drop
    out.append(
        f"**Return:** the rule grew {pct(ms['cagr'])} a year against {pct(mb['cagr'])} for {benchmark_name.lower()} "
        f"({pts(d_ret)} a year)."
    )
    out.append(
        f"**Worst drop:** {pct(-ms['max_drawdown'])} from a peak, against {pct(-mb['max_drawdown'])}. "
        f"That is {'shallower' if d_dd > 0.005 else 'deeper' if d_dd < -0.005 else 'about the same'}"
        + (f" by {abs(d_dd) * 100:.0f} points." if abs(d_dd) > 0.005 else ".")
    )
    ahead_ret, ahead_dd = d_ret > 0.002, d_dd > 0.02
    if ahead_ret and ahead_dd:
        verdict = "It beat the yardstick on both return and risk. That is rare and worth being suspicious of: check the luck test and the held-out period before believing it."
    elif not ahead_ret and ahead_dd:
        kept = f"{ms['cagr'] / mb['cagr'] * 100:.0f}% of the return" if mb["cagr"] > 0 and ms["cagr"] > 0 else "some of the return"
        verdict = (f"This is a **trade, not a free lunch**: it kept {kept} while making the worst fall "
                   f"{abs(d_dd) * 100:.0f} points shallower. Whether that is worth it depends on whether you would really have held through the yardstick's worst stretch.")
    elif ahead_ret and not ahead_dd:
        verdict = "It earned more but did not fall less, so the extra return came with at least as much pain. That points to taking more risk, not being smarter."
    else:
        verdict = f"It was **worse on return and no better on risk** than {benchmark_name.lower()}. On this ticker and period, simply holding was the better plan."
    out.append(verdict)
    if ms.get("sharpe") is not None and mb.get("sharpe") is not None:
        better = ms["sharpe"] > mb["sharpe"] + 0.05
        worse = ms["sharpe"] < mb["sharpe"] - 0.05
        out.append(
            f"**Return per unit of risk (Sharpe):** {ms['sharpe']:.2f} against {mb['sharpe']:.2f}. "
            + ("The rule was more efficient with the risk it took." if better else "The rule was less efficient with its risk." if worse else "About the same efficiency.")
        )
    return out


def costs_and_activity(key, ms: dict, cagr_no_cost: float | None, cost_bps, years: float) -> list[str]:
    out = []
    if "trades" in ms:
        per_year = ms["trades"] / years if years else 0
        out.append(f"**Activity:** {ms['trades']} trades in {years:.1f} years (about {per_year:.1f} a year), invested {pct(ms['time_invested'], 0)} of the time.")
        if ms["time_invested"] < 0.6:
            out.append("It spent a lot of time in cash. Cash earns nothing here, so every day out of the market is a day the rule had to be right to break even.")
    if cagr_no_cost is not None:
        drag = cagr_no_cost - ms["cagr"]
        if drag >= 0.003:
            out.append(f"**Cost drag:** with zero costs the rule would have earned {pct(cagr_no_cost)} a year instead of {pct(ms['cagr'])}, so costs took {pts(drag).replace('+', '')} a year.")
        else:
            out.append(f"**Cost drag:** small. With zero costs the result would be {pct(cagr_no_cost)} a year, close to the {pct(ms['cagr'])} shown.")
    if key == "dca":
        out.append("**Why DCA usually trails in a rising market:** the money waiting to be invested misses gains while it sits in cash. "
                   "Its benefit is a gentler entry and less regret if prices fall right after you start, not a higher expected return.")
    return out


def luck_section(p: float | None, level_text: str, observed, median_random, n_trials: int, has_timing: bool, dd_benefit: bool = False) -> list[str]:
    if not has_timing:
        return ["Dollar-cost averaging has no market timing to test, so there is no luck test. The comparison with investing on day one is the whole story."]
    out = [level_text]
    if p is not None and observed is not None and median_random is not None:
        out.append(f"For scale: the rule's timing earned {pct(observed)} a year before costs, while a typical random placement of the same in-and-out pattern earned {pct(median_random)}.")
    if dd_benefit and (p is None or p > 0.05):
        out.append("The luck test asks whether the timing earned extra return. It does not judge the shallower worst drop, which comes from sitting in cash "
                   "during falls by design; that benefit is real in this history but is a different question.")
    if n_trials > 1:
        out.append(f"You have looked at {n_trials} variations. Each extra try makes a lucky-looking result more likely, which is why the bar for believing it rises.")
    return out


def held_out_section(note_text: str, ms_test: dict | None, mb_test: dict | None, benchmark_name) -> list[str]:
    out = [note_text]
    if ms_test and mb_test:
        out.append(
            f"In the held-out period the rule returned {pct(ms_test['cagr'])} a year against {pct(mb_test['cagr'])}, "
            f"with a worst drop of {pct(-ms_test['max_drawdown'])} against {pct(-mb_test['max_drawdown'])}."
        )
    out.append("This is one test on one stretch of history. A rule that passes it has earned more trust, not certainty.")
    return out


def takeaway(symbol, key, ms, mb, p, n_trials, revealed, overfit_level, has_timing) -> list[str]:
    d_ret = ms["cagr"] - mb["cagr"]
    d_dd = ms["max_drawdown"] - mb["max_drawdown"]
    out = []
    if d_ret <= 0.002 and d_dd <= 0.02:
        out.append(f"**Bottom line:** on {symbol} over this period, the rule did not earn its complexity. Holding was at least as good, and that is a legitimate and common result.")
    elif d_ret <= 0.002 and d_dd > 0.02:
        out.append("**Bottom line:** the rule is a risk-management tool here rather than a return booster. Judge it on whether the smoother ride is worth the lower return.")
    else:
        weak_luck = has_timing and (p is None or p > 0.05)
        if weak_luck:
            out.append("**Bottom line:** it earned more, but the luck test cannot separate that from chance. Treat it as an interesting lead, not a finding.")
        else:
            out.append("**Bottom line:** it earned more and the timing looks better than chance on this period. The next question is whether that survives other tickers and fresh data.")
    if revealed and overfit_level == "warn":
        out.append("The held-out period weakened the case. That is the test doing its job.")
    steps = [
        "Run the same rule on two or three other tickers. A real effect usually shows up beyond one.",
        "Nudge the setting up and down a bit. If the result swings wildly, it was fitted to one lucky number.",
        "Raise the trading cost to 25 bps to see whether the edge survives realistic friction.",
    ]
    if not revealed and has_timing:
        steps.append("When you are settled on the rule, reveal the held-out period once. Do not tune after peeking.")
    out.append("**What to try next:** " + " ".join(f"({i}) {s}" for i, s in enumerate(steps, 1)))
    out.append("Hypothetical results on historical data; past performance does not predict the future. Educational, not advice.")
    return out


def write_summary(
    *, symbol, key, label, params, cost_bps, source, start, end, split, train_pct, benchmark_name,
    ms, mb, cagr_no_cost, luck, luck_text, n_trials, has_timing, revealed, overfit=None, ms_test=None, mb_test=None,
) -> list[Section]:
    years = ms["years"]
    sections: list[Section] = [
        ("The setup", setup_section(symbol, key, params, cost_bps, source, start, end, split, train_pct, benchmark_name)),
        ("What happened", what_happened(symbol, key, ms, mb, benchmark_name)),
        ("Costs & activity", costs_and_activity(key, ms, cagr_no_cost, cost_bps, years)),
        ("Is it luck?", luck_section((luck or {}).get("p_value"), luck_text, (luck or {}).get("observed"),
                                     (luck or {}).get("median_random"), n_trials, has_timing,
                                     dd_benefit=(ms["max_drawdown"] - mb["max_drawdown"]) > 0.02)),
    ]
    if revealed and overfit:
        sections.append(("Held-out test", held_out_section(overfit[1], ms_test, mb_test, benchmark_name)))
    sections.append(("Takeaway", takeaway(symbol, key, ms, mb, (luck or {}).get("p_value"), n_trials, revealed,
                                          overfit[0] if overfit else None, has_timing)))
    return [(t, b) for t, b in sections if b]
