"""
Stock Deep-Dive: one company in plain words, with key numbers, pros and cons, price and risk, analysts and news.

Starts from the dashboard's Stock of the day (same screen, so they always agree) and goes further: more measures,
the price history against the S&P 500, dividends, analyst ratings, upcoming earnings, headlines.
Read-only. Company numbers: Finnhub free tier. Prices: Yahoo Finance. Research, not advice.
"""

import datetime as dt
import re

import pandas as pd
import streamlit as st

import ui

import brief_lib as bl
import deep_charts as dc
import deep_lib as dlib
import deep_text as dtx
import hold_lib as hl
import dividend_lib as dl
import idea_lib as il
import idea_state as ist
import lab_charts as lc
import portfolio_state as ps

st.set_page_config(page_title="Stock Deep-Dive", layout="wide")
ui.apply()

CHART_CFG = {"displayModeBar": False}
ICON = {"Good": "🟢 Good", "OK": "🟡 OK", "Watch": "🟠 Watch", "": "—"}


# ---------- Cached loaders ----------
@st.cache_data(ttl=6 * 3600, show_spinner=False)
def load_earnings(symbol, start, end, key):
    return bl.finnhub_get("calendar/earnings", {"from": start.isoformat(), "to": end.isoformat(), "symbol": symbol}, key)


@st.cache_data(ttl=1800, show_spinner=False)
def load_news(symbol, start, end, key):
    return bl.fetch_company_news(symbol, start, end, key)


@st.cache_data(ttl=3600, show_spinner=False)
def load_target(symbol, key):
    return bl.finnhub_get("stock/price-target", {"symbol": symbol}, key)


def tile(col, name, value, delta=None, help=None, delta_color="normal"):
    with col.container(border=True):
        st.metric(name, value, delta=delta, help=help, delta_color=delta_color)


def pc(x, d=1, signed=False):
    return dtx.pc(x, d, signed)


# ---------- Sidebar, portfolio (percent-only) ----------
ps.unlock_sidebar()
portfolio = ps.get_portfolio()
held = set(ps.held_symbols(portfolio))
weights = ps.weight_lookup(portfolio)
key = ps.secret("FINNHUB_API_KEY")
today = ui.today_central()
mode = ui.mode()

st.title("🔬 Stock Deep-Dive")
st.caption("One company in plain words: the numbers, the pros and cons, and the price history. Research, not a recommendation or financial advice.")

# ---------- Which stock? ----------
idea = None
if key:
    idea = ist.screen_today(key, tuple(sorted(ist.exclusions(held))), today.toordinal(), st.session_state.get("idea_offset", 0))
pick = (idea or {}).get("best")
pick_sym = pick["symbol"] if pick else None
ranked = sorted(held, key=lambda s: -weights.get(s, 0))
default = pick_sym or (ranked[0] if ranked else "AAPL")
NONE = "Type a ticker"
options = [NONE] + ([f"{pick_sym} · today's stock idea"] if pick_sym else []) + [f"{s} · you hold this" for s in ranked[:10]]


def _picked():
    v = st.session_state.get("deep_pick", NONE)
    if v != NONE:
        st.session_state["deep_typed"] = v.split(" ")[0]
        st.session_state["deep_pick"] = NONE


inbox = st.session_state.pop("deep_symbol", None)       # set by the "Open the full deep-dive" buttons on other pages
if inbox:
    st.session_state["deep_typed"] = inbox
st.session_state.setdefault("deep_typed", default)
c1, c2 = st.columns([1, 2])
with c1:
    typed = st.text_input("Ticker", key="deep_typed", max_chars=10, help="A US stock or ETF, like AAPL or VOO.")
with c2:
    st.selectbox("Or pick one", options, key="deep_pick", on_change=_picked)
symbol = (typed or "").strip().upper()
if not re.fullmatch(r"[A-Z][A-Z0-9.\-]{0,9}", symbol):
    st.warning("Enter a ticker symbol using letters, like AAPL or BRK.B.")
    st.stop()

# ---------- Load everything for this symbol (each part can fail on its own) ----------
notes = []
quote = profile = metrics = trends = None
if key:
    for name, fn in (("price", lambda: ist.quote(symbol, key)), ("company profile", lambda: ist.profile(symbol, key)),
                     ("company numbers", lambda: ist.metrics(symbol, key)), ("analyst ratings", lambda: ist.trends(symbol, key))):
        try:
            val = fn()
        except Exception as e:  # noqa: BLE001
            notes.append(f"Couldn't load {name} ({type(e).__name__}).")
            val = None
        if name == "price":
            quote = val
        elif name == "company profile":
            profile = val
        elif name == "company numbers":
            metrics = val
        else:
            trends = val
else:
    notes.append("Add `FINNHUB_API_KEY` to Secrets for company numbers, analyst ratings and news. Price history still works without it.")

with st.spinner("Loading price history…"):
    hist = ps.load_history(symbol)
    bench = ps.load_history("SPY") if symbol != "SPY" else None
prices, divs = hist["prices"], hist["divs"]
if hist["error"] and hist["error"] != "no history":
    notes.append(f"Couldn't load price history ({hist['error']})")
stats = dlib.price_stats(prices, divs, bench["prices"] if bench else None, bench["divs"] if bench else None) if len(prices) else None
div = dl.dividend_profile(divs, today) if len(divs) else None
has_data = bool(quote and quote.get("c")) or stats is not None or bool(metrics)
if not has_data:
    st.error(f"Couldn't find data for {symbol}. Check the ticker (class shares use a dot, like BRK.B).")
    for n in notes:
        st.caption(n)
    st.stop()

earn = None
if key:
    try:
        earn = dlib.earnings_in_days(load_earnings(symbol, today, today + dt.timedelta(days=120), key), symbol, today)
    except Exception as e:  # noqa: BLE001
        notes.append(f"Couldn't load the earnings date ({type(e).__name__}).")

fund = bool(key) and metrics is not None and dlib.is_fund(profile, metrics)
ev = None if (fund or not metrics) else dlib.assess(symbol, quote, metrics, trends, stats, div, earn[0] if earn else None)
held_ctx = dlib.held_context(symbol, weights) if portfolio else None
windows = hl.history_windows(prices, divs) if len(prices) else []
recov = hl.recoveries(prices, divs) if len(prices) else None
hz = hl.horizon(stats, recov, ev, fund, metrics)

# ---------- Header ----------
name = (profile or {}).get("name") or symbol
size = dlib.size_bucket((profile or {}).get("marketCapitalization") or dlib.metric(metrics, "mcap"))
chips = [("Fund / ETF" if fund else (size[0] if size else "Stock"), "info")]
if (profile or {}).get("finnhubIndustry"):
    chips.append((profile["finnhubIndustry"], "info"))
if (profile or {}).get("exchange"):
    chips.append(((profile["exchange"] or "").split(" ")[0], "info"))
if pick_sym == symbol:
    chips.append(("Stock of the day", "ok"))
if held_ctx and held_ctx["held"]:
    chips.append((f"You hold {held_ctx['weight']:.0f}% of invested", "warn"))
st.header(f"{name} ({symbol})")
ui.status_strip(chips)

price = (quote or {}).get("c") or (stats or {}).get("last")
cols = st.columns(5)
day = (quote or {}).get("dp")
tile(cols[0], "Price", f"${price:,.2f}" if price else "n/a", f"{day:+.2f}% today" if day is not None else None)
mc = (profile or {}).get("marketCapitalization") or dlib.metric(metrics, "mcap")
tile(cols[1], "Market value", (dlib.money_words(mc) or "n/a").replace("about ", "") if mc else "n/a", help="What the whole company is worth at today's price.")
pe = dlib.metric(metrics, "pe")
tile(cols[2], "P/E", f"{pe:.1f}" if pe is not None else "n/a", help="Price per dollar of yearly profit. Higher means more growth is expected.")
dy = dlib.metric(metrics, "div_yield")
tile(cols[3], "Dividend yield", f"{dy:.2f}%" if dy else "none", help="Yearly dividend as a share of the price.")
tile(cols[4], "1-year return", pc(stats["1Y"], 1, True) if stats and stats.get("1Y") is not None else "n/a", help="Price change plus dividends over the past year.")

# ---------- Written summary (first, like the other pages) ----------
sections = dict(dtx.write_summary(symbol, profile=profile, quote=quote, metrics=metrics, ev=ev, stats=stats, trends=trends, held=held_ctx, fund=fund))
st.subheader("In plain words")
for b in sections["In plain words"]:
    st.markdown(f"- {ui.esc(b)}")
if ev is not None:
    pro_col, con_col = st.columns(2)
    with pro_col:
        with st.container(border=True):
            st.markdown(f"**What looks good** ({len(ev['pros'])})")
            for b in sections["What looks good"]:
                st.markdown(f"- {ui.esc(b)}")
    with con_col:
        with st.container(border=True):
            st.markdown(f"**What to watch** ({len(ev['cons'])})")
            for b in sections["What to watch"]:
                st.markdown(f"- {ui.esc(b)}")
    st.markdown("**Bottom line**")
    for b in sections["Bottom line"]:
        st.markdown(f"- {ui.esc(b)}")
    if "How it fits you" in sections:
        st.markdown("**How it fits you**")
        for b in sections["How it fits you"]:
            st.markdown(f"- {ui.esc(b)}")
st.subheader("How long to hold it")
if hz:
    ui.status_strip([(f"Planning window: {hz['text']}", "info"), (hz["style"], "info")])
for b in dtx.holding_summary(symbol, hz, windows, recov, div, held_ctx, fund):
    st.markdown(f"- {ui.esc(b)}")
st.caption("Written by rules from the numbers on this page, with no AI. Describes the past, not the future; informational, not financial advice.")
st.divider()

# ---------- Details ----------
tabs = st.tabs(["📊 Key numbers", "📈 Price, risk & dividends", "⏳ How long to hold", "🧑‍🏫 Analysts & news", "🧮 How it's scored"])
t_keys, t_price, t_hold, t_people, t_rules = tabs

with t_keys:
    rows = dlib.key_numbers(metrics)
    if fund:
        st.info("This looks like a fund or ETF, so company measures don't apply. See the price tab.")
    elif not rows:
        st.info("Company numbers aren't available for this ticker right now.")
    else:
        st.caption("Good / OK / Watch are rules of thumb, not verdicts. Fair levels differ by industry, so compare with a rival in the same business.")
        for group in dict.fromkeys(r["group"] for r in rows):
            st.markdown(f"##### {group}")
            df = pd.DataFrame([{"Measure": r["label"], "Value": r["shown"], "Read": ICON[r["read"]], "What it means": r["meaning"]} for r in rows if r["group"] == group])
            st.dataframe(df, hide_index=True, width="stretch")
        missing = [label for _g, label, k, *_ in dlib.KEYS if dlib.metric(metrics, k) is None]
        if missing:
            st.caption("Not available for this ticker: " + ", ".join(missing) + ".")
    if metrics:
        with st.expander("Everything Finnhub returned"):
            raw = pd.DataFrame(sorted((k, v) for k, v in metrics.items() if isinstance(v, (int, float)) and not isinstance(v, bool)), columns=["Field", "Value"])
            st.dataframe(raw, hide_index=True, width="stretch")

with t_price:
    if stats is None:
        st.info("Price history isn't available for this ticker right now.")
    else:
        cols = st.columns(4)
        tile(cols[0], "Past month", pc(stats["1M"], 1, True) if stats["1M"] is not None else "n/a")
        tile(cols[1], "Past 3 months", pc(stats["3M"], 1, True) if stats["3M"] is not None else "n/a")
        tile(cols[2], "3 years, per year", pc(stats["3Y"], 1, True) if stats["3Y"] is not None else "n/a", help="Average yearly return, dividends included.")
        tile(cols[3], "Past 5 years, per year", pc(stats["5Y"], 1, True) if stats["5Y"] is not None else "n/a")
        cols = st.columns(4)
        tile(cols[0], "Yearly swings", pc(stats["volatility"], 0) if stats["volatility"] is not None else "n/a",
             help="Typical size of yearly ups and downs. The broad market is roughly 15–20%.", delta_color="off")
        tile(cols[1], "Worst fall (5 yrs)", pc(stats["max_drawdown"], 0), f"from a peak, bottom {stats['max_drawdown_date']:%b %Y}", delta_color="off")
        tile(cols[2], "Now vs its peak", pc(stats["current_drawdown"], 1, True), help="How far below its highest point of the past five years.")
        beta = dlib.metric(metrics, "beta") if dlib.metric(metrics, "beta") is not None else stats["beta"]
        tile(cols[3], "Beta (vs market)", f"{beta:.2f}" if beta is not None else "n/a", help="1.0 moves like the market; 1.5 swings about half again as much.", delta_color="off")

        years = {"1 year": 1, "2 years": 2, "5 years": 5}[st.radio("Chart range", ["1 year", "2 years", "5 years"], index=1, horizontal=True, label_visibility="collapsed")]
        st.markdown("**Price with its 50- and 200-day averages**")
        st.plotly_chart(dc.price_chart(prices, mode, years=years), width="stretch", config=CHART_CFG)
        st.caption(f"Above both averages is often read as an uptrend, below both as a downtrend. It describes the past. Now {pc(stats['vs50'], 1, True) if stats['vs50'] is not None else 'n/a'} vs the 50-day and "
                   f"{pc(stats['vs200'], 1, True) if stats['vs200'] is not None else 'n/a'} vs the 200-day.")

        if symbol != "SPY" and bench and len(bench["prices"]):
            curves = dlib.compare_curves(prices, divs, bench["prices"], bench["divs"], 5)
            if len(curves) == 2:
                l, r = st.columns(2, gap="large")
                with l:
                    st.markdown("**Growth of \\$10,000 vs the S&P 500**")
                    st.plotly_chart(lc.equity_chart({symbol: curves["Stock"], "S&P 500": curves["S&P 500"]}, mode, height=300), width="stretch", config=CHART_CFG)
                with r:
                    st.markdown("**Falls from each peak**")
                    dd = {symbol: curves["Stock"] / curves["Stock"].cummax() - 1, "S&P 500": curves["S&P 500"] / curves["S&P 500"].cummax() - 1}
                    st.plotly_chart(lc.drawdown_chart(dd, mode, height=300), width="stretch", config=CHART_CFG)
                st.caption("Dividends reinvested, last five years (or since both have data). A hypothetical, not your results.")
            tbl = dlib.returns_table(prices, divs, bench["prices"], bench["divs"])
            if not tbl.empty:
                show = tbl.copy()
                for c in ("Stock", "S&P 500", "Difference"):
                    show[c] = show[c] * 100
                show = show.rename(columns={"Stock": symbol})
                st.dataframe(show, hide_index=True, width="stretch", column_config={c: st.column_config.NumberColumn(c, format="%+.1f%%") for c in (symbol, "S&P 500", "Difference")})

        st.markdown("##### Dividends")
        if div and div["active"]:
            rows = [("Last payment", f"${div['last_amount']:.2f} per share, ex-date {div['last_ex']:%b %d, %Y}"),
                    ("Pays", div["freq_name"] or "irregularly"),
                    ("Estimated yearly total", f"${div['annual_rate']:.2f} per share" if div["annual_rate"] else "n/a")]
            if div.get("cagr") is not None:
                rows.append(("Dividend growth", f"{div['cagr']:+.1f}% a year over {div['cagr_years']} years"))
            rows.append(("Years of raises in a row", str(div.get("streak") or 0)))
            if div.get("next_ex"):
                rows.append(("Next ex-dividend date (estimated)", f"{div['next_ex']:%b %d, %Y}"))
            st.dataframe(pd.DataFrame(rows, columns=["Item", "Detail"]), hide_index=True, width="stretch")
            st.caption("From the payment history. Dividends can be cut or stopped, and the next date is an estimate.")
        else:
            st.caption("No regular dividend found in the price history" + (f" ({div['reason']})." if div and div.get("reason") else "."))

with t_hold:
    st.markdown("##### How often holding it paid off")
    if windows:
        st.plotly_chart(dc.hold_chart(windows, mode), width="stretch", config=CHART_CFG)
        tbl = pd.DataFrame([{"Held for": f"{w['years']} year" + ("s" if w["years"] > 1 else ""), "Periods tested": w["periods"],
                             "Ended in a gain": w["share_gain"] * 100,
                             "Typical, per year": (w["median_per_year"] or 0) * 100, "Worst, total": w["worst_total"] * 100,
                             "Best, total": w["best_total"] * 100} for w in windows])
        st.dataframe(tbl, hide_index=True, width="stretch", column_config={
            "Ended in a gain": st.column_config.NumberColumn(format="%.0f%%"),
            "Typical, per year": st.column_config.NumberColumn(format="%+.1f%%"),
            "Worst, total": st.column_config.NumberColumn(format="%+.0f%%"),
            "Best, total": st.column_config.NumberColumn(format="%+.0f%%")})
        st.caption("Every possible start date in its price history, dividends reinvested. Periods overlap and come from one stretch of history, so this shows a range, not a forecast.")
    else:
        st.caption("Not enough price history to test holding periods (needs a bit over a year per length tested).")
    st.markdown("##### Its biggest falls and how long they took to heal")
    eps = (recov or {}).get("episodes") or []
    if eps:
        st.dataframe(pd.DataFrame([{"Peak": f"{e['peak']:%b %Y}", "Low point": f"{e['trough']:%b %Y}", "Fall": e["depth"] * 100,
                                    "Back to the old high": f"{e['recovered']:%b %Y}" if e["recovered"] is not None else "Not yet",
                                    "Peak to recovery": f"{e['total_days'] / 365.25:.1f} years" if e["total_days"] is not None else "Still waiting"} for e in eps]),
                     hide_index=True, width="stretch")
        st.caption("Falls of 15% or more over roughly the past ten years. Coming back is not guaranteed.")
    else:
        st.caption("No fall of 15% or more in the available history.")
    st.markdown("##### What would make a long hold worth a second look")
    for r in hl.rechecks(stats, ev, div, earn[0] if earn else None, fund):
        st.markdown(f"- {'🟡' if r['flag'] else '🟢'} **{r['what']}.** {ui.esc(r['why'])} *Now: {ui.esc(r['now'])}*")
    st.caption("These are prompts to look again, not sell signals. How the window is chosen:")
    st.dataframe(pd.DataFrame(hl.RULES, columns=["Step", "Rule"]), hide_index=True, width="stretch")

with t_people:
    if not key:
        st.info("Add `FINNHUB_API_KEY` to Secrets to see analyst ratings, earnings dates and news.")
    else:
        st.markdown("##### Analysts")
        if trends and il.consensus_slices(trends[0]):
            score = bl.analyst_score(trends[0])
            l, r = st.columns([2, 3])
            with l:
                tile(st, "Consensus", il.consensus_verdict(score), f"score {score:+.2f} of ±2", delta_color="off")
                shift = bl.analyst_shift(trends)
                if shift:
                    st.caption(f"{shift['direction'].capitalize()} than the month before ({shift['score_before']:+.2f} → {shift['score_now']:+.2f}).")
            with r:
                st.plotly_chart(dc.analyst_bars(trends[0], mode), width="stretch", config=CHART_CFG)
            st.caption("Analysts skew bullish and tend to lag the price. Treat ratings as one input, not an answer.")
        else:
            st.caption("No analyst ratings for this ticker.")
        if not st.session_state.get("price_targets_blocked"):
            try:
                pt = load_target(symbol, key)
                if pt and pt.get("targetMean"):
                    st.markdown(f"**Average analyst price target:** ${pt['targetMean']:,.2f}" + (f" (range ${pt['targetLow']:,.2f} to ${pt['targetHigh']:,.2f})" if pt.get("targetLow") and pt.get("targetHigh") else ""))
            except Exception:  # noqa: BLE001 - not on the free plan for most accounts; skip quietly
                st.session_state["price_targets_blocked"] = True
        st.markdown("##### Next earnings report")
        if earn:
            n, d = earn
            st.markdown(f"**{d:%a %b %d, %Y}** ({'today' if n == 0 else 'tomorrow' if n == 1 else f'in {n} days'}). Prices often move sharply on earnings day.")
        else:
            st.caption("No report date in the next 120 days (or it hasn't been announced).")
        st.markdown("##### Recent headlines")
        try:
            items = bl.select_news(load_news(symbol, today - dt.timedelta(days=7), today, key), limit=5)
        except Exception as e:  # noqa: BLE001
            items = []
            notes.append(f"Couldn't load news ({type(e).__name__}).")
        if items:
            for it in items:
                st.markdown(f"- [{ui.esc(it['headline'])}]({it['url']}) · {ui.esc(it['source'])} · {it['published']:%b %d}")
            st.caption("Headlines are links to the publisher; they are not summarized or endorsed here.")
        else:
            st.caption("No recent headlines.")

with t_rules:
    st.markdown("Each measure gets **Good / OK / Watch** from these rules of thumb. The pros and cons use the same lines as the dashboard's Stock of the day, then add the extra signals below.")
    st.dataframe(pd.DataFrame(dlib.rules_table(), columns=["Group", "Measure", "Good when", "Watch when"]), hide_index=True, width="stretch")
    st.markdown("**Extra signals used in the pros and cons**")
    st.dataframe(pd.DataFrame(dlib.EXTRA_RULES, columns=["Signal", "Rule"]), hide_index=True, width="stretch")
    st.markdown("**The Stock of the day screen (shared with the dashboard)**")
    st.dataframe(pd.DataFrame(il.RULES, columns=["Measure", "What it looks at", "Rule"]), hide_index=True, width="stretch")
    for b in dtx.worth_knowing():
        st.caption(ui.esc(b))

for n in notes:
    st.caption(n)
