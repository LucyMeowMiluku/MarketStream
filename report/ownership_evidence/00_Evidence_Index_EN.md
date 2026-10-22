> Audit, 22 October 2026: [07_Revised_Report_CN.md](07_Revised_Report_CN.md) is the sole report master; English is a companion translation. Use the [run ledger](Evidence_Attachments/Result_Run_Ledger_20261022.md) and [registry](reproduction_outputs/audit_20261022/result_registry.json) for numbers and missing provenance. Historical runs are not current-system results.

# MarketStream Technical Ownership Evidence Index

Prepared: 17 September 2026  
Working branch: `codex/core-simplification`  
Base commit: `bb0df67fad42ef6cf4c544b5e3711d57cd32f3fd`  
Evidence snapshot commit: `6bcdd04d42f266c820eebb6e0c28099cd288265f`  
Project stage: research prototype and technical validation

## Purpose

This package responds to concerns about my technical understanding, decisions,
validation, and contribution. It does not treat the Git repository or the final
report as sufficient evidence on their own. Each important statement is linked to
code, a test, an experiment output, a literature source, or an available AI log.

The supervisor has not yet confirmed this package as an accepted assessment format.
It is my evidence-based response to the four gaps described in my email.

## Requirement map

| Requirement | Main document | Primary evidence | Status |
|---|---|---|---|
| Verify the literature | [`04_Literature_Verification_CN.md`](04_Literature_Verification_CN.md) | Paper sections, pages, DOI or official source, and report claim | Completed for the 12 references used in the report; access limits are marked |
| Explain architecture decisions and technical contribution | [`01_Technical_Ownership_Evidence_EN.md`](01_Technical_Ownership_Evidence_EN.md), [`02_Technical_Contribution_Log_CN.md`](02_Technical_Contribution_Log_CN.md) | Code, tests, Git history, debugging records, and AI logs | Completed with explicit human/AI boundaries |
| Provide reproducible experiment records | [`03_Experiment_Reproducibility_CN.md`](03_Experiment_Reproducibility_CN.md) | Commands, JSON outputs, source type, protocol, and limitations | Current tests and synthetic protocol rerun; infrastructure soak blocked by local Docker state |
| Provide available AI interaction logs and an index | [`05_AI_Log_Index_CN.md`](05_AI_Log_Index_CN.md), [`AI_Logs/README.md`](AI_Logs/README.md) | Project-related Codex task IDs and accessible transcripts | Project tasks indexed; Claude history unavailable; account export pending |

## Evidence classes

I use four evidence classes throughout this package.

1. **Current-version measured result.** Reproduced on the present working tree.
2. **Historical result.** Produced by an older implementation or protocol and kept
   to explain project development.
3. **Controlled technical validation.** Produced from generated sequences,
   injected anomalies, or synthetic transport traffic. It does not measure real
   market accuracy.
4. **Not yet demonstrated.** The required data, labels, environment, or independent
   review is incomplete.

## Current evidence baseline

| Item | Current evidence | Classification | Boundary |
|---|---:|---|---|
| Automated tests | 63 passed in 4.67 s | Current-version measured result | Shows conformance to the present test suite, not production reliability |
| Ruff | All checks passed | Current-version measured result | Static checks only |
| Generated CEP protocol | Precision 0.750, Recall 1.000, F1 0.857 | Controlled technical validation | Generated factor sequences, not real market labels |
| Generated CEP computation | SYN-TRACE-20261022: p50 0.0150 ms, p99 0.0688 ms | Current-version measured result on synthetic snapshots | Excludes Kafka, database, and network time |
| Negative controls | 40 alerting cases out of 240 | Controlled technical validation | 40 cases emit 60 alerts included in the 120 total FP |
| Latest available Kafka/database soak | 240 events, 76 alerts, p95 1.616 s | Historical controlled validation dated 10 September 2026 | No rerun in this audit; September 17 notes reported Docker unavailable |
| Older Kafka/database soak | 240 events, 88 alerts, p95 1.718 s | Historical controlled validation dated 6 August 2026 | Retained to show the earlier run, not used as the current result |
| Alpaca IEX live run | 48,734 events over about 88 seconds | Historical real-input engineering validation | Warm-up only. It does not provide real detection Precision or Recall |
| Real historical effectiveness | No eligible result | Not yet demonstrated | Labels remain unreviewed and unfrozen |

## Main corrections made in this package

- `160 passed` is an older-version result. CHECKS-20261022 has 63 tests; the September 17 summary had 62.
- The latest available soak has 76 alerts. The 88-alert run is retained as an older
  run instead of being silently replaced.
- 120 FP = 60 unmatched positive-scenario alerts + 60 negative-control alerts. The 40/240 figure counts alerting cases; those 40 cases emit 60 alerts already included in total FP.
- The old 0.0033 ms comparison and the current synthetic timing are not presented as
  one experiment.
- The old ML comparison used real OHLCV with injected anomalies. It does not prove
  that the current CEP system is better on real market events.
- The IEX run proves data transport and factor generation only. IEX is not the full
  consolidated SIP market.
- Real historical metrics are withheld until all 12 abnormal and 12 normal intervals
  are independently reviewed and frozen.

## Package navigation

- [`01_Technical_Ownership_Evidence_EN.md`](01_Technical_Ownership_Evidence_EN.md): main English ownership statement.
- [`01_Technical_Ownership_Evidence_CN.md`](01_Technical_Ownership_Evidence_CN.md): Chinese fact-checking version.
- [`02_Technical_Contribution_Log_CN.md`](02_Technical_Contribution_Log_CN.md): six contribution records.
- [`03_Experiment_Reproducibility_CN.md`](03_Experiment_Reproducibility_CN.md): experiment protocols and interpretation.
- [`04_Literature_Verification_CN.md`](04_Literature_Verification_CN.md): verification of all report references.
- [`05_AI_Log_Index_CN.md`](05_AI_Log_Index_CN.md): project-related AI interaction index.
- [`06_Report_Revision_Log_CN.md`](06_Report_Revision_Log_CN.md): correction register.
- [`07_Revised_Report_EN.md`](07_Revised_Report_EN.md): revised English report.
- [`Evidence_Attachments/Git_Evidence.md`](Evidence_Attachments/Git_Evidence.md): version and authorship evidence.
- [`Evidence_Attachments/Test_Outputs.md`](Evidence_Attachments/Test_Outputs.md): reproduced checks.
- [`Evidence_Attachments/Experiment_Artifact_Index.md`](Evidence_Attachments/Experiment_Artifact_Index.md): raw experiment map.

- [`08_Contribution_Attribution_Matrix_EN.md`](08_Contribution_Attribution_Matrix_EN.md): decision, execution and evidence matrix (22 October 2026).
- [`08_Contribution_Attribution_Matrix_CN.md`](08_Contribution_Attribution_Matrix_CN.md): Chinese matrix.
- [`Evidence_Attachments/Decision_Log_Excerpts.md`](Evidence_Attachments/Decision_Log_Excerpts.md): original record locations and excerpts.

- [`Evidence_Attachments/Attribution_Validation_20261022.md`](Evidence_Attachments/Attribution_Validation_20261022.md): attribution verification results.

- [`09_Core_Contribution_Statement_EN.md`](09_Core_Contribution_Statement_EN.md): concise statement of personal leadership and AI-assisted development.
- [`09_Core_Contribution_Statement_CN.md`](09_Core_Contribution_Statement_CN.md): Chinese contribution statement.

## Authorship and AI statement

I led the selection of MarketStream’s core solution and its development priorities, scope, key design constraints, and verification requirements. I prioritised the backend pipeline, selected eight factors across three time windows with six CEP patterns as the detection architecture, and drove core simplification and modularisation. I directly specified baseline persistence, retention of the latest 20 trading days per cell, three explicit startup modes, and recovery requirements. I also required real-data evaluation, anomaly intervals identified in advance, and visual replay.

AI served as an auxiliary development tool: it provided technical advice, helped elaborate proposals, generated and refactored code, executed tests and debugging, and drafted and revised report text. AI contributed specific proposals for the factors, windows, patterns and explicit state-machine refactoring; implementation proceeded after my approval. Those proposals and generation records remain identified in the provenance materials.

My core contributions are solution selection, concrete problem and constraint design, development trade-offs, verification requirements, and report revision decisions. The contribution matrix separately evidences requirements I directly proposed and advice I chose to adopt, linking my decisions, AI assistance, and the resulting code and experiment artifacts.

The [attribution matrix](08_Contribution_Attribution_Matrix_EN.md) is the decision-to-evidence map, with a [Chinese version](08_Contribution_Attribution_Matrix_CN.md). The [log excerpts](Evidence_Attachments/Decision_Log_Excerpts.md) identify original records and distinguish direct requirements, adoption decisions and AI execution. Architecture selection is not conflated with first proposal, and testing is not conflated with manual authorship.

Sole initial authorship of the detailed architecture, all core/state-machine code and the extent of personally written report text are unconfirmed. Git identities record repository versions; they do not settle generation provenance. Claude history remains unavailable and is not reconstructed. Private chats and unrelated projects remain excluded.

## Remaining gaps

- Personal code/prose authorship requires specific editing evidence; archived JSONL includes existing escaping defects documented in the log excerpts.

- The supervisor has not yet stated whether this evidence format is sufficient.
- The real-event label registry is still a draft and is not frozen.
- The evidence snapshot records the core simplification, baseline-persistence work,
  current tests, selected experiment artifacts, and this package. Large historical
  datasets, model binaries, presentation drafts, and unrelated local browser files
  remain outside the snapshot.
- A new Kafka/database soak needs a running Docker or compatible local service stack.
- ChatGPT account data export may arrive after this first package version.
