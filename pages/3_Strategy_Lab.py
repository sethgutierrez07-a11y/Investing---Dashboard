"""
Strategy Lab: test a simple rule on past prices, honestly.

Nothing here touches your accounts; it only needs a ticker. Prices come from Yahoo Finance
(via yfinance). Optional secret: TWELVEDATA_API_KEY (free) as a backup source.

What keeps it honest: trades happen the day AFTER a signal, costs are charged, the later
part of history is held out until you choose to look, a "random timing" test asks whether
the rule beat luck, and a counter tracks how many variations you have tried.
"""

import streamlit as st

import lab_charts as lc
import lab_lib as lab
import price_data as pdx

st.set_page_config(page_title="Strategy Lab", layout="wide")

CHART_CFG = {"displayModeBar": False}


def secret(name: str):
    try:
        return st.secrets[name]
    except Exception:
        return None


def theme_mode() -> str:
    try:
        return "light" if st.context.theme.type == "light" else "dark"
    except Exception:
        return "dark"


@st.cache_data(ttl=6 * 3600, show_spinner="Loading price history…")
def history(symbol: str, twelve_key):
    return pdx.load_history(symbol, twelve_key)


mode = theme_mode()
st.title("🧪 Strategy Lab")
st.caption(
    "Test a simple trading rule on past prices, and find out whether it beat luck. Hypothetical results on historical data: "
    "no real trades, and past performance does not predict the future. Educational, not advice."
)

# ---------- Controls ----------
with st.sidebar:
    st.header("Lab settings")
    symbol = st.text_input("Ticker", value="SPY", help="A stock or ETF, e.g. SPY, VOO, AAPL.").strip().upper()
    key = st.selectbox("Strategy", list(lab.STRATEGIES), format_func=lambda k: lab.STRATEGIES[k].label)
    strat = lab.STRATEGIES[key]
    st.caption(strat.blurb)
    params = {}
    for pkey, label, lo, hi, default, step in strat.params:
        params[pkey] = st.slider(label, lo, hi, default, step)
    cost_bps = st.slider("Trading cost (basis points per trade)", 0, 50, 10, 5,
                         help="10 bps = 0.10% of the amount traded each time you buy or sell. Covers spread and slippage.")
    train_pct = st.slider("Training period (% of history)", 50, 90, 70, 5,
                          help="The rest is held out until you choose to look at it.")
    uploaded = st.file_uploader("Or use your own prices (CSV)", type="csv",
                                help="Needs a Date column and a Close or Adj Close column. Handy if the price sources are down.")
    if st.button("Reset trial counter and held-out lock"):
        st.session_state["lab_trials"] = set()
        st.session_state["lab_revealed"] = set()
        st.rerun()

if not symbol and uploaded is None:
    st.info("Enter a ticker in the sidebar.")
    st.stop()

# ---------- Data ----------
try:
    if uploaded is not None:
        prices = pdx.require_enough(pdx.parse_csv(uploaded.getvalue()), "your file")
        source, problems = "Your uploaded CSV", []
        symbol = f"CSV:{uploaded.name}"
    else:
        prices, source, problems = history(symbol, secret("TWELVEDATA_API_KEY"))
except pdx.PriceDataError as e:
    st.error(f"Couldn't get price history for {symbol or 'that file'}. {e}")
    st.info(
        "Try another ticker, wait a minute (free price sources rate-limit), or upload a CSV in the sidebar "
        "(Yahoo Finance's Historical Data tab has a Download button). A free `TWELVEDATA_API_KEY` in Secrets adds a backup source."
    )
    st.stop()

# ---------- Run ----------
run = lab.run_strategy(key, prices, params, cost_bps)
bench = lab.run_lump_sum(prices, cost_bps) if key == "dca" else lab.run_buy_hold(prices, cost_bps)
split = lab.split_date(prices.index, train_pct / 100)

# Track every distinct setup you look at: the more you try, the likelier your best one is luck.
trial_id = (symbol, key, tuple(sorted(params.items())), cost_bps, train_pct)
trials = st.session_state.setdefault("lab_trials", set())
trials.add(trial_id)
n_trials = len(trials)
revealed = symbol in st.session_state.setdefault("lab_revealed", set())

train_s, train_b = lab.window_returns(run.returns, end=split), lab.window_returns(bench.returns, end=split)
test_s, test_b = lab.window_returns(run.returns, start=split), lab.window_returns(bench.returns, start=split)
m_train_s, m_train_b = lab.metrics(train_s, run.positions), lab.metrics(train_b)
m_test_s, m_test_b = lab.metrics(test_s, run.positions), lab.metrics(test_b)

st.markdown(
    f"**{symbol}** · {prices.index[0]:%b %Y} to {prices.index[-1]:%b %Y} · {len(prices):,} trading days · source: {source}. "
    f"Training period: {prices.index[0]:%b %Y} to {split:%b %Y} ({train_pct}%)."
)
for p in problems:
    st.caption(f"Note: {p}")
if "split-adjusted" in source:
    st.warning("This source leaves out dividends, so every result (including buy-and-hold) is understated for dividend payers.")

# ---------- Results on the training period ----------
st.subheader("How it did on the training period")
if m_train_s is None or m_train_b is None:
    st.warning("Not enough history in the training window. Use a longer history or a larger training share.")
    st.stop()

k1, k2, k3 = st.columns(3)
k1.metric("Yearly return", lab.metrics_table({"s": m_train_s}).loc["Yearly return (CAGR)", "s"],
          delta=f"{(m_train_s['cagr'] - m_train_b['cagr']) * 100:+.1f} pts vs {bench.name.lower()}", delta_color="normal")
k2.metric("Worst drop", f"{m_train_s['max_drawdown'] * 100:.1f}%",
          delta=f"{(m_train_s['max_drawdown'] - m_train_b['max_drawdown']) * 100:+.1f} pts vs {bench.name.lower()}", delta_color="normal",
          help="The biggest fall from a peak. A smaller (less negative) number means a smoother ride.")
k3.metric("Return per unit of risk", lab.metrics_table({"s": m_train_s}).loc["Return per unit of risk (Sharpe)", "s"],
          help="Sharpe ratio, with a 0% risk-free rate. Higher is better; above 1 is good.")

with st.container(border=True):
    st.plotly_chart(
        lc.equity_chart({run.name: lab.rebased_equity(train_s), bench.name: lab.rebased_equity(train_b)}, mode),
        width="stretch", config=CHART_CFG,
    )
    st.caption(f"Growth of a hypothetical ${lab.START_CAPITAL:,.0f}, after {cost_bps} bps trading costs.")

with st.expander("Side-by-side numbers and drawdowns"):
    st.dataframe(lab.metrics_table({run.name: m_train_s, bench.name: m_train_b}), width="stretch")
    st.plotly_chart(lc.drawdown_chart({run.name: lab.drawdown(train_s), bench.name: lab.drawdown(train_b)}, mode),
                    width="stretch", config=CHART_CFG)

# ---------- Is it luck? ----------
st.subheader("Is it luck?")
with st.container(border=True):
    if not strat.has_timing:
        st.info(
            "Dollar-cost averaging has no market timing to test. The honest comparison is the one above: on a market that mostly "
            "rises, investing everything on day one usually wins, and DCA's real benefit is a gentler way in and less regret."
        )
    else:
        res = lab.timing_luck_test(run.positions, lab.window_returns(prices.pct_change().fillna(0.0), end=split))
        level, text = lab.luck_verdict(res["p_value"], n_trials, res.get("reason"))
        if res["p_value"] is not None:
            st.plotly_chart(lc.luck_chart(res["sims"], res["observed"], mode), width="stretch", config=CHART_CFG)
            st.caption(
                f"The rule's in-and-out pattern was shuffled to 2,000 random positions in time, keeping how long it was invested. "
                f"Your rule earned {res['observed'] * 100:.1f}% a year before costs; the typical random placement earned "
                f"{res['median_random'] * 100:.1f}%."
            )
        {"good": st.success, "warn": st.warning, "neutral": st.info}[level](text)

# ---------- Trial counter ----------
with st.container(border=True):
    st.markdown(f"**Variations you've tried this session: {n_trials}**")
    st.caption(
        f"Every different ticker, strategy, setting, cost or split you look at counts as a try. If you test {n_trials} pure-luck ideas, "
        f"there is a {lab.chance_of_false_hit(n_trials) * 100:.0f}% chance at least one looks significant (p ≤ 5%). "
        f"To believe your best one, it should beat p ≤ {lab.adjusted_threshold(n_trials) * 100:.2f}%."
    )

# ---------- Held-out period ----------
st.subheader("The held-out test")
with st.container(border=True):
    if not revealed:
        st.markdown(
            f"Everything above used only {prices.index[0]:%b %Y} to {split:%b %Y}. The remaining {100 - train_pct}% "
            f"({split:%b %Y} to {prices.index[-1]:%b %Y}) is locked so you can't tune your rule to it."
        )
        st.caption("Once you peek, further tweaking stops being a clean test. Settle on your rule first.")
        if st.button("Reveal the held-out period"):
            st.session_state["lab_revealed"].add(symbol)
            st.rerun()
    else:
        st.markdown(f"Held-out period: {split:%b %Y} to {prices.index[-1]:%b %Y}, data the rule was never tuned on.")
        if m_test_s is None or m_test_b is None:
            st.warning("The held-out period is too short to judge.")
        else:
            st.plotly_chart(
                lc.equity_chart({run.name: lab.rebased_equity(test_s), bench.name: lab.rebased_equity(test_b)}, mode, height=300),
                width="stretch", config=CHART_CFG,
            )
            both = lab.metrics_table({f"{run.name} (training)": m_train_s, f"{bench.name} (training)": m_train_b,
                                      f"{run.name} (held out)": m_test_s, f"{bench.name} (held out)": m_test_b})
            st.dataframe(both, width="stretch")
            level, text = lab.overfit_note(m_train_s, m_train_b, m_test_s, m_test_b)
            {"good": st.success, "warn": st.warning, "neutral": st.info}[level](text)

# ---------- Learn ----------
with st.expander("How to read this (and what the lab can't tell you)"):
    st.markdown(
        """
- **No peeking:** a rule that sees today's close trades at *tomorrow's* close. Backtests that act on a price they couldn't have known are the most common way results get inflated.
- **Costs:** every buy or sell costs a little. A rule that trades often can look great with zero costs and lose with realistic ones.
- **Worst drop:** the biggest fall from a peak. Many rules earn *less* than buy-and-hold but fall less, and that can be the whole point.
- **Held-out test:** it is easy to find a setting that fit the past. The question is whether it works on data it never saw.
- **Is it luck:** compares your rule's timing with the same in-and-out pattern at random moments. A low percentage means few random placements did as well.
- **Trial counter:** try enough variations and one will look brilliant by chance. This is how many "great" strategies are born.
- **Limits:** one ticker, one history, daily prices. Markets change, and a rule that worked in this period may not work in the next.
"""
    )
