> Audit, 22 October 2026: [07_Revised_Report_CN.md](07_Revised_Report_CN.md) is the sole report master; English is a companion translation. Use the [run ledger](Evidence_Attachments/Result_Run_Ledger_20261022.md) and [registry](reproduction_outputs/audit_20261022/result_registry.json) for numbers and missing provenance. Historical runs are not current-system results.

# MarketStream Literature Verification

## 1. Summary Table

| ID | Paper | Claim Used in the Report | Location in the Original Source | My Understanding | What It Supports | What It Does Not Support | Change in the Report |
|---|---|---|---|---|---|---|---|
| [1] | Barrie et al., MEDOS | It constructs physically meaningful derived parameters from raw measurements, compares them with typical values, and gives confidence for an event. | NTRS abstract; PDF Section II, “Core MEDOS Algorithms,” around PDF pp. 2–4; validation in Section III | The main idea of MEDOS is not to apply one threshold directly to a raw value. It first uses domain knowledge to construct derived parameters and then makes an event decision. | It supports the design motivation for interpretable derived values and retained confidence or evidence. | It does not prove MarketStream's eight factors, MAD thresholds, financial anomaly accuracy, or user trust. | Keep the cross-domain inspiration. Replace “makes users trust the system” with the weaker statement “aims to improve understandability.” |
| [2] | Bhattacharya et al. | Point Adjustment can over-reward a partial detection and produce an inflated F1 score. The paper proposes Balanced Adjustment. | Abstract; Section 1, PDF pp. 1–2; Figure 1; Section 2.2, around pp. 3–4 | A time-series anomaly is often an event interval rather than a set of independent points. Expanding one detected point into a correct detection of the whole interval can hide missed detections and false alarms. | It supports avoiding simple Point Adjustment and reporting event-level TP, FP, and FN explicitly. | It does not show that MarketStream's one-to-one forward matching is the only correct method. It also does not validate the project parameters. | Keep the reference, but state that MarketStream only borrows the concern about fair evaluation. It does not directly implement the paper's Balanced Adjustment method. |
| [3] | Cont, Kukanov, and Stoikov | Short-term price changes are approximately linear in OFI at the best bid and ask. The slope is negatively related to market depth. | Abstract, published pp. 47–48; OFI definition and empirical results in Sections 2–4; Conclusion | Order-flow events explain short-term price changes better than trading volume alone. However, the paper's OFI includes limit orders, cancellations, and market orders. | It supports adding quote and trade imbalance information, together with market-depth or spread-related information. | It does not show that MarketStream's simplified `quote_imbalance` is the same as strict OFI. IEX top-of-book quotes are also not the same as full TAQ or SIP depth. | Keep the financial motivation. Remove the strong claim that the paper directly proves the three project factors are more explanatory. |
| [4] | Drew et al. | An ICU produced 2,558,760 alarms in 31 days, with 187 audible alarms per bed per day. Of 12,671 annotated arrhythmia alarms, 88.8% were false positives. | Printable PDF p. 1, Abstract and Results; Discussion, around pp. 8–9 | A large number of alarms, repeated alarms, and low-value alerts create a real burden. The causes include thresholds, patient conditions, and algorithm limitations. | It supports reporting alert burden, duplicate rate, and delay or sustained confirmation in addition to precision. | It does not support transferring the ICU false-positive rate of 88.8% to financial alerts. It also does not support the project's 300-second cooldown. | Keep the figures and their limits. State clearly that this is only a risk analogy. |
| [5] | Guha et al., RRCF | It uses dynamically updated random cut forests and summaries for streaming anomaly detection. | PMLR p. 2712, Abstract; Section 1, pp. 2712–2714; Definition 1; experiments and conclusion, pp. 2718–2721 | Online anomaly detection can use updateable data structures. It does not always require a deep sequence model. | It supports the reasonableness of a lightweight streaming baseline and keeping simple baselines from the older system. | It does not show that CEP is better than RRCF. The paper also does not validate the ordering of financial events. | Replace the broad phrase “works well” with the narrower statement that the paper demonstrates feasibility on public datasets. |
| [6] | Gyllstrom et al., SASE | It filters and relates real-time RFID data, then turns low-level readings into actionable events through complex patterns. | PDF p. 1, Abstract; Section 2, pp. 2–3; language and query sections; retail scenario | The general value of CEP comes from relationships, order, windows, and combinations. It does not come from fixed indicators in one domain. | It supports using stateful event relationships to express news confirmation, sustained pressure, and cross-asset combinations. | It does not support any MarketStream financial pattern, direction, threshold, or five-minute window. | Keep the reference and state clearly that the financial meaning is defined and validated by this project. |
| [7] | Liu and Paparrizos, TSB-AD | It identifies problems in the data, metrics, and experimental settings of existing benchmarks. It includes 1,070 time series, 40 datasets, and 40 algorithms, and recommends VUS-PR. | Abstract and Introduction, PDF pp. 1–2; dataset integrity and measure reliability sections; benchmark results | Model comparisons are only reliable when the data, metrics, and tuning protocols are consistent. More complex neural networks are not always better. | It supports fair, reproducible, and consistent evaluation protocols. It also shows that model quality should not be judged only by model complexity. | It does not show that MarketStream's event-level metrics are equivalent to VUS-PR. It also does not validate real-time alert burden. | Keep the reference. Replace the possibly misleading phrase “the same parameter settings” with “a consistent benchmark setup and sufficient tuning.” |
| [8] | MacKinlay | An event study uses a normal-return model to calculate the difference between actual and expected returns. This difference is the abnormal return. | Journal p. 13, Introduction; event-study procedure around pp. 14–15; normal and abnormal return formulation around pp. 17–19 | A change in one stock should be interpreted relative to a normal model or a market model. | It supports the motivation for `market_residual`: removing common market movement. | It does not support treating `r_i-r_m` as a strict abnormal return. A formal model normally requires parameter estimation and event-window statistics. | Keep the reference, but continue to call the project method a lightweight approximation. Do not say that the project implements a formal event study. |
| [9] | Manzoor et al., StreamSpot | It incrementally processes streaming heterogeneous graphs with bounded sketches. The paper reports more than 100K edges per second and strong detection results on simulated data. | KDD p. 1035, Abstract; Section 1, pp. 1035–1037; method and complexity sections; experiments | A real-time system can retain structural information with bounded summaries and can limit its time and memory use. | It supports the engineering motivation for bounded state, online updates, and structural relationships. | It does not show that financial data can achieve the paper's accuracy or throughput. StreamSpot is also not a CEP system. | Keep the reference and continue to state that the experiments used system-call and attack graphs. |
| [10] | Powell et al., NISTIR 8219 | It demonstrates behavioural anomaly detection in two environments: robotic manufacturing and a process similar to chemical production control. | NISTIR 8219 Abstract and Executive Summary; Section 3, pp. 6–14; Section 4, pp. 14–16 | Anomaly monitoring must be interpreted within a specific physical process, architecture, and operating environment. | It supports the importance of context and normal operating state. It also supports the point that thresholds cannot be copied directly across domains. | It does not support MarketStream's baseline formula. It also does not prove that one behavioural anomaly detection algorithm is always best. | Replace “deployed” with “demonstrated in two demonstration environments” to avoid describing the work as a production deployment. |
| [11] | Prytherch et al., ViEWS | It presents a paper-based weighted early warning score. The AUROC for death within 24 hours was 0.888, with a 95% confidence interval of 0.880–0.895. | PubMed Abstract; journal pp. 932–937; Results in the abstract | A small number of domain variables can form an interpretable score after grading and weighting. The paper also compares trigger workload. | It supports the design motivation for a small number of interpretable and graded factors. | It does not support the claim that fewer variables are always accurate. The medical AUROC and weights also cannot be transferred to finance. | Replace “very high accuracy” with “an AUROC of 0.888 on this clinical dataset” to avoid a value judgement. |
| [12] | Tetlock | Pessimism in the *Wall Street Journal* is related to later downward market pressure, price reversal, and trading volume. | *Journal of Finance* p. 1139, Abstract; Section II, content factor; Section III, empirical tests; pp. 1144–1160 | News text can be converted into a quantitative sentiment variable. However, correlation and predictive relationships do not mean that the news is the fundamental cause. | It supports using news as a context signal and requiring price confirmation. | It does not support the accuracy of the current small sentiment lexicon, the five-minute window, or a causal interpretation of one article. | Keep the reference. Replace “extreme optimism also produces high volume” with the paper's more accurate wording, “unusually high or low pessimism.” |

## 2. Six Most Relevant Papers Used in the Report

### [1] Barrie et al. — MEDOS

- Source: https://ntrs.nasa.gov/api/citations/20250002215/downloads/MEDOSJSR.pdf

- Introduction: MEDOS mainly explains how a spacecraft can identify events in space and make operational decisions based on them. A traditional spacecraft follows commands written into a schedule in advance. However, the time of some events cannot be known in advance. Examples include entering a radiation belt or crossing a magnetospheric boundary. If ground staff must first notice every event and then send a command, communication delay can be large. This is especially important for distant missions or satellite groups. MEDOS aims to let a spacecraft identify events locally from sensor data and trigger operations based on the result.

  MEDOS has two main steps. First, it combines several raw spacecraft measurements, such as voltage and magnetic-field direction, into meaningful derived parameters that experts already understand, such as plasma density. Second, it compares these parameters with typical values and event definitions from published work and past flight experience. Instead of using only fixed thresholds, the system uses fuzzy membership functions to measure how well each parameter matches a target event. It then combines evidence from several parameters and outputs confidence that the event has occurred.

- Ideas used in the project:

  | MEDOS Idea | Inspiration for MarketStream |
  |---|---|
  | **A fixed threshold should not be applied directly to raw data:** MEDOS does not raise an event from one raw telemetry value. It first creates meaningful derived parameters. | Before making an event decision from complex real-time data, the raw inputs can be converted into derived states with meaning in that domain. MarketStream does not apply fixed anomaly thresholds directly to raw trade, quote, bar, or news data. It first calculates eight financial factors. |
  | **An anomaly should be judged relative to normal operating conditions:** MEDOS compares derived parameters with typical values. | Event detection should not depend only on an absolute value. It should also consider the typical range for the current object and operating state. The same volume may be normal at the market open but unusual at midday. Different tickers also require different thresholds. MarketStream therefore compares each current factor with a historical baseline for the same ticker, cadence, session, and intraday slot. |
  | **An alert should provide understandable evidence:** MEDOS uses interpretable derived parameters and gives confidence for an event instead of only a yes-or-no result. | The output should retain domain meaning and the basis of the decision. It should not only give an unexplained anomaly score. MarketStream does not use the fuzzy confidence method from MEDOS, but it follows a similar direction of producing an interpretable anomaly result. A `DetectionResult` therefore retains the pattern, direction, factor states, quality flags, and original event IDs. |

### [2] Bhattacharya et al. — Towards Unbiased Evaluation of Time-series Anomaly Detector

- Source: https://openreview.net/pdf?id=CseY9pxbsN

- Introduction: This paper mainly asks whether the evaluation of time-series anomaly detection is fair. In ordinary classification, each point is usually classified separately as normal or anomalous. However, a time-series anomaly often lasts for a period of time. For example, an equipment failure or a market anomaly may continue for several minutes. An anomaly should therefore be treated as a continuous event, not just as many independent anomalous points.

  Many studies use Point Adjustment to handle this issue. If a detector identifies one point inside an anomalous interval, the whole interval can be counted as correctly detected. As a result, a system that happens to detect only one point may still be treated as if it found the complete anomalous event. This increases true positives and can make F1 too high. The detector's performance may then be overestimated. At the same time, a false alarm in a normal interval is still counted as only one false positive. The reward and penalty are therefore not balanced.

  The paper proposes Balanced Adjustment. When it extends true positives inside an anomalous interval, it also adjusts false positives in normal intervals. This gives more balanced treatment to correct and incorrect detections.

- Ideas used in the project: The project mainly borrows the evaluation concern that motivated Balanced Adjustment.

  | Unbiased TSAD Evaluation Idea | Inspiration for MarketStream |
  |---|---|
  | **A time point and an anomalous event are not the same concept:** A time-series anomaly usually lasts for a period of time. Each point should not always be treated as an independent classification result. | MarketStream evaluates complete financial anomaly events. It compares each `DetectionResult` with a predefined ground-truth event instead of checking only whether every `FactorSnapshot` was classified correctly. |
  | **A partial hit may inflate the evaluation result:** Traditional Point Adjustment can extend one detected point to a correct detection of the entire anomalous interval. This can inflate TP and F1. | Even if one true event produces several consecutive alerts, it can count as no more than one TP. The project uses one-to-one event matching. Unmatched alerts count as FP, and true events that are not detected count as FN. |

### [3] Cont et al. — The Price Impact of Order Book Events

- Source: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1712822

- Introduction: This paper studies the relationship between order events and short-term price changes. It uses NYSE Trades and Quotes data for 50 US stocks. The authors consider three types of order events: limit orders, market orders, and cancellations. These events change supply and demand near the best bid and best ask.

  The paper introduces Order Flow Imbalance (OFI). OFI represents the difference between buying and selling pressure around the best bid and ask. It does not only count completed trades. It also includes changes caused by new limit orders and cancellations. Over short time intervals, OFI has an approximately linear relationship with price changes. When buy-side order flow is stronger, the price is more likely to rise. When sell-side order flow is stronger, the price is more likely to fall.

  The paper also finds that the price impact of order flow depends on the market's ability to absorb trades. When there are fewer resting orders at the best quotes, a smaller order-flow imbalance may cause a larger price change.

- Ideas used in the project:

  | Order Flow Imbalance Idea | Inspiration for MarketStream |
  |---|---|
  | **Market anomalies should not be judged only from trading volume:** Short-term price changes are related to imbalance between buy-side and sell-side order flow. Limit orders, market orders, and cancellations can all change market supply and demand. | In addition to `relative_volume`, the project considers quote pressure and trade direction. It therefore includes `quote_imbalance` and `signed_trade_imbalance`. However, these two factors are simplified indicators and are not the same as the strict OFI defined in the paper. |
  | **The effect of order flow depends on market liquidity:** The impact of OFI is related to market depth. When market depth is lower, the same imbalance may cause a larger price change. | This suggests that liquidity conditions should also be considered when identifying unusual order flow. The project therefore examines displayed quote size and `spread_stress`. However, the spread is not the same as market depth, and the IEX top-of-book quotes used by the project cannot represent the complete market order book. |

### [4] Gyllstrom et al. — SASE: Complex Event Processing over Streams

- Sources:

  - https://www.skilift-simmerberg.de/~patrick/papers/cidr07.pdf
  - https://arxiv.org/abs/cs/0612128

- Introduction: This paper is an early important study of complex event processing (CEP). RFID technology was becoming more common in supply chains, retail, and healthcare. Sensors produced large amounts of raw data, but low-level readings did not directly provide the meaning needed by an application. The authors proposed SASE to extract and match useful complex events efficiently from large, low-level real-time streams.

  The paper has three main contributions. First, it provides an SQL-like language designed for event-pattern matching. Second, SASE uses a dataflow model similar to a relational database for efficient execution. Third, SASE is not only an algorithm. It provides a complete three-layer system. The physical layer collects signals from RFID hardware. The data-cleaning layer converts raw signals into basic event streams. The complex-event-processing layer processes these event streams in real time, creates alerts, and stores useful events in a database for historical queries.

  The paper uses a retail theft scenario. A possible theft pattern can be defined as follows: an item is read on a shelf, it is not read at the checkout, and it is later read at the exit gate. If this event sequence appears, the system identifies a possible theft and raises an alert.

- Ideas used in the project:

  | SASE Idea | Inspiration for MarketStream |
  |---|---|
  | **One data point may not be meaningful by itself. A combination can form an event:** SASE combines records from a shelf, checkout, and exit to detect an item leaving without payment. | MarketStream should not identify a market anomaly from only one price movement or one unusual factor. It combines the eight factors into CEP patterns before making an event decision. |
  | **The order and time range of events matter:** SASE specifies what occurs first, what occurs later, and how quickly a pattern must be completed. | The project uses CEP state machines and time windows. For example, news appears first, and then price and trading activity must change before a news-shock pattern is completed. Sustained order pressure must also continue over a period of time instead of appearing at only one moment. |

### [5] MacKinlay — Event Studies in Economics and Finance

- Sources:

  - https://ideas.repec.org/a/aea/jeclit/v35y1997i1p13-39.html
  - https://www.bu.edu/econ/files/2011/01/MacKinlay-1996-Event-Studies-in-Economics-and-Finance.pdf

- Introduction: This paper mainly answers one question: after an economic event occurs, how much of a company's stock-price change can be linked to that event rather than to normal market movement? The paper explains the event-study method. It is used to examine whether a clearly defined event causes an unusual change in a company's stock price or value. Its basic logic is:

  `abnormal return = actual return - expected normal return without the event`

  The paper describes three main parts. First, the researcher defines the event date and the event window. The event window includes a period before and after the event. Second, data from before the event are used to estimate normal returns. The normal return is then subtracted from the actual return to obtain the abnormal return. Third, abnormal returns over several days can be added to form a cumulative abnormal return. Statistical tests can then be used to check whether the result is clearly different from normal movement.

  The paper uses quarterly earnings announcements as an example. The author collected 600 quarterly earnings announcements from the 30 companies in the Dow Jones Industrial Index. The announcements were divided into good news, no news, and bad news. The abnormal returns and cumulative abnormal returns around the announcements were then compared across these groups.

- Ideas used in the project:

  | Event Study Idea | Inspiration for MarketStream |
  |---|---|
  | An abnormal return should be judged from the difference between the actual return and the expected normal return. Market returns can help estimate the normal performance of one stock. | MarketStream includes the `market_residual` factor. It subtracts the market return from the return of one stock so that a general market rise or fall is less likely to be treated as a stock-specific anomaly. |

- Report change: `market_residual = r_i-r_m` continues to be described as a lightweight approximation. It is not described as a formal abnormal return.

### [6] Tetlock — Giving Content to Investor Sentiment: The Role of Media in the Stock Market

- Sources:

  - https://onlinelibrary.wiley.com/doi/10.1111/j.1540-6261.2007.01232.x
  - https://www.uts.edu.au/globalassets/sites/default/files/adg_cons2015_tetlock-journal-of-finance-2007.pdf

- Introduction: This paper studies whether pessimism in news media is related to short-term market returns and trading volume. The author discusses three possible explanations. First, media reports may contain new fundamental information and therefore have a longer-term effect on prices. Second, media sentiment may influence investor behaviour and create short-term buying or selling pressure. Third, the media may only describe market changes that have already happened and may provide no additional predictive information.

  The author analyses daily market columns in *The Wall Street Journal* and examines the timing of media sentiment, market returns, and trading volume. The results show that unusually pessimistic media content is usually followed by downward market pressure on the next trading day. Part of this effect reverses over the following days. Earlier market declines also make later reporting more pessimistic. The paper therefore shows a two-way relationship between media sentiment and market movement. Media pessimism is closer to a measure of short-term investor sentiment and trading pressure than to a simple measure of long-term fundamental information.

- Ideas used in the project:

  | Media Sentiment Idea | How It Is Used in MarketStream |
  |---|---|
  | **News sentiment can provide supporting information for a market anomaly:** The paper finds that media pessimism is related to short-term price pressure and trading activity. | The project includes a news-sentiment factor to add context to price, volume, and order-flow information. However, the project uses a simple lexicon score and does not reproduce the paper's sentiment method. |
  | **News sentiment cannot explain a price change by itself:** Media sentiment may influence investors, but a market decline may also make later reporting more pessimistic. The paper also finds that part of the price effect later reverses. | The project does not treat negative news as an anomaly by itself. It requires confirmation from price, volume, or order flow. The system can only identify changes that occur close together in time. It cannot prove that the news caused the price change. |

## Overall Changes After Literature Verification

1. Replace every statement that “the literature proves the MarketStream design is correct” with the narrower statement that “the literature provides design motivation.”
2. Describe NISTIR 8219 as “demonstrated,” not as a production deployment.
3. Clearly separate Cont's strict OFI from the simplified imbalance factors used in the current project.
4. Clearly separate MacKinlay's abnormal return from the simple `r_i-r_m` calculation.
5. Clearly separate Bhattacharya's Balanced Adjustment from the project's one-to-one event matching.
6. Do not transfer the metrics from MEDOS, ViEWS, StreamSpot, or ICU alarms across domains.
7. Treat the windows and thresholds of the six financial patterns as project parameters. Do not attribute them to the papers above.
