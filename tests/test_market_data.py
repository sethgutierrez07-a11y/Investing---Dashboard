"""Market data plumbing: symbol lists, cleaning, parallel fetch. The network call itself is never made."""

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import market_data as md  # noqa: E402


def test_symbol_lists_are_consistent():
    assert len({s for s, _ in md.INDEXES}) == 4 and len(md.SECTORS) == 11 and len(md.RATES) == 4
    for group in (md.INDEXES, md.RATES, md.SECTORS, md.OTHER):
        assert all(isinstance(s, str) and isinstance(n, str) and n for s, n in group)
    assert set(md.CORE) == {s for s, _ in md.INDEXES} | {"^VIX", "^TNX"}
    assert not set(md.CORE) & set(md.EXTRA)                         # nothing fetched twice
    assert "^TNX" not in md.EXTRA                                   # the 10-year is in CORE
    all_syms = set(md.CORE) | set(md.EXTRA)
    assert all_syms == {s for g in (md.INDEXES, md.RATES, md.SECTORS, md.OTHER) for s, _ in g} | {"^VIX"}


def test_clean_sorts_dedups_and_drops_bad_rows():
    idx = pd.to_datetime(["2026-11-17", "2026-11-16", "2026-11-18", "2026-11-18"])
    out = md.clean(pd.Series([2.0, 1.0, 3.0, 3.0], index=idx))
    assert out["error"] is None and list(out["close"]) == [1.0, 2.0, 3.0]
    assert md.clean(None)["error"] == "no data" and md.clean(pd.Series(dtype=float))["error"] == "no data"
    assert md.clean(pd.Series([0.0, -1.0], index=idx[:2]))["error"] == "no data"


def test_fetch_many_dedups_keeps_order_and_passes_period():
    calls = []

    def fake(sym, period):
        calls.append((sym, period))
        return {"close": pd.Series([1.0]), "error": None}

    out = md.fetch_many(["B", "A", "B", "C"], "5d", fetcher=fake)
    assert list(out) == ["B", "A", "C"] and sorted(calls) == [("A", "5d"), ("B", "5d"), ("C", "5d")]
    assert md.fetch_many([], fetcher=fake) == {}


def test_one_failure_does_not_lose_the_others():
    def fake(sym, period):
        return {"close": pd.Series(dtype=float), "error": "Yahoo didn't answer (X)."} if sym == "BAD" else {"close": pd.Series([1.0]), "error": None}

    out = md.fetch_many(["A", "BAD", "C"], fetcher=fake)
    assert out["BAD"]["error"] and out["A"]["error"] is None and out["C"]["error"] is None


def test_fetch_close_never_raises(monkeypatch):
    class Boom:
        def __init__(self, s):
            pass

        def history(self, **k):
            raise RuntimeError("429")

    import types
    fake_yf = types.SimpleNamespace(Ticker=Boom)
    monkeypatch.setitem(sys.modules, "yfinance", fake_yf)
    r = md.fetch_close("^GSPC")
    assert r["close"].empty and "Yahoo didn't answer" in r["error"]

    class Empty(Boom):
        def history(self, **k):
            return pd.DataFrame()

    monkeypatch.setitem(sys.modules, "yfinance", types.SimpleNamespace(Ticker=Empty))
    assert md.fetch_close("^GSPC")["error"] == "no data"

    class Good(Boom):
        def history(self, **k):
            assert k["auto_adjust"] is True and k["interval"] == "1d"
            return pd.DataFrame({"Close": [1.0, 2.0]}, index=pd.to_datetime(["2026-11-17", "2026-11-18"]).tz_localize("America/New_York"))

    monkeypatch.setitem(sys.modules, "yfinance", types.SimpleNamespace(Ticker=Good))
    r = md.fetch_close("^GSPC")
    assert r["error"] is None and list(r["close"]) == [1.0, 2.0] and r["close"].index.tz is None
