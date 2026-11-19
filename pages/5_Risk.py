"""
Risk — how bumpy your portfolio is, how alike your holdings are, how it would have handled bad
stretches, and a rough "what if the market fell" test. Read-only; percent-only (no dollar amounts
of yours appear). Everything is a BACKCAST: today's holdings at today's weights over past prices.

Same secrets and lock as Holdings. Prices come from Yahoo Finance (cached 12h, shared with Dividends).
"""

import time

import pandas as pd
import streamlit as st

import ui

import holdings_lib as hl
import lab_charts as lc
import lab_lib as lab
import portfolio_state as ps
import risk_charts as rc_charts
import risk_lib as rl
import risk_text as rt

st.set_page_config(page_title="Risk", layout="wide")
ui.apply()

CHART_CFG = {"displayModeBar": False}
MAX_HOLDINGS = 20
WINDOWS = {"1 year": 1, "3 years": 3, "5 years": 5}


def theme_mode() -> str:
    try:
        return "light" if st.context.theme.type == "light" else "dark"
    except Exception:
        return "dark"


# ---------- Access gate (same rules as Holdings; fails closed) ----------
expected = ps.secret("APP_PASSWORD")
if not expected:
    st.title("🛡️ Risk")
    st.error(
        "This page shows private account data, so it stays locked until you set a password. "
        'Add `APP_PASSWORD = "choose-something-long"` under ⋮ → Settings → Secrets, then reload.'
    )
    st.stop()

if not st.session_state.get("holdings_unlocked"):
    st.title("🛡️ Risk")
    entered = st.text_input("Password", type="password")
    if st.button("Unlock"):
        if hl.password_ok(entered, expected):
            st.session_state["holdings_unlocked"] = True
            st.rerun()
        else:
            time.sleep(2)  # slows down password guessing
            st.error("Wrong password.")
    st.stop()

if not (ps.secret("SNAPTRADE_CLIENT_ID") and ps.secret("SNAPTRADE_CONSUMER_KEY")):
    st.title("🛡️ Risk")
    st.info("Not connected yet. Add `SNAPTRADE_CLIENT_ID` and `SNAPTRADE_CONSUMER_KEY` to Secrets (same as the Holdings page).")
    st.stop()

with st.sidebar:
    st.header("Risk settings")
    window = st.radio("Look-back window", list(WINDOWS), index=1, help="How much history to measure over. Longer covers more market moods.")
    if st.button("Refresh now"):
        st.cache_data.clear()
        st.rerun()
    if st.button("Lock"):
        st.session_state["holdings_unlocked"] = False
        st.rerun()

mode = theme_mode()
st.title("🛡️ Risk")
portfolio = ps.get_portfolio()
if portfolio is None:
    st.info("Couldn't read your portfolio right now. Check the Holdings page first: if it loads there, reload this page.")
    st.stop()
st.caption("How bumpy your mix is and how it would have handled bad times. A backcast of today's holdings, not your account's actual "
           "path. Informational only, not financial advice.")

# ---------- Data ----------
merged = portfolio["merged"]
mv = {s: float(v) for s, v in zip(merged["Symbol"], merged["Market value"]) if s and s != "?" and pd.notna(v) and v > 0}
syms = list(mv)[:MAX_HOLDINGS]

with st.spinner("Loading price history…"):
    hist = {s: ps.load_history(s) for s in syms + ["SPY"]}
failed = [s for s in syms if hist[s]["error"]]
rets = {s: rl.total_returns(hist[s]["prices"], hist[s]["divs"]) for s in syms if not hist[s]["error"]}
spy = rl.total_returns(hist["SPY"]["prices"], hist["SPY"]["divs"]) if not hist["SPY"]["error"] else pd.Series(dtype=float)

if spy.empty:
    st.warning("Couldn't load the S&P 500 (SPY) history from Yahoo Finance, which this page needs as its yardstick. Try Refresh in a minute.")
    st.stop()
if failed:
    st.warning(f"Couldn't load price history for {', '.join(failed)} (Yahoo may be rate-limiting). They're left out.")

years_wanted = WINDOWS[window]
df, excluded = rl.aligned_returns(rets, years_wanted)
if df.empty:
    st.info("Not enough overlapping price history to measure risk. Try a longer window, or Refresh.")
    st.stop()
market = spy.reindex(df.index).dropna()
df = df.loc[market.index]
if len(df) < rl.MIN_DAYS // 2:
    st.info("Not enough overlapping history with the S&P 500 to measure risk.")
    st.stop()

cols = list(df.columns)
weights = rl.normalize_weights({s: mv[s] for s in cols}, cols)
port = rl.portfolio_returns(df, weights)
pm, sm = rl.risk_metrics(port), rl.risk_metrics(market)
years = pm["years"]
corr = rl.correlation(df) if len(cols) >= 2 else None
avg_corr = rl.avg_pairwise_corr(corr, weights) if corr is not None else None
div_ratio = rl.diversification_ratio(df, weights) if len(cols) >= 2 else None
hi, lo = rl.extreme_pairs(corr) if corr is not None else (None, None)
rc = rl.risk_contributions(df, weights)
betas = rl.betas(df, market)
beta_p = rl.portfolio_beta(weights, betas)
episodes = rl.drawdown_episodes(port)
hist_rows = rl.history_table(port, market)

# ---------- Summary (filled at the end, once the stress slider below has been read) ----------
st.subheader("Summary")
summary_box = st.container()
st.divider()

k1, k2, k3, k4 = st.columns(4)
with k1.container(border=True):
    st.metric("Yearly swings", hl.pct(pm["volatility"] * 100, signed=False, digits=0),
              delta=f"S&P 500: {sm['volatility'] * 100:.0f}%", delta_color="off",
              help="Volatility: how much the mix's value typically swings over a year.")
with k2.container(border=True):
    st.metric("Worst fall from a peak", hl.pct(-pm["max_drawdown"] * 100, signed=False, digits=0),
              delta=f"S&P 500: {-sm['max_drawdown'] * 100:.0f}%", delta_color="off",
              help="The deepest drop from a high point in this window.")
with k3.container(border=True):
    st.metric("Beta vs S&P 500", f"{beta_p:.2f}" if beta_p is not None else "—",
              help="1.0 moves with the market; above 1 moves more; below 1 moves less.")
with k4.container(border=True):
    st.metric("Avg. correlation", f"{avg_corr:.2f}" if avg_corr is not None else "—",
              help="How alike your holdings are. Near 1: they move together. Near 0: independent.")
st.caption(f"Measured over {years:.1f} years ({df.index[0]:%b %Y} to {df.index[-1]:%b %Y}), {len(cols)} holding(s)."
           + (f" Left out for short history: {', '.join(excluded)}." if excluded else ""))
st.write("")

tab_div, tab_bad, tab_stress = st.tabs(["🧩 Diversification", "📉 Bad stretches", "🧪 Stress test"])

# ---------- Diversification ----------
with tab_div:
    if corr is not None:
        st.markdown("**How alike your holdings are**")
        st.caption("Correlation of daily moves: 1 means they rise and fall together, 0 means unrelated. Darker = more alike.")
        st.plotly_chart(rc_charts.corr_heatmap(corr, mode), width="stretch", config=CHART_CFG)
    else:
        st.info("One holding in this window, so there is nothing to compare it with.")
    st.markdown("**Share of your money vs. share of the risk**")
    st.caption("A bar longer on the risk side means that holding adds more bumpiness than its size suggests.")
    order = list(rc.sort_values(ascending=False).index)
    st.plotly_chart(rc_charts.risk_vs_money(order, [weights[s] * 100 for s in order], [float(rc[s]) * 100 for s in order], mode),
                    width="stretch", config=CHART_CFG)
    table = pd.DataFrame({
        "Symbol": order,
        "Share of money %": [weights[s] * 100 for s in order],
        "Share of risk %": [float(rc[s]) * 100 for s in order],
        "Own yearly swings %": [float(df[s].std() * (rl.TRADING_DAYS ** 0.5) * 100) for s in order],
        "Beta": [betas[s] for s in order],
    })
    st.dataframe(table, hide_index=True, width="stretch", column_config={
        "Share of money %": st.column_config.NumberColumn("Share of money", format="%.0f%%"),
        "Share of risk %": st.column_config.NumberColumn("Share of risk", format="%.0f%%"),
        "Own yearly swings %": st.column_config.NumberColumn("Own yearly swings", format="%.0f%%"),
        "Beta": st.column_config.NumberColumn("Beta", format="%.2f"),
    })
    st.caption("An ETF counts as one ticker here. Weights use today's market values among the holdings shown.")

# ---------- Bad stretches ----------
with tab_bad:
    st.markdown("**Growth of $10,000: your mix vs. the S&P 500**")
    st.caption("Hypothetical: today's mix at today's weights, rebalanced daily, dividends included. Not your account's actual path.")
    st.plotly_chart(lc.equity_chart({"Your mix": lab.rebased_equity(port), "S&P 500": lab.rebased_equity(market)}, mode),
                    width="stretch", config=CHART_CFG)
    st.markdown("**How far below its peak each was**")
    st.plotly_chart(lc.drawdown_chart({"Your mix": lab.drawdown(port), "S&P 500": lab.drawdown(market)}, mode),
                    width="stretch", config=CHART_CFG)
    left, right = st.columns(2, gap="large")
    with left:
        st.markdown("**Deepest falls**")
        if episodes:
            ep = pd.DataFrame([{"Peak": e["peak"], "Bottom": e["trough"], "Fall %": e["depth"] * 100,
                                "Back at peak": e["recovered"]} for e in episodes])
            st.dataframe(ep, hide_index=True, width="stretch", column_config={
                "Peak": st.column_config.DateColumn(format="MMM YYYY"),
                "Bottom": st.column_config.DateColumn(format="MMM YYYY"),
                "Fall %": st.column_config.NumberColumn("Fall", format="%.0f%%"),
                "Back at peak": st.column_config.DateColumn(format="MMM YYYY"),
            })
            st.caption("An empty 'Back at peak' means it hadn't gotten back by the end of the data.")
        else:
            st.info("No fall of 5% or more from a peak in this window.")
    with right:
        st.markdown("**Famous bad stretches**")
        if hist_rows:
            ht = pd.DataFrame([{"Stretch": h["label"], "Your mix %": h["mix"] * 100, "S&P 500 %": h["market"] * 100} for h in hist_rows])
            st.dataframe(ht, hide_index=True, width="stretch", column_config={
                "Your mix %": st.column_config.NumberColumn("Your mix", format="%+.0f%%"),
                "S&P 500 %": st.column_config.NumberColumn("S&P 500", format="%+.0f%%"),
            })
        else:
            st.info("The data in this window doesn't cover a famous selloff. Try the 5-year window.")

# ---------- Stress test ----------
with tab_stress:
    shock = st.slider("If the market fell by…", min_value=5, max_value=50, value=20, step=5, format="%d%%",
                      help="A rough estimate from how each holding moved with the market in this window.") * -1
    shocks = sorted({-10, -20, -30, shock}, reverse=True)
    st_tbl = rl.stress_table(weights, betas, shocks=shocks)
    if beta_p is None or st_tbl.empty:
        st.info("Not enough overlapping history to estimate how your mix reacts to a market fall.")
        stress_rows, biggest = [], None
    else:
        st.markdown("**Estimated fall of your mix**")
        st.plotly_chart(rc_charts.stress_bars([f"Market {s}%" for s in st_tbl["Market move %"]], list(st_tbl["Your mix %"]), mode),
                        width="stretch", config=CHART_CFG)
        row = st_tbl[st_tbl["Market move %"] == shock].iloc[0]
        contrib = row.drop(["Market move %", "Your mix %"]).astype(float).sort_values()
        st.markdown(f"**Where a {abs(shock)}% market fall would come from**")
        ct = pd.DataFrame({"Symbol": list(contrib.index), "Adds to the fall (points)": list(contrib.values)})
        st.dataframe(ct, hide_index=True, width="stretch", column_config={
            "Adds to the fall (points)": st.column_config.NumberColumn(format="%.1f"),
        })
        st.caption("Estimate = beta x the market move, weighted by your holdings. In real crashes holdings tend to fall together more "
                   "than their history suggests, so treat this as a floor on the damage, not a forecast.")
        stress_rows = [{"market": float(r["Market move %"]), "mix": float(r["Your mix %"])}
                       for _, r in st_tbl.iterrows() if r["Market move %"] in (-10, -20, -30)]
        worst = contrib.index[0] if len(contrib) else None
        biggest = (worst, abs(float(contrib.iloc[0])) / abs(float(row["Your mix %"]))) if worst and row["Your mix %"] else None

# ---------- Fill the summary ----------
with summary_box:
    sections = rt.write_summary(
        pm=pm, sm=sm, years=years, n=len(cols), n_days=len(df), rc=rc, weights=weights, beta_p=beta_p, avg_corr=avg_corr,
        div_ratio=div_ratio, hi=hi, lo=lo, excluded=excluded, episodes=episodes, hist=hist_rows,
        stress_rows=stress_rows, biggest=biggest)
    for tab, (_title, bullets) in zip(st.tabs([t for t, _ in sections]), sections):
        with tab:
            for b in bullets:
                st.markdown(f"- {b}")
    st.caption("Written by rules from the numbers on this page, with no AI. Backcast and estimates only; informational, not financial advice.")
