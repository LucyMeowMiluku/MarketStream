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

(Filled in after this proposal is committed; see below.)
