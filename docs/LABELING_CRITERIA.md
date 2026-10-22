# Labeling criteria for the reviewed real-market intervals

**Status: PROPOSED — awaiting approval by the project lead (XI LU).** Nothing in this file
may be changed after approval except through a dated amendment written before any interval is
labelled. No interval may be labelled until the status line reads *APPROVED*.

## 0. Independence

- The rules below were written from first principles and general market conventions. No
  detector output (CEP, Isolation Forest, replay traces, dashboard alerts) for any candidate
  date was produced or consulted.
- Disclosure: while writing the review guide, the author of this proposal saw the candidate
  list and one evidence summary (`aapl-fy24-q2-reaction`). No thresholds were set with
  reference to it, and no other candidate data was inspected.
- The only data used to check the rules is a disjoint period (2023-08 to 2023-11, Section 7),
  which overlaps no candidate interval, no candidate baseline (earliest 2024-01) and no holdout
  (2025-05/06).
- Labels describe the market, not the detector: they use consolidated SIP minute bars (the
  whole market), while the detector reads IEX (about 1–3% of volume). Whether the detector
  can see an event is irrelevant to its label.

## 1. Fixed measurement window

Each candidate keeps its pre-registered 90-minute window (09:30–11:00 or 14:00–15:30 New York
time). Reviewers do not move or resize windows; a window that does not meet the rules is
excluded, not adjusted.

## 2. Measurements (computed by the review tool, all from SIP 1-minute bars)

| Symbol | Meaning |
|---|---|
| reference price `P_ref` | opening windows: previous regular-session close (close of the 15:59 bar); other windows: close of the minute before the window |
| `P_open`, `P_end` | open of the first window minute; close of the last window minute |
| gap `G` | `P_open / P_ref − 1` (≈ 0 for afternoon windows) |
| in-window move `W` | `P_end / P_open − 1` |
| total move `M` | `P_end / P_ref − 1` — the move the window ends with |
| range `R` | `(highest high − lowest low) / P_ref` inside the window |
| volume `V` | shares traded inside the window |
| excess move `X` | `M` of the stock minus `M` of QQQ (single stocks only) |

**Typical value** = the median of the same measurement, for the same ticker and the same clock
window, over the **20 previous regular sessions** (the day itself excluded). Moves use absolute
values. Each ratio is `today / typical`, e.g. `r_M = |M| / median(|M| over 20 sessions)`.

*Why this way:* the same 1% move means different things for SPY and TSLA, and the opening 90
minutes are always busier than the afternoon. Comparing a stock with itself at the same time
of day removes both effects. The median ignores a few unusual days in the reference period.

## 3. Anomaly — all of A1–A5 must hold

| Rule | Requirement | Plain-language reason |
|---|---|---|
| A1 magnitude | `r_M ≥ 4` **and** `|M| ≥ 1.0%` (single stocks) or `≥ 0.5%` (SPY, QQQ) | At least four times the usual move for this time slot. If moves were bell-shaped this is about 2.7 standard deviations (roughly 1 day in 150); real markets have fatter tails, so Section 7 reports the actual rate. The floor stops a very calm reference month from turning a small move into an "anomaly". |
| A2 participation | `r_V ≥ 2` | Real news brings in more trading. Doubling the usual volume is a common "unusual volume" screen. |
| A3 documented cause | at least one https source describing a catalyst that became public **after the reference time and before the window end** | Makes the label checkable by anyone, and is required by the label schema. A headline alone is not enough; A1 and A2 must also hold. Preferred sources: company IR / SEC filings, Federal Reserve, BLS/BEA, exchange notices; then major news outlets. |
| A4 clear direction | not (gap and in-window move have opposite signs **and** `|W| ≥ 0.5·|G|`) | If the price jumps at the open and then gives back half or more of the jump, the event has no single direction. |
| A5 complete data | at least 95% of window minutes present for the ticker, SPY and QQQ; no trading halt in the window | Missing data cannot support a label. |

**Direction** = sign of `M` (up if positive). The gap and the in-window move are both shown
and recorded, but the label uses `M`, because an event is the market's total reaction measured
from the last price before the news.

**Scope** (recorded, not part of the label): for single stocks, *stock-specific* if
`r_X ≥ 4`, otherwise *market-wide*. **Event type** (recorded): `earnings`, `company_news`,
`macro_release`, `market_wide_shock`, `other` — deliberately not the detector's pattern names.

## 4. Normal — all of N1–N6 must hold

| Rule | Requirement | Plain-language reason |
|---|---|---|
| N1 quiet price | `r_M ≤ 1.5` and `r_R ≤ 1.5` | The move and the intraday swing are both close to usual. |
| N2 quiet volume | `r_V ≤ 1.5` | Usual participation. |
| N3 quiet market | SPY and QQQ each have `r_M ≤ 1.5` in the same window | A calm stock on a turbulent market day is not a clean control. |
| N4 no company catalyst | no material news about the ticker published after the reference time and before the window end | Material = earnings/guidance, company press release or filing, M&A, product event, executive change, legal/regulatory decision, trading halt, index change. Routine analyst notes, price-target changes and general market commentary do **not** count. |
| N5 no scheduled macro event | none of: FOMC statement/press conference/minutes, Fed Chair testimony, CPI, PPI, Employment Situation, PCE/Personal Income, GDP advance estimate — released after the reference time and before the window end | These move the whole market on schedule. Check the official calendars (links in the tool). |
| N6 complete data | as A5 | |

"No news found" is not evidence on its own; N1–N3 must also hold.

## 5. Everything else is excluded

The gap between the thresholds (moves between 1.5× and 4× the usual, volume between 1.5× and
2×) is a deliberate grey zone. An interval that satisfies neither A1–A5 nor N1–N6 is
**excluded** (`reject`) and replaced. Also excluded: uncertain catalyst timing, a direction
conflict (A4), incomplete data, a trading halt, or a reviewer who is unsure. Excluding is
always allowed; forcing a label is not.

*Why:* a benchmark is more trustworthy with fewer, clear-cut labels than with many borderline
ones. Thresholds are never relaxed to reach 12 + 12.

## 6. Recording and replacements

- **Confidence:** 0.9 when every applicable threshold is met with at least a 25% margin
  (e.g. `r_M ≥ 5`, `r_V ≥ 2.5`; for normals `r_M ≤ 1.2`); otherwise 0.7.
- For every interval record the measured values, each rule's result, the sources checked
  (with publication times), the decision and a short reason. The review tool does this.
- **Replacements:** a rejected candidate is replaced from the candidate pool, or with a new
  candidate of the same ticker, applying the same rules blind. The 12 + 12 set must cover AAPL,
  TSLA, NVDA, QQQ and SPY. Replacement reasons are recorded.
- Same-day related intervals (e.g. a stock and QQQ on the same market-wide shock) are allowed
  but must be flagged as not independent.
- A second reviewer should label at least kind and direction independently; disagreements
  are resolved by one discussion, otherwise the interval is excluded and replaced.

## 7. Base rates on a disjoint period (informative only)

Run after the proposal above was committed: `scripts/labeling_base_rates.py`, SIP split-adjusted
minute bars, 64 sessions (2023-08-14 to 2023-11-10) × 5 tickers × 2 windows = 640
ticker-windows, each against its own 20 prior sessions. Only the market-data rules can be
applied automatically (A1, A2, A4, A5; N1, N2, N3, N6); A3, N4 and N5 need a person.
Outputs: `report/ownership_evidence/reproduction_outputs/labeling_base_rates_2023/`.

| Group (market-data rules only) | Windows | Share |
|---|---:|---:|
| Anomaly rules A1+A2+A4+A5 | 4 | 0.6% |
| Normal rules N1+N2+N3+N6 | 308 | 48.1% |
| Grey zone (excluded) | 328 | 51.3% |
| A1 magnitude alone | 26 | 4.1% |

The four anomaly-eligible windows are recognisable events of that period: AAPL on 2023-09-07
(down), QQQ 14:00–15:30 on 2023-09-20 (down, FOMC day), NVDA on 2023-10-17 (down, export-rule
day), QQQ 14:00–15:30 on 2023-11-01 (up, FOMC day).

Checks against known events of the same period:

| Day, ticker | Context | Move ratio | Volume ratio | Result |
|---|---|---:|---:|---|
| 2023-10-19 TSLA | earnings after previous close, −8.8% | 6.8 | 1.5 | grey: fails **A2 only** |
| 2023-08-24 NVDA | earnings, opened up then faded | 1.0 | 3.1 | grey: fails A1 and A4 (as intended) |
| 2023-11-03 AAPL | earnings, modest reaction | 2.0 | 2.0 | grey: fails A1 |
| 2023-09-13, 2023-10-12 SPY | CPI release 08:30 | 0.8, 0.1 | 0.9, 0.7 | pass N1–N3; **N5 must exclude them** |

## 8. Open decision before approval: is volume required for an anomaly?

The base rates show that A2 (volume ≥ 2× typical) excludes a textbook earnings reaction
(TSLA 2023-10-19: −8.8%, 6.8× its usual move, volume 1.5×). After overnight news much of the
repricing happens before the open, so regular-session volume does not necessarily double.

- **Option 1 — keep A2 as proposed.** Very strict: 0.6% of ordinary windows qualify on market
  data; clear gap reactions without doubled volume are excluded.
- **Option 2 — volume becomes supporting evidence (recommended).** Anomaly = A1 + A3 + A4 + A5;
  volume is recorded and the 0.9 confidence level additionally requires `r_V ≥ 2`. On market
  data 15 of 640 windows (2.3%) qualify before the documented-cause check A3, which then
  removes moves without a public cause.

Clarification proposed with either option: A3 accepts any documented public cause, including a
major analyst rating change, provided it became public after the reference time; N4 still
ignores routine analyst notes, because a move large enough to matter already fails N1.

The project lead chooses an option; the chosen text then replaces Section 3 and the status
line becomes *APPROVED* with the date.
