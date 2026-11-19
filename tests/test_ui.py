"""
Look-and-feel checks: the stylesheet, the theme file, the home page's status strip and shortcuts.
These can't judge taste; they catch the things that silently break styling (a blank line that ends the
<style> block, an invalid color, text that is unreadable on its background, a page that forgot ui.apply()).
"""

import datetime as dt
import re
import runpy
import sys
import tomllib
from pathlib import Path
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
import ui  # noqa: E402

THEME = tomllib.loads((ROOT / ".streamlit" / "config.toml").read_text())["theme"]


# ---------------------------------------------------------------- stylesheet
@pytest.mark.parametrize("m", ["light", "dark"])
def test_stylesheet_is_one_unbroken_block(m):
    c = ui.css(m)
    assert "\n\n" not in c and "{p[" not in c and "{{" not in c and "}}" not in c     # no blank lines, no unfilled f-string
    assert c.count("{") == c.count("}")
    for needle in ("stMetricValue", "stMetricLabel", "tab-highlight", "ix-chip", "ix-eyebrow", "stApp"):
        assert needle in c


def test_modes_differ_and_unknown_mode_falls_back_to_dark():
    assert ui.css("light") != ui.css("dark") and ui.css("whatever") == ui.css("dark")


def test_gradient_title_underline_never_clips_the_emoji():
    # background-clip:text with a transparent fill would make an emoji in a title vanish
    assert "text-fill-color" not in ui.css("dark") and "background-clip: text" not in ui.css("dark")


def test_apply_injects_one_style_block_for_the_active_theme():
    for typ, expect in (("light", "#0369a1"), ("dark", "#38bdf8")):
        st = MagicMock()
        st.context.theme.type = typ
        sys.modules["streamlit"], saved = st, sys.modules.get("streamlit")
        try:
            ui.apply()
        finally:
            sys.modules["streamlit"] = saved
        (call,) = st.markdown.call_args_list
        assert call.args[0].startswith("<style>") and call.args[0].rstrip().endswith("</style>")
        assert call.kwargs["unsafe_allow_html"] is True and expect in call.args[0]


def test_mode_defaults_to_dark_when_streamlit_cannot_say():
    st = MagicMock()
    del st.context
    saved = sys.modules.get("streamlit")
    sys.modules["streamlit"] = st
    try:
        assert ui.mode() == "dark"
    finally:
        sys.modules["streamlit"] = saved


# ---------------------------------------------------------------- html helpers
def test_chips_escape_text_and_unknown_tone_falls_back():
    h = ui.chips_html([("<b>x</b> & y", "ok"), ("z", "nonsense")])
    assert "<b>x</b>" not in h and "&lt;b&gt;x&lt;/b&gt; &amp; y" in h
    assert "ix-ok" in h and "ix-off" in h and "\n" not in h and "  " not in h


def test_data_status_wording():
    q = {"A": {"c": 1}, "B": {"c": 2}, "C": None}
    now = dt.datetime(2026, 11, 18, 21, 7, tzinfo=dt.timezone.utc)
    s = dict(ui.data_status(q, configured=True, unlocked=True, has_portfolio=True, now=now))
    assert s["Market data partial · 2/3 quotes"] == "warn" and s["Fidelity connected · read-only"] == "ok"
    assert s["Updated 3:07 PM CT"] == "info"
    allq = ui.data_status({"A": {"c": 1}}, True, False, False, now)
    assert allq[0] == ("Market data live · 1/1 quotes", "ok") and allq[1][0].startswith("Account locked")
    assert ui.data_status({"A": None}, False, False, False, now)[0][0] == "Market data unavailable"
    assert ui.data_status({}, False, False, False, now)[1] == ("Account not connected", "off")
    assert ui.data_status({"A": {"c": 1}}, True, True, False, now)[1][0].startswith("Account couldn't be read")
    assert all("$" not in t for t, _ in allq)


def test_clock_uses_central_time_both_seasons():
    assert ui.clock(dt.datetime(2026, 1, 15, 18, 5, tzinfo=dt.timezone.utc)) == "12:05 PM CT"
    assert ui.clock(dt.datetime(2026, 7, 15, 18, 5, tzinfo=dt.timezone.utc)) == "1:05 PM CT"


def test_nav_tiles_point_at_real_pages_registered_in_app_py():
    app = (ROOT / "app.py").read_text()
    for path, title, _, _ in ui.NAV:
        assert (ROOT / path).exists() and f'st.Page("{path}", title="{title}"' in app
    st = MagicMock()
    st.columns.side_effect = lambda n: [MagicMock() for _ in range(n)]
    saved = sys.modules.get("streamlit")
    sys.modules["streamlit"] = st
    try:
        ui.nav_tiles()
    finally:
        sys.modules["streamlit"] = saved
    assert [c.args[0] for c in st.page_link.call_args_list] == [p for p, *_ in ui.NAV]


def test_nav_tiles_survive_a_failing_page_link():
    st = MagicMock()
    st.columns.side_effect = lambda n: [MagicMock() for _ in range(n)]
    st.page_link.side_effect = RuntimeError("not registered")
    saved = sys.modules.get("streamlit")
    sys.modules["streamlit"] = st
    try:
        ui.nav_tiles()
    finally:
        sys.modules["streamlit"] = saved
    assert st.markdown.called


# ---------------------------------------------------------------- theme file
def lum(hexcolor):
    h = hexcolor.lstrip("#")
    ch = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    ch = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in ch]
    return 0.2126 * ch[0] + 0.7152 * ch[1] + 0.0722 * ch[2]


def ratio(a, b):
    la, lb = sorted((lum(a), lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


@pytest.mark.parametrize("m", ["light", "dark"])
def test_theme_colors_are_valid_and_readable(m):
    t = THEME[m]
    for k, v in t.items():
        if k != "sidebar":
            assert re.fullmatch(r"#[0-9a-fA-F]{6}", v), (m, k, v)
    bg, panel = t["backgroundColor"], t["secondaryBackgroundColor"]
    assert ratio(t["textColor"], bg) >= 7 and ratio(t["textColor"], panel) >= 7          # body text, AAA
    assert ratio(t["primaryColor"], bg) >= 4.5 and ratio(t["linkColor"], bg) >= 4.5      # accent and links read as text
    assert ratio(t["greenColor"], bg) >= 3.5 and ratio(t["redColor"], bg) >= 3.5         # metric deltas
    sb = t["sidebar"]
    assert ratio(t["textColor"], sb["backgroundColor"]) >= 7 and ratio(t["primaryColor"], sb["backgroundColor"]) >= 4.5


def test_light_and_dark_define_the_same_keys():
    assert set(THEME["light"]) == set(THEME["dark"]) and set(THEME["light"]["sidebar"]) == set(THEME["dark"]["sidebar"])


def test_chart_surface_matches_the_page_background():
    import test_lab_charts  # noqa: F401  (installs a plotly stand-in if plotly is missing)
    sys.modules.pop("holdings_charts", None)
    import holdings_charts as hc
    assert hc.TOKENS["dark"]["surface"] == THEME["dark"]["backgroundColor"]
    assert hc.TOKENS["light"]["surface"] == THEME["light"]["backgroundColor"]


def test_fonts_and_streamlit_version_support_the_theme():
    for k in ("font", "headingFont", "codeFont"):
        assert THEME[k].count(":https://fonts.googleapis.com/") == 1
    req = (ROOT / "requirements.txt").read_text()
    assert re.search(r"streamlit>=1\.(5[1-9]|[6-9]\d)", req)           # light/dark theme tables need 1.51+


# ---------------------------------------------------------------- every page uses it
@pytest.mark.parametrize("page", ["dashboard.py", "pages/1_Daily_Brief.py", "pages/2_Holdings.py", "pages/3_Strategy_Lab.py",
                                  "pages/4_Dividends.py", "pages/5_Risk.py", "pages/6_Market.py", "pages/7_Learn.py"])
def test_every_page_applies_the_style_right_after_page_config(page):
    src = (ROOT / page).read_text()
    assert re.search(r"^st\.set_page_config\(.*\)\nui\.apply\(\)\n", src, re.M), page
    assert re.search(r"^import ui$", src, re.M)


# ---------------------------------------------------------------- home page
def home(monkeypatch, unlocked):
    import test_personalized_pages_smoke as sp
    return sp.run(monkeypatch, "dashboard.py", unlocked=unlocked)


def test_home_shows_status_strip_and_shortcuts_locked(monkeypatch):
    st, _, snap = home(monkeypatch, unlocked=False)
    html = " ".join(str(c.args[0]) for c in st.markdown.call_args_list if c.args)
    assert "ix-strip" in html and "Market data live · 3/3 quotes" in html and "Account locked" in html
    assert "Personal research terminal" in html and "<style>" in html
    links = [c.args[0] for c in st.page_link.call_args_list]
    assert links[:len(ui.NAV)] == [p for p, *_ in ui.NAV]              # the tip card adds one more link after the tiles
    assert snap == []                                                  # styling never touches the brokerage


def test_home_status_says_connected_when_unlocked_and_keeps_all_original_content(monkeypatch):
    st, _, _ = home(monkeypatch, unlocked=True)
    html = " ".join(str(c.args[0]) for c in st.markdown.call_args_list if c.args)
    assert "Fidelity connected · read-only" in html
    text = " ".join(str(c) for n in ("title", "caption", "subheader", "metric") for c in getattr(st, n).call_args_list)
    for kept in ("Investing Dashboard", "Your portfolio today", "Your holdings", "Analyst consensus", "Stock of the day"):
        assert kept in text, kept
