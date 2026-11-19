"""
Learn tab logic: tip of the day, glossary search, reading paths. Pure functions, no Streamlit.

The tip of the day is the same all day for everyone (it depends only on the date) and walks through
every tip before repeating, in a fixed but shuffled order so neighbouring days differ in topic.
"""

from __future__ import annotations

import datetime as dt
import hashlib

import learn_content as lc


def _order(tips: list[dict]) -> list[dict]:
    """Stable shuffle: sort by a hash of the tip id (does not change between runs or Python versions)."""
    return sorted(tips, key=lambda x: hashlib.sha256(x["id"].encode()).hexdigest())


def tip_of_the_day(today: dt.date, tips: list[dict] | None = None, offset: int = 0) -> dict:
    """The tip for `today`. `offset` steps forward for an 'another tip' button without changing the daily one."""
    pool = _order(tips if tips is not None else lc.TIPS)
    if not pool:
        raise ValueError("no tips")
    return pool[(today.toordinal() + offset) % len(pool)]


def index_of(term: str) -> dict[str, dict]:
    return {e["term"].lower(): e for e in lc.GLOSSARY}


def find_term(name: str | None) -> dict | None:
    if not name:
        return None
    return index_of(name).get(name.lower())


def search_glossary(query: str = "", category: str | None = None, entries: list[dict] | None = None) -> list[dict]:
    """Entries whose term, definition or 'why it matters' contains every word of the query. Term matches first."""
    entries = entries if entries is not None else lc.GLOSSARY
    words = [w for w in (query or "").lower().split() if w]
    out = []
    for e in entries:
        if category and category != "All" and e["category"] != category:
            continue
        hay_term = e["term"].lower()
        hay = " ".join([hay_term, e["short"].lower(), e["why"].lower()])
        if all(w in hay for w in words):
            rank = 0 if words and all(w in hay_term for w in words) else 1
            out.append((rank, hay_term, e))
    out.sort(key=lambda x: (x[0], x[1]))
    return [e for _, _, e in out]


def path_entries(path: dict) -> list[dict]:
    return [e for e in (find_term(t) for t in path["terms"]) if e]


def check_content(glossary: list[dict] | None = None, tips: list[dict] | None = None, paths: list[dict] | None = None,
                  page_paths: set[str] | None = None) -> list[str]:
    """Structural problems in the content (empty list = fine). Used by the tests."""
    glossary = glossary if glossary is not None else lc.GLOSSARY
    tips = tips if tips is not None else lc.TIPS
    paths = paths if paths is not None else lc.PATHS
    problems: list[str] = []
    terms = [e["term"] for e in glossary]
    lower = {t.lower() for t in terms}
    if len(lower) != len(terms):
        problems.append("duplicate glossary term")
    for e in glossary:
        if e["category"] not in lc.CATEGORIES:
            problems.append(f"{e['term']}: unknown category")
        for r in e["related"]:
            if r.lower() not in lower:
                problems.append(f"{e['term']}: related term '{r}' not in glossary")
            if r.lower() == e["term"].lower():
                problems.append(f"{e['term']}: relates to itself")
        if e["app"] and page_paths is not None and e["app"][1] not in page_paths:
            problems.append(f"{e['term']}: app page {e['app'][1]} not registered")
    ids = [x["id"] for x in tips]
    if len(set(ids)) != len(ids):
        problems.append("duplicate tip id")
    for x in tips:
        if x["term"] and x["term"].lower() not in lower:
            problems.append(f"tip {x['id']}: term '{x['term']}' not in glossary")
        if x["app"] and page_paths is not None and x["app"] not in page_paths:
            problems.append(f"tip {x['id']}: app page {x['app']} not registered")
    for p in paths:
        for t in p["terms"]:
            if t.lower() not in lower:
                problems.append(f"path {p['title']}: '{t}' not in glossary")
    return problems
