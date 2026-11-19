"""
Reference data for the Balance check on the Holdings page. Plain tables, no logic.

Everything here is APPROXIMATE and drifts over time (index funds rebalance, SCHD rebuilds every March).
AS_OF says when the numbers were last checked. A fund that isn't listed is shown as "not classified" instead of guessed.
Sources for the checked rows: Schwab Asset Management (SCHD, March 2026 reconstitution) and published S&P 500 sector weights (spring 2026).
Sector names are the 11 standard GICS sectors.
"""

from __future__ import annotations

AS_OF = "spring 2026"

IT, COMM, DISC = "Technology", "Communication Services", "Consumer Discretionary"
FIN, HEALTH, IND = "Financials", "Health Care", "Industrials"
STAPLES, ENERGY, UTIL = "Consumer Staples", "Energy", "Utilities"
RE, MAT = "Real Estate", "Materials"
SECTORS = [IT, FIN, COMM, DISC, HEALTH, IND, STAPLES, ENERGY, UTIL, RE, MAT]
GROWTH_SECTORS = (IT, COMM, DISC)          # the sectors people usually mean by "growth"; tracked as one number

# S&P 500 sector weights, % (about spring 2026)
MARKET = {IT: 32.0, FIN: 12.5, COMM: 11.4, DISC: 10.5, HEALTH: 9.3, IND: 8.7, STAPLES: 5.0, ENERGY: 3.4, UTIL: 3.2, RE: 1.9, MAT: 2.1}

SP500 = dict(MARKET)
TOTAL_MARKET = {IT: 32.0, FIN: 13.5, COMM: 10.0, DISC: 10.5, HEALTH: 9.5, IND: 9.5, STAPLES: 4.5, ENERGY: 3.3, UTIL: 2.5, RE: 2.3, MAT: 1.9}
NASDAQ100 = {IT: 52.0, COMM: 16.0, DISC: 13.0, HEALTH: 5.5, STAPLES: 5.0, IND: 4.5, UTIL: 1.3, MAT: 1.0, ENERGY: 0.5, FIN: 0.7}
LARGE_GROWTH = {IT: 55.0, DISC: 16.0, COMM: 12.0, HEALTH: 6.0, IND: 5.0, FIN: 3.0, STAPLES: 1.5, RE: 0.5, ENERGY: 0.3, MAT: 0.5, UTIL: 0.2}
LARGE_VALUE = {FIN: 21.0, HEALTH: 15.0, IND: 14.0, IT: 10.0, STAPLES: 9.0, ENERGY: 7.0, DISC: 6.0, COMM: 6.0, UTIL: 5.0, RE: 4.0, MAT: 3.0}
SCHD = {STAPLES: 19.2, HEALTH: 18.6, ENERGY: 16.5, IND: 11.6, IT: 11.0, FIN: 8.8, COMM: 7.1, DISC: 6.5, UTIL: 0.1}
HIGH_DIVIDEND = {FIN: 20.0, HEALTH: 13.0, IND: 13.0, IT: 11.0, STAPLES: 10.0, ENERGY: 8.0, UTIL: 6.0, COMM: 6.0, DISC: 6.0, MAT: 3.0, RE: 3.0}
DIV_GROWTH = {IT: 24.0, FIN: 20.0, HEALTH: 15.0, IND: 11.0, STAPLES: 9.0, DISC: 8.0, COMM: 5.0, ENERGY: 3.0, UTIL: 3.0, MAT: 2.0}
INTERNATIONAL = {FIN: 22.0, IND: 14.0, IT: 13.0, DISC: 11.0, HEALTH: 9.0, STAPLES: 7.0, MAT: 7.0, COMM: 5.0, ENERGY: 5.0, UTIL: 3.0, RE: 3.0}

US, INTL, BOND, CASH, OTHER = "US stocks", "International stocks", "Bonds", "Cash", "Other"


def _f(name, kind, asset, sectors=None):
    return {"name": name, "kind": kind, "asset": asset, "sectors": sectors}


def _one(sector, name):
    return _f(name, "One sector", {US: 100}, {sector: 100.0})


FUNDS = {
    # whole US market / S&P 500
    "VOO": _f("Vanguard S&P 500", "US large companies", {US: 100}, SP500),
    "SPY": _f("SPDR S&P 500", "US large companies", {US: 100}, SP500),
    "IVV": _f("iShares Core S&P 500", "US large companies", {US: 100}, SP500),
    "SPLG": _f("SPDR Portfolio S&P 500", "US large companies", {US: 100}, SP500),
    "SCHX": _f("Schwab US Large-Cap", "US large companies", {US: 100}, SP500),
    "VTI": _f("Vanguard Total Stock Market", "Whole US market", {US: 100}, TOTAL_MARKET),
    "ITOT": _f("iShares Core S&P Total US", "Whole US market", {US: 100}, TOTAL_MARKET),
    "SCHB": _f("Schwab US Broad Market", "Whole US market", {US: 100}, TOTAL_MARKET),
    # growth / tech
    "QQQ": _f("Invesco QQQ (Nasdaq-100)", "Growth-leaning", {US: 100}, NASDAQ100),
    "QQQM": _f("Invesco Nasdaq 100", "Growth-leaning", {US: 100}, NASDAQ100),
    "VUG": _f("Vanguard Growth", "Growth-leaning", {US: 100}, LARGE_GROWTH),
    "SCHG": _f("Schwab US Large-Cap Growth", "Growth-leaning", {US: 100}, LARGE_GROWTH),
    "IWF": _f("iShares Russell 1000 Growth", "Growth-leaning", {US: 100}, LARGE_GROWTH),
    "MGK": _f("Vanguard Mega Cap Growth", "Growth-leaning", {US: 100}, LARGE_GROWTH),
    "VGT": _one(IT, "Vanguard Information Technology"),
    "XLK": _one(IT, "Technology Select Sector SPDR"),
    "FTEC": _one(IT, "Fidelity MSCI Information Technology"),
    "SMH": _one(IT, "VanEck Semiconductor"),
    "SOXX": _one(IT, "iShares Semiconductor"),
    # value / dividend
    "SCHD": _f("Schwab US Dividend Equity", "Dividend payers", {US: 100}, SCHD),
    "VYM": _f("Vanguard High Dividend Yield", "Dividend payers", {US: 100}, HIGH_DIVIDEND),
    "VIG": _f("Vanguard Dividend Appreciation", "Dividend growers", {US: 100}, DIV_GROWTH),
    "DGRO": _f("iShares Core Dividend Growth", "Dividend growers", {US: 100}, DIV_GROWTH),
    "VTV": _f("Vanguard Value", "Value-leaning", {US: 100}, LARGE_VALUE),
    "SCHV": _f("Schwab US Large-Cap Value", "Value-leaning", {US: 100}, LARGE_VALUE),
    "IWD": _f("iShares Russell 1000 Value", "Value-leaning", {US: 100}, LARGE_VALUE),
    # one-sector funds
    "XLF": _one(FIN, "Financial Select Sector SPDR"),
    "XLV": _one(HEALTH, "Health Care Select Sector SPDR"),
    "XLE": _one(ENERGY, "Energy Select Sector SPDR"),
    "XLU": _one(UTIL, "Utilities Select Sector SPDR"),
    "XLP": _one(STAPLES, "Consumer Staples Select Sector SPDR"),
    "XLY": _one(DISC, "Consumer Discretionary Select Sector SPDR"),
    "XLI": _one(IND, "Industrial Select Sector SPDR"),
    "XLC": _one(COMM, "Communication Services Select Sector SPDR"),
    "XLB": _one(MAT, "Materials Select Sector SPDR"),
    "XLRE": _one(RE, "Real Estate Select Sector SPDR"),
    "VNQ": _one(RE, "Vanguard Real Estate"),
    # outside the US
    "VXUS": _f("Vanguard Total International", "Outside the US", {INTL: 100}, INTERNATIONAL),
    "IXUS": _f("iShares Core MSCI Total International", "Outside the US", {INTL: 100}, INTERNATIONAL),
    "VEA": _f("Vanguard Developed Markets", "Outside the US", {INTL: 100}, INTERNATIONAL),
    "IEFA": _f("iShares Core MSCI EAFE", "Outside the US", {INTL: 100}, INTERNATIONAL),
    "SCHF": _f("Schwab International Equity", "Outside the US", {INTL: 100}, INTERNATIONAL),
    "VWO": _f("Vanguard Emerging Markets", "Outside the US", {INTL: 100}, INTERNATIONAL),
    "IEMG": _f("iShares Core MSCI Emerging Markets", "Outside the US", {INTL: 100}, INTERNATIONAL),
    "VT": _f("Vanguard Total World", "US and international", {US: 62, INTL: 38}, TOTAL_MARKET),
    # bonds, cash, other
    "BND": _f("Vanguard Total Bond Market", "Bonds", {BOND: 100}),
    "AGG": _f("iShares Core US Aggregate Bond", "Bonds", {BOND: 100}),
    "SCHZ": _f("Schwab US Aggregate Bond", "Bonds", {BOND: 100}),
    "BNDX": _f("Vanguard Total International Bond", "Bonds", {BOND: 100}),
    "VGSH": _f("Vanguard Short-Term Treasury", "Bonds", {BOND: 100}),
    "IEF": _f("iShares 7-10 Year Treasury", "Bonds", {BOND: 100}),
    "TLT": _f("iShares 20+ Year Treasury", "Bonds", {BOND: 100}),
    "LQD": _f("iShares Investment Grade Corporate Bond", "Bonds", {BOND: 100}),
    "SGOV": _f("iShares 0-3 Month Treasury", "Cash-like", {CASH: 100}),
    "BIL": _f("SPDR 1-3 Month T-Bill", "Cash-like", {CASH: 100}),
    "SHV": _f("iShares Short Treasury Bond", "Cash-like", {CASH: 100}),
    "GLD": _f("SPDR Gold Shares", "Gold", {OTHER: 100}),
    "IAU": _f("iShares Gold Trust", "Gold", {OTHER: 100}),
    "IBIT": _f("iShares Bitcoin Trust", "Crypto", {OTHER: 100}),
}

# Finnhub often files well-known companies under a different label than the standard sector, so these win over the lookup.
STOCK_SECTORS = {}
for _sector, _syms in {
    IT: "AAPL MSFT NVDA AVGO AMD INTC QCOM TXN ORCL CRM ADBE CSCO IBM MU AMAT PLTR NOW INTU",
    COMM: "GOOGL GOOG META NFLX DIS T VZ CMCSA TMUS",
    DISC: "AMZN TSLA HD MCD NKE SBUX LOW BKNG TJX ABNB",
    STAPLES: "WMT COST KO PEP PG PM MO MDLZ CL TGT KR",
    FIN: "JPM BAC WFC GS MS V MA BRK.B BRK-B AXP SCHW C BLK",
    HEALTH: "UNH JNJ LLY PFE MRK ABBV AMGN ABT TMO ISRG",
    ENERGY: "XOM CVX COP SLB EOG",
    IND: "CAT GE HON UPS LMT RTX BA DE UNP",
    UTIL: "NEE SO DUK AEP",
    RE: "AMT PLD O EQIX",
    MAT: "LIN SHW FCX",
}.items():
    for _s in _syms.split():
        STOCK_SECTORS[_s] = _sector

# Finnhub's industry label -> sector. First match wins, so order matters.
INDUSTRY_WORDS = [
    (UTIL, ("utilit",)),
    (RE, ("real estate", "reit")),
    (ENERGY, ("energy", "oil", "petroleum")),
    (HEALTH, ("pharma", "biotech", "health", "life sciences", "medical", "drug")),
    (FIN, ("bank", "insurance", "financial", "capital markets", "brokerage")),
    (COMM, ("media", "telecom", "communications", "entertainment", "publishing")),
    (STAPLES, ("beverage", "food", "tobacco", "household", "personal products", "consumer products", "supermarket")),
    (DISC, ("retail", "auto", "apparel", "textile", "luxury", "leisure", "hotel", "restaurant", "homebuild", "consumer services", "diversified consumer")),
    (IND, ("aerospace", "defense", "machinery", "airline", "logistics", "transportation", "building", "construction", "electrical",
           "commercial services", "professional services", "trading companies", "industrial", "road", "marine", "engineering", "distributors")),
    (MAT, ("chemical", "metals", "mining", "paper", "forest", "packaging", "steel", "containers")),
    (IT, ("semiconductor", "technology", "software", "computer", "electronic")),
]

# Reference mixes people commonly use as starting points: not a recommendation. growth = range for the share of stock money in
# technology + communication + consumer discretionary (the S&P 500 itself is about 54%).
PRESETS = {
    "Balanced": {"stocks": 60, "bonds": 35, "cash": 5, "other": 0, "intl": 25, "growth": (40, 55),
                 "blurb": "Steadier ride: a good share in bonds and cash."},
    "Balanced, leaning growth": {"stocks": 80, "bonds": 15, "cash": 5, "other": 0, "intl": 25, "growth": (50, 65),
                                 "blurb": "Mostly stocks, with a smaller cushion of bonds and cash."},
    "Growth": {"stocks": 90, "bonds": 7, "cash": 3, "other": 0, "intl": 25, "growth": (55, 70),
               "blurb": "Nearly all stocks, tilted toward growth sectors."},
    "Aggressive growth": {"stocks": 100, "bonds": 0, "cash": 0, "other": 0, "intl": 20, "growth": (60, 80),
                          "blurb": "All stocks and a strong growth tilt. Expect big swings."},
}
DEFAULT_PRESET = "Balanced, leaning growth"
