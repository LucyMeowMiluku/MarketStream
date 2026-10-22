# MarketStream experiment reconciliation and reproduction — 22 October 2026

The sole report master is [the Chinese revision](07_Revised_Report_CN.md); English is a companion translation. The authoritative per-run record is the [run ledger](Evidence_Attachments/Result_Run_Ledger_20261022.md), with a [machine-readable registry](reproduction_outputs/audit_20261022/result_registry.json). Each entry records source snapshot, run ID, data source, labels, parameters, raw output and conclusion scope; missing historical fields remain null.

| Layer | Run/artifact ID | Supported result and boundary |
|---|---|---|
| Code checks | CHECKS-20261022 | 63 tests passed in 4.67s and Ruff passed; 62 is the September 17 summary, 160 is an incompletely bound older claim |
| Synthetic trace | SYN-TRACE-20261022 | TP/FP/FN=360/120/0; P/R/F1=0.750/1.000/0.857; process p50/p95/p99=0.0150/0.0306/0.0688 ms |
| Separate ablation pass | SYN-SUITE-20261022 | Removing dislocation gives 300/0/60; removing activity changes nothing; timings cannot be pooled with trace |
| Legacy injection | LEGACY-INJECTED (artifact ID; original run ID absent) | Saved historical CEP/ML F1=0.7846/0.6392; exact execution snapshot missing |
| Kafka/database | Three original soak IDs | 15, 88 and 76 alerts belong to separate runs; saved latest p95=1.615935s; no rerun in this audit |
| Short real input | alpaca-live-20260819T144908Z | 48,734 events over about 88.289s; warm-up, no accuracy labels |
| Formal real replay | No run or output | All four label files remain unfrozen; no real-market effectiveness metrics |

## Corrected accounting

120 FP = 60 unmatched positive-scenario alerts + 60 negative-control alerts. The 40/240 figure counts alerting cases; those 40 cases emit 60 alerts already included in total FP.

Positive scenarios emit 420 alerts and controls emit 60, for 480 total. Row-level truth, detections and unmatched IDs are retained in [scenarios.json](reproduction_outputs/audit_20261022/scenarios.json); [reconciliation.json](reproduction_outputs/audit_20261022/reconciliation.json) verifies global and partitioned matching agree. The decomposition is established for this new traced run, not retroactively proven for old aggregate-only files.

## Reproduction

From the project root: `.venv/bin/python -m report.tools.audit_results`. This replaces files in audit_20261022; preserve a copy before rerunning for comparison. The script archives source, tests and lockfiles before two sequential passes. See [provenance.json](reproduction_outputs/audit_20261022/provenance.json) and [source_snapshot.tar.gz](reproduction_outputs/audit_20261022/source_snapshot.tar.gz). HEAD alone does not identify the dirty working tree. Check commands: `.venv/bin/pytest -q` and `.venv/bin/ruff check .`, with saved text outputs alongside the JSON.

The synthetic protocol directly constructs factor states. Its 1.604 alerts/ticker-hour includes artificial ten-minute gaps; cooldown=0 and zero duplicates do not verify production cooldown. The bootstrap resamples truth-hit indicators with FP fixed, so all hits produce degenerate intervals. Historical injection/soak/IEX files lack exact execution hashes and some raw rows; claims are limited to saved historical summaries. The audit does not restore services or claim a completed formal replay.
