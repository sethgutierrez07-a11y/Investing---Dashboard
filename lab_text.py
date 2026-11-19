"""
Free, rule-based written summary for the Strategy Lab. No AI, no network, no Streamlit.

Turns the numbers on the page into plain sentences about THIS ticker and THIS rule:
what the rule does, what happened, the risk/return trade-off, what costs did, whether
luck can explain it, how the held-out period compared, and a plain verdict on the rule and on the stock itself.
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


def usd(x: float) -> str:
    return f"${x:,.0f}"


def md(text: str) -> str:
    """Streamlit renders $...$ as math, so dollar signs are escaped before going into markdown."""
    return text.replace("$", "\\$")


def rule_name(key: str, params: dict) -> str:
    if key == "trend":
        return f"The {params['window']}-day trend rule"
    if key == "momentum":
        return f"The {params['lookback']}-day momentum rule"
    return "Dollar-cost averaging"


def outcome(d_ret: float, d_dd: float) -> str:
    """One word for how the rule did against its yardstick. d_dd > 0 means a shallower worst drop."""
    r, d = 0.005, 0.02
    if d_ret >= r:
        return "win" if d_dd >= -d else "win_risky"
    if d_ret <= -r:
        return "safer" if d_dd > d else "lose"
    if d_dd > d:
        return "smoother"
    return "bumpier" if d_dd < -d else "tie"


def end_value(m: dict) -> float:
    return 10_000 * (1 + m["cagr"]) ** m["years"]


def stock_class(cagr: float, dd: float) -> tuple[str, str]:
    """(short description, one-sentence read) of the stock itself over the period."""
    if cagr < 0:
        return "a stock that lost money", "It lost money over the period, so any rule was working against a falling stock."
    if cagr < 0.03:
        return "a weak performer", ("Returns this low are in the range savings accounts or bond funds have paid at times, "
                                    "so holding it was not well rewarded.")
    if dd <= -0.4:
        word = "strong" if cagr >= 0.12 else "decent"
        return f"a {word} but volatile stock", f"The returns were real, but only for holders who could sit through a {pct(-dd, 0)} fall."
    if cagr >= 0.12:
        if dd > -0.3:
            return "a strong, fairly steady stock", "A strong stretch without a deep scare."
        return "a strong stock with real swings", f"Strong returns, with a {pct(-dd, 0)} fall along the way that tested patience."
    if cagr >= 0.08 and dd > -0.3:
        return "a solid, fairly steady stock", "A solid stretch without a deep scare."
    return "a solid, ordinary performer", "A decent stretch with the usual ups and downs."


def stock_lines(symbol: str, mb: dict, profile: dict | None) -> list[str]:
    years = mb["years"]
    out = [f"**How {symbol} held up:** it grew {pct(mb['cagr'])} a year over {years:.1f} years ({usd(end_value(mb))} from {usd(10_000)}), "
           f"with a worst drop of {pct(-mb['max_drawdown'])} and yearly swings of about {pct(mb['volatility'], 0)}."]
    if profile:
        bits = []
        if profile["longest_underwater_years"] >= 0.25:
            if profile["still_underwater"]:
                bits.append(f"it was below an earlier high for {profile['longest_underwater_years']:.1f} years and had not recovered by the end of the period")
            else:
                bits.append(f"its longest wait to get back to an earlier high was {profile['longest_underwater_years']:.1f} years")
        if profile["years_total"] >= 3:
            bits.append(f"it was up in {profile['years_up']} of {profile['years_total']} full calendar years "
                        f"(best {profile['best_year'][0]}: {profile['best_year'][1] * 100:+.0f}%, worst {profile['worst_year'][0]}: {profile['worst_year'][1] * 100:+.0f}%)")
        if bits:
            out.append("Along the way, " + "; ".join(bits) + ".")
    return out


def significance(out: str, p: float | None, n_trials: int, has_timing: bool, ms: dict, revealed: bool,
                 overfit_level: str | None) -> tuple[str, str]:
    """(full sentence(s), short clause for the 'in short' line)."""
    if not has_timing:
        return ("Nothing to test for luck here: this compares two ways of getting the same money in, so the gap is simply the "
                "price or the benefit of waiting.", "")
    if out in ("lose", "bumpier", "tie"):
        return ("The luck test is beside the point: a rule that did not help does not need explaining away.", "")
    from lab_lib import adjusted_threshold  # pure function; imported here to keep this module light

    if p is None:
        strength, text = "none", "There was not enough timing in this window to run the luck test."
    else:
        thr = adjusted_threshold(n_trials)
        if p <= thr and p <= 0.05:
            strength = "strong"
            text = f"The edge is unlikely to be luck: only {p * 100:.1f}% of random placements did as well" + (f", even after counting your {n_trials} tries" if n_trials > 1 else "") + "."
        elif p <= 0.2:
            strength = "suggestive"
            text = f"It is suggestive but not proven: {p * 100:.0f}% of random placements did as well, which luck produces often."
        else:
            strength = "none"
            text = f"Luck can explain it: {p * 100:.0f}% of random placements did as well or better."
    if out in ("safer", "smoother"):
        lead = "The smoother ride is built in, because the rule steps aside during falls, so it is real for this history. "
        if p is None:
            text = lead + "There was not enough timing in this window to say whether the timing itself was skilful."
        elif strength == "strong":
            text = (lead + f"The timing also beat chance: only {p * 100:.1f}% of random placements with the same in-and-out pattern did as well. "
                    "It avoided bad stretches better than luck would, but it still earned less than simply holding.")
        elif strength == "suggestive":
            text = lead + f"Its timing looks somewhat better than random ({p * 100:.0f}% of random placements did as well), though luck does that often."
        else:
            text = (lead + f"Its timing was no better than random ({p * 100:.0f}% of random placements did as well), "
                    "so the safety comes from being out of the market at all, not from picking good moments.")
        short = {"strong": "its timing beat chance but not holding", "suggestive": "its timing is only suggestively better than chance",
                 "none": "the safety comes from being out of the market, not from good timing"}[strength]
    else:
        short = None
    extra = []
    if "trades" in ms and ms["trades"] < 10:
        extra.append(f"With only {ms['trades']} trades this is a small sample.")
    if ms["years"] < 5:
        extra.append(f"It covers just {ms['years']:.1f} years.")
    if revealed and overfit_level == "good":
        extra.append("On the held-out data it held up.")
    elif revealed and overfit_level == "warn":
        extra.append("On the held-out data the edge faded or vanished, which weakens the case.")
    elif not revealed:
        extra.append("The held-out period is still sealed, so this is training-period evidence only.")
    if short is None:
        short = {"strong": "the edge looks real rather than luck", "suggestive": "the evidence is suggestive, not proven",
                 "none": "luck can explain it"}[strength]
    return " ".join([text] + extra), short


HEADLINES = {
    "win": "{rn} beat {bench} on {symbol}.",
    "win_risky": "{rn} earned more than {bench} on {symbol}, but with deeper drops.",
    "safer": "{rn} traded return for a smoother ride on {symbol}.",
    "lose": "{rn} did not beat {bench} on {symbol}.",
    "smoother": "{rn} matched {bench} on {symbol} with a smoother ride.",
    "bumpier": "{rn} matched {bench} on return on {symbol} but with bigger drops.",
    "tie": "{rn} and {bench} came out about the same on {symbol}.",
}


def takeaway(symbol, key, params, benchmark_name, ms, mb, p, n_trials, revealed, overfit_level, has_timing, profile=None) -> list[str]:
    d_ret = ms["cagr"] - mb["cagr"]
    d_dd = ms["max_drawdown"] - mb["max_drawdown"]
    rn, bench = rule_name(key, params), benchmark_name.lower()
    out_code = outcome(d_ret, d_dd)
    headline = HEADLINES[out_code].format(rn=rn, bench=bench, symbol=symbol)
    sig_text, sig_short = significance(out_code, p, n_trials, has_timing, ms, revealed, overfit_level)
    descr, read = stock_class(mb["cagr"], mb["max_drawdown"])

    a, b = usd(end_value(ms)), usd(end_value(mb))
    drops = f"{pct(-ms['max_drawdown'])} against {pct(-mb['max_drawdown'])}"
    numbers = {
        "win": f"{usd(10_000)} became {a} with the rule against {b} for {bench} ({pct(ms['cagr'])} against {pct(mb['cagr'])} a year), and the worst drop was {drops}.",
        "win_risky": f"{usd(10_000)} became {a} against {b}, but the worst drop was {drops}: the extra return came with extra pain.",
        "safer": f"{usd(10_000)} became {a} with the rule against {b} for {bench}, giving up {abs(d_ret) * 100:.1f} points a year. In exchange the worst drop was {drops}.",
        "lose": f"{usd(10_000)} became {a} with the rule against {b} for {bench}, and the worst drop was {drops}, so it was not safer either.",
        "smoother": f"Both turned {usd(10_000)} into about {a}, but the worst drop was {drops}.",
        "bumpier": f"Both turned {usd(10_000)} into about {a}, but the worst drop was {drops}, so the rule only added risk.",
        "tie": f"{usd(10_000)} became {a} against {b}, with worst drops of {drops}. There is no meaningful gap to explain.",
    }[out_code]

    short = f"**In short:** {headline}" + (f" {sig_short[0].upper() + sig_short[1:]}." if sig_short else "") + f" {symbol} itself was {descr} over this period."
    lines = [short, f"**The outcome:** {numbers}", f"**Does it matter?** {sig_text}"]
    lines += stock_lines(symbol, mb, profile)
    context = read
    if out_code in ("win", "safer", "smoother") and mb["max_drawdown"] <= -0.35:
        context += " It also had a deep fall for the rule to sidestep, which is what rules like this exist for."
    elif out_code in ("safer", "lose") and mb["cagr"] >= 0.12:
        context += " A stock that climbs like this is hard for any sit-out rule to beat, because every day in cash misses gains."
    lines.append(f"**The read on {symbol}:** {context}")
    lines.append("Hypothetical results on historical data from the training period shown; past performance does not predict the future. Educational, not advice.")
    return lines


def write_summary(
    *, symbol, key, label, params, cost_bps, source, start, end, split, train_pct, benchmark_name,
    ms, mb, cagr_no_cost, luck, luck_text, n_trials, has_timing, revealed, overfit=None, ms_test=None, mb_test=None,
    profile=None,
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
    sections.append(("Takeaway", takeaway(symbol, key, params, benchmark_name, ms, mb, (luck or {}).get("p_value"), n_trials,
                                          revealed, overfit[0] if overfit else None, has_timing, profile)))
    return [(t, b) for t, b in sections if b]
