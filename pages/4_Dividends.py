"""
Dividends — what your holdings pay, what is coming, which companies it comes from, and whether
reinvesting (DRIP) helps. Read-only: SnapTrade account activity plus Yahoo Finance history.

Same secrets and lock as the Holdings page (APP_PASSWORD, SNAPTRADE_CLIENT_ID, SNAPTRADE_CONSUMER_KEY).
"""

import time

import pandas as pd
import streamlit as st

import dividend_charts as dc
import dividend_data as dd
import dividend_lib as dl
import dividend_text as dt
import holdings_lib as hl
import portfolio_state as ps

st.set_page_config(page_title="Dividends", layout="wide")

CHART_CFG = {"displayModeBar": False}
MAX_HISTORIES = 20  # tickers whose dividend history we load (cached 12h)
DOLLAR_COLS = ["Annual income", "Received 12m", "Per payment", "Amount", "Value", "Per share"]


def theme_mode() -> str:
    try:
        return "light" if st.context.theme.type == "light" else "dark"
    except Exception:
        return "dark"


# ---------- Access gate (same rules as Holdings; fails closed) ----------
expected = ps.secret("APP_PASSWORD")
if not expected:
    st.title("💰 Dividends")
    st.error(
        "This page shows private account data, so it stays locked until you set a password. "
        'Add `APP_PASSWORD = "choose-something-long"` under ⋮ → Settings → Secrets, then reload.'
    )
    st.stop()

if not st.session_state.get("holdings_unlocked"):
    st.title("💰 Dividends")
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
    st.title("💰 Dividends")
    st.info("Not connected yet. Add `SNAPTRADE_CLIENT_ID` and `SNAPTRADE_CONSUMER_KEY` to Secrets (same as the Holdings page).")
    st.stop()

with st.sidebar:
    st.header("Dividend settings")
    hide = st.toggle("Hide dollar amounts", value=False, help="Show only percentages (good for screenshots).")
    if st.button("Refresh now"):
        st.cache_data.clear()
        st.rerun()
    if st.button("Lock"):
        st.session_state["holdings_unlocked"] = False
        st.rerun()

mode = theme_mode()
TODAY = pd.Timestamp.now(tz="America/Chicago").tz_localize(None).normalize()
UNIT = "%" if hide else "$"


# ---------- Cached readers ----------
@st.cache_data(ttl=3600, show_spinner="Reading your dividend activity…")
def load_activities(accounts: list, day: str) -> dict:
    try:
        client = hl.make_client(ps.secret("SNAPTRADE_CLIENT_ID"), ps.secret("SNAPTRADE_CONSUMER_KEY"))
        return dd.fetch_activities(client, accounts, pd.Timestamp(day))
    except Exception as e:  # noqa: BLE001 — the page still works without received amounts
        return {"items": [], "errors": [type(e).__name__], "shape": {}, "range_days": None}


@st.cache_data(ttl=43200, show_spinner=False)
def load_history(symbol: str) -> dict:
    return dd.fetch_history(symbol)


def cfg(df, mapping: dict) -> dict:
    """Column config only for columns that are actually shown."""
    return {k: v for k, v in mapping.items() if k in df.columns}


def share_of(values, total):
    return [v / total * 100 if total else 0.0 for v in values]


# ---------- Portfolio ----------
portfolio = ps.get_portfolio()
st.title("💰 Dividends")
if portfolio is None:
    st.info(
        "Couldn't read your portfolio right now. Check the Holdings page first: if it loads there, reload this page."
    )
    st.stop()
st.caption("What your holdings pay, what is coming, and whether reinvesting helps. Read-only and informational, not financial advice.")

merged = portfolio["merged"]
syms = [s for s in merged["Symbol"] if s and s != "?"][:MAX_HISTORIES]
accounts = [{k: r["account"].get(k) for k in ("id", "name", "institution_name")}
            for r in portfolio["raw"] if isinstance(r.get("account"), dict) and not r.get("error")]

acts = load_activities(accounts, TODAY.strftime("%Y-%m-%d"))
act = dl.parse_activities(acts["items"])

histories: dict = {}
with st.spinner("Loading each holding's dividend history…"):
    for s in syms:
        histories[s] = load_history(s)
failed = [s for s, h in histories.items() if h["error"] and h["error"] != "no history"]
profiles = {s: dl.dividend_profile(h["divs"], TODAY) for s, h in histories.items() if not h["error"] or h["error"] == "no history"}

shares = {s: float(u) for s, u in zip(merged["Symbol"], merged["Units"]) if pd.notna(u)}
lags = dl.pay_lags(dl.cash_dividends(act), {s: h["divs"] for s, h in histories.items()})
proj = dl.project_payments(shares, profiles, TODAY, 12, lags)
received_ttm = dl.received_by_symbol(act, TODAY)
table = dl.company_table(merged, received_ttm, profiles)
port = dl.portfolio_income(table)
income = dl.income_summary(act, TODAY)
reinv = dl.reinvestment(act)

# ---------- Summary (filled at the end, once the DRIP controls below have been read) ----------
st.subheader("Summary")
summary_box = st.container()
st.divider()

if failed:
    st.warning(f"Couldn't load dividend history for {', '.join(failed)} (Yahoo Finance may be rate-limiting). "
               "They're left out of the projections. Try Refresh in a minute.")
for e in acts["errors"]:
    st.warning(f"Activity: {e}")

# ---------- KPI tiles ----------
k1, k2, k3, k4, k5 = st.columns(5)
with k1.container(border=True):
    st.metric("Expected, next 12 months", "••••" if hide else hl.money(port["annual"]),
              delta=None if hide else f"≈ {hl.money(port['monthly'])} a month", delta_color="off",
              help="Today's share counts × each ticker's latest per-share payout. An estimate, not a promise.")
with k2.container(border=True):
    st.metric("Received, last 12 months", "••••" if hide else (hl.money(income["ttm"]) if income["n"] else "—"),
              delta=(f"{income['growth_pct']:+.0f}% vs year before" if income["growth_pct"] is not None
                     else (f"feed covers only {income['covered_days']} days" if income["n"] and not income["full_year"] else None)),
              delta_color="off", help="From SnapTrade's account activity. Needs a full year of feed to be a true 12 months.")
with k3.container(border=True):
    st.metric("Yield on value", hl.pct(port["yield_pct"], signed=False) if port["yield_pct"] is not None else "—",
              help="Expected yearly income ÷ what your holdings are worth today.")
with k4.container(border=True):
    st.metric("Yield on cost", hl.pct(port["yoc_pct"], signed=False) if port["yoc_pct"] is not None else "—",
              help="Expected yearly income ÷ what you originally paid, for holdings with a known cost basis.")
with k5.container(border=True):
    st.metric("Holdings that pay", f"{port['payers']} of {port['holdings']}")
st.write("")

tab_recv, tab_next, tab_co, tab_drip, tab_grow = st.tabs(
    ["💵 Received", "📅 Coming up", "🏢 By company", "🔁 DRIP", "📈 Growth"])

# ---------- Received ----------
with tab_recv:
    d_all = dl.cash_dividends(act)
    if d_all.empty:
        st.info(
            "No dividend payments came back from SnapTrade's activity feed. Fidelity activity can be limited by the "
            "broker connection. Everything under 'Coming up' still works, because it uses each ticker's own history."
        )
    else:
        m = dl.by_month(act, TODAY, 24)
        total24 = float(m["Amount"].sum())
        vals = share_of(m["Amount"], total24) if hide else list(m["Amount"])
        st.markdown("**Dividends received, by month**")
        st.caption("Last 24 months, by the day the cash arrived." + (" Shown as a share of the 24-month total." if hide else ""))
        st.plotly_chart(dc.month_bars(list(m["Month"].dt.strftime("%b %y")), vals, mode, UNIT), width="stretch", config=CHART_CFG)

        left, right = st.columns(2, gap="large")
        with left:
            st.markdown("**By year**")
            y = dl.by_year(act)
            y["Change %"] = y["Amount"].pct_change() * 100
            yv = y.drop(columns=["Amount"]) if hide else y
            st.dataframe(yv, hide_index=True, width="stretch", column_config=cfg(yv, {
                "Year": st.column_config.NumberColumn(format="%d"),
                "Amount": st.column_config.NumberColumn("Received", format="$%.0f"),
                "Change %": st.column_config.NumberColumn("vs prior year", format="%+.0f%%"),
            }))
            if income["first"] is not None:
                st.caption(f"Activity in the feed starts {income['first']:%b %-d, %Y}, so the earliest year may be partial.")
        with right:
            st.markdown("**Latest payments**")
            rp = dl.recent_payments(act, 12)
            if not reinv["has_rei"]:
                rp = rp.drop(columns=["Reinvested"])
            rp = rp.drop(columns=["Amount"]) if hide else rp
            st.dataframe(rp, hide_index=True, width="stretch", column_config=cfg(rp, {
                "Date": st.column_config.DateColumn(format="MMM D, YYYY"),
                "Amount": st.column_config.NumberColumn(format="$%.2f"),
                "Reinvested": st.column_config.CheckboxColumn("Reinvested?"),
            }))
    with st.expander("Data shape (field names only, no values)"):
        st.json({"activity_rows_returned": len(acts["items"]), "days_requested": acts["range_days"], **acts["shape"]})

# ---------- Coming up ----------
with tab_next:
    if proj.empty:
        st.info("Nothing could be projected: no holding has a regular dividend schedule I could read, "
                "or the payment histories didn't load.")
    else:
        pv = dl.projected_by_month(proj, TODAY, 12)
        order = list(pv.sum().sort_values(ascending=False).index)
        series = {s: list(pv[s]) for s in order[:5]}
        if len(order) > 5:
            series["Other"] = list(pv[order[5:]].sum(axis=1))
        total12 = float(pv.to_numpy().sum())
        if hide:
            series = {k: share_of(v, total12) for k, v in series.items()}
        st.markdown("**Expected dividends, next 12 months**")
        st.caption("Estimated pay month, stacked by company. Uses each ticker's latest per-share payout and today's share "
                   "counts: no raises, cuts or new purchases assumed." + (" Shown as a share of the 12-month total." if hide else ""))
        st.plotly_chart(dc.stacked_months(list(pv.index.strftime("%b %y")), series, mode, UNIT), width="stretch", config=CHART_CFG)
        st.markdown("**Next payments**")
        up = proj.head(12).rename(columns={"PerShare": "Per share"})
        up = up[["PayDate", "Symbol", "ExDate", "Per share", "Amount"]]
        up = up.drop(columns=["Amount", "Per share"]) if hide else up
        st.dataframe(up, hide_index=True, width="stretch", column_config=cfg(up, {
            "PayDate": st.column_config.DateColumn("Est. pay date", format="MMM D, YYYY"),
            "ExDate": st.column_config.DateColumn("Est. ex-dividend date", format="MMM D, YYYY"),
            "Per share": st.column_config.NumberColumn(format="$%.4f"),
            "Amount": st.column_config.NumberColumn("Est. amount", format="$%.2f"),
        }))
        st.caption(f"Pay date = ex-dividend date + your usual delay (about {lags['__default__']} days across your history). "
                   "You must own the shares before the ex-dividend date to receive that payment.")

# ---------- By company ----------
with tab_co:
    payers = table[table["Held"] & (table["Annual income"] > 0)].sort_values("Annual income", ascending=False)
    if payers.empty and table.empty:
        st.info("No holdings to show.")
    else:
        if not payers.empty:
            top = payers.head(8)
            st.markdown("**Where the income comes from, versus how much you've invested**")
            st.caption("A bar longer on the income side means that holding pays more than its size suggests.")
            st.plotly_chart(dc.share_vs_weight(list(top["Symbol"]), list(top["Income share %"]),
                                               [float(v) if pd.notna(v) else 0.0 for v in top["Share of invested %"]], mode),
                            width="stretch", config=CHART_CFG)
        cols = ["Symbol", "Company", "Status", "Pays", "Per payment", "Next ex-date", "Annual income", "Received 12m",
                "Yield %", "Yield on cost %", "Income share %", "Share of invested %"]
        view = table[cols]
        view = view.drop(columns=[c for c in DOLLAR_COLS if c in view.columns]) if hide else view
        st.dataframe(view, hide_index=True, width="stretch", column_config=cfg(view, {
            "Per payment": st.column_config.NumberColumn("Per share / payment", format="$%.4f"),
            "Next ex-date": st.column_config.DateColumn("Next ex-date (est.)", format="MMM D, YYYY"),
            "Annual income": st.column_config.NumberColumn("Yearly income", format="$%.0f"),
            "Received 12m": st.column_config.NumberColumn("Received (12 mo)", format="$%.0f"),
            "Yield %": st.column_config.NumberColumn("Yield", format="%.1f%%"),
            "Yield on cost %": st.column_config.NumberColumn("Yield on cost", format="%.1f%%"),
            "Income share %": st.column_config.ProgressColumn("Share of income", format="%.0f%%", min_value=0, max_value=100),
            "Share of invested %": st.column_config.NumberColumn("Share of invested", format="%.0f%%"),
        }))
        st.caption("'Yield' divides expected yearly income by today's value; 'yield on cost' divides by what you paid. "
                   "ETFs count as one holding here, as on the Holdings page.")

# ---------- DRIP ----------
sim, sim_symbol, cash_apy = None, None, 0.0
with tab_drip:
    st.markdown("**In your account**")
    if not act.empty and reinv["has_rei"] and reinv["rate"] is not None:
        c1, c2 = st.columns(2)
        c1.metric("Dividend cash reinvested", f"{reinv['rate'] * 100:.0f}%")
        rows = []
        px = {s: (float(v) / float(u) if u else None) for s, v, u in zip(merged["Symbol"], merged["Market value"], merged["Units"])}
        for s, units in reinv["units_by_symbol"].items():
            rows.append({"Symbol": s, "Shares added": units,
                         "Worth today": (units * px[s]) if px.get(s) else None,
                         "Reinvested %": reinv["rate_by_symbol"].get(s, 0.0) * 100})
        if rows:
            rdf = pd.DataFrame(rows).sort_values("Shares added", ascending=False)
            rdf = rdf.drop(columns=["Worth today"]) if hide else rdf
            st.dataframe(rdf, hide_index=True, width="stretch", column_config=cfg(rdf, {
                "Shares added": st.column_config.NumberColumn(format="%.4f"),
                "Worth today": st.column_config.NumberColumn(format="$%.0f"),
                "Reinvested %": st.column_config.NumberColumn(format="%.0f%%"),
            }))
    elif not act.empty:
        st.info("No reinvestment rows appear next to your dividends, so they look to be landing as cash. "
                "(Fidelity's reinvestment setting on each position is the source of truth.)")
    else:
        st.info("No activity to check, so I can't tell whether your dividends are reinvested.")

    st.divider()
    st.markdown("**Replay: reinvest vs. take the cash**")
    st.caption(dt.md("Uses a made-up $10,000 and a ticker's REAL past prices and dividends. It shows what reinvesting would have "
                     "done, not what your account did. The past doesn't predict the future."))
    pickable = list(payers["Symbol"])
    other = st.text_input("Or try any ticker", value="", help="For example SCHD or KO. Any dividend payer works.").strip().upper()
    sim_symbol = other or (st.selectbox("Holding to replay", pickable) if pickable else None)
    horizon = st.radio("Look back", ["3 years", "5 years", "10 years", "As far as Yahoo goes"], index=2, horizontal=True)
    cash_apy = st.slider("What the dividend cash would earn if you kept it", min_value=0.0, max_value=6.0, value=0.0,
                         step=0.5, help="0% is the plain baseline. A money-market fund might pay a few percent.") / 100
    years = {"3 years": 3, "5 years": 5, "10 years": 10}.get(horizon)
    if sim_symbol:
        h = histories.get(sim_symbol) or load_history(sim_symbol)
        if h["error"]:
            st.warning(f"Couldn't load history for {sim_symbol}: {h['error']}")
        else:
            lag = int(min(max(lags.get(sim_symbol, lags["__default__"]), 0), 30))
            sim = dl.simulate_drip(h["prices"], h["divs"], years=years, pay_lag_days=lag, cash_apy=cash_apy)
            if sim is None:
                st.info(f"{sim_symbol} doesn't have enough price history with dividends in that window to replay.")
            else:
                sim["symbol"] = sim_symbol
                a, b, c = st.columns(3)
                a.metric("Reinvested", dt.usd(sim["drip_end"]), delta=f"{sim['drip_cagr']:.1f}% a year", delta_color="off")
                b.metric("Dividends as cash", dt.usd(sim["cash_end"]), delta=f"{sim['cash_cagr']:.1f}% a year", delta_color="off")
                c.metric("Reinvesting adds", dt.usd(sim["advantage"]), delta=f"{sim['advantage_pct']:+.1f}%", delta_color="off")
                st.plotly_chart(dc.drip_chart({"Reinvested": sim["drip"], "Dividends as cash": sim["cash"],
                                               "Price only": sim["price_only"]}, mode), width="stretch", config=CHART_CFG)
                st.caption(f"{sim['start']:%b %Y} to {sim['end']:%b %Y}. 'Price only' is the stock without any dividends. "
                           "Reinvesting buys at the close a few days after each ex-dividend date; taxes and trading costs are ignored.")

    st.divider()
    st.markdown("**What if? (a hypothetical, not a forecast)**")
    st.caption(dt.md("Pick your own assumptions and see how reinvesting compounds over time, starting from $10,000."))
    w1, w2, w3, w4 = st.columns(4)
    start_y = round(port["yield_pct"] or 3.0, 1)
    w_yield = w1.slider("Starting yield %", min_value=0.5, max_value=8.0, value=min(max(start_y, 0.5), 8.0), step=0.1)
    w_price = w2.slider("Price growth % a year", min_value=-5.0, max_value=15.0, value=6.0, step=0.5)
    w_div = w3.slider("Dividend growth % a year", min_value=-5.0, max_value=15.0, value=5.0, step=0.5)
    w_years = w4.slider("Years", min_value=5, max_value=40, value=20, step=1)
    wi = dl.project_growth(10_000, w_yield, w_price, w_div, int(w_years), cash_apy * 100)
    st.plotly_chart(dc.whatif_chart(wi, mode), width="stretch", config=CHART_CFG)
    end_row = wi.iloc[-1]
    st.caption(dt.md(f"After {int(w_years)} years: {dt.usd(end_row['DRIP'])} reinvested vs {dt.usd(end_row['Cash'])} as cash "
                     f"(the gap is {dt.usd(end_row['DRIP'] - end_row['Cash'])}). Dividends are paid once a year in this simple model."))

# ---------- Growth ----------
with tab_grow:
    g = table[table["Held"]].dropna(subset=["Growth %"]).sort_values("Growth %", ascending=False)
    if g.empty:
        st.info("Not enough history to measure dividend growth. It needs at least three full calendar years of regular "
                "payments for a holding.")
    else:
        st.markdown("**How fast each dividend has grown (per share, per year)**")
        st.caption("Measured over complete calendar years with the usual number of payments. Special one-off dividends are left out.")
        st.plotly_chart(dc.growth_bars(list(g["Symbol"]), [float(v) for v in g["Growth %"]], mode), width="stretch", config=CHART_CFG)
        gt = g[["Symbol", "Company", "Growth %", "Growth years", "Streak", "Yield %"]]
        st.dataframe(gt, hide_index=True, width="stretch", column_config=cfg(gt, {
            "Growth %": st.column_config.NumberColumn("Growth a year", format="%+.1f%%"),
            "Growth years": st.column_config.NumberColumn("Years measured", format="%d"),
            "Streak": st.column_config.NumberColumn("Higher years in a row", format="%d"),
            "Yield %": st.column_config.NumberColumn("Yield", format="%.1f%%"),
        }))
        st.caption("A rising dividend per share isn't the same as a safe one; check why it is growing before leaning on it.")

# ---------- Fill the summary ----------
with summary_box:
    sections = dt.write_summary(
        income=income, reinv=reinv, port=port, table=table, proj=proj, drip=sim, drip_symbol=sim_symbol, cash_apy=cash_apy,
        activity_ok=bool(acts["items"]) or not acts["errors"], hide=hide)
    for tab, (_title, bullets) in zip(st.tabs([t for t, _ in sections]), sections):
        with tab:
            for b in bullets:
                st.markdown(f"- {dt.md(b)}")
    st.caption("Written by rules from the numbers on this page, with no AI. Estimates only; informational, not financial advice.")
