# -*- coding: utf-8 -*-
"""
El Nino and the cocoa-sugar spread
==================================
Thesis: El Nino is bullish COCOA (hot/dry West Africa hurts the crop) and
bearish SUGAR, while COFFEE has no clean directional signal once you control
for La Nina. The tradeable expression is therefore a market-neutral spread:
LONG COCOA / SHORT SUGAR into a strong El Nino.

This script tests that claim honestly, with the robustness checks that separate
a real finding from a pretty chart:
  * abnormal returns (CAR), not raw indexed levels        -> removes drift
  * a La Nina control                                     -> removes seasonality
  * leave-one-out on the spread                           -> is it one event?
  * HAC (Newey-West) standard errors with long maxlags    -> honest inference
  * definition robustness (threshold & lag)               -> not an artifact

Every design choice is explained in plain language in the companion file
METHODOLOGY.md. Run in Spyder cell by cell (Ctrl+Enter). Free data only.
Requires:  pip install yfinance plotly statsmodels
"""

# %% Cell 0 -- imports & config -------------------------------------------------
import numpy as np
import pandas as pd
import requests
from io import StringIO
import statsmodels.api as sm
import plotly.graph_objects as go
import plotly.io as pio
pio.renderers.default = "browser"        # charts open in your web browser

# pandas renamed the month-end code from "M" to "ME" in 2.2 -- pick the right one:
_pv = tuple(int(x) for x in pd.__version__.split(".")[:2])
MONTH_END = "ME" if _pv >= (2, 2) else "M"

TICKERS = {"KC=F": "coffee", "CC=F": "cocoa", "SB=F": "sugar", "BRL=X": "usdbrl"}
START     = "1999-01-01"   # yfinance continuous futures realistically start here
PRE, POST = 6, 18          # event window: 6 months before, 18 after onset
EST       = 12             # months before the window used to estimate "normal" drift
HAC_LAGS  = 18             # Newey-West lags: >= event-window length (key fix)

ONI_URL = "https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt"
SEASON_TO_MONTH = {"DJF": 1, "JFM": 2, "FMA": 3, "MAM": 4, "AMJ": 5, "MJJ": 6,
                   "JJA": 7, "JAS": 8, "ASO": 9, "SON": 10, "OND": 11, "NDJ": 12}


# %% Cell 1 -- load ONI (NOAA CPC) ---------------------------------------------
def load_oni(url=ONI_URL):
    txt = requests.get(url, timeout=30).text
    df = pd.read_csv(StringIO(txt), sep=r"\s+")
    df.columns = [c.strip().upper() for c in df.columns]     # SEAS YR TOTAL ANOM
    df["month"] = df["SEAS"].map(SEASON_TO_MONTH)
    df["date"] = pd.to_datetime(dict(year=df["YR"], month=df["month"], day=1))
    oni = df.set_index("date")["ANOM"].sort_index().rename("ONI")
    oni.index = oni.index + pd.offsets.MonthEnd(0)           # align to month-end
    return oni

oni = load_oni()
print("ONI loaded:", oni.index.min().date(), "->", oni.index.max().date(),
      "| latest:", round(oni.iloc[-1], 2))


# %% Cell 2 -- load prices ------------------------------------------------------
import yfinance as yf

def _close(raw):
    if isinstance(raw.columns, pd.MultiIndex):
        lvl0 = set(raw.columns.get_level_values(0))
        return raw["Close"] if "Close" in lvl0 else raw.xs("Close", axis=1, level=1)
    return raw[["Close"]]

raw = yf.download(list(TICKERS), start=START, auto_adjust=True, progress=False)
px = _close(raw).rename(columns=TICKERS).resample(MONTH_END).last()
print(px.tail(3).round(2))


# %% Cell 3 -- panel, returns, and the SPREAD ----------------------------------
rets = np.log(px).diff()
rets.columns = [f"{c}_ret" for c in rets.columns]

data = px.join(rets)
data["ONI"] = oni.reindex(data.index)
# LONG COCOA / SHORT SUGAR, dollar-neutral, in log-return space:
data["spread_ret"] = data["cocoa_ret"] - data["sugar_ret"]
data = data.dropna(subset=["ONI"])
print(data[["ONI", "cocoa_ret", "sugar_ret", "spread_ret"]].tail(4).round(3))


# %% Cell 4 -- El Nino & La Nina onsets ----------------------------------------
def find_onsets(oni, thresh=0.5, sustain=5, min_gap_m=18, warm=True):
    """First month ONI crosses the threshold and stays for ~`sustain` months.
       warm=True -> El Nino (>= +thresh); warm=False -> La Nina (<= -thresh)."""
    t = abs(thresh)
    v, idx = oni.dropna().values, oni.dropna().index
    onsets, last = [], -10**9
    for i in range(len(v) - sustain):
        if warm:
            cross = v[i] >= t and (i == 0 or v[i - 1] < t)
            hold = (v[i:i + sustain] >= t).sum() >= sustain - 1
        else:
            cross = v[i] <= -t and (i == 0 or v[i - 1] > -t)
            hold = (v[i:i + sustain] <= -t).sum() >= sustain - 1
        if cross and hold and (i - last) >= min_gap_m:
            onsets.append(idx[i]); last = i
    return onsets

warm = find_onsets(data["ONI"], warm=True)
cold = find_onsets(data["ONI"], warm=False)
print("El Nino onsets:", [d.strftime('%Y-%m') for d in warm])
print("La Nina onsets:", [d.strftime('%Y-%m') for d in cold])


# %% Cell 5 -- CAR event study + "where is the signal?" -------------------------
def car_study(ret, onsets, pre=PRE, post=POST, est=EST):
    """Cumulative ABNORMAL return around each onset, centred at 0 at onset.
       Abnormal = return minus that event's own pre-window average return
       (a constant-mean benchmark), so the general softs uptrend is removed."""
    idx, paths = ret.index, {}
    for o in onsets:
        loc = idx.get_indexer([o], method="nearest")[0]
        if loc - pre - est < 0 or loc + post >= len(idx):
            continue
        bench = ret.iloc[loc - pre - est: loc - pre].mean()      # "normal" drift
        ar = ret.iloc[loc - pre: loc + post + 1] - bench          # abnormal returns
        car = ar.cumsum(); car.index = range(-pre, post + 1)
        paths[o] = (car - car.loc[0]) * 100                       # centre at onset, %
    df = pd.DataFrame(paths)
    return df.mean(axis=1), df.std(axis=1) / np.sqrt(df.shape[1]), df

def band(fig, mean, se, name, color):
    fig.add_scatter(x=mean.index, y=mean, mode="lines", name=name, line=dict(color=color))
    fig.add_scatter(x=list(mean.index) + list(mean.index[::-1]),
                    y=list(mean + se) + list((mean - se)[::-1]),
                    fill="toself", line=dict(width=0), fillcolor=color, opacity=0.15,
                    showlegend=False, hoverinfo="skip")

fig = go.Figure()
for c, col in [("cocoa", "#E4572E"), ("sugar", "#2E8B57"), ("coffee", "#4C6FFF")]:
    m, s, _ = car_study(data[f"{c}_ret"], warm)
    band(fig, m, s, c, col)
fig.add_hline(y=0, line_dash="dot"); fig.add_vline(x=0, line_dash="dash")
fig.update_layout(title="Where is the signal? Cumulative abnormal return after an El Nino onset",
                  xaxis_title="months from onset", yaxis_title="cumulative abnormal return (%)",
                  template="plotly_white")
fig.show()


# %% Cell 6 -- THE HEADLINE: long-cocoa/short-sugar spread, warm vs cold --------
m_w, s_w, df_w = car_study(data["spread_ret"], warm)
m_c, s_c, df_c = car_study(data["spread_ret"], cold)

fig = go.Figure()
band(fig, m_w, s_w, f"El Nino (n={df_w.shape[1]})", "#E4572E")
band(fig, m_c, s_c, f"La Nina (n={df_c.shape[1]})", "#4C6FFF")
fig.add_hline(y=0, line_dash="dot"); fig.add_vline(x=0, line_dash="dash")
fig.update_layout(title="Long cocoa / short sugar — cumulative abnormal spread return",
                  xaxis_title="months from onset", yaxis_title="spread CAR (%)",
                  template="plotly_white")
fig.show()
print(f"Spread CAR at +12m: El Nino {m_w.loc[12]:+.1f}%   La Nina {m_c.loc[12]:+.1f}%")


# %% Cell 7 -- ROBUSTNESS: leave-one-out + base rate ---------------------------
# Is the spread result driven by one event? Drop each El Nino event in turn.
fig = go.Figure()
for o in df_w.columns:
    loo = df_w.drop(columns=o).mean(axis=1)
    fig.add_scatter(x=loo.index, y=loo, mode="lines", line=dict(color="#BBBBBB", width=1),
                    name=f"drop {o.strftime('%Y')}", showlegend=False, hoverinfo="skip")
fig.add_scatter(x=m_w.index, y=m_w, mode="lines", line=dict(color="#E4572E", width=3),
                name="all events")
fig.add_hline(y=0, line_dash="dot"); fig.add_vline(x=0, line_dash="dash")
fig.update_layout(title="Leave-one-out: spread CAR dropping each El Nino event (grey) vs all (red)",
                  xaxis_title="months from onset", yaxis_title="spread CAR (%)",
                  template="plotly_white")
fig.show()

H = 12
per_event = df_w.loc[H]
print(f"\nBASE RATE at +{H}m across {per_event.shape[0]} El Nino events:")
for o, v in per_event.items():
    print(f"   {o.strftime('%Y-%m')}: {v:+.1f}%")
print(f"   -> spread positive in {int((per_event > 0).sum())} of {per_event.shape[0]} events")


# %% Cell 8 -- FORMAL TEST: HAC regression (the rigorous claim) -----------------
def lagged_xcorr(driver, series, max_lag=18):
    return pd.Series({k: driver.shift(k).corr(series) for k in range(max_lag + 1)})

best_lag = int(lagged_xcorr(data["ONI"], data["spread_ret"]).abs().idxmax())
print("Spread lead-lag peak at", best_lag, "months\n")

def hac_reg(y_col, lag, controls=("usdbrl_ret",)):
    d = data.copy()
    d["ONI_lag"] = d["ONI"].shift(lag)
    cols = ["ONI_lag", *controls]
    d = d.dropna(subset=[y_col, *cols])
    X = sm.add_constant(d[cols])
    m = sm.OLS(d[y_col], X).fit(cov_type="HAC", cov_kwds={"maxlags": HAC_LAGS})
    return m

for y in ["cocoa_ret", "sugar_ret", "spread_ret"]:
    m = hac_reg(y, best_lag)
    b, t, p = m.params["ONI_lag"], m.tvalues["ONI_lag"], m.pvalues["ONI_lag"]
    print(f"{y:12s}  ONI(lag {best_lag}) coef {b:+.4f}  t={t:+.2f}  p={p:.3f}  R2={m.rsquared:.3f}")


# %% Cell 9 -- ROBUSTNESS: does it survive different definitions? ---------------
print("Spread CAR at +12m by ONI threshold (event-study definition):")
for thr in [0.5, 0.75, 1.0]:
    w = find_onsets(data["ONI"], thresh=thr, warm=True)
    m, _, dfx = car_study(data["spread_ret"], w)
    print(f"   threshold >= {thr}:  {m.loc[12]:+5.1f}%   (n={dfx.shape[1]} events)")

print("\nSpread regression coef by lag (regression definition):")
for lg in sorted({max(best_lag - 3, 0), best_lag, best_lag + 3}):
    m = hac_reg("spread_ret", lg)
    print(f"   lag {lg:2d}m:  coef {m.params['ONI_lag']:+.4f}  t={m.tvalues['ONI_lag']:+.2f}")


# %% Cell 10 -- LIVE OVERLAY: the "so what" ------------------------------------
recent = data["ONI"].iloc[-24:]
fig = go.Figure()
fig.add_scatter(x=recent.index, y=recent.values, mode="lines+markers", name="ONI (last 24m)")
fig.add_hline(y=0.5, line_dash="dot", annotation_text="El Nino threshold")
fig.update_layout(title="Live setup: ONI trajectory into the forecast super El Nino",
                  xaxis_title="date", yaxis_title="ONI", template="plotly_white")
fig.show()

print("\n=== BASE-RATE READOUT (your interview line) ===")
print(f"Latest ONI {data['ONI'].iloc[-1]:+.2f} as of {data.index[-1].date()}.")
print(f"In {df_w.shape[1]} historical El Nino events, long-cocoa/short-sugar returned "
      f"{m_w.loc[12]:+.1f}% (median across events) by +12m,")
print(f"positive in {int((df_w.loc[12] > 0).sum())} of {df_w.shape[1]}. "
      f"La Nina control: {m_c.loc[12]:+.1f}%.")
