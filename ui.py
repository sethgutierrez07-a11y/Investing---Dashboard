"""
Shared look and feel. One place for the polish so every page matches.

How it works:
  * Colors, fonts and radii are native Streamlit theme settings in .streamlit/config.toml.
  * apply() adds a small CSS layer on top (page glow, type, metric cards, tabs, dividers).
    It only uses Streamlit's public data-testid hooks, and every rule is "nice to have": if a future
    Streamlit version renames something, that one rule stops applying and the page still works.
  * Small HTML helpers for the home page: eyebrow(), status_strip(), nav_tiles().

Streamlit is imported inside the functions so tests can swap it out without stale module state.
Nothing here reads or shows account data.
"""

from __future__ import annotations

import datetime as dt
from html import escape

# Mode-specific colors for the CSS layer. Chart colors stay in holdings_charts (validated palette).
PALETTE = {
    "dark": {
        "accent": "#38bdf8", "accent2": "#a78bfa", "glow": "rgba(56,189,248,.38)",
        "card": "linear-gradient(160deg, rgba(56,189,248,.060), rgba(167,139,250,.030) 60%, rgba(255,255,255,.015))",
        "card_border": "rgba(120,150,200,.22)", "card_hover": "rgba(56,189,248,.60)", "card_shadow": "0 1px 0 rgba(255,255,255,.04) inset",
        "hair": "rgba(148,163,184,.30)", "muted": "rgba(230,237,247,.64)", "faint": "rgba(148,163,184,.16)",
        "page": ("radial-gradient(1100px 520px at 8% -12%, rgba(56,189,248,.13), transparent 62%),"
                 "radial-gradient(900px 440px at 100% -8%, rgba(167,139,250,.10), transparent 58%),"
                 "linear-gradient(rgba(148,163,184,.035) 1px, transparent 1px),"
                 "linear-gradient(90deg, rgba(148,163,184,.035) 1px, transparent 1px)"),
        "page_size": "auto, auto, 46px 46px, 46px 46px",
        "ok": "#2bb673", "warn": "#e8a317", "off": "#8b98ad", "info": "#38bdf8",
    },
    "light": {
        "accent": "#0369a1", "accent2": "#6d4fd6", "glow": "rgba(3,105,161,.22)",
        "card": "linear-gradient(180deg, #ffffff, rgba(255,255,255,.82))",
        "card_border": "rgba(15,23,42,.11)", "card_hover": "rgba(3,105,161,.55)",
        "card_shadow": "0 1px 2px rgba(15,23,42,.05), 0 10px 26px -14px rgba(15,23,42,.14)",
        "hair": "rgba(15,23,42,.18)", "muted": "rgba(15,23,42,.62)", "faint": "rgba(15,23,42,.08)",
        "page": ("radial-gradient(1000px 460px at 6% -14%, rgba(3,105,161,.08), transparent 62%),"
                 "radial-gradient(800px 400px at 100% -10%, rgba(109,79,214,.06), transparent 58%)"),
        "page_size": "auto, auto",
        "ok": "#0b8a55", "warn": "#b7791f", "off": "#64748b", "info": "#0369a1",
    },
}


def mode() -> str:
    """'light' or 'dark', whichever theme the viewer is using (dark if Streamlit can't say)."""
    try:
        import streamlit as st
        return "light" if st.context.theme.type == "light" else "dark"
    except Exception:
        return "dark"


def css(m: str = "dark") -> str:
    """The stylesheet for one mode. No blank lines on purpose: Markdown ends an HTML block at a blank line."""
    p = PALETTE["light" if m == "light" else "dark"]
    rules = f"""
@keyframes ix-pulse {{ 0% {{ box-shadow: 0 0 0 0 {p['glow']}; }} 70% {{ box-shadow: 0 0 0 7px rgba(0,0,0,0); }} 100% {{ box-shadow: 0 0 0 0 rgba(0,0,0,0); }} }}
[data-testid="stElementContainer"]:has(> [data-testid="stMarkdown"] style) {{ display: none; }}
[data-testid="stApp"] {{ background-image: {p['page']}; background-size: {p['page_size']}; background-attachment: fixed; }}
[data-testid="stHeader"] {{ background: transparent; }}
[data-testid="stDecoration"] {{ display: none; }}
[data-testid="stMainBlockContainer"] {{ max-width: 1400px; padding-top: 2.6rem; padding-bottom: 4rem; }}
::selection {{ background: {p['glow']}; }}
h1, h2, h3 {{ letter-spacing: -0.02em; }}
[data-testid="stMainBlockContainer"] h1 {{ font-weight: 700; font-size: 2.35rem; line-height: 1.12; }}
[data-testid="stMainBlockContainer"] h1::after {{ content: ""; display: block; width: 68px; height: 3px; margin-top: .6rem; border-radius: 3px; background: linear-gradient(90deg, {p['accent']}, {p['accent2']}); box-shadow: 0 0 16px {p['glow']}; }}
[data-testid="stMainBlockContainer"] h3 {{ font-weight: 650; }}
[data-testid="stCaptionContainer"] {{ line-height: 1.55; }}
[data-testid="stMetricLabel"] p {{ text-transform: uppercase; letter-spacing: .09em; font-size: .70rem; font-weight: 600; opacity: .72; }}
[data-testid="stMetricValue"] {{ font-family: 'Space Grotesk', Inter, system-ui, sans-serif; font-weight: 600; font-size: 2rem; letter-spacing: -0.02em; font-variant-numeric: tabular-nums; }}
[data-testid="stMetricDelta"] {{ font-variant-numeric: tabular-nums; font-weight: 600; }}
[data-testid="stVerticalBlockBorderWrapper"]:is(:has([data-testid="stMetric"]), :has(.ix-tile-note)):not(:has([data-testid="stVerticalBlockBorderWrapper"])) {{ background: {p['card']}; border-color: {p['card_border']}; box-shadow: {p['card_shadow']}; transition: border-color .2s ease, box-shadow .2s ease; }}
[data-testid="stVerticalBlockBorderWrapper"]:is(:has([data-testid="stMetric"]), :has(.ix-tile-note)):not(:has([data-testid="stVerticalBlockBorderWrapper"])):hover {{ border-color: {p['card_hover']}; box-shadow: 0 0 0 1px {p['card_hover']}, 0 8px 28px -12px {p['glow']}; }}
button[data-baseweb="tab"] {{ font-weight: 600; letter-spacing: .01em; }}
[data-baseweb="tab-list"] {{ gap: .15rem; }}
[data-baseweb="tab-highlight"] {{ height: 3px; border-radius: 3px; box-shadow: 0 0 12px {p['glow']}; }}
[data-testid^="stBaseButton"] {{ transition: box-shadow .2s ease, border-color .2s ease; font-weight: 600; }}
[data-testid^="stBaseButton"]:hover {{ box-shadow: 0 0 0 1px {p['card_hover']}, 0 6px 22px -10px {p['glow']}; }}
[data-testid="stMainBlockContainer"] hr {{ border: none; height: 1px; background: linear-gradient(90deg, transparent, {p['hair']}, transparent); margin: 1.6rem 0; }}
[data-testid="stExpander"] summary {{ font-weight: 600; }}
[data-testid="stSidebar"] {{ background-image: linear-gradient(180deg, {p['faint']}, transparent 38%); }}
[data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3 {{ font-size: 1.05rem; text-transform: uppercase; letter-spacing: .09em; opacity: .8; }}
::-webkit-scrollbar {{ width: 10px; height: 10px; }}
::-webkit-scrollbar-thumb {{ background: {p['hair']}; border-radius: 10px; border: 2px solid transparent; background-clip: content-box; }}
.ix-eyebrow {{ display: flex; align-items: center; gap: .55rem; font-size: .72rem; font-weight: 700; letter-spacing: .22em; text-transform: uppercase; color: {p['accent']}; margin: 0 0 .35rem 0; }}
.ix-dot {{ width: 8px; height: 8px; border-radius: 50%; background: {p['ok']}; animation: ix-pulse 2.4s ease-out infinite; }}
.ix-label {{ font-size: .72rem; font-weight: 700; letter-spacing: .18em; text-transform: uppercase; color: {p['accent']}; margin: 0 0 .3rem 0; }}
.ix-tip {{ font-size: 1.12rem; line-height: 1.6; margin: .1rem 0 .5rem 0; }}
.ix-strip {{ display: flex; flex-wrap: wrap; gap: .5rem; margin: .2rem 0 1rem 0; }}
.ix-chip {{ display: inline-flex; align-items: center; gap: .45rem; padding: .28rem .7rem; border-radius: 999px; font-size: .78rem; font-weight: 600; letter-spacing: .01em; border: 1px solid {p['card_border']}; background: {p['faint']}; white-space: nowrap; }}
.ix-chip i {{ width: 7px; height: 7px; border-radius: 50%; display: inline-block; }}
.ix-ok i {{ background: {p['ok']}; box-shadow: 0 0 8px {p['ok']}; }}
.ix-warn i {{ background: {p['warn']}; box-shadow: 0 0 8px {p['warn']}; }}
.ix-off i {{ background: {p['off']}; }}
.ix-info i {{ background: {p['info']}; box-shadow: 0 0 8px {p['info']}; }}
.ix-tile-note {{ color: {p['muted']}; font-size: .8rem; line-height: 1.45; margin: .15rem 0 0 0; }}
"""
    return "\n".join(line for line in rules.splitlines() if line.strip())


def apply() -> None:
    """Inject the shared stylesheet. Call once per page, right after st.set_page_config."""
    import streamlit as st
    st.markdown(f"<style>\n{css(mode())}\n</style>", unsafe_allow_html=True)


# ---------------------------------------------------------------- small HTML pieces (home page)
def esc(text: str) -> str:
    """Escape $ so Streamlit's Markdown does not read "$10 ... $20" as a math formula."""
    return (text or "").replace("$", "\\$")


def today_central(now: dt.datetime | None = None) -> dt.date:
    """Today's date in the owner's time zone (the server runs in UTC, which is a day ahead each evening)."""
    try:
        from zoneinfo import ZoneInfo
        return (now or dt.datetime.now(dt.timezone.utc)).astimezone(ZoneInfo("America/Chicago")).date()
    except Exception:
        return (now or dt.datetime.now(dt.timezone.utc)).date()


def label(text: str) -> None:
    import streamlit as st
    st.markdown(f'<div class="ix-label">{escape(text)}</div>', unsafe_allow_html=True)


def tip_card(tip: dict, full: bool = False) -> None:
    """A bordered card with one tip. `full` adds the 'read next' line for the Learn page."""
    import streamlit as st
    import learn_lib as ll
    with st.container(border=True):
        label(f"💡 Tip of the day · {tip['topic']}")
        st.markdown(f'<div class="ix-tip">{escape(tip["text"])}</div>', unsafe_allow_html=True)
        entry = ll.find_term(tip.get("term"))
        if full and entry:
            st.caption(esc(f"Read next in the glossary: {entry['term']}. {entry['short']}"))
        if tip.get("app") and full:
            names = {p: (title, icon) for p, title, icon, _ in NAV}
            title, icon = names.get(tip["app"], ("this tab", "➡️"))
            try:
                st.page_link(tip["app"], label=f"See it in {title}", icon=icon)
            except Exception:
                pass
        elif not full:
            try:
                st.page_link("pages/7_Learn.py", label="More tips and the glossary", icon="🎓")
            except Exception:
                pass


def deep_dive_button(symbol: str, key: str, label: str = "Open the full deep-dive →") -> None:
    """Jump to the Stock Deep-Dive tab with this ticker preselected."""
    import streamlit as st
    if st.button(label, key=key):
        st.session_state["deep_symbol"] = symbol
        try:
            st.switch_page("pages/8_Deep_Dive.py")
        except Exception:
            st.info("Open the Stock Deep-Dive tab to see it.")


def idea_compact(res: dict, key: str) -> None:
    """Short Stock-of-the-day card for pages that are not the dashboard. `res` is idea_state.screen_today()'s result."""
    import streamlit as st
    best = res.get("best")
    with st.container(border=True):
        label("💡 Stock of the day · an idea to research")
        if not best:
            st.caption("Couldn't screen enough candidates right now (the free data plan has a per-minute limit). Try again in a minute.")
            return
        sym = best["symbol"]
        day = best.get("day_pct")
        head = f"**{sym}**" + (f" · {res['name']}" if res.get("name") else "")
        if best.get("price"):
            head += f" · ${best['price']:,.2f}" + (f" ({day:+.2f}% today)" if day is not None else "")
        st.markdown(esc(head))
        good = "; ".join(f"{lab.lower()}" for lab, _ in best["pros"][:3]) or "nothing stood out"
        watch = "; ".join(f"{lab.lower()}" for lab, _ in best["cons"][:3]) or "no red flags on these measures"
        st.markdown(esc(f"Looks good: {good}. Watch: {watch}."))
        st.caption("A screen on past numbers, not a recommendation.")
        deep_dive_button(sym, key)


def eyebrow(text: str) -> None:
    import streamlit as st
    st.markdown(f'<div class="ix-eyebrow"><span class="ix-dot"></span>{escape(text)}</div>', unsafe_allow_html=True)


def chips_html(chips: list[tuple[str, str]]) -> str:
    """chips = [(text, tone)] with tone in ok / warn / off / info. Single line: no blank lines, no indentation."""
    body = "".join(
        f'<span class="ix-chip ix-{tone if tone in ("ok", "warn", "off", "info") else "off"}"><i></i>{escape(text)}</span>'
        for text, tone in chips
    )
    return f'<div class="ix-strip">{body}</div>'


def status_strip(chips: list[tuple[str, str]]) -> None:
    import streamlit as st
    if chips:
        st.markdown(chips_html(chips), unsafe_allow_html=True)


def clock(now: dt.datetime | None = None) -> str:
    """'3:07 PM CT' in the owner's time zone (the server runs in UTC)."""
    try:
        from zoneinfo import ZoneInfo
        t = (now or dt.datetime.now(dt.timezone.utc)).astimezone(ZoneInfo("America/Chicago"))
        return f"{t.strftime('%I:%M %p').lstrip('0')} CT"
    except Exception:
        t = now or dt.datetime.now(dt.timezone.utc)
        return f"{t.strftime('%H:%M')} UTC"


def data_status(quotes: dict, configured: bool, unlocked: bool, has_portfolio: bool, now: dt.datetime | None = None) -> list[tuple[str, str]]:
    """The 'is everything healthy?' chips. Pure: takes plain facts, returns [(text, tone)]."""
    total = len(quotes)
    live = sum(1 for q in quotes.values() if q and q.get("c"))
    if total == 0:
        market = ("Market data: nothing to load", "off")
    elif live == total:
        market = (f"Market data live · {live}/{total} quotes", "ok")
    elif live:
        market = (f"Market data partial · {live}/{total} quotes", "warn")
    else:
        market = ("Market data unavailable", "warn")
    if has_portfolio:
        account = ("Fidelity connected · read-only", "ok")
    elif configured and not unlocked:
        account = ("Account locked · unlock in sidebar", "warn")
    elif configured:
        account = ("Account couldn't be read right now", "warn")
    else:
        account = ("Account not connected", "off")
    return [market, account, (f"Updated {clock(now)}", "info"), ("No trading · this app can't place orders", "off")]


NAV = [
    ("pages/1_Daily_Brief.py", "Daily Brief", "🗞️", "What changed in your holdings: news, earnings and filings."),
    ("pages/2_Holdings.py", "Holdings", "💼", "Your positions, allocation and gains at a glance."),
    ("pages/3_Strategy_Lab.py", "Strategy Lab", "🧪", "Test a trading rule honestly against just holding."),
    ("pages/4_Dividends.py", "Dividends", "💰", "Income received, what's coming, and reinvesting."),
    ("pages/5_Risk.py", "Risk", "🛡️", "How bumpy your mix is and how it holds up in a fall."),
    ("pages/6_Market.py", "Market", "🌐", "Indexes, sectors, rates and a calendar of what's coming."),
    ("pages/8_Deep_Dive.py", "Stock Deep-Dive", "🔬", "One company in plain words: key numbers, pros and cons."),
    ("pages/7_Learn.py", "Learn", "🎓", "A plain-English glossary and a financial tip every day."),
]


def nav_tiles(per_row: int = 4) -> None:
    """Shortcuts to the other pages, a few per row. If linking fails for any reason the page still loads."""
    import streamlit as st
    for start in range(0, len(NAV), per_row):
        chunk = NAV[start:start + per_row]
        cols = st.columns(per_row)
        for col, (path, title, icon, note) in zip(cols, chunk):
            with col.container(border=True):
                try:
                    st.page_link(path, label=title, icon=icon)
                except Exception:
                    st.markdown(f"**{icon} {title}**")
                st.markdown(f'<p class="ix-tile-note">{escape(note)}</p>', unsafe_allow_html=True)
