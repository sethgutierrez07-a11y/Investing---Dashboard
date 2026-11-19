"""Holdings page: the Balance check section (asset mix, sectors, ideas to browse) with fake SnapTrade and fake Finnhub."""

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_holdings_page_smoke as hp  # noqa: E402
import test_personalized_pages_smoke as sp  # noqa: E402
from test_holdings_page_smoke import POSITIONS, rp  # noqa: E402

KEYED = {**hp.GOOD_SECRETS, "FINNHUB_API_KEY": "fh"}
EXTRA = [rp("ZZZZ", 10, 100.0, 90.0), rp("SCHD", 300, 80.0, 70.0, "et", "ETF")]      # an unknown stock and a fund in the built-in table


class Fh(sp.Http):
    def __init__(self, industry="Semiconductors", fail_profile=False):
        super().__init__()
        self.industry, self.fail_profile = industry, fail_profile

    def get(self, url, params=None, headers=None, timeout=None):
        sym = (params or {}).get("symbol")
        resp = super().get(url, params, headers, timeout)
        if url.endswith("/stock/profile2"):
            if self.fail_profile and sym == "ZZZZ":
                resp.raise_for_status.side_effect = RuntimeError("429")
            elif sym == "ZZZZ":
                resp.json.return_value = {"name": "Zed Corp", "finnhubIndustry": self.industry, "country": "US"}
        return resp

    def profile_symbols(self):
        return [p["symbol"] for u, p in self.urls if u.endswith("/stock/profile2")]


def run(monkeypatch, secrets=KEYED, positions=POSITIONS + EXTRA, http=None, preset=None):
    import requests
    http = http or Fh()
    monkeypatch.setattr(requests, "get", http.get)
    st = hp.make_streamlit(False, True, secrets)
    if preset:
        st.selectbox.side_effect = lambda label, options, index=0, **k: preset
    hp.run_page(monkeypatch, st, positions=positions)
    return st, http


def md(st):
    return " ".join(str(c.args[0]) for c in st.markdown.call_args_list if c.args)


def frames(st):
    return [c.args[0] for c in st.dataframe.call_args_list if c.args and isinstance(c.args[0], pd.DataFrame)]


def test_section_renders_with_three_tabs_and_the_growth_leaning_default(monkeypatch):
    st, _ = run(monkeypatch)
    assert "⚖️ Balance check" in [c.args[0] for c in st.subheader.call_args_list]
    labels = [c.args[0] for c in st.tabs.call_args_list][-1]
    assert labels == ["🧱 Asset mix", "🏭 Sectors", "💡 Ideas to browse"]
    assert st.selectbox.call_args.args[1] == ["Balanced", "Balanced, leaning growth", "Growth", "Aggressive growth"]
    assert st.selectbox.call_args.kwargs["index"] == 1
    assert "Balanced, leaning growth:" in " ".join(str(c) for c in st.caption.call_args_list)


def test_every_table_has_unique_named_columns_and_sectors_are_in_the_table(monkeypatch):
    st, _ = run(monkeypatch)
    for f in frames(st):
        cols = [str(c) for c in f.columns]
        assert len(set(cols)) == len(cols) and all(c.strip() for c in cols)
    sec = next(f for f in frames(st) if "Gap (points)" in f.columns)
    assert len(sec) == 11 and set(sec["Read"]) <= {"Heavy", "Light", "Near market"}
    staples = sec[sec["Sector"] == "Consumer Staples"].iloc[0]
    assert staples["Read"] == "Heavy" and "SCHD" in staples["Mostly from"]                  # SCHD is the big staples source here
    assert next(f for f in frames(st) if list(f.columns) == ["Step", "Rule"]) is not None


def test_only_unplaced_stocks_cost_a_profile_lookup_and_get_their_sector(monkeypatch):
    st, http = run(monkeypatch)
    looked_up = http.profile_symbols()
    assert looked_up.count("ZZZZ") == 1
    assert not set(looked_up) & {"AAPL", "MSFT", "VOO", "SCHD"}                                # the built-in table covers these: no call
    assert "Not classified" not in md(st)                                                      # Semiconductors -> Technology: placed
    sec = next(f for f in frames(st) if "Gap (points)" in f.columns)
    assert sec[sec["Sector"] == "Technology"].iloc[0]["You"] > 0


def test_a_failed_profile_lookup_leaves_the_stock_unplaced_without_breaking_the_page(monkeypatch):
    big = [rp("ZZZZ", 100, 100.0, 90.0)]
    st, _ = run(monkeypatch, positions=POSITIONS + big, http=Fh(fail_profile=True))
    assert "Not classified" in md(st) and "ZZZZ" in md(st)
    assert st.plotly_chart.call_count >= 4


def test_without_a_finnhub_key_funds_and_overrides_still_work(monkeypatch):
    st, http = run(monkeypatch, secrets=hp.GOOD_SECRETS)
    assert http.urls == []                                                                      # no Finnhub traffic at all
    assert any("Gap (points)" in f.columns for f in frames(st))
    assert "Today's stock idea" not in md(st)


def test_todays_idea_line_appears_with_a_key_and_names_a_sector_only_when_it_has_one(monkeypatch):
    st, _ = run(monkeypatch)
    line = [c.args[0] for c in st.markdown.call_args_list if c.args and "Today's stock idea" in str(c.args[0])]
    assert len(line) <= 1
    if line:
        assert "is in" in line[0] and "$" not in line[0]


def test_preset_choice_changes_the_reference_numbers(monkeypatch):
    st, _ = run(monkeypatch, preset="Aggressive growth")
    assert "Aggressive growth:" in " ".join(str(c) for c in st.caption.call_args_list)
    st2, _ = run(monkeypatch, preset="Balanced")
    assert "100% stocks" not in " ".join(str(c) for c in st2.caption.call_args_list)


def test_balance_text_never_contains_dollar_amounts(monkeypatch):
    st, _ = run(monkeypatch)
    balance_bullets = [str(c.args[0]) for c in st.markdown.call_args_list if c.args and str(c.args[0]).startswith("- **")]
    assert balance_bullets and not any("$" in b for b in balance_bullets)
    for c in st.metric.call_args_list:
        if c.args and c.args[0] in ("Outside the US", "Growth tilt"):
            assert "$" not in str(c)


def test_a_bonds_and_cash_only_account_does_not_crash_the_section(monkeypatch):
    bonds = [rp("BND", 100, 70.0, 72.0, "et", "ETF")]
    st, _ = run(monkeypatch, positions=bonds)
    assert "No sector data" in " ".join(str(c) for c in st.info.call_args_list)
    assert "Stocks" in " ".join(str(c) for c in st.metric.call_args_list)
