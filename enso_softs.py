# -*- coding: utf-8 -*-
"""
ENSO  ->  Soft commodities
==========================
Does the equatorial-Pacific sea-surface-temperature index (ONI) lead the prices
of coffee, cocoa and sugar? And with an El Nino forming now, what does history
imply for 2026-27?

Run this in Spyder cell by cell (each `# %%` block is a cell: Ctrl+Enter).
Phases:  1 data -> 2 lead-lag -> 3 event study -> 4 HAC regression -> 5 live overlay
Everything runs on FREE data (NOAA CPC + Yahoo Finance via yfinance).

Requires:  pip install yfinance plotly statsmodels
"""

# %% Cell 0 -- imports & config -------------------------------------------------
import numpy as np
import pandas as pd
import requests
from io import StringIO
import statsmodels.api as sm
import plotly.graph_objects as go

# Front-month continuous futures on Yahoo Finance:
TICKERS = {
    "KC=F": "coffee",
    "CC=F": "cocoa",
    "SB=F": "sugar",
    "CT=F": "cotton",
    "OJ=F": "orange_juice",
    "BRL=X": "usdbrl",   # FX control (USD/BRL): Brazil grows coffee & sugar
}
COMMODITIES = ["coffee", "cocoa", "sugar", "cotton", "orange_juice"]
START = "1999-01-01"     # yfinance continuous futures realistically start ~here
MAX_LAG = 18             # months to test ONI leading prices

# NOAA Climate Prediction Center — Oceanic Nino Index (monthly, back to 1950):
ONI_URL = "https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt"
# Each row is a 3-month season; map it to its CENTRE month:
SEASON_TO_MONTH = {"DJF": 1, "JFM": 2, "FMA": 3, "MAM": 4, "AMJ": 5, "MJJ": 6,
                   "JJA": 7, "JAS": 8, "ASO": 9, "SON": 10, "OND": 11, "NDJ": 12}
# NOTE: RONI (the newer relative index NOAA adopted in 2026) lives in the same
# directory: https://www.cpc.ncep.noaa.gov/data/indices/  -- swap it in later
# as a robustness check once the ONI pipeline works.


# %% Cell 1 -- load ONI from NOAA ----------------------------------------------
def load_oni(url=ONI_URL):
    """Return a monthly ONI series indexed by month-END timestamps."""
    txt = requests.get(url, timeout=30).text
    df = pd.read_csv(StringIO(txt), sep=r"\s+")           # cols: SEAS YR TOTAL ANOM
    df.columns = [c.strip().upper() for c in df.columns]
    df["month"] = df["SEAS"].map(SEASON_TO_MONTH)
    df["date"] = pd.to_datetime(dict(year=df["YR"], month=df["month"], day=1))
    oni = (df.set_index("date")["ANOM"].sort_index()
             .rename("ONI"))
    oni.index = oni.index + pd.offsets.MonthEnd(0)         # align to month-end
    return oni

oni = load_oni()
print(oni.tail(8))
go.Figure(go.Scatter(x=oni.index, y=oni.values, mode="lines")
          ).update_layout(title="ONI (NOAA CPC)", template="plotly_white").show()


# %% Cell 2 -- load soft-commodity prices --------------------------------------
import yfinance as yf

def _close_frame(raw):
    """Robustly pull the Close panel out of a yfinance multi-ticker download."""
    if isinstance(raw.columns, pd.MultiIndex):
        lvl0 = raw.columns.get_level_values(0)
        return raw["Close"] if "Close" in set(lvl0) else raw.xs("Close", axis=1, level=1)
    return raw[["Close"]]

def load_prices(tickers=TICKERS, start=START):
    raw = yf.download(list(tickers), start=start, auto_adjust=True, progress=False)
    px = _close_frame(raw).rename(columns=tickers)
    px = px.resample("ME").last()                          # month-end levels
    return px

px = load_prices()
print(px.tail(4).round(2))


# %% Cell 3 -- build one aligned monthly panel ---------------------------------
rets = np.log(px).diff()                                   # monthly log returns
rets.columns = [f"{c}_ret" for c in rets.columns]

data = px.join(rets)
data["ONI"] = oni.reindex(data.index)                      # months line up (month-end)
data = data.dropna(subset=["ONI"])
print(data[["ONI", "coffee", "coffee_ret"]].tail(6).round(3))


# %% Cell 4 -- LEAD-LAG: does ONI lead prices? (the signature chart) -----------
def lagged_xcorr(driver, series, max_lag=MAX_LAG):
    """corr( driver(t-k) , series(t) ) for k=0..max_lag. Positive k = driver leads."""
    return pd.Series({k: driver.shift(k).corr(series) for k in range(max_lag + 1)})

# Correlate ONI level (shifted) against each commodity's monthly return.
xcorr = {c: lagged_xcorr(data["ONI"], data[f"{c}_ret"]) for c in COMMODITIES}
xcorr = pd.DataFrame(xcorr)
best_lag = xcorr.abs().idxmax()
print("Peak-|corr| lag (months) by commodity:\n", best_lag)

fig = go.Figure()
for c in ["coffee", "cocoa", "sugar"]:
    fig.add_bar(x=xcorr.index, y=xcorr[c], name=c)
fig.update_layout(title="ONI leads soft-commodity returns — cross-correlation by lag",
                  xaxis_title="ONI lead (months)", yaxis_title="correlation",
                  barmode="group", template="plotly_white")
fig.show()
fig.write_html("chart_leadlag.html")


# %% Cell 5 -- EVENT STUDY: the typical price path around an El Nino onset ------
def find_el_nino_onsets(oni, thresh=0.5, sustain=5, min_gap_m=18):
    """Onset = ONI crosses >= thresh and stays there ~sustain months. Rough NOAA rule."""
    v, idx = oni.dropna().values, oni.dropna().index
    onsets, last_i = [], -10**9
    for i in range(len(v) - sustain):
        crossed = v[i] >= thresh and (i == 0 or v[i - 1] < thresh)
        if crossed and (v[i:i + sustain] >= thresh).sum() >= sustain - 1 and (i - last_i) >= min_gap_m:
            onsets.append(idx[i]); last_i = i
    return onsets

def event_study(level, onsets, pre=6, post=18):
    """Normalise each commodity's price to 100 at onset; average across events."""
    idx, paths = level.index, []
    for onset in onsets:
        loc = idx.get_indexer([onset], method="nearest")[0]
        if loc - pre < 0 or loc + post >= len(idx):
            continue
        w = level.iloc[loc - pre: loc + post + 1].copy()
        w = 100 * w / w.iloc[pre]
        w.index = range(-pre, post + 1)
        paths.append(w)
    comp = pd.concat(paths, axis=1)
    return comp.mean(axis=1), comp.std(axis=1), comp.shape[1]

onsets = find_el_nino_onsets(data["ONI"])
print("Detected El Nino onsets:", [d.strftime('%Y-%m') for d in onsets])

fig = go.Figure()
for c in ["coffee", "cocoa", "sugar"]:
    mean, sd, n = event_study(data[c], onsets)
    fig.add_scatter(x=mean.index, y=mean.values, mode="lines", name=f"{c} (n={n})")
    fig.add_scatter(x=list(mean.index) + list(mean.index[::-1]),
                    y=list(mean + sd) + list((mean - sd)[::-1]),
                    fill="toself", opacity=0.12, line=dict(width=0),
                    showlegend=False, hoverinfo="skip")
fig.add_vline(x=0, line_dash="dash")
fig.update_layout(title="Average price path around an El Nino onset (=100 at month 0)",
                  xaxis_title="months from onset", yaxis_title="price (indexed)",
                  template="plotly_white")
fig.show()
fig.write_html("chart_eventstudy.html")


# %% Cell 6 -- HAC REGRESSION: rigour (Newey-West standard errors) --------------
def hac_regression(data, commodity, lag, controls=("usdbrl_ret",)):
    d = data.copy()
    d["ONI_lag"] = d["ONI"].shift(lag)
    d["month"] = d.index.month
    cols = ["ONI_lag", *controls]
    d = d.dropna(subset=[f"{commodity}_ret", *cols])
    X = sm.add_constant(pd.concat([d[cols],
                                   pd.get_dummies(d["month"], prefix="m",
                                                  drop_first=True).astype(float)], axis=1))
    y = d[f"{commodity}_ret"]
    # HAC (Newey-West) because monthly return data is autocorrelated/overlapping:
    return sm.OLS(y, X).fit(cov_type="HAC", cov_kwds={"maxlags": lag + 2})

for c in ["coffee", "cocoa", "sugar"]:
    m = hac_regression(data, c, lag=int(best_lag[c]))
    print(f"\n=== {c} | ONI lag {int(best_lag[c])}m ===")
    print(f"ONI_lag coef {m.params['ONI_lag']:+.4f}  t={m.tvalues['ONI_lag']:+.2f}  "
          f"p={m.pvalues['ONI_lag']:.3f}  R2={m.rsquared:.3f}")


# %% Cell 7 -- LIVE OVERLAY: the "so what" (super El Nino forming now) ----------
# Plot the current ONI trajectory against the historical composite you built above,
# so you can state a base-rate view. Fill this in once Cells 1-6 look right:
#   - take the last ~12 months of `data["ONI"]`
#   - overlay recent coffee/cocoa/sugar paths on the event-study composite
#   - annotate NOAA's current El Nino advisory + your read
print("Latest ONI:", round(data['ONI'].iloc[-1], 2), "as of", data.index[-1].date())
