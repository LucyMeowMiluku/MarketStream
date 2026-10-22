> Audit, 22 October 2026: [07_Revised_Report_CN.md](07_Revised_Report_CN.md) is the sole report master; English is a companion translation. Use the [run ledger](Evidence_Attachments/Result_Run_Ledger_20261022.md) and [registry](reproduction_outputs/audit_20261022/result_registry.json) for numbers and missing provenance. Historical runs are not current-system results.

# MarketStream: my leadership of core contributions

Author: XI LU. Revised: 22 October 2026.

I led the selection of MarketStream’s core solution and its development priorities, scope, key design constraints, and verification requirements. I prioritised the backend pipeline, selected eight factors across three time windows with six CEP patterns as the detection architecture, and drove core simplification and modularisation. I directly specified baseline persistence, retention of the latest 20 trading days per cell, three explicit startup modes, and recovery requirements. I also required real-data evaluation, anomaly intervals identified in advance, and visual replay.

AI served as an auxiliary development tool: it provided technical advice, helped elaborate proposals, generated and refactored code, executed tests and debugging, and drafted and revised report text. AI contributed specific proposals for the factors, windows, patterns and explicit state-machine refactoring; implementation proceeded after my approval. Those proposals and generation records remain identified in the provenance materials.

My core contributions are solution selection, concrete problem and constraint design, development trade-offs, verification requirements, and report revision decisions. The contribution matrix separately evidences requirements I directly proposed and advice I chose to adopt, linking my decisions, AI assistance, and the resulting code and experiment artifacts.

## Core contributions and direct evidence

| Work I led | Concrete decisions and outputs | Direct evidence |
|---|---|---|
| Architecture and implementation priorities | Prioritised the backend; selected eight factors, 10-second / 1-minute / 5-minute windows and six CEP patterns; required simplification and modularisation | Matrix D01–D03; A L68, L70; B L209, L235 |
| State and recovery requirements | Specified database persistence, the business key, 20 trading days, restoration into memory, a separate startup module and three explicit modes | D04, D05; C L3, L30, L44 |
| Credible evaluation | Challenged accuracy/recall provenance; required real data, prior anomaly intervals and HTML replay; approved freezing and leakage safeguards | D06, D07; D L3, L67 |
| Engineering verification | Required completion and reruns of outstanding Alpaca live, historical-data and Kafka-to-database checks | D08; A L213, L423 |
| Report structure and argument requirements | Required anomaly definitions, named studies and numbered citations; simpler architecture/experiment chapters; metric units, denominators and separate count, proportion and latency tables | D09, D10; F L84, L93, L139; G L173, L272, L324; H L3 |

The [five-column matrix](08_Contribution_Attribution_Matrix_EN.md) maps claims, my actions, AI assistance, log locations and artifacts. The [original-log excerpts](Evidence_Attachments/Decision_Log_Excerpts.md) provide messages, line numbers and the file-key legend.

## Specific AI assistance

AI provided technical advice and elaboration; generated event, factor, state-machine, persistence and replay code; assisted refactoring, tool execution, testing and diagnosis; and drafted and revised substantial reference-report text. My leadership is evidenced by concrete decisions and requirements. AI advice and implementation are evidenced by assistant messages, tool calls and artifacts. Both sources remain inspectable.

## Attribution criteria

This statement claims leadership of core solution selection, development scope and key requirements, with AI-assisted prototype development. Approval is not recast as initial authorship of every detail, and AI-generated code or text is not relabelled as my manual work. The extent of personal code and paragraph authorship remains subject to the matrix’s unresolved items. Supervisor guidance, public methods and third-party platforms retain their attribution. Existing experiments support the prototype and controlled verification; real-market detection performance awaits frozen-label evaluation.


## Verification scope (22 October 2026)

Engineering-verification decisions are supported by the decision logs; effectiveness claims must use the [run ledger](Evidence_Attachments/Result_Run_Ledger_20261022.md). 120 FP = 60 unmatched positive-scenario alerts + 60 negative-control alerts. The 40/240 figure counts alerting cases; those 40 cases emit 60 alerts already included in total FP. The archived audit tree passed 63 tests and Ruff; historical soak, injection and short IEX results remain separate. No formal real-market replay has eligible labels or metrics. Tests and saved outputs establish behavior within their protocols, not who authored the code.
