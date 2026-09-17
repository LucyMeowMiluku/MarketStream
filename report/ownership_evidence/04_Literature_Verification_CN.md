# MarketStream 文献核实表

核实日期：2026-09-17  
核实范围：`report/report draft.md` 参考文献 [1]–[12]

## 核实方法

- 优先使用作者公开 PDF、期刊页面、会议论文集或政府机构正式报告。
- “原文位置”同时记录论文页码或章节。只有摘要可访问时会明确说明。
- 表中的“支持”表示文献可以支持报告里的背景或设计动机，不表示文献验证了 MarketStream。
- MarketStream 的窗口、阈值、六类模式和实验结果仍需要项目自己的证据。
- 以下内容均为转述。没有复制长段原文。

## 总表

| 编号 | 文献 | 报告中使用的观点 | 原文位置 | 我的理解 | 支持什么 | 不支持什么 | 报告处理 |
|---|---|---|---|---|---|---|---|
| [1] | Barrie et al., MEDOS | 从原始测量构造有物理意义的派生参数，再与典型值比较并给出事件置信度 | NTRS 摘要；PDF Section II “Core MEDOS Algorithms”，约 PDF pp. 2–4；Section III 验证 | MEDOS 的重点不是直接对原始值做单一阈值，而是先用领域知识构造派生量，再形成事件判断 | 支持“可解释派生量”和“保留置信/证据”的设计动机 | 不支持 MarketStream 的八因子、MAD 阈值、金融异常准确率或用户信任已经被证明 | 保留跨领域启发；把“能让使用者信任”改成更弱的“旨在提高可理解性” |
| [2] | Bhattacharya et al. | Point Adjustment 会过度奖励部分命中，导致 F1 偏高；提出 Balanced Adjustment | Abstract；Section 1，PDF pp. 1–2；Figure 1；Section 2.2，约 pp. 3–4 | 时间序列异常通常是事件区间，而不是独立点。把区间内一次命中扩展为整段正确，会隐藏漏报与误报 | 支持避免简单 point adjustment，以及显式报告事件级 TP/FP/FN | 不直接推出 MarketStream 的“一对一向前匹配”是唯一正确方法，也不验证项目参数 | 保留，明确 MarketStream 只是借鉴公平评测问题，没有直接实现论文 BA |
| [3] | Cont, Kukanov & Stoikov | 短时间价格变化与最优报价处的 OFI 近似线性相关，斜率与市场深度负相关 | Abstract，published pp. 47–48；OFI definition and empirical results in Sections 2–4；Conclusion | 订单流事件比单独交易量更能解释短期价格变化，但论文 OFI 同时考虑限价单、撤单和市价单 | 支持引入 quote/trade imbalance 和市场深度/价差类信息 | 不支持 MarketStream 的简化 `quote_imbalance` 就等同严格 OFI；IEX 顶层报价也不等于完整 TAQ/SIP 深度 | 保留金融动机；删除“直接证明本项目三个因子更有解释力”的过强说法 |
| [4] | Drew et al. | ICU 31 天产生 2,558,760 个报警；187 audible alarms/bed/day；12,671 个标注心律报警中 88.8% 为 FP | Printable PDF p. 1 Abstract/Results；Discussion，约 pp. 8–9 | 告警数量、重复和低价值提示会形成实际负担。问题来自阈值、患者状态和算法等多种因素 | 支持除 Precision 外还报告 alert burden、重复率和延迟/持续确认 | 不支持把 ICU 的 88.8% 比例迁移到金融告警，也不支持项目的 300 秒 cooldown | 保留数字和边界；明确只是风险类比 |
| [5] | Guha et al., RRCF | 用可动态更新的随机切割森林/摘要处理 streaming anomaly detection | PMLR p. 2712 Abstract；Section 1 pp. 2712–2714；Definition 1；experiments and conclusion pp. 2718–2721 | 在线异常检测可以使用可更新的数据结构，不一定必须依赖深度序列模型 | 支持轻量 streaming baseline 的合理性，以及旧系统保留简单基线 | 不支持 CEP 比 RRCF 更好；论文也没有验证金融事件顺序 | 把“效果不错”改成论文在公开数据上展示可行性，避免泛化 |
| [6] | Gyllstrom et al., SASE | 过滤和关联实时 RFID 数据，通过复杂模式把低层读数变成可行动事件 | PDF p. 1 Abstract；Section 2 pp. 2–3；language/query sections；retail scenario | CEP 的通用价值在于关系、顺序、窗口和组合，而不是某个领域的固定指标 | 支持用状态化事件关系表达新闻确认、持续压力和跨资产组合 | 不支持任何 MarketStream 金融模式、方向、阈值或五分钟窗口 | 保留，并明确金融语义由本项目定义和验证 |
| [7] | Liu & Paparrizos, TSB-AD | 指出现有 benchmark 的数据、指标和实验设置问题；整理 1,070 条时间序列、40 个数据集和 40 种算法；推荐 VUS-PR | Abstract and Introduction，PDF pp. 1–2；dataset integrity and measure reliability sections；benchmark results | 模型比较只有在数据、指标和调参协议一致时才可信。复杂神经网络并不总是最好 | 支持公平、可复现、统一协议，以及不能仅按模型复杂度判断优劣 | 不支持 MarketStream 的事件级指标等价于 VUS-PR；也不验证实时告警压力 | 保留；删除“统一参数设置”这种可能误导表述，改为统一 benchmark setup 和充分调参 |
| [8] | MacKinlay | 事件研究通过正常收益模型计算实际收益与预期收益之差，即异常收益 | Journal p. 13 Introduction；event-study procedure around pp. 14–15；normal/abnormal return formulation around pp. 17–19 | 单只股票的变化需要相对正常模型或市场模型解释 | 支持 `market_residual` 的动机：扣除共同市场变化 | 不支持 `r_i-r_m` 等于严格 abnormal return。严格模型通常需要估计参数和事件窗口统计 | 保留，但持续称为“轻量近似”，不能写成实现了正式 event study |
| [9] | Manzoor et al., StreamSpot | streaming heterogeneous graph 在有界 sketch 下增量处理；论文报告超过 100K edges/s 和模拟数据上的高检测结果 | KDD p. 1035 Abstract；Section 1 pp. 1035–1037；method/complexity sections；experiments | 实时系统可以用有界摘要保留结构信息，并限制时间与内存 | 支持有界 state、在线更新和结构关系的工程动机 | 不支持金融数据能达到论文的 accuracy/throughput；StreamSpot 也不是 CEP | 保留，且继续注明实验是系统调用/攻击图 |
| [10] | Powell et al., NISTIR 8219 | 在机器人制造与类似化工过程控制的两个环境演示 behavioral anomaly detection | NISTIR 8219 Abstract/Executive Summary；Section 3 pp. 6–14；Section 4 pp. 14–16 | 异常监控必须放在具体物理过程、架构和运行环境中解释 | 支持“上下文与正常运行状态重要”以及跨场景不能直接复制阈值 | 不支持 MarketStream 的 baseline 公式，也不证明某种 BAD 算法普遍最优 | 将“部署”改成“在两个 demonstration environments 中演示”，避免写成生产部署 |
| [11] | Prytherch et al., ViEWS | 纸面加权早期预警分数；24 小时院内死亡 AUROC 0.888，95% CI 0.880–0.895 | PubMed Abstract；journal pp. 932–937；Results in abstract | 少量领域变量经过分级和加权可以形成可解释评分。论文还比较触发工作量 | 支持少量可解释、分级因子的设计动机 | 不支持“变量少就一定准确”，也不支持把医疗 AUROC 或权重迁移到金融 | 将“准确度非常高”改成“该临床数据集上的 AUROC 为 0.888”，避免价值判断 |
| [12] | Tetlock | WSJ 媒体悲观度与后续市场下行压力、价格回归和交易量相关 | Journal of Finance p. 1139 Abstract；Section II content factor；Section III empirical tests；pp. 1144–1160 | 新闻文本可以形成量化情绪变量，但相关性和预测关系不等于新闻是基本面原因 | 支持将新闻作为上下文信号并要求价格确认 | 不支持当前小词表 sentiment 的准确性、五分钟窗口或单篇新闻因果解释 | 保留；把“极度乐观也带来高交易量”改成论文更准确的“unusually high or low pessimism”表述 |

## 逐篇核实记录

### [1] Barrie et al. — MEDOS

- 正式来源：[NASA NTRS 20250002215](https://ntrs.nasa.gov/citations/20250002215)
- PDF：[MEDOSJSR.pdf](https://ntrs.nasa.gov/api/citations/20250002215/downloads/MEDOSJSR.pdf)
- 核实结果：NTRS 摘要明确说明 MEDOS 从机载测量计算具有物理意义的 derived parameters，再使用 fuzzy sets 与典型值比较并形成 event confidence。PDF Section II 展开两个阶段：派生特征与事件分类。
- 对项目的实际影响：我借鉴的是“先构造可解释状态，再判断事件”。MarketStream 没有实现 MEDOS 的 fuzzy system。
- 报告修改：不再写“他们发现这种方式让一线人员更信任”这种因果较强的句子。改为作者认为熟悉的参数和 likelihood 表达有助于建立信任。

### [2] Bhattacharya et al. — Unbiased TSAD Evaluation

- 正式来源：[OpenReview PDF](https://openreview.net/pdf?id=CseY9pxbsN)
- 预印本：[arXiv 2409.13053](https://arxiv.org/abs/2409.13053)
- 核实结果：Abstract 和 Figure 1 明确批评传统 PA 偏向 TP，并提出 Balanced Adjustment 同时对 FP 做对称调整。
- 对项目的实际影响：项目没有直接实现 BA。它选择事件级一对一匹配，目的是不让同一异常被重复计算 TP。
- 报告修改：删除“采用了 BA”的暗示，改为“受到评测偏差问题启发”。

### [3] Cont et al. — Order Flow Imbalance

- 正式来源：[SSRN record](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1712822)
- 预印本：[arXiv 1011.6402](https://arxiv.org/abs/1011.6402)
- DOI：[10.1093/jjfinec/nbt003](https://doi.org/10.1093/jjfinec/nbt003)
- 核实结果：Abstract 明确写出短时间价格变化主要由 best bid/ask 的 OFI 驱动，线性关系斜率与市场深度成反比；trade volume 关系更 noisy。
- 对项目的实际影响：支持关注报价压力和成交方向，但当前实现没有限价单新增/撤单的完整 OFI。
- 报告修改：把“直接金融学依据”改为“因子选择动机”，并强调简化和 IEX 覆盖限制。

### [4] Drew et al. — Alarm Fatigue

- 正式来源：[PLOS ONE article](https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0110274)
- PDF：[Printable PDF](https://journals.plos.org/plosone/article/file?id=10.1371%2Fjournal.pone.0110274&type=printable)
- 核实结果：Abstract/Results 支持报告中的 461 patients、31 days、2,558,760 alarms、187 audible alarms/bed/day 和 88.8% FP。
- 对项目的实际影响：支持单独报告告警负担和重复，而不只报告 detection score。
- 报告修改：继续明确医疗报警率不能迁移到金融系统。

### [5] Guha et al. — Robust Random Cut Forest

- 正式来源：[PMLR page](https://proceedings.mlr.press/v48/guha16.html)
- PDF：[PMLR PDF](https://proceedings.mlr.press/v48/guha16.pdf)
- 核实结果：论文提出能用于 dynamic streams 的 robust random cut forest，并用点对模型复杂度的 externality 定义异常。
- 对项目的实际影响：支持保留简单、可更新的统计/树模型作为对比，而不是默认深度学习一定更合适。
- 报告修改：不再用“很扎实的 baseline”这种主观措辞，改为“可更新的 streaming detector 代表”。

### [6] Gyllstrom et al. — SASE

- 正式来源：[arXiv cs/0612128](https://arxiv.org/abs/cs/0612128)
- 作者项目页：[SASE publications](https://sase.cs.umass.edu/index.php?page=content_types)
- 核实结果：论文使用复杂事件语言和查询处理，把 RFID low-level readings 过滤、关联为 meaningful actionable events。
- 对项目的实际影响：支持表达顺序、窗口和组合。金融 pattern 内容仍由 MarketStream 负责。
- 报告修改：保留当前限制说明。

### [7] Liu & Paparrizos — TSB-AD

- 作者 PDF：[LiuNeurIPS24.pdf](https://www.paparrizos.org/papers/LiuNeurIPS24.pdf)
- OpenReview：[paper PDF](https://openreview.net/pdf?id=oRKkE4E9P5)
- 核实结果：Abstract 支持 1,070 time series、40 datasets、40 algorithms、dataset integrity、measure reliability 和 comprehensive benchmarking。作者结论是简单方法经常优于更复杂方法，不是永远更好。
- 对项目的实际影响：支持公平协议、数据质量和不以复杂度作为贡献。
- 报告修改：用“often”而不是“普遍”。MarketStream 事件指标不称为 VUS-PR。

### [8] MacKinlay — Event Studies

- 书目信息：[RePEc/AEA record](https://ideas.repec.org/a/aea/jeclit/v35y1997i1p13-39.html)
- 可访问 PDF：[Boston University mirror](https://www.bu.edu/econ/files/2011/01/MacKinlay-1996-Event-Studies-in-Economics-and-Finance.pdf)
- 核实结果：p. 13 说明 event study 衡量经济事件对 firm value 的影响。后续方法使用 normal return model，并定义 actual minus normal 为 abnormal return。
- 对项目的实际影响：支持相对市场背景判断个股变化。
- 报告修改：`market_residual = r_i-r_m` 持续标为轻量近似，不称为正式 abnormal return。

### [9] Manzoor et al. — StreamSpot

- 正式 PDF：[KDD 2016 paper](https://www.kdd.org/kdd2016/papers/files/rfp0693-manzoorA.pdf)
- 预印本：[arXiv 1602.04844](https://arxiv.org/abs/1602.04844)
- 核实结果：Abstract 支持 fully streaming、memory-efficient sketch、constant-time update 和超过 100K edges/s；实验使用模拟系统调用图。
- 对项目的实际影响：支持有界状态设计。
- 报告修改：不把论文 accuracy 或 throughput 当作 MarketStream 指标。

### [10] Powell et al. — NISTIR 8219

- 正式来源：[NIST publication page](https://www.nist.gov/publications/securing-manufacturing-industrial-control-systems-behavioral-anomaly-detection)
- PDF：[NIST.IR.8219.pdf](https://nvlpubs.nist.gov/nistpubs/ir/2020/NIST.IR.8219.pdf)
- 核实结果：Abstract 和 Section 3 支持两个 demonstration environments。Section 4 记录 demonstration scenarios and findings。
- 对项目的实际影响：异常检测需要结合具体 operating environment 和正常行为。
- 报告修改：把“部署在两个环境”改为“在两个演示环境中展示”。

### [11] Prytherch et al. — ViEWS

- 正式来源：[PubMed 20637974](https://pubmed.ncbi.nlm.nih.gov/20637974/)
- DOI：[10.1016/j.resuscitation.2010.04.014](https://doi.org/10.1016/j.resuscitation.2010.04.014)
- 核实结果：PubMed Abstract 支持 198,755 observation sets、35,585 admissions、24-hour mortality AUROC 0.888 和 95% CI。
- 访问限制：本轮未获得出版社完整 PDF，因此变量权重细节不在本材料中转述。
- 报告修改：将“准确度非常高”改为客观数字和数据集范围。

### [12] Tetlock — Media Sentiment

- 正式来源：[Wiley article page](https://onlinelibrary.wiley.com/doi/10.1111/j.1540-6261.2007.01232.x)
- 可访问 PDF：[UTS mirror](https://www.uts.edu.au/globalassets/sites/default/files/adg_cons2015_tetlock-journal-of-finance-2007.pdf)
- 核实结果：Abstract 支持 high media pessimism 与价格下行压力及之后的反转有关，也支持 unusually high or low pessimism 与高交易量有关。
- 对项目的实际影响：新闻可作为上下文信号，但不能从相关性直接推出单篇新闻造成价格变化。
- 报告修改：保留新闻后价格确认，明确当前 sentiment 只是小词表分数，不是论文中的完整内容分析模型。

## 文献核实后的总体修改

1. 把所有“文献证明 MarketStream 设计正确”的句子改为“文献提供设计动机”。
2. NISTIR 8219 使用“demonstrated”，不写成生产部署。
3. Cont 的严格 OFI 与当前简化 imbalance 明确区分。
4. MacKinlay 的 abnormal return 与简单 `r_i-r_m` 明确区分。
5. Bhattacharya 的 BA 与本项目一对一事件匹配明确区分。
6. MEDOS、ViEWS、StreamSpot 和 ICU 告警的指标不跨领域迁移。
7. 六个金融 pattern 的窗口和阈值属于项目参数，不能归因于上述论文。

