# 数字—运行—结论台账（2026-10-22）

唯一报告主稿：[中文修订报告](../07_Revised_Report_CN.md)。英文修订稿是对应译稿。旧草稿、参考稿、提交1和 ZIP 为历史材料，不得抽取其中数字拼接为“当前系统结果”。本台账统一摘要、实验章、讨论、结论及贡献文档的实验口径，不改变原始日志或历史 JSON。

机器可核查清单：[result_registry.json](../reproduction_outputs/audit_20261022/result_registry.json)。每项保存原文件路径、SHA-256、run ID、版本／快照、数据来源、标签、参数、原始输出与结论范围。`null` 表示未找到依据，不表示不存在，也不能用当前默认配置补写历史配置。历史摘要可被追溯到保存的文件，并不等于历史运行已完全可复现。

## 1. 本轮代码与检查：CHECKS-20261022

- 代码版本／工作树：HEAD `05b88c09657a8bba03407a6aea944f487e8500ce` 加未提交变更；完整参与核验的 Python 源码、测试及锁文件保存在 [source_snapshot.tar.gz](../reproduction_outputs/audit_20261022/source_snapshot.tar.gz)，逐文件 hash 和总 manifest hash 见 [provenance.json](../reproduction_outputs/audit_20261022/provenance.json)。不把 HEAD 单独当作运行版本；归档不含凭据、数据库状态或依赖二进制。
- run ID：`CHECKS-20261022` 为本轮人工分配的核验 ID。
- 数据来源：归档源码与 tests；标签版本：不适用。
- 参数：`.venv/bin/pytest -q`；`.venv/bin/ruff check .`。
- 原始输出：[pytest.txt](../reproduction_outputs/audit_20261022/pytest.txt) 为 **63 passed in 4.67s**；[ruff.txt](../reproduction_outputs/audit_20261022/ruff.txt) 为 `All checks passed!`。
- 结论范围：满足当前测试与静态检查约定。新增 `test_synthetic_accounting.py` 验证负对照检测包含在总 FP，且场景触发数不等于告警数。历史 2026-09-17 的 62 tests 见 [Test_Outputs.md](Test_Outputs.md)，不是本轮测试数；160 tests 缺完整运行绑定，只保留为旧材料记载。

## 2. 合成实验：两次独立 pass，不混用计时

- 版本／快照：同上归档；生产检测逻辑未修改，仅给 `run_protocol` 增加可选逐场景记录。
- run ID：`SYN-TRACE-20261022`（provenance 外层批次 ID 为 `audit-synthetic-20261022`）、`SYN-SUITE-20261022`，本轮分配；不是原文件内嵌 ID。
- 数据：`evaluation/synthetic_scenarios.py` 生成 FactorSnapshot，不使用真实市场事件。因子状态直接构造，不能验证从 raw events 到因子和 baseline 的统计有效性。
- 标签：生成器 `expected_pattern/expected_direction`；版本由归档内生成器 SHA-256 固定；快照 baseline 标识 `frozen-synthetic-v1`。无独立人工真实标签。
- 参数：20 seeds × low/medium/high（z=4.5/6.5/9.0）；六类正场景与四类负对照；每场景重建 detector；cooldown=0；场景起点相隔 10 分钟；一对一、同 ticker/pattern/direction、只允许 truth 起止内向前匹配，无额外 grace。
- 原始输出：[factor_cep_traced.json](../reproduction_outputs/audit_20261022/factor_cep_traced.json)、[scenarios.json](../reproduction_outputs/audit_20261022/scenarios.json)、[reconciliation.json](../reproduction_outputs/audit_20261022/reconciliation.json)；消融另见 [factor_cep_suite.json](../reproduction_outputs/audit_20261022/factor_cep_suite.json)。复现命令：项目根目录执行 `.venv/bin/python -m report.tools.audit_results`（会更新该审计输出目录，需比较时先复制保留）。

| 输入集合 | 场景数 | 告警条数 | TP | FP | FN | 至少告警一次的场景数 |
|---|---:|---:|---:|---:|---:|---:|
| 正场景 | 360 | 420 | 360 | 60 | 0 | 360 |
| 负对照 | 240 | 60 | 0 | 60 | 0 | 40 |
| 总计 | 600 | 480 | 360 | 120 | 0 | 400 |

**120 FP = 60 正场景未匹配告警 + 60 负对照告警**；40/240=16.7% 是负对照场景触发率，40 个触发场景共发出 60 条告警。这 60 条已经包含于总 FP，不可再相加。正场景额外 FP 来自 high `flash_reversal`（20 条）和 high `cross_asset_shock`（40 条）；负对照 FP 来自 high `orderly_market_move`（20 个场景、40 条）和 high `stale_news`（20 个场景、20 条）。其他组合没有 FP。明细保留 seed、强度、场景 ID、truth、每条检测 ID、pattern、方向与时间；全局匹配和逐场景匹配已核对一致。

Precision=360/480=0.750，Recall=360/360=1.000，F1=0.857143；正确匹配的首次事件时间延迟 p50/p95/p99=10/30/30 秒，并非 wall-clock 端到端延迟。

| pass | CEP process 计时 p50 / p95 / p99（ms） | 用法 |
|---|---|---|
| SYN-TRACE-20261022 | 0.015041 / 0.03058815 / 0.06876917 | 主稿本轮计时，逐场景记录在计时段外 |
| SYN-SUITE-20261022 | 0.013750 / 0.023292 / 0.04269491 | 单独顺序执行的 suite baseline，提供消融；不能替换 trace 的某一分位数 |
| SYN-20260917 | 0.013083 / 0.018752 / 0.029878 | 旧保存 JSON，无内嵌 run ID／完整执行快照，仅历史对照 |

计时仅包围 `detector.process`，不含深拷贝、生成、记录、Kafka、网络或数据库。本轮不同 pass 即有差异，不能声称 p99 永远低于 0.03 ms。历史数据 `data/evaluation/factor_cep.json` 也是另一个未完整绑定运行的旧产物。

消融使用 SYN-SUITE-20261022 的 `ablations`：删除 dislocation 后 TP/FP/FN=300/0/60，Precision=1、Recall=0.833333、F1=0.909091，负对照0/240；删除 activity 不变。其余消融数值由该 JSON 对应字段直接支持。结论仅为预设因子序列的规则覆盖及取舍，不是独立市场效果证明。

1.604 alerts/ticker-hour 的实现分母是首末 truth/detection 时间跨度 × ticker 数，包含人为插入的十分钟间隔，不能解释为实际交易期告警负担。duplicate rate=0 也不能证明生产 cooldown 或数据库 dedupe：本协议 cooldown=0、各场景重建 detector。bootstrap 对 truth 命中标记重采样、固定 FP；全命中使区间退化，未估计正常期 FP 不确定性。

## 3. 旧版注入对比：LEGACY-INJECTED

- 代码版本／工作树快照：**缺失准确执行快照**；不从当前源码重建历史协议。run ID／执行时间：原 JSON 未记录；`LEGACY-INJECTED` 是本轮工件索引 ID。
- 数据来源：保存结果标记 `real_ohlcv_with_synthetic_injections`；配置 period=60d，AAPL/TSLA/NVDA，4209 test windows。历史说明称五分钟 OHLCV 与合成情绪，但确切输入文件 revision/hash 和训练模型绑定缺失。
- 标签版本：225 个程序化注入异常，标签文件 hash 未记录，不是独立真实标签。
- 参数：train_ratio=0.7，injection_rate=0.05，seed=42；完整配置仅以 JSON 记录为准。
- 原始输出：[comparison_60d_0.05.json](../../../data/comparison_results_nfa_tuned/comparison_60d_0.05.json)，hash 见机器清单。
- 结果：ML TP/FP/FN=163/122/62，F1=0.6392，mean compute=4.5135 ms；CEP full=184/60/41，F1=0.7846，mean=0.0033 ms；automata-only=11/7/214，F1=0.0905。表中值为保存的汇总，不能证成当前六状态机在真实市场优于 ML。
- 结论范围：仅旧注入协议的历史观察。缺逐窗口预测，无法独立重算每条历史匹配；不能把该 mean 与本轮 synthetic p50/p99 拼接成“当前速度优势”。

## 4. Kafka／数据库测试：三个独立 run

| run ID | 生成时间（UTC） | 输入／落库事件 | 告警 | p50 / p95 / p99（秒） | 保存 gate |
|---|---|---:|---:|---|---|
| soak-61164fa173 | 2026-08-06 08:16:22 | 150/150 | 15 | 1.163553 / 1.484251 / 1.488049 | false，expected_alert_sample=false |
| soak-702644010d | 2026-08-06 08:17:11 | 240/240 | 88 | 1.417574 / 1.718380 / 1.737660 | true |
| soak-b735cff438 | 2026-09-10 08:23:12 | 240/240 | 76 | 1.476217 / 1.615935 / 1.727292 | true |

- 版本／工作树快照：三个运行均未在 report.json 中绑定执行代码 hash；不能因告警数不同就断言原因是代码变化。完整命令、运行状态和实际 baseline 配置未保存。
- 数据来源：`mode=soak` 合成 transport events，MarketEvent→Kafka→factor→Kafka→CEP→PostgreSQL。不是正常市场流量。
- 标签版本：不适用（非检测准确率评测）；参数以各报告 sample/gates 为准，不能拿今天脚本默认参数填补。
- 原始输出：`data/evaluation/<run ID>/report.json`；[kafka_db_soak.json](../../../data/evaluation/kafka_db_soak.json) 与 76-alert report 内容相同，仅别名，不是第四次运行。per-alert 数据及全部原始输入未作为报告附件保存。
- 结论范围：这些保存的 gate 报告支持相应 run 的持久化、重复和追溯检查；无法在本轮重新逐条审计数据库内容，也不证明生产 SLA、长期可靠性或检测准确率。报告曾写 76-alert p50=1.357/p99=1.625，与原始文件不符，现更正。2026-09-17 Docker 阻塞是当时记录；2026-10-22 未启动服务、未重跑 soak。

## 5. 短时真实输入验证：alpaca-live-20260819T144908Z

- 代码版本／工作树快照：缺失准确执行 hash。run ID 来自原始文件。
- 数据来源：Alpaca IEX WebSocket，`real_live_soak`；原始事件行未随该汇总文件保存。
- 标签版本：无，`metric_eligible=false`，warm-up-only。
- 参数：2026-08-19 14:49:10.204889Z 至 14:50:38.494241Z，约 88.289 秒；5 tickers；完整启动参数缺失。
- 原始输出：[alpaca_live_e2e.json](../../../data/evaluation/alpaca_live_e2e.json)。48,734=48,283 quote+446 trade+5 bar；48,729 clean+5 feed_gap；stale_bar=0。10s/1m/5m snapshots=40/5/5，tickers_per_cadence=5。
- 结论范围：保存的汇总及 gate 支持短时接入、落库与 cadence 生成。news gate 只支持鉴权／订阅，不证明收到新闻；总类别中没有 news。也没有“每个 ticker 都有每一种事件”的交叉计数。不能报告准确率、全天稳定性或推广至 consolidated SIP。

## 6. 正式真实回放：尚无合格运行

- 代码版本：仅本轮归档的 evaluator 实现；**无正式运行快照、run ID 或指标输出**。
- 数据来源：预注册标签声明 Alpaca/IEX real_historical；没有配套完成的真实微观事件 dataset manifest／正式 replay output，日线数据不能代替该输入。
- 标签版本：`iex_benchmark_v1.draft.json`、`ai_preannotated.json`、`.v2.json`、`.v3.json`，均24区间（12 anomaly、12 normal）、`frozen=false`；分别固定文件 hash 于机器清单。AI 预标注不是独立审阅批准。
- 参数／准入要求：标签独立批准与冻结；dataset manifest/hash 匹配；baseline 早于 evaluation；评测期间 baseline 不回写；结束 warm-up；拒绝 synthetic/soak 输入。这些是实现约束，不是已完成实验结果。
- 原始输出：四个标签文件存在；正式结果不存在。没有运行就不赋予虚构 run ID。
- 结论范围：不报告真实历史 Precision、Recall、F1 或真实正常期误警率；贡献只可主张提出／实现与测试准入协议，不能主张已验证真实市场有效性。

## 2026-10-23 新增运行（当前结果以本节为准）

机器清单：[audit_20261023/result_registry.json](../reproduction_outputs/audit_20261023/result_registry.json)。

### CHECKS-20261023

- 代码版本：HEAD `738abfb`，工作树干净（`dirty_tree=false`），源码快照 [source_snapshot.tar.gz](../reproduction_outputs/audit_20261023/source_snapshot.tar.gz)。
- 参数：`uv run pytest -q`；`uv run ruff check .`。原始输出：[pytest.txt](../reproduction_outputs/audit_20261023/pytest.txt) 为 **91 passed in 5.01s**；[ruff.txt](../reproduction_outputs/audit_20261023/ruff.txt) 为 `All checks passed!`。
- 结论范围：当前代码符合测试声明的行为，不证明市场效果。

### SYN-TRACE-20261023 / SYN-SUITE-20261023

- 代码版本：同上；命令 `uv run python -m report.tools.audit_results --output report/ownership_evidence/reproduction_outputs/audit_20261023 --run-id audit-synthetic-20261023`。
- 数据与标签：与 SYN-*-20261022 相同的生成器、种子、强度与匹配规则（20 seeds × low/medium/high，cooldown=0）。
- 结果：TP/FP/FN = 360/0/0，Precision/Recall/F1 = 1.000/1.000/1.000，负对照 0/240；首次检测延迟 p50/p95/p99 = 10/30/30 s；1.815 alerts/ticker-hour（分母口径同上，随参与 ticker 集合变化）；trace pass CEP 计时 p50/p95/p99 = 0.0132/0.0178/0.0259 ms，suite pass 为 0.0126/0.0173/0.0210 ms。消融 F1：activity 1.000，liquidity 与 microstructure 0.800，market context 与 news 0.909，price 0，各单一模式 0.909。
- 结论范围：删除单因子极端价格例外（项目计划第 4 项“依据负对照误报做一次预先声明的规则改动”）之后的**样本内**实现检查；负对照正是该修订的依据，生成协议已饱和，不代表检测能力。SYN-*-20261022 保留为修订前对照。

### ZMAD-20261023：零 MAD 敏感性检验

- 代码版本：检验在 `0a2f010` 之前完成，预注册 `d37edbe`，修订 `6bbbb16`；采纳规则见 `738abfb`。
- 数据：Alpaca IEX 2023-10-02 至 2023-11-10，30 个交易日、五标的、两时段；报价每秒保留最后一笔；manifest SHA-256 前缀 `bdc5f9344a343a6d`（本地，不公开）。
- 标签：无（无标签校准）。
- 原始输出：[zero_mad_20261023/summary.json](../reproduction_outputs/zero_mad_20261023/summary.json)、[per_block.json](../reproduction_outputs/zero_mad_20261023/per_block.json)。
- 结论范围：尺度规则是否主导或扭曲输出；主方案 C3、C4 通过，C2 不通过（CEP 22.6%、IF 24.3%）；不报告 Precision/Recall。详见 `docs/ZERO_MAD_SENSITIVITY_CN.md`。

### LABEL-BASE-2023：标注准则基准率

- 数据：Alpaca SIP 拆股调整分钟线，2023-07-10 至 2023-11-10，计量 2023-08-14 起 64 个交易日 × 5 标的 × 2 时段 = 640 个窗口。
- 参数：`docs/LABELING_CRITERIA.md` 中可自动计算的市场数据规则（A1、A2、A4、A5；N1–N3、N6）。
- 原始输出：[labeling_base_rates_2023/summary.json](../reproduction_outputs/labeling_base_rates_2023/summary.json)。
- 结论范围：准则在不相交时期的触发频率，仅供批准准则时参考；准则已于 2026-10-23 以 volume option 2 批准。

## 核验覆盖与保留缺口

本轮逐项对照摘要、实验与结论数字，重跑 synthetic 基线及消融、重算逐场景 FP 分区、核对历史 JSON 的计数／比例／分位数、检查全部四个标签文件并同步中英文贡献材料。原始日志、历史 JSON 和 ZIP 未改写。旧汇总缺 execution hash、逐条原始输出、数据／标签版本时，已记录为缺失并缩小为“保存的历史汇总”，未将复跑结果当成旧运行的逐条证据。文献及个人决策归属不在本次数值复核的重新审阅范围内。

## 7. 历史覆盖资料：HIST-COVERAGE-20260814（不属于正式回放结果）

代码／执行快照和run ID未记录；保存manifest的generated_at为2026-08-14T09:45:08.355972Z。数据来源：`data/historical/alpaca/ohlcv_1d_12m.csv`实际provider为Yahoo Finance，5个ticker各277行；`news_12m.jsonl`为Alpaca/Benzinga，15,148个ticker关联行、10,930个不同article_id。标签版本：无。参数：requested_start/end=2025-07-09/2026-08-13；manifest记录60/20/20时间段，未证明正式回放按此执行。原始CSV、JSONL和manifest的hash见机器清单。实际新闻最早2025-06-19T15:00:18Z、最晚2026-08-13T20:31:17Z，不能把请求日期写成全部实际覆盖范围。结论仅为保存数据的覆盖和候选事件资料；不是微观事件baseline，也不是完成的正式评测。
