"""SEC CIK snapshot for frozen V3 universe (SEC company_tickers.json, 2026-09-22).

Ticker-to-CIK mapping must be checked against the live SEC submissions response
before any filing is accepted. Symbol/CIK changes require a versioned update.
"""
from .v3_universe import ELIGIBLE

CIKS = {
    "NVDA": 1045810, "AMD": 2488, "MU": 723125, "INTC": 50863,
    "AAPL": 320193, "MSFT": 789019, "AMZN": 1018724, "GOOGL": 1652044,
    "META": 1326801, "UBER": 1543151, "JPM": 19617, "BAC": 70858,
    "WFC": 72971, "PYPL": 1633917, "WMT": 104169, "TGT": 27419,
    "HD": 354950, "DIS": 1744489, "GM": 1467858, "CAT": 18230,
    "XOM": 2115436, "CVX": 93410, "UNH": 731766, "PFE": 78003,
    "NFLX": 1065280, "TSLA": 1318605, "PLTR": 1321655, "SOFI": 1818874,
    "HOOD": 1783879, "XYZ": 1512673, "AFRM": 1820953, "RBLX": 1315098,
    "SHOP": 1594805, "CRWD": 1535527, "DDOG": 1561550, "SNOW": 1640147,
    "DKNG": 1883685, "ROKU": 1428439, "CCL": 815097, "DAL": 27904,
    "F": 37996, "FCX": 831259, "ON": 1097864, "MRVL": 1835632,
}
assert set(CIKS) == ELIGIBLE and len(set(CIKS.values())) == len(CIKS)
