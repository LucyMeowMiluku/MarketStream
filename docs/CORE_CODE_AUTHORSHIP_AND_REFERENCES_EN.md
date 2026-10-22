# MarketStream code provenance, personal decisions and AI implementation

Revised: 22 October 2026. Author: XI LU. **I led the core solution and development priorities; AI assisted development.**

I led the selection of MarketStream’s core solution and its development priorities, scope, key design constraints, and verification requirements. I prioritised the backend pipeline, selected eight factors across three time windows with six CEP patterns as the detection architecture, and drove core simplification and modularisation. I directly specified baseline persistence, retention of the latest 20 trading days per cell, three explicit startup modes, and recovery requirements. I also required real-data evaluation, anomaly intervals identified in advance, and visual replay.

AI served as an auxiliary development tool: it provided technical advice, helped elaborate proposals, generated and refactored code, executed tests and debugging, and drafted and revised report text. AI contributed specific proposals for the factors, windows, patterns and explicit state-machine refactoring; implementation proceeded after my approval. Those proposals and generation records remain identified in the provenance materials.

My core contributions are solution selection, concrete problem and constraint design, development trade-offs, verification requirements, and report revision decisions. The contribution matrix separately evidences requirements I directly proposed and advice I chose to adopt, linking my decisions, AI assistance, and the resulting code and experiment artifacts.

The [attribution matrix](../report/ownership_evidence/08_Contribution_Attribution_Matrix_EN.md) maps each decision to original messages and code. The [log excerpts](../report/ownership_evidence/Evidence_Attachments/Decision_Log_Excerpts.md) preserve roles, original line numbers and timestamps. The [Chinese module map](CORE_CODE_AUTHORSHIP_AND_REFERENCES_CN.md) provides additional file detail.

AI generation is recorded for initial event/quality/factor code (A L81), CEP changes (A L85), explicit machines (B L253), factor module splitting (B L268/L274), baseline repository/checkpoints/startup (C L61/L63/L67), replay (D L83/L92), and the full report reference draft (F L52–L56). My recorded decisions include architecture adoption (A L70), simplification and modularisation (B L209/L235), direct persistence requirements (C L3/L30), real-data and prior-label requirements (D L3/L67), reruns (A L213/L423), and report changes (E07–E09).

The project-specific combination of factors, time scales, financial event patterns, state, recovery and evaluation is a project contribution. Personal decision ownership is established per item; it does not imply sole manual implementation or first invention of public methods. MAD, quantiles, order imbalance, market residuals, CEP and Isolation Forest retain their public-method attribution. Kafka, TimescaleDB, Alpaca and scikit-learn remain third-party tools. A method citation does not itself establish source-code copying or a complete source audit.

Sole initial authorship of every detailed design, all manual core code, and the extent of personally written report prose are unconfirmed. Specific personal edits require diffs or editing history. Git author identity, header names, code understanding and successful tests cannot alone establish generation provenance. Missing Claude history remains disclosed and original archived logs are preserved.


## Verification scope (22 October 2026)

Engineering-verification decisions are supported by the decision logs; effectiveness claims must use the [run ledger](../report/ownership_evidence/Evidence_Attachments/Result_Run_Ledger_20261022.md). 120 FP = 60 unmatched positive-scenario alerts + 60 negative-control alerts. The 40/240 figure counts alerting cases; those 40 cases emit 60 alerts already included in total FP. The archived audit tree passed 63 tests and Ruff; historical soak, injection and short IEX results remain separate. No formal real-market replay has eligible labels or metrics. Tests and saved outputs establish behavior within their protocols, not who authored the code.
