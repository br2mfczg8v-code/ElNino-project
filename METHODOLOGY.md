# Methodology — El Niño and the cocoa–sugar spread

Plain-language companion to `enso_cocoa_sugar.py`. It explains **what** each step does, **why** it's there, and the **caveat** that comes with it — so you can defend every line of the project in an interview. Read it once and you'll be able to answer almost any question thrown at the work.

---

## The thesis in one paragraph

A well-known market story says El Niño drives up soft-commodity prices. When you test it properly, the popular version (El Niño → coffee) doesn't survive scrutiny. The real, mechanism-backed signal is that El Niño is **bullish cocoa** — its hot, dry pattern damages the West African crop that grows ~60% of the world's cocoa — and **bearish sugar**. Because those move in opposite directions, the clean way to express it is a market-neutral **spread: long cocoa, short sugar**, put on into a strong El Niño. This project measures how that spread has behaved around past El Niños, and stress-tests whether the result is real or luck.

---

## The data

Everything is free and reproducible, which matters — an interviewer can rerun it.

- **ENSO signal — the ONI (Oceanic Niño Index)** from NOAA's Climate Prediction Center. It's the standard measure of how warm or cool the equatorial Pacific is: above +0.5 °C is El Niño, below −0.5 °C is La Niña. Monthly, back to 1950.
- **Prices** — cocoa (`CC=F`), sugar (`SB=F`), and coffee (`KC=F`) front-month futures from Yahoo Finance, plus USD/BRL (`BRL=X`) as a control (Brazil is a huge softs producer, so the currency moves these markets independently of weather).

---

## The design choices, one by one

### Monthly data and log returns
**What:** I collapse daily prices to month-end and work in log returns.
**Why:** ENSO evolves over months, not days, so daily noise just gets in the way. Log returns add up cleanly over time (a −10% then +10% is roughly zero), which makes the cumulative maths honest.
**Caveat:** Monthly data means fewer observations — a real constraint given how rare El Niños are.

### Turning the ONI seasons into months
**What:** NOAA publishes the ONI as overlapping three-month seasons (DJF, JFM, …). I map each season to its **centre month** (DJF → January, and so on).
**Why:** It puts the climate index on the same monthly calendar as prices so they can be lined up.
**Caveat:** The ONI is therefore a 3-month smoothed number by construction — which is exactly why El Niños look like they "peak in December" (the NDJ/DJF seasons); that's the index design, not a data error.

### Defining when an El Niño "starts"
**What:** An onset is the first month the ONI crosses its threshold (+0.5 for warm, −0.5 for cold) and then **stays there for about five months**, with events kept at least 18 months apart.
**Why:** A single month above the line can be noise; requiring persistence approximates NOAA's official "five overlapping seasons" rule and picks out genuine events. The 18-month gap stops one long event being double-counted.
**Caveat:** These cutoffs are judgement calls, so I test that the result survives moving them (see *Robustness*).

### The spread: long cocoa / short sugar
**What:** The headline object isn't cocoa or sugar alone — it's `cocoa return − sugar return`, a dollar-neutral long/short.
**Why:** Two reasons. First, it matches the economics: the signal is *opposite-signed* in the two crops, so trading them against each other captures both sides at once. Second, and more subtly, it **cancels out whatever moves all soft commodities together** — the dollar, general risk appetite, the broad commodity trend — leaving mostly the ENSO-specific difference. That makes the test cleaner *and* describes a more sophisticated, hedged trade than "buy cocoa."
**Caveat:** A spread assumes you can actually short sugar and that the two legs stay comparably sized; in reality there's financing and roll cost I'm not modelling.

### Abnormal returns (CAR), not raw indexed price lines
**What:** For each event I don't just index the price to 100 at the onset. I first estimate that market's **"normal" drift** from the year *before* the event window, subtract it, and accumulate what's left — the *cumulative abnormal return* (CAR).
**Why:** This is the single most important fix. Soft commodities drifted upward over 2000–2026, so *any* window looks like it "rises after an event" — even random dates. My first attempt fell into exactly this trap: prices rose after both El Niño **and** La Niña. Subtracting each event's own normal drift removes that background trend, so what remains is genuinely attributable to the event, not to the general bull market.
**Caveat:** The "constant drift" benchmark is simple; a fancier version would model each market's risk factors. And CAR still can't fully remove pre-existing momentum.

### Centering at the onset
**What:** Every event's CAR is set to zero at month 0 (the onset).
**Why:** So all events are compared on the same footing — "how much did the spread move *because of* the event," starting from a common zero.
**Caveat:** Watch the months *before* zero. In a clean natural experiment the lines should sit near zero pre-onset. If they wander, some of the "signal" may be a pre-trend — an honest thing to flag rather than hide.

### The La Niña control
**What:** I run the identical event study around **La Niña** onsets and compare.
**Why:** It's the placebo. If the spread only moves after El Niño and *not* after La Niña, the effect is really about the warm phase. If it moves the same after both, it's just seasonality or drift. Comparing the two also cancels any calendar effect common to both, because El Niños and La Niñas tend to land in similar parts of the year.
**Caveat:** There are even fewer La Niña events than El Niño ones, so the control itself is noisy.

### Leave-one-out
**What:** I recompute the spread's average path five times, each time **dropping one El Niño event**, and plot them all.
**Why:** With only a handful of events, one dramatic year (say 2015–16) could be creating the whole result. If the average stays positive no matter which event you remove, it's a pattern; if it collapses when you drop one, it's an anecdote. This directly answers the first question a sharp interviewer asks: *"is this just one event?"*
**Caveat:** Even surviving leave-one-out doesn't make a 5–7 event sample large; it just rules out the worst failure mode.

### HAC (Newey–West) standard errors — with long lags
**What:** In the regression I use Newey–West standard errors with the lag length set to the full event-window length (~18 months), not a token number.
**Why:** My event windows overlap in time and monthly returns are autocorrelated, which makes ordinary statistics *think* they have far more independent information than they do — and report false confidence. Newey–West widens the error bars to account for that overlap. Setting the lags long enough to cover the overlap is the difference between honest and misleadingly-significant.
**Caveat:** HAC helps but can't manufacture information that isn't there; with few events the honest p-values will be modest.

### The regression as the *formal* claim
**What:** The event-study charts are the illustration; the regression of returns on the lagged ONI is the formal statistical test.
**Why:** Event-study charts use price *levels*, which trend and can mislead. Returns are stationary and better behaved for inference, so the regression is the object I'd stand behind numerically, with the chart as the intuition.
**Caveat:** Even the regression is on a short sample — treat coefficients as suggestive, not laws.

### Robustness to definitions
**What:** I rerun the spread result across ONI thresholds (0.5 / 0.75 / 1.0) and across nearby lags (peak ±3 months).
**Why:** To show the finding isn't an artifact of one lucky choice of cutoff. If long-cocoa/short-sugar stays positive across all of them, that's real robustness.
**Caveat:** If it only works at one specific threshold or lag, that's a red flag — and better to discover it here than live.

### Multiple comparisons — the honesty note
**What:** I looked at three commodities (coffee, cocoa, sugar) and am reporting the two that showed signal.
**Why to disclose it:** With three tries, finding one effect in each direction by chance isn't shocking. What rescues it is that the mechanisms were **specified in advance from agronomy** (West African drought for cocoa) rather than mined — so the biology, not the p-value, carries the "why these two." Say this out loud; it shows you understand the trap.

---

## What you can — and can't — honestly claim

**Can say:** "Across the El Niño events since 2000, a long-cocoa/short-sugar spread earned a positive cumulative abnormal return by ~12 months, it survived a La Niña control and leave-one-out, and it's consistent with the agronomy. With a super El Niño forecast to peak this winter, that's the live setup."

**Should not say:** "El Niño *makes* cocoa go up," or wave a three-star p-value. With 5–7 events you cannot get airtight significance — and claiming it is the fastest way to lose credibility. The right frame is a **probabilistic base rate with named caveats**, which is exactly how a trader thinks about an edge.

---

## Known limitations (say these before you're asked)

- **Small sample.** ~7 El Niño / ~5 La Niña events in the price era. Everything is suggestive, not proven.
- **Possible pre-trend.** If the pre-onset lines aren't flat, part of the move may predate the event.
- **Short price history.** Free futures data realistically starts ~2000, so the big 1982/1997 events aren't in the return series.
- **Proxy and cost gaps.** Front-month futures ignore roll yield; the spread ignores financing and shorting cost.
- **Event dating is fuzzy.** "Onset" depends on the threshold rule; reasonable people would date some events a month or two differently.

None of these sink the project — naming them *is* the sophisticated version of the project.

---

## How to talk about it (30 seconds)

> "Everyone repeats that El Niño lifts soft commodities. I tested it and the popular coffee version washes out against a La Niña control. The signal actually sits in cocoa — bullish, from West African drought — and sugar — bearish — in opposite directions, so I trade the spread: long cocoa, short sugar. It survives leave-one-out and different thresholds, though it's a small sample so I treat it as a base rate, not a law. With a super El Niño forecast to peak this winter, it's a live setup, and the code and write-up are on my GitHub."

Lead with the reversal (the popular story failing), because *finding your own hypothesis is wrong and saying so* is the most credible thing you can do in a markets interview.
