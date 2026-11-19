"""
Market: a short, calm overview of the market, with an Advanced view for more detail, plus one calendar of
what's coming (earnings, estimated ex-dividend dates, Fed decisions, market closures).

Public market data only (Yahoo Finance, no key). The calendar uses your watchlist: your holdings when
unlocked, or a sample list. Read-only.
"""

import datetime as dt

import pandas as pd
import streamlit as st

import ui

import brief_lib as bl
import dividend_lib as dl
import event_lib as el
import market_charts as mc
import market_data as md
import market_lib as ml
import market_text as mt
import portfolio_state as ps

st.set_page_config(page_title="Market", layout="wide")
ui.apply()

CHART_CFG = {"displayModeBar": False}
PERIODS = ["1D", "1M", "3M", "YTD"]


# ---------- Cached loaders (network lives here; everything else is pure) ----------
@st.cache_data(ttl=300, show_spinner=False)
def load_core():
    return md.fetch_many(md.CORE)


@st.cache_data(ttl=900, show_spinner=False)
def load_extra():
    return md.fetch_many(md.EXTRA)


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def load_earnings(start, end, key):
    return bl.fetch_earnings_calendar(start, end, key)


def closes_of(results: dict) -> dict:
    return {s: r["close"] for s, r in results.items() if not r.get("error") and len(r["close"])}


def spark(s, n=63):
    return [float(x) for x in s.iloc[-n:]] if s is not None and len(s) else None


def tile(col, name, value, delta=None, series=None, delta_color="normal", help=None):
    with col.container(border=True):
        kw = {"chart_data": series, "chart_type": "line"} if series else {}
        st.metric(name, value, delta=delta, delta_color=delta_color, help=help, **kw)


def signed(x, digits=1):
    return mt.pc(x, digits, signed=True)


# ---------- Sidebar and watchlist ----------
ps.unlock_sidebar()
portfolio = ps.get_portfolio()
tickers, held = ps.watchlist_sidebar(portfolio)
with st.sidebar:
    if st.button("Refresh now"):
        st.cache_data.clear()
        st.rerun()

today = ui.today_central()
mode = ui.mode()

st.title("🌐 Market")
st.caption("A calm overview of the market, and what's coming up. Public market data only. Informational, not financial advice.")

status = el.market_status()
ui.status_strip([(status["label"], status["tone"]), ("Prices from Yahoo Finance · may be delayed", "info"), (f"Updated {ui.clock()}", "info")])
advanced = st.toggle("Advanced view", value=False, help="Adds sectors, interest rates, volatility, index detail and other markets.")

summary_box = st.container()
st.divider()

# ---------- Core data ----------
with st.spinner("Loading market data…"):
    core = load_core()
closes = closes_of(core)
names = dict(md.INDEXES)
sp_close = closes.get("^GSPC")

if sp_close is None:
    st.warning("Couldn't load market prices from Yahoo Finance right now (it sometimes rate-limits cloud servers). "
               "Try Refresh in a minute. The calendar below still works.")
    idx_returns, sp, vix, ten, latest = {}, None, None, None, None
else:
    idx_returns = {name: ml.period_returns(closes.get(sym))["1D"] for sym, name in md.INDEXES if sym in closes}
    sp = ml.trend_stats(sp_close)
    latest = sp_close.index[-1]
    vix = float(closes["^VIX"].iloc[-1]) if "^VIX" in closes else None
    ten_s = ml.normalize_yield(closes.get("^TNX"))
    ten = {"level": float(ten_s.iloc[-1]), "m1": ml.level_changes(ten_s)["1M"]} if len(ten_s) else None

    cols = st.columns(4)
    for col, (sym, name) in zip(cols, md.INDEXES):
        s = closes.get(sym)
        if s is None:
            tile(col, name, "n/a")
            continue
        r = ml.period_returns(s)["1D"]
        tile(col, name, f"{float(s.iloc[-1]):,.0f}", signed(r, 2) if r is not None else None, spark(s))
    cols = st.columns(4)
    reg = ml.vix_regime(vix)
    tile(cols[0], "VIX (expected volatility)", f"{vix:.1f}" if vix is not None else "n/a", reg[0] if reg else None, spark(closes.get("^VIX")), "off",
         "How much the options market expects the S&P 500 to swing over the next 30 days. Long-run average: roughly 20.")
    ten_chg = ten["m1"] if ten else None
    tile(cols[1], "10-year Treasury yield", f"{ten['level']:.2f}%" if ten else "n/a",
         f"{ten_chg:+.2f} pts over 1 month" if ten_chg is not None else None, spark(ten_s), "off",
         "The interest rate the US government pays to borrow for 10 years. Many other rates key off it.")
    tile(cols[2], "S&P 500 vs 200-day average", signed(sp["vs200"]) if sp["vs200"] is not None else "n/a",
         {"up": "Uptrend", "down": "Downtrend", "mixed": "Mixed signals"}.get(sp["trend"]), None, "off",
         "How far the index sits above or below its average of the last 200 trading days.")
    tile(cols[3], "S&P 500 from 52-week high", signed(sp["from_high"]) if sp["from_high"] is not None else "n/a", None, None, "off",
         "0% means it closed at its highest level of the past year.")
    failed = [n for s, n in [*md.INDEXES, md.VIX] if s not in closes]
    if failed:
        st.caption(f"Couldn't load: {', '.join(failed)}.")

# ---------- Advanced view ----------
table = br = od = spread = y_short = y_long = None
if advanced:
    st.subheader("In more detail")
    with st.spinner("Loading sectors, rates and other markets…"):
        extra = load_extra()
    ex_closes = closes_of(extra)
    all_closes = {**closes, **ex_closes}
    t_sectors, t_rates, t_index, t_other = st.tabs(["Sectors", "Rates & volatility", "Index detail", "Other markets"])
    sector_names = dict(md.SECTORS)

    table = ml.sector_table(ex_closes, sector_names)
    br = ml.breadth(table)
    od = ml.offense_vs_defense(table)

    with t_sectors:
        if table.empty:
            st.info("Sector data isn't available right now. Try Refresh in a minute.")
        else:
            period = st.radio("Period", PERIODS, index=1, horizontal=True, label_visibility="collapsed")
            ordered = table.dropna(subset=[period]).sort_values(period, ascending=False)
            st.plotly_chart(mc.sector_bars(list(ordered["Sector"]), list(ordered[period]), mode), width="stretch", config=CHART_CFG)
            if br:
                st.caption(f"{br[0]} of {br[1]} sectors are up over the past month. Sectors are the 11 S&P 500 groups, tracked here by their largest ETFs.")
            show = table.copy()
            for c in PERIODS:
                show[c] = show[c] * 100
            st.dataframe(show.drop(columns="Symbol"), hide_index=True, width="stretch", column_config={
                c: st.column_config.NumberColumn(c, format="%+.1f%%") for c in PERIODS})

    with t_rates:
        order = [s for s, _ in md.RATES]
        labels = [n for _, n in md.RATES]
        rate_closes = {s: all_closes[s] for s in order if s in all_closes}
        if len(rate_closes) < 2:
            st.info("Treasury yields aren't available right now. Try Refresh in a minute.")
        else:
            l, r = st.columns(2, gap="large")
            with l:
                st.markdown("**Treasury yield curve**")
                st.plotly_chart(mc.yield_curve(labels, {"Now": ml.curve_points(rate_closes, order), "1 month ago": ml.curve_points(rate_closes, order, 21),
                                                        "1 year ago": ml.curve_points(rate_closes, order, 252)}, mode), width="stretch", config=CHART_CFG)
                y_short = ml.curve_points(rate_closes, ["^IRX"])[0] if "^IRX" in rate_closes else None
                y_long = ml.curve_points(rate_closes, ["^TNX"])[0] if "^TNX" in rate_closes else None
                spread = ml.curve_spread(y_short, y_long)
                if spread is not None:
                    st.caption(f"10-year minus 3-month: {spread:+.2f} percentage points, so the curve is {ml.curve_label(spread)}. "
                               "A normal curve slopes up, since lending for longer pays more.")
            with r:
                st.markdown("**VIX over the past year**")
                v = closes.get("^VIX")
                if v is None:
                    st.info("VIX isn't available right now.")
                else:
                    v1 = v.iloc[-252:]
                    st.plotly_chart(mc.vix_chart(v1.index, v1.values, mode), width="stretch", config=CHART_CFG)
                    reg = ml.vix_regime(float(v.iloc[-1]))
                    if reg:
                        st.caption(f"Now {float(v.iloc[-1]):.1f}: {reg[0].lower()} ({reg[1]}).")

    with t_index:
        names_all = {s: n for s, n in md.INDEXES}
        it = ml.index_table(closes, names_all)
        if it.empty:
            st.info("Index data isn't available right now.")
        else:
            pct_cols = ["1D", "1W", "1M", "3M", "YTD", "1Y", "vs 50-day", "vs 200-day", "From 52-wk high"]
            show = it.copy()
            for c in pct_cols:
                show[c] = show[c] * 100
            cfg = {c: st.column_config.NumberColumn(c, format="%+.1f%%") for c in pct_cols}
            cfg["Level"] = st.column_config.NumberColumn("Level", format="%,.0f")
            st.dataframe(show, hide_index=True, width="stretch", column_config=cfg)
            st.caption("Price returns (dividends not included). \"vs 50-day\" and \"vs 200-day\" show how far each index sits above or below its moving average.")

    with t_other:
        cols = st.columns(4)
        for col, (sym, name) in zip(cols, md.OTHER):
            s = ex_closes.get(sym)
            if s is None:
                tile(col, name, "n/a")
                continue
            r = ml.period_returns(s)
            tile(col, name, f"{float(s.iloc[-1]):,.2f}", signed(r["1D"], 2) if r["1D"] is not None else None, spark(s))
        st.caption("Gold and oil are futures prices; the dollar index measures the dollar against a basket of major currencies.")
    st.divider()

# ---------- Calendar ----------
st.subheader("What's coming")
c1, c2 = st.columns([2, 3])
with c1:
    days = st.select_slider("Look ahead", options=[7, 14, 30, 60], value=14, format_func=lambda d: f"{d} days")
with c2:
    kinds = st.multiselect("Show", el.TYPES, default=el.TYPES)

events = el.builtin_events(today, 60)
notes = []

key = ps.secret("FINNHUB_API_KEY")
if key and tickers:
    try:
        cal = load_earnings(today, today + dt.timedelta(days=60), key)
        events += el.earnings_events(bl.filter_earnings(cal, tickers, today))
    except Exception as e:  # noqa: BLE001
        notes.append(f"Couldn't load earnings dates ({type(e).__name__}).")
elif not key:
    notes.append("Add `FINNHUB_API_KEY` to Secrets to see earnings dates.")

if tickers:
    with st.spinner("Estimating ex-dividend dates…"):
        histories = {s: ps.load_history(s) for s in tickers}
    profiles = {s: dl.dividend_profile(h["divs"], today) for s, h in histories.items() if not h["error"] or h["error"] == "no history"}
    proj = dl.project_payments({s: 1.0 for s in profiles}, profiles, today, 4)
    events += el.exdividend_events(proj, today, 60)
    unreadable = [s for s, h in histories.items() if h["error"] and h["error"] != "no history"]
    if unreadable:
        notes.append(f"Couldn't check dividend history for {', '.join(unreadable)}.")

timeline = el.build_timeline(events, today, days, kinds or None)
if timeline.empty:
    st.info(f"Nothing matching falls in the next {days} days.")
else:
    st.dataframe(timeline, hide_index=True, width="stretch", column_config={
        "Date": st.column_config.DateColumn("Date", format="MMM D, YYYY"),
        "In (days)": st.column_config.NumberColumn("In (days)", format="%d"),
    })
for n in notes:
    st.caption(n)
st.caption(f"Earnings and ex-dividend dates are for your watchlist ({'your holdings' if held else 'the sample list'}). "
           "Ex-dividend dates are estimates from each company's payment history: confirm on the company's investor page. "
           f"Fed decisions are built in through {dt.date(2027, 9, 30):%b %Y} and market closures through {dt.date(2027, 12, 31):%b %Y}.")

# ---------- Fill the summary ----------
with summary_box:
    st.subheader("Summary")
    if sp is None:
        st.info("The summary needs market prices, which didn't load. Try Refresh in a minute.")
    else:
        sections = mt.write_summary(idx=idx_returns, latest=latest, sp=sp, vix=vix, ten=ten, table=table, br=br, od=od, spread=spread,
                                    y_short=y_short, y_long=y_long, events=events, today=today)
        if not advanced:
            sections = [s for s in sections if s[0] in ("The short version", "Coming up")]
        for tab, (_title, bullets) in zip(st.tabs([t for t, _ in sections]), sections):
            with tab:
                for b in bullets:
                    st.markdown(f"- {ui.esc(b)}")
        st.caption("Written by rules from the numbers on this page, with no AI. Describes the past, not the future; informational, not financial advice.")
