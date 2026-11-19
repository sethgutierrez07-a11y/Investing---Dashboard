"""
Learn: a tip for today, a plain-English glossary and short reading paths.

No account data, no network calls, no password needed. General education, not advice.
Terms link to the tab where you can see the idea in your own numbers.
"""

import streamlit as st

import ui

import learn_content as lc
import learn_lib as ll

st.set_page_config(page_title="Learn", layout="wide")
ui.apply()

st.title("🎓 Learn")
st.caption("Plain-English explanations of the ideas behind this dashboard, plus one tip a day. General education only, not financial advice.")

# ---------- Tip of the day ----------
today = ui.today_central()
offset = int(st.session_state.get("tip_offset", 0))
tip = ll.tip_of_the_day(today, offset=offset)
ui.tip_card(tip, full=True)
b1, b2, _ = st.columns([1, 1, 4])
with b1:
    another = st.button("Another tip", help="Browse more tips. Tomorrow's tip changes on its own.")
with b2:
    back = bool(offset) and st.button("Back to today's tip")
if another:
    st.session_state["tip_offset"] = offset + 1
    st.rerun()
if back:
    st.session_state["tip_offset"] = 0
    st.rerun()
st.write("")

tab_gloss, tab_paths = st.tabs(["📖 Glossary", "🧭 Reading paths"])

# ---------- Glossary ----------
with tab_gloss:
    c1, c2 = st.columns([2, 3])
    with c1:
        query = st.text_input("Search", placeholder="Try: risk, dividend, beta…", label_visibility="collapsed")
    with c2:
        category = st.radio("Topic", ["All"] + lc.CATEGORIES, horizontal=True, label_visibility="collapsed")
    results = ll.search_glossary(query, category)
    st.caption(f"{len(results)} of {len(lc.GLOSSARY)} terms" + (f" matching “{query.strip()}”" if query.strip() else ""))

    def show(e, expanded):
        with st.expander(f"**{e['term']}**  ·  {e['category']}", expanded=expanded):
            st.markdown(ui.esc(e["short"]))
            st.markdown(ui.esc("**Why it matters:** " + e["why"]))
            if e.get("example"):
                st.markdown(ui.esc("**Example:** " + e["example"]))
            if e.get("app"):
                label, path = e["app"]
                try:
                    st.page_link(path, label=f"See it in {label}", icon="➡️")
                except Exception:
                    pass
            if e["related"]:
                st.caption("Related: " + ", ".join(e["related"]))

    if not results:
        st.info("No terms match that. Try a shorter word, or pick All.")
    elif category == "All" and not query.strip():
        for cat in lc.CATEGORIES:
            group = [e for e in results if e["category"] == cat]
            if group:
                st.markdown(f"##### {cat}")
                for e in sorted(group, key=lambda x: x["term"].lower()):
                    show(e, False)
    else:
        for e in results:
            show(e, len(results) <= 3)

# ---------- Reading paths ----------
with tab_paths:
    st.caption("A good order to read things in. Each path is a handful of terms that build on one another; open the glossary tab for the full explanation.")
    for p in lc.PATHS:
        with st.container(border=True):
            st.markdown(f"**{p['title']}**  ·  {p['level']}")
            st.caption(p["blurb"])
            for i, e in enumerate(ll.path_entries(p), 1):
                st.markdown(ui.esc(f"{i}. **{e['term']}**: {e['short']}"))
