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
# Light = beige ground with black ink; dark = black ground with beige ink. Same two tones, swapped.
PALETTE = {
    "dark": {
        "accent": "#ede6d6", "accent2": "#bdb29b", "glow": "rgba(237,230,214,.16)",
        "card": "#1c1915", "card_border": "#3a352d", "card_hover": "#ede6d6", "card_shadow": "none",
        "hair": "rgba(237,230,214,.26)", "muted": "rgba(237,230,214,.66)", "faint": "rgba(237,230,214,.07)",
        "page": "none", "page_size": "auto",
        "ok": "#8fb07a", "warn": "#d9a441", "off": "#8f8570", "info": "#ede6d6",
    },
    "light": {
        "accent": "#14120f", "accent2": "#6b6358", "glow": "rgba(20,18,15,.14)",
        "card": "#f7f2e7", "card_border": "#cfc5b0", "card_hover": "#14120f", "card_shadow": "none",
        "hair": "rgba(20,18,15,.30)", "muted": "rgba(20,18,15,.66)", "faint": "rgba(20,18,15,.06)",
        "page": "none", "page_size": "auto",
        "ok": "#4f6b3a", "warn": "#8a6a1f", "off": "#6b6358", "info": "#14120f",
    },
}

# Two switchable looks over the same beige-and-black theme. The theme file sets the colors; a look sets
# the type and the shape of things (serif and airy, or mono figures and square panels).
LOOKS = {"editorial": "Editorial", "research": "Research"}
DEFAULT_LOOK = "editorial"


def look() -> str:
    """The look the viewer picked this session (the ?look= address, if they reloaded), else the default."""
    try:
        import streamlit as st
        for v in (st.session_state.get("look"), st.query_params.get("look")):
            if isinstance(v, str) and v in LOOKS:
                return v
    except Exception:
        pass
    return DEFAULT_LOOK


def mode() -> str:
    """'light' or 'dark', whichever theme the viewer is using (dark if Streamlit can't say)."""
    try:
        import streamlit as st
        return "light" if st.context.theme.type == "light" else "dark"
    except Exception:
        return "dark"


def look_css(name: str, p: dict) -> str:
    """Extra rules for one look. Unknown names get the default look."""
    if name == "research":
        return f"""
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=Newsreader:wght@400;500;600&display=swap');
[data-testid="stMainBlockContainer"] :is(h1, h2, h3) {{ font-family: 'Newsreader', Georgia, serif; font-weight: 500; letter-spacing: -0.01em; }}
[data-testid="stMainBlockContainer"] h1 {{ font-size: 2.3rem; line-height: 1.1; }}
[data-testid="stMainBlockContainer"] h1::after {{ width: 100%; height: 2px; margin-top: .7rem; border-radius: 0; background: {p['accent']}; box-shadow: none; }}
[data-testid="stMainBlockContainer"] {{ padding-top: 1.8rem; }}
[data-testid="stMetricValue"] {{ font-family: 'IBM Plex Mono', ui-monospace, monospace; font-weight: 500; font-size: 1.7rem; letter-spacing: -0.02em; }}
[data-testid="stMetricLabel"] p {{ font-family: 'IBM Plex Mono', ui-monospace, monospace; font-size: .66rem; letter-spacing: .12em; }}
[data-testid="stMetricDelta"] {{ font-family: 'IBM Plex Mono', ui-monospace, monospace; font-size: .8rem; }}
[data-testid="stVerticalBlockBorderWrapper"]:is(:has([data-testid="stMetric"]), :has(.ix-tile-note)):not(:has([data-testid="stVerticalBlockBorderWrapper"])) {{ border-radius: 3px; border: 1px solid {p['card_border']}; }}
button[data-baseweb="tab"] {{ font-family: 'IBM Plex Mono', ui-monospace, monospace; font-size: .74rem; text-transform: uppercase; letter-spacing: .08em; }}
[data-baseweb="tab-highlight"] {{ height: 2px; border-radius: 0; box-shadow: none; }}
.ix-eyebrow, .ix-label {{ font-family: 'IBM Plex Mono', ui-monospace, monospace; font-size: .66rem; letter-spacing: .16em; }}
.ix-chip {{ border-radius: 3px; font-family: 'IBM Plex Mono', ui-monospace, monospace; font-size: .72rem; }}
[data-testid="stSidebar"] {{ border-right: 1px solid {p['card_border']}; }}
[data-testid="stHeader"] {{ border-bottom: 1px solid {p['card_border']}; }}
"""
    return f"""
@import url('https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1&display=swap');
[data-testid="stMainBlockContainer"] :is(h1, h2, h3) {{ font-family: 'Instrument Serif', Georgia, serif; font-weight: 400; letter-spacing: -0.02em; }}
[data-testid="stMainBlockContainer"] h1 {{ font-size: 3.4rem; line-height: 1.02; }}
[data-testid="stMainBlockContainer"] h2 {{ font-size: 2.1rem; }}
[data-testid="stMainBlockContainer"] h3 {{ font-size: 1.6rem; }}
[data-testid="stMainBlockContainer"] h1::after {{ width: 100%; height: 1px; margin-top: 1rem; border-radius: 0; background: {p['hair']}; box-shadow: none; }}
[data-testid="stMainBlockContainer"] {{ padding-top: 3rem; }}
[data-testid="stMetricValue"] {{ font-family: 'Instrument Serif', Georgia, serif; font-weight: 400; font-size: 2.6rem; letter-spacing: -0.02em; }}
[data-testid="stVerticalBlockBorderWrapper"]:is(:has([data-testid="stMetric"]), :has(.ix-tile-note)):not(:has([data-testid="stVerticalBlockBorderWrapper"])) {{ border-radius: 4px; padding: .4rem .3rem; }}
[data-baseweb="tab-highlight"] {{ height: 2px; border-radius: 0; box-shadow: none; }}
.ix-chip {{ border-radius: 999px; }}
"""


def css(m: str = "dark", skin: str = "editorial") -> str:
    """The stylesheet for one mode and look. No blank lines on purpose: Markdown ends an HTML block at a blank line."""
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
[data-testid="stVerticalBlockBorderWrapper"]:is(:has([data-testid="stMetric"]), :has(.ix-tile-note)):not(:has([data-testid="stVerticalBlockBorderWrapper"])):hover {{ border-color: {p['card_hover']}; box-shadow: 0 0 0 1px {p['card_hover']}; }}
button[data-baseweb="tab"] {{ font-weight: 600; letter-spacing: .01em; }}
[data-baseweb="tab-list"] {{ gap: .15rem; }}
[data-baseweb="tab-highlight"] {{ height: 3px; border-radius: 3px; box-shadow: 0 0 12px {p['glow']}; }}
[data-testid^="stBaseButton"] {{ transition: box-shadow .2s ease, border-color .2s ease; font-weight: 600; }}
[data-testid^="stBaseButton"]:hover {{ box-shadow: 0 0 0 1px {p['card_hover']}; }}
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
.ix-ok i {{ background: {p['ok']}; }}
.ix-warn i {{ background: {p['warn']}; }}
.ix-off i {{ background: {p['off']}; }}
.ix-info i {{ background: {p['info']}; }}
.ix-tile-note {{ color: {p['muted']}; font-size: .8rem; line-height: 1.45; margin: .15rem 0 0 0; }}
"""
    rules += look_css(skin if skin in LOOKS else DEFAULT_LOOK, p)
    # a CSS @import is only honoured before every other rule, so lift the look's @import lines to the top
    lines = [ln for ln in rules.splitlines() if ln.strip()]
    imports = [ln for ln in lines if ln.startswith("@import")]
    return "\n".join(imports + [ln for ln in lines if not ln.startswith("@import")])


def look_switch() -> str:
    """Show the Editorial / Research switch at the top of the sidebar and return the chosen look.
    The choice lives in this browser session; the address also carries it, so a reload keeps it."""
    import streamlit as st
    current = look()
    picked = None
    try:
        picked = st.sidebar.segmented_control("Look", list(LOOKS), format_func=LOOKS.get, default=current, key="look",
                                              selection_mode="single", width="stretch")
    except Exception:
        pass
    choice = picked if isinstance(picked, str) and picked in LOOKS else current
    try:
        if st.query_params.get("look") != choice:
            st.query_params["look"] = choice
    except Exception:
        pass
    return choice


def apply() -> None:
    """Inject the shared stylesheet. Call once per page, right after st.set_page_config."""
    import streamlit as st
    choice = look_switch()
    st.markdown(f"<style>\n{css(mode(), choice)}\n</style>", unsafe_allow_html=True)


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
