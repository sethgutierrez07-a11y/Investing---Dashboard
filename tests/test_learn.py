"""Learn tab: content structure, tip of the day, glossary search, and the page itself."""

import datetime as dt
import re
import runpy
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
import learn_content as lc  # noqa: E402
import learn_lib as ll  # noqa: E402

PAGE_PATHS = set(re.findall(r'st\.Page\("([^"]+)"', (ROOT / "app.py").read_text()))
HYPE = ["guaranteed", "can't lose", "cannot lose", "risk-free", "risk free", "will go up", "easy money", "get rich", "always wins", "never fails"]


# ---------------------------------------------------------------- content
def test_content_has_no_structural_problems():
    assert ll.check_content(page_paths=PAGE_PATHS) == []
    assert len(lc.GLOSSARY) >= 40 and len(lc.TIPS) >= 60


def test_check_content_catches_each_kind_of_problem():
    g = [dict(term="A", category="Basics", short="s", why="w", example=None, app=("Risk", "pages/nope.py"), related=("B", "A"))]
    t = [dict(id="x", topic="T", text="t", term="Zzz", app=None), dict(id="x", topic="T", text="t", term=None, app="pages/nope.py")]
    p = [dict(title="P", level="l", blurb="b", terms=["Missing"])]
    bad = ll.check_content(g, t, p, PAGE_PATHS)
    joined = " | ".join(bad)
    for needle in ("related term 'B'", "relates to itself", "not registered", "duplicate tip id", "term 'Zzz'", "'Missing' not in glossary"):
        assert needle in joined
    dup = ll.check_content(g + [dict(g[0], term="a")], [], [], None)
    assert "duplicate glossary term" in dup
    assert "unknown category" in " ".join(ll.check_content([dict(g[0], category="Nope", related=())], [], [], None))


def test_entries_are_plain_and_bounded():
    for e in lc.GLOSSARY:
        assert 40 <= len(e["short"]) <= 330, e["term"]
        assert 25 <= len(e["why"]) <= 330, e["term"]
        assert e["short"].rstrip().endswith((".", ")")) and e["why"].rstrip().endswith((".", ")"))
    for x in lc.TIPS:
        assert 40 <= len(x["text"]) <= 300, x["id"]
        assert "$" not in x["text"], x["id"]               # the tip card renders HTML, where a stray $ would be a math marker elsewhere


def test_no_hype_or_certainty_language_anywhere():
    blobs = [" ".join(str(v) for v in e.values()).lower() for e in lc.GLOSSARY] + [x["text"].lower() for x in lc.TIPS]
    for b in blobs:
        for w in HYPE:
            # allowed only when negated ("never guaranteed") or when quoted as a scam warning ("words like guaranteed ...")
            negated = re.search(r"(no|not|nothing|never|isn't|aren't|neither)[^.]{0,40}" + re.escape(w), b)
            warning = re.search(r"words like[^.]*" + re.escape(w) + r"[^.]*scam", b)
            if w in b and not (negated or warning):
                pytest.fail(f"{w!r} in: {b[:80]}")


def test_tip_topics_are_varied_and_paths_are_sensible():
    assert len({x["topic"] for x in lc.TIPS}) >= 6
    assert len(lc.PATHS) >= 4
    for p in lc.PATHS:
        assert 3 <= len(p["terms"]) <= 12 and len(ll.path_entries(p)) == len(p["terms"])


# ---------------------------------------------------------------- tip of the day
def test_tip_is_the_same_all_day_and_changes_daily():
    d = dt.date(2026, 11, 19)
    assert ll.tip_of_the_day(d) == ll.tip_of_the_day(d)
    assert ll.tip_of_the_day(d) != ll.tip_of_the_day(d + dt.timedelta(days=1))


def test_no_repeat_until_every_tip_has_been_shown():
    n = len(lc.TIPS)
    start = dt.date(2026, 1, 1)
    ids = [ll.tip_of_the_day(start + dt.timedelta(days=i))["id"] for i in range(n)]
    assert len(set(ids)) == n                                # a full cycle covers every tip exactly once
    assert ll.tip_of_the_day(start)["id"] == ll.tip_of_the_day(start + dt.timedelta(days=n))["id"]


def test_neighbouring_days_rarely_share_a_topic():
    start = dt.date(2026, 1, 1)
    topics = [ll.tip_of_the_day(start + dt.timedelta(days=i))["topic"] for i in range(len(lc.TIPS))]
    same = sum(a == b for a, b in zip(topics, topics[1:]))
    assert same <= len(topics) * 0.3


def test_order_does_not_depend_on_input_order():
    d = dt.date(2026, 5, 5)
    assert ll.tip_of_the_day(d, tips=lc.TIPS) == ll.tip_of_the_day(d, tips=list(reversed(lc.TIPS)))


def test_offset_steps_through_other_tips_without_changing_the_daily_one():
    d = dt.date(2026, 11, 19)
    seen = {ll.tip_of_the_day(d, offset=k)["id"] for k in range(5)}
    assert len(seen) == 5 and ll.tip_of_the_day(d, offset=0) == ll.tip_of_the_day(d)
    assert ll.tip_of_the_day(d, offset=len(lc.TIPS)) == ll.tip_of_the_day(d)


def test_empty_tip_list_raises_clearly():
    with pytest.raises(ValueError):
        ll.tip_of_the_day(dt.date(2026, 1, 1), tips=[])


# ---------------------------------------------------------------- search
def test_search_finds_by_term_definition_and_is_case_insensitive():
    assert [e["term"] for e in ll.search_glossary("DIVIDEND")][0].lower().startswith("dividend")
    assert ll.search_glossary("zzzzqqq") == []
    assert len(ll.search_glossary("")) == len(lc.GLOSSARY)


def test_search_requires_every_word_and_ranks_term_matches_first():
    one = ll.search_glossary("yield")
    two = ll.search_glossary("yield curve")
    assert 0 < len(two) <= len(one)
    assert "yield" in one[0]["term"].lower()
    for e in two:
        assert "yield" in (e["term"] + e["short"] + e["why"]).lower() and "curve" in (e["term"] + e["short"] + e["why"]).lower()


def test_search_filters_by_category():
    for cat in lc.CATEGORIES:
        assert all(e["category"] == cat for e in ll.search_glossary("", cat))
    assert len(ll.search_glossary("", "All")) == len(lc.GLOSSARY)
    assert {e["category"] for e in lc.GLOSSARY} == set(lc.CATEGORIES)          # no empty category tab


def test_find_term():
    assert ll.find_term("stock")["term"] == "Stock"
    assert ll.find_term(None) is None and ll.find_term("nonsense") is None


# ---------------------------------------------------------------- the page
def make_streamlit(query="", category="All", offset=0, press=None):
    st = MagicMock(name="streamlit")
    st.session_state = {"tip_offset": offset} if offset else {}
    st.text_input.return_value = query
    st.radio.return_value = category
    st.button.side_effect = lambda label, **k: label == press
    st.columns.side_effect = lambda spec, **k: [MagicMock() for _ in range(spec if isinstance(spec, int) else len(spec))]
    st.tabs.side_effect = lambda labels: [MagicMock() for _ in labels]
    st.context.theme.type = "dark"
    st.rerun.side_effect = RuntimeError("rerun")
    return st


def run(monkeypatch, st):
    monkeypatch.setitem(sys.modules, "streamlit", st)
    runpy.run_path(str(ROOT / "pages" / "7_Learn.py"), run_name="__main__")


def md(st):
    return " ".join(str(c.args[0]) for c in st.markdown.call_args_list if c.args)


def test_page_renders_tip_glossary_and_paths_with_no_network_or_account(monkeypatch):
    st = make_streamlit()
    run(monkeypatch, st)
    html = md(st)
    assert "Tip of the day" in html and "<style>" in html
    assert st.expander.call_count == len(lc.GLOSSARY)
    for p in lc.PATHS:
        assert p["title"] in html
    assert not st.secrets.__getitem__.called                                   # never asks for a key
    assert [c.args[0] for c in st.tabs.call_args_list] == [["📖 Glossary", "🧭 Reading paths"]]


def test_page_search_filters_and_opens_few_results(monkeypatch):
    st = make_streamlit(query="dividend")
    run(monkeypatch, st)
    n = len(ll.search_glossary("dividend"))
    assert 0 < st.expander.call_count == n < len(lc.GLOSSARY)
    if n <= 3:
        assert all(c.kwargs["expanded"] for c in st.expander.call_args_list)


def test_page_no_match_message(monkeypatch):
    st = make_streamlit(query="zzzzqqq")
    run(monkeypatch, st)
    assert st.expander.call_count == 0 and "No terms match" in " ".join(str(c) for c in st.info.call_args_list)


def test_another_tip_button_advances_and_back_button_resets(monkeypatch):
    st = make_streamlit(press="Another tip")
    with pytest.raises(RuntimeError):
        run(monkeypatch, st)
    assert st.session_state["tip_offset"] == 1
    st = make_streamlit(offset=3, press="Back to today's tip")
    with pytest.raises(RuntimeError):
        run(monkeypatch, st)
    assert st.session_state["tip_offset"] == 0


def test_dollar_signs_in_glossary_are_escaped_for_markdown(monkeypatch):
    st = make_streamlit(query="market cap")
    run(monkeypatch, st)
    text = md(st)
    assert "$" not in text.replace("\\$", "")


def test_home_shows_the_tip_of_the_day(monkeypatch):
    import test_personalized_pages_smoke as sp
    st, _, _ = sp.run(monkeypatch, "dashboard.py", unlocked=False)
    html = " ".join(str(c.args[0]) for c in st.markdown.call_args_list if c.args)
    assert "Tip of the day" in html
    assert "pages/7_Learn.py" in [c.args[0] for c in st.page_link.call_args_list]
