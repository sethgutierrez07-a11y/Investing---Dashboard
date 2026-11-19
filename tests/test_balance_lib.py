"""Balance check: reference tables stay sane, classification, the mix maths, comparisons, plain-words suggestions, chart."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_lab_charts  # noqa: F401,E402  (installs a plotly stand-in if plotly is missing)

for m in ("balance_charts", "risk_charts", "holdings_charts"):
    sys.modules.pop(m, None)
import balance_charts as bc  # noqa: E402
import balance_data as bd  # noqa: E402
import balance_lib as bal  # noqa: E402

IT, FIN, COMM, DISC, HEALTH, IND, STAPLES, ENERGY, UTIL, RE, MAT = bd.SECTORS


# ---------------------------------------------------------------- reference tables
def test_market_weights_add_to_100_and_cover_the_eleven_sectors():
    assert len(bd.SECTORS) == 11 and set(bd.MARKET) == set(bd.SECTORS)
    assert sum(bd.MARKET.values()) == pytest.approx(100.0, abs=0.5)


@pytest.mark.parametrize("sym", sorted(bd.FUNDS))
def test_every_fund_row_is_well_formed(sym):
    f = bd.FUNDS[sym]
    assert f["name"] and f["kind"] and sum(f["asset"].values()) == pytest.approx(100.0)
    assert set(f["asset"]) <= {bd.US, bd.INTL, bd.BOND, bd.CASH, bd.OTHER}
    if f["sectors"] is not None:
        assert set(f["sectors"]) <= set(bd.SECTORS) and sum(f["sectors"].values()) == pytest.approx(100.0, abs=3.0), sym
    if set(f["asset"]) & {bd.US, bd.INTL}:
        assert f["sectors"], f"{sym}: a stock fund needs sector weights"
    else:
        assert f["sectors"] is None


def test_schd_is_the_defensive_dividend_fund_it_really_is():
    s = bd.FUNDS["SCHD"]["sectors"]
    assert max(s, key=s.get) == STAPLES and s[ENERGY] > 15 and s[IT] < 15
    assert s[STAPLES] + s[HEALTH] + s[ENERGY] > 50


def test_stock_overrides_use_real_sectors_and_known_names():
    assert set(bd.STOCK_SECTORS.values()) <= set(bd.SECTORS)
    assert bd.STOCK_SECTORS["AMZN"] == DISC and bd.STOCK_SECTORS["WMT"] == STAPLES and bd.STOCK_SECTORS["V"] == FIN and bd.STOCK_SECTORS["GOOGL"] == COMM


@pytest.mark.parametrize("name,p", sorted(bd.PRESETS.items()))
def test_presets_add_to_100_and_order_from_steady_to_aggressive(name, p):
    assert p["stocks"] + p["bonds"] + p["cash"] + p["other"] == 100 and p["growth"][0] < p["growth"][1] and p["blurb"]
    assert bd.DEFAULT_PRESET in bd.PRESETS
    assert [bd.PRESETS[k]["stocks"] for k in bd.PRESETS] == sorted(bd.PRESETS[k]["stocks"] for k in bd.PRESETS)


# ---------------------------------------------------------------- classifying
@pytest.mark.parametrize("industry,sector", [("Semiconductors", IT), ("Technology", IT), ("Utilities", UTIL), ("Gas Utilities", UTIL), ("Real Estate", RE),
                                             ("Banking", FIN), ("Insurance", FIN), ("Pharmaceuticals", HEALTH), ("Biotechnology", HEALTH),
                                             ("Media", COMM), ("Telecommunication", COMM), ("Beverages", STAPLES), ("Tobacco", STAPLES),
                                             ("Retail", DISC), ("Automobiles", DISC), ("Aerospace & Defense", IND), ("Machinery", IND),
                                             ("Chemicals", MAT), ("Metals & Mining", MAT), ("Energy", ENERGY), ("Oil & Gas", ENERGY)])
def test_industry_words_map_to_sectors(industry, sector):
    assert bal.sector_from_industry(industry) == sector


def test_unknown_or_missing_industry_is_none_not_a_guess():
    assert bal.sector_from_industry(None) is None and bal.sector_from_industry("") is None and bal.sector_from_industry("Mystery Widgets") is None


def test_overrides_beat_the_industry_label_and_unknowns_use_it():
    assert bal.sector_for_stock("AMZN", "Retail") == DISC and bal.sector_for_stock("WMT", "Retail") == STAPLES
    assert bal.sector_for_stock("amzn", None) == DISC
    assert bal.sector_for_stock("ZZZZ", "Semiconductors") == IT and bal.sector_for_stock("ZZZZ", None) is None


def test_only_unplaced_single_stocks_need_a_profile_lookup():
    assert bal.needs_profile("ZZZZ", "Stock") and not bal.needs_profile("AAPL", "Stock") and not bal.needs_profile("ZZZZ", "ETF")


def test_classify_each_kind():
    assert bal.classify("SPAXX", "Cash equiv.")["asset"] == {bd.CASH: 1.0}
    assert bal.classify("X", "Bond")["asset"] == {bd.BOND: 1.0} and bal.classify("X", "Crypto")["asset"] == {bd.OTHER: 1.0}
    c = bal.classify("AAPL", "Stock")
    assert c["asset"] == {bd.US: 1.0} and c["sectors"] == {IT: 1.0}
    j = bal.classify("ZZZZ", "Stock", {"country": "JP", "finnhubIndustry": "Automobiles"})
    assert j["asset"] == {bd.INTL: 1.0} and j["sectors"] == {DISC: 1.0}
    assert bal.classify("ZZZZ", "Stock", {"country": "US"})["sectors"] is None                  # US but no sector: placed in assets, not sectors
    assert bal.classify("ZZZZ", "Stock")["asset"] == {bd.US: 1.0}
    f = bal.classify("schd", "ETF")
    assert f["asset"] == {bd.US: 1.0} and sum(f["sectors"].values()) == pytest.approx(1.0) and f["kind"] == "Dividend payers"
    assert bal.classify("VT", "ETF")["asset"] == pytest.approx({bd.US: 0.62, bd.INTL: 0.38})
    assert bal.classify("NOPE", "ETF") is None and bal.classify("NOPE", "Fund") is None and bal.classify("NOPE", "Other") is None


# ---------------------------------------------------------------- the picture
def hold(sym, cls, w):
    return {"symbol": sym, "class": cls, "weight": w}


def test_asset_and_sector_maths_for_a_simple_portfolio():
    ex = bal.build([hold("SCHD", "ETF", 50), hold("VOO", "ETF", 20), hold("AAPL", "Stock", 10), hold("CASH", "Cash equiv.", 20)])
    assert ex["total"] == 100 and ex["stocks"] == pytest.approx(80) and ex["asset"][bd.CASH] == pytest.approx(20)
    assert ex["intl_share"] == 0 and ex["coverage"] == 1.0 and ex["unclassified"] == []
    schd = {k: v / sum(bd.SCHD.values()) for k, v in bd.SCHD.items()}
    want_staples = (50 * schd[STAPLES] + 20 * bd.SP500[STAPLES] / sum(bd.SP500.values())) / 80 * 100
    assert ex["sectors"][STAPLES] == pytest.approx(want_staples)
    assert sum(ex["sectors"].values()) == pytest.approx(100.0)
    assert ex["sources"][STAPLES][0][0] == "SCHD" and ex["sources"][STAPLES][0][1] > 75
    assert ex["growth_share"] == pytest.approx(sum(ex["sectors"][s] for s in bd.GROWTH_SECTORS))
    assert list(ex["sectors"]) == sorted(ex["sectors"], key=lambda s: -ex["sectors"][s])


def test_international_and_bond_and_other_land_in_their_own_buckets():
    ex = bal.build([hold("VXUS", "ETF", 20), hold("BND", "ETF", 10), hold("IBIT", "ETF", 5), hold("VOO", "ETF", 65)])
    assert ex["asset"][bd.INTL] == pytest.approx(20) and ex["asset"][bd.BOND] == pytest.approx(10) and ex["asset"][bd.OTHER] == pytest.approx(5)
    assert ex["stocks"] == pytest.approx(85) and ex["intl_share"] == pytest.approx(20 / 85 * 100)
    assert "BND" not in {s for v in ex["sources"].values() for s, _ in v}             # bonds never count toward sectors


def test_single_stocks_without_a_sector_are_unclassified_and_reduce_coverage():
    ex = bal.build([hold("AAPL", "Stock", 50), hold("ZZZZ", "Stock", 25), hold("NOPE", "ETF", 25)])
    assert ex["stocks"] == pytest.approx(75)                                          # ZZZZ is a US stock even without a sector
    assert dict(ex["unclassified"]) == pytest.approx({"ZZZZ": 25, "NOPE": 25}) and ex["unclassified_pct"] == pytest.approx(50)
    assert ex["coverage"] == pytest.approx(50 / 75) and ex["sectors"] == {IT: pytest.approx(100.0)}
    withp = bal.build([hold("AAPL", "Stock", 50), hold("ZZZZ", "Stock", 25)], {"ZZZZ": {"finnhubIndustry": "Banking"}})
    assert withp["coverage"] == 1.0 and withp["sectors"][FIN] == pytest.approx(100 / 3)


def test_zero_negative_and_missing_weights_are_ignored_and_empty_is_safe():
    ex = bal.build([hold("AAPL", "Stock", 0), hold("MSFT", "Stock", -5), {"symbol": "X", "class": "Stock", "weight": None}])
    assert ex["total"] == 0 and ex["intl_share"] is None and ex["growth_share"] is None and ex["coverage"] is None and ex["sectors"] == {}
    assert bal.build([])["unclassified"] == [] and bal.suggestions(bal.build([]), bd.DEFAULT_PRESET) == []


# ---------------------------------------------------------------- comparisons
def mix(stocks, bonds=0, cash=0, other=0, intl=0):
    """An extraction with just asset numbers set."""
    ex = bal.build([hold("VOO", "ETF", stocks - intl), hold("VXUS", "ETF", intl), hold("BND", "ETF", bonds), hold("SGOV", "ETF", cash), hold("GLD", "ETF", other)])
    return ex


@pytest.mark.parametrize("stocks,status", [(80, "On target"), (85, "On target"), (85.5, "Heavy"), (75, "On target"), (74.5, "Light")])
def test_asset_rows_use_a_five_point_band(stocks, status):
    ex = bal.build([hold("VOO", "ETF", stocks), hold("BND", "ETF", 100 - stocks)])
    row = bal.compare_assets(ex, "Balanced, leaning growth")[0]
    assert row["name"] == "Stocks" and row["status"] == status and row["target"] == 80 and row["diff"] == pytest.approx(stocks - 80)


def test_asset_rows_cover_every_category_in_order():
    rows = bal.compare_assets(mix(80, bonds=10, cash=5, other=5), "Balanced, leaning growth")
    assert [r["name"] for r in rows] == ["Stocks", "Bonds", "Cash", "Other"]
    assert [r["status"] for r in rows] == ["On target", "On target", "On target", "On target"]
    heavy_other = bal.compare_assets(mix(80, bonds=10, cash=4, other=6), "Balanced, leaning growth")[3]
    assert heavy_other["status"] == "Heavy" and heavy_other["target"] == 0


def test_region_and_growth_bands():
    assert bal.compare_region(bal.build([hold("AAPL", "Stock", 100)]), "Growth")["status"] == "Light"
    even = bal.build([hold("VOO", "ETF", 75), hold("VXUS", "ETF", 25)])
    assert bal.compare_region(even, "Growth")["status"] == "On target" and bal.compare_region(bal.build([hold("BND", "ETF", 5)]), "Growth") is None
    lo, hi = bd.PRESETS["Growth"]["growth"]

    def with_growth(g):
        return {"growth_share": g}
    for g, status in ((lo - 0.1, "Light"), (lo, "On target"), (hi, "On target"), (hi + 0.1, "Heavy")):
        assert bal.compare_growth(with_growth(g), "Growth")["status"] == status
    assert bal.compare_growth({"growth_share": None}, "Growth") is None
    assert bal.compare_growth(with_growth(60), "Growth")["market"] == pytest.approx(53.9)


def fake_ex(sectors):
    return {"sectors": sectors, "sources": {}}


def test_heavy_and_light_boundaries_exactly():
    def st(sector, yours):
        return next(r for r in bal.compare_sectors(fake_ex({sector: yours})) if r["sector"] == sector)["status"]
    assert st(STAPLES, 12.9) == "Near market" and st(STAPLES, 13.0) == "Heavy"                 # market 5.0 + 8
    assert st(STAPLES, 2.5) == "Near market" and st(STAPLES, 2.4) == "Light"                   # under half the market weight and 2+ points short
    assert st(UTIL, 1.2) == "Light" and st(UTIL, 1.7) == "Near market"                          # 3.2 market: needs 2.0 points short and under 1.6
    assert st(RE, 0.0) == "Near market"                                                         # 1.9 market: only 1.9 points short, too small to call light
    assert st(IT, 0.0) == "Light" and st(IT, 32.0) == "Near market"


def test_sector_rows_come_biggest_gap_first_and_carry_their_sources():
    ex = bal.build([hold("SCHD", "ETF", 100)])
    rows = bal.compare_sectors(ex)
    assert [abs(r["diff"]) for r in rows] == sorted((abs(r["diff"]) for r in rows), reverse=True)
    assert len(rows) == 11 and rows[0]["sector"] in (IT, STAPLES, ENERGY)
    assert next(r for r in rows if r["sector"] == STAPLES)["from"] == [("SCHD", pytest.approx(100.0))]


# ---------------------------------------------------------------- plain words
def schd_heavy():
    return bal.build([hold("SCHD", "ETF", 70), hold("VOO", "ETF", 10), hold("CASH", "Cash equiv.", 20)])


def texts(notes):
    return " ".join(n["text"] for n in notes)


def test_a_schd_heavy_portfolio_is_told_where_the_heaviness_comes_from():
    notes = bal.suggestions(schd_heavy(), "Balanced, leaning growth")
    heavy = [n for n in notes if n["kind"] == "heavy"]
    assert any(n["sector"] == STAPLES for n in heavy) and any(n["sector"] == ENERGY for n in heavy)
    assert "Mostly from SCHD" in next(n["text"] for n in heavy if n["sector"] == STAPLES)
    light = [n for n in notes if n["kind"] == "light"]
    assert any(n["sector"] == IT for n in light)
    assert "more points would bring it to the market's weight" in light[0]["text"] and "browse" in light[0]["text"]
    assert "Outside the US" in texts(notes) and "Growth tilt" in texts(notes)


def test_light_sector_order_depends_on_the_preset_only_through_the_growth_lean():
    ex = bal.build([hold("XLE", "ETF", 50), hold("XLU", "ETF", 50)])
    growth = [n["sector"] for n in bal.suggestions(ex, "Growth") if n["kind"] == "light"]
    steady = [n["sector"] for n in bal.suggestions(ex, "Balanced") if n["kind"] == "light"]
    assert growth == [IT, COMM, DISC]                       # all three growth sectors lead, biggest gap first
    assert steady == [IT, FIN, COMM]                        # plain biggest-gap order (technology 32, financials 12.5, communication 11.4)


def test_stock_heavy_note_only_when_stocks_run_above_the_mix():
    all_stock = bal.suggestions(bal.build([hold("VOO", "ETF", 100)]), "Balanced, leaning growth")
    assert "isn't wrong for a long time horizon" in next(n["text"] for n in all_stock if n["text"].startswith("**Stocks:**"))
    light = bal.suggestions(bal.build([hold("VOO", "ETF", 40), hold("BND", "ETF", 60)]), "Balanced, leaning growth")
    assert "isn't wrong" not in next(n["text"] for n in light if n["text"].startswith("**Stocks:**"))


def test_on_target_portfolio_has_no_asset_or_sector_complaints():
    ex = bal.build([hold("VOO", "ETF", 45), hold("VXUS", "ETF", 15), hold("BND", "ETF", 35), hold("SGOV", "ETF", 5)])
    notes = bal.suggestions(ex, "Balanced")
    assert [n["kind"] for n in notes if n["kind"] in ("asset", "region", "growth", "heavy", "light")] == []


def test_todays_idea_says_whether_it_adds_balance_or_adds_to_the_tilt():
    ex = schd_heavy()
    light = next(n["text"] for n in bal.suggestions(ex, "Growth", {"symbol": "NVDA", "sector": IT}) if n["kind"] == "pick")
    heavy = next(n["text"] for n in bal.suggestions(ex, "Growth", {"symbol": "KO", "sector": STAPLES}) if n["kind"] == "pick")
    near = next(n["text"] for n in bal.suggestions(ex, "Growth", {"symbol": "AMGN", "sector": FIN}) if n["kind"] == "pick")
    assert "NVDA" in light and "would add balance" in light and "KO" in heavy and "add to the tilt" in heavy and "close to the market's weight" in near
    assert not [n for n in bal.suggestions(ex, "Growth", None) if n["kind"] == "pick"]
    assert not [n for n in bal.suggestions(ex, "Growth", {"symbol": "X", "sector": None}) if n["kind"] == "pick"]


def test_unclassified_holdings_are_called_out_once_they_matter():
    base = [hold("VOO", "ETF", 90)]
    assert not [n for n in bal.suggestions(bal.build(base + [hold("NOPE", "ETF", 4.9)]), "Growth") if n["kind"] == "gap"]
    gap = next(n["text"] for n in bal.suggestions(bal.build(base + [hold("NOPE", "ETF", 5.0)]), "Growth") if n["kind"] == "gap")
    assert "NOPE (5%)" in gap and "rather than guessed" in gap


def test_wording_is_percent_only_and_never_a_buy_signal():
    ex = schd_heavy()
    t = texts(bal.suggestions(ex, "Growth", {"symbol": "NVDA", "sector": IT}))
    assert "$" not in t and not any(w in t.lower() for w in ("you should buy", "buy now", "sell ", "must ", "guarantee"))
    assert all("$" not in b for _s, b in bal.how_it_works())


# ---------------------------------------------------------------- chart
@pytest.mark.parametrize("mode", ["light", "dark"])
def test_compare_bars_builds_for_both_modes_and_sizes_with_rows(mode):
    rows = [{"label": s, "yours": 10.0, "ref": 12.0} for s in bd.SECTORS]
    assert bc.compare_bars(rows, mode, ref_label="S&P 500") is not None
    bc.compare_bars(rows[:1], mode)
    bc.compare_bars([{"label": "Stocks", "yours": 0.0, "ref": 0.0}], mode)


# ---------------------------------------------------------------- extra boundaries
@pytest.mark.parametrize("intl,status", [(17.0, "On target"), (16.9, "Light"), (33.0, "On target"), (33.1, "Heavy")])
def test_outside_the_us_band_is_eight_points(intl, status):
    ex = bal.build([hold("VOO", "ETF", 100 - intl), hold("VXUS", "ETF", intl)])
    assert bal.compare_region(ex, "Growth")["status"] == status                         # Growth reference is 25%


def test_sources_under_a_quarter_of_a_sector_are_not_named():
    assert bal._src({"from": [("A", 24.9)]}) == ""
    assert bal._src({"from": [("A", 60.0), ("B", 25.0), ("C", 24.0)]}) == " Mostly from A (60%) and B (25%)."
    assert bal._src({"from": []}) == ""


def test_at_most_three_heavy_and_three_light_sectors_are_listed():
    ex = bal.build([hold("XLE", "ETF", 25), hold("XLP", "ETF", 25), hold("XLU", "ETF", 25), hold("XLV", "ETF", 25)])
    notes = bal.suggestions(ex, "Growth")
    assert len([n for n in notes if n["kind"] == "heavy"]) == 3 and len([n for n in notes if n["kind"] == "light"]) == 3
