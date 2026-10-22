> 2026-10-22 核验口径：唯一报告主稿为 [07_Revised_Report_CN.md](07_Revised_Report_CN.md)，英文为对应译稿。数字、版本与缺失依据以[运行台账](Evidence_Attachments/Result_Run_Ledger_20261022.md)及[机器清单](reproduction_outputs/audit_20261022/result_registry.json)为准；历史结果不能合并为当前系统结果。

# MarketStream 文献核实

## 1.总表

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

## 2.只使用了其中最相关的六篇作为参考

### [1] Barrie et al. — MEDOS

- 来源：https://ntrs.nasa.gov/api/citations/20250002215/downloads/MEDOSJSR.pdf

- 简介：MEDOS主要讲了航天器怎样在太空中自动识别事件，并根据事件做出操作决定。传统航天器会按照预先写好的时间表执行命令。但有些事件无法提前确定时间，例如，航天器进入辐射带、穿过磁层边界等。如果每个事件都等地面人员发现，再向航天器发送命令，通信延迟会很大，特别是对于远距离任务或卫星群。MEDOS的目标是，让航天器根据传感器数据，在本地识别事件，并根据识别结果触发操作。

  MEDOS 主要有两个步骤。第一步，把航天器多条原始数据（电压、磁场方向等）组合起来，形成具有实际意义且专家熟悉的派生参数（如等离子体密度）。第二步，将这些派生参数与文献、历史飞行经验等典型值和事件定义进行比较。系统不再使用固定的阈值，而是通过 fuzzy membership function 判断每个参数与目标事件的符合程度，再组合多个参数的证据，输出事件发生的 confidence。

- 项目中借鉴的观点：

  | MEDOS 的观点                                                 | 对 MarketStream 的启发                                       |
  | ------------------------------------------------------------ | ------------------------------------------------------------ |
  | **不能只对原始数据使用固定阈值**：MEDOS不会直接对单个原始遥测数据报警，会先形成有实际意义的派生参数。 | 对复杂实时数据进行事件判断前，可以先把原始输入转换成具有该领域实际意义的派生状态。项目中不直接对原始数据trade / quote / bar / news使用固定阈值判断异常，而是先计算八个有金融意义因子。 |
  | **异常要相对于正常运行状态判断**：MEDOS 会把派生参数与典型值比较。 | 事件检测不能只看绝对数值，还需要参考当前对象和运行状态下的典型范围。同样的成交量在开盘可能正常，在午间可能异常。不同的标的的阈值也不一样。因此在项目中，需将当前因子与相同 ticker、cadence、session 和 intraday slot 的历史 baseline 比较。 |
  | **告警应该给出可理解的证据**：MEDOS 的derived parameters 是可解释的值，且最后判断后会给出confidence而不只是一个判断。 | 系统输出应该保留领域含义和判断依据，而不只是输出一个无法解释的异常分数。项目中没有使用 MEDOS 的 fuzzy confidence，但是选择了相似的可解释异常结果的这一种方向。因此，DetectionResult 还需保留 pattern、方向、因子状态、质量标记和原始 event IDs |

### [2] Bhattacharya et al. — Towards Unbiased Evaluation of Time-series Anomaly Detector

- 来源：https://openreview.net/pdf?id=CseY9pxbsN

- 简介：主要讨论时间序列异常检测的评测结果是否公平。普通分类通常把每个时间点单独判断为正常或异常。但是，时间序列中的异常经常会持续一段时间。例如，一次设备故障或市场异常可能连续存在几分钟。因此，异常应该被理解为一个连续事件，而不只是很多互相独立的异常点。

  为了处理这个问题，很多研究使用 Point Adjustment。它的做法是，只要系统检测到异常区间中的一个时间点，就算作整个异常区间都检测正确。这就会导致，一个系统即使只碰巧命中了一个点，也可能被当作发现了整个异常事件。但是这种方法会增加 True Positive，让 F1 变得过高，导致检测器性能被高估。同时，正常区间中的一次错误告警仍然只计算为一个 FP，导致系统得到的奖励和惩罚并不平衡。

  因此，论文提出了 Balanced Adjustment。该方法在扩展异常区间内 TP 的同时，也会对正常区间中的 FP 进行相应调整，使正确检测和错误检测受到更平衡的处理。

- 项目中借鉴的观点：项目主要借鉴了参考论文设计 Balanced Adjustment 的思路。

  | **Unbiased TSAD Evaluation 的观点**                          | **对 MarketStream 的启发**                                   |
  | ------------------------------------------------------------ | ------------------------------------------------------------ |
  | **时间点和异常事件不是同一个概念**：时间序列异常通常会持续一段时间，不能只把每个时间点作为独立的分类结果。 | MarketStream 评测的是完整的金融异常事件。因此，项目比较的是 DetectionResult 与预先定义的真实异常事件，而不是只检查每个 FactorSnapshot 是否预测正确。 |
  | **部分命中可能使评测结果过高**：传统 Point Adjustment 可能把异常区间中的一次命中扩展为整个区间都检测正确，从而使 TP 和 F1 偏高。 | 同一个真实异常即使产生多条连续告警，也最多计算一次 TP。项目使用一对一事件匹配，未匹配的告警计算为 FP，未被发现的真实事件计算为 FN。 |

### [3] Cont et al. —  The Price Impact of Order Book Events

- 来源：https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1712822

- 简介：该篇论文研究了订单事件与短期价格变化之间的关系。文中使用的数据是记录 50 只美国股票的 NYSE Trades and Quotes。作者关注三种订单事件：限价单、市价单和撤单。这些事件会改变最优买价和最优卖价附近的供需情况。

  论文提出了 Order Flow Imbalance（OFI）。它表示最优买卖价附近买方力量和卖方力量的差异。OFI 不只统计已经完成的成交，也考虑新增限价单和撤单带来的变化。在较短的时间范围内，OFI 与价格变化接近线性关系。当买方订单流更强时，价格更可能上涨；当卖方订单流更强时，价格更可能下跌。

  论文还发现，订单流对价格的影响与市场可以承接多少交易有关。当买卖报价上的挂单较少时，较小的订单流也可能引起较大的价格变化。

- 项目中借鉴的观点：

  | **Order Flow Imbalance  **                                   | 对MarketStream 的启发                                        |
  | ------------------------------------------------------------ | ------------------------------------------------------------ |
  | **不能只根据成交量判断市场异常**：短期价格变化与买卖双方的订单流失衡有关。限价单、市价单和撤单都可能改变市场供需 | 项目除了计算 `relative_volume`，也关注报价和成交方向。因此加入了 `quote_imbalance` 和 `signed_trade_imbalance`，用于表示买卖双方的压力。不过，这两个因子只是简化指标，不等于论文中严格定义的 OFI。 |
  | **订单流的影响与市场流动性有关**：OFI 对价格的影响与市场深度有关。市场深度越低，同样的订单流失衡可能产生更大的价格变化。 | 这说明判断订单流异常时，还需要考虑当时的市场流动性状态。项目因此也观察报价量和 `spread_stress`。但是，价差不等于市场深度，而且项目使用的 IEX 顶层报价不能代表完整市场订单簿。 |

### [4] Gyllstrom et al. — SASE: Complex Event Processing over Streams

- 来源：https://www.skilift-simmerberg.de/~patrick/papers/cidr07.pdf

  https://arxiv.org/abs/cs/0612128

- 简介：该篇论文是CEP的早期重要论文之一。研究背景是随着 RFID（射频识别）技术在供应链、零售、医疗等领域的普及，传感器会产生海量的原始数据，但底层数据太原始无业务层需要的实际含义。为了解决这些问题，作者提出了 SASE 系统，目的从海量、底层的实时数据流中，高效地提取和匹配出有业务价值的“复杂事件”。

  论文有三大核心贡献。第一，提供了一种为事件模式匹配设计的类似于 SQL 的语言。第二，为了底层执行速度更快，SASE 采用了一种类似关系型数据库的Dataflow模型。第三，SASE 不仅仅是一个算法，它提供了一个三层架构的完整系统。物理层用于收集 RFID 硬件信号，数据清洗层用于将原始信号转化为基础事件流，复杂事件处理层用于实时处理这些事件流，输出告警，同时将有用的事件存档到数据库中，以供历史查询。

  在论文中展示了一个零售店防盗场景。假设要检测是否有商品被偷，可以定义该事件逻辑为：商品在货架被读取了 ，随后没有在收银台被读取，最后在出口门禁被读取了。如果出现了这一特定时间序列，系统就会立刻捕获偷窃这一事件然后警报。

- 项目中借鉴的观点：

  | **SASE 的观点**                                              | 对 MarketStream 的启发                                       |
  | ------------------------------------------------------------ | ------------------------------------------------------------ |
  | 单个数据没有意义，组合起来才是事件：SASE会组合货架、收银台和出口等多条记录来判断商品未结账离店等异常事件。 | MarketStream 不能只根据一次价格变化或一个异常因子就判断为市场异常事件。将八因子分别组合成CEP组合再判断是否为异常事件。 |
  | **事件之间的顺序和时间范围很重要**：SASE 会规定事件先发生什么、后发生什么，以及模式需要在多长时间内完成。 | 项目受此启发使用了 CEP 状态机和时间窗口的设计。例如，新闻先出现，随后价格和成交活动发生变化，才能形成新闻冲击模式。持续订单压力也需要在一段时间内连续出现，而不是只看某一个时刻。 |

### [5] MacKinlay — Event Studies in Economics and Finance

- 来源：https://ideas.repec.org/a/aea/jeclit/v35y1997i1p13-39.html

  https://www.bu.edu/econ/files/2011/01/MacKinlay-1996-Event-Studies-in-Economics-and-Finance.pdf

- 简介：这篇论文主要回答了一个问题：某个经济事件发生后，一家公司股票的变化，有多少可以被认为是这个事件带来的，而不是整个市场正常波动造成的。文章中使用 Event Study 研究方法用于分析某个明确事件是否引起了股票价格或公司价值的异常变化，其逻辑可以定义为异常收益 = 实际收益 - 没有该事件时的预期正常收益

  论文主要介绍了三个核心内容。第一，研究者需要确定事件日期和事件窗口。事件窗口包括事件发生前后的一段时间。第二，需要先使用事件发生前的数据估计正常收益。然后用实际收益减去正常收益，得到异常收益。第三，可以将多天的异常收益累加为累计异常收益，并通过统计检验判断结果是否明显偏离正常水平。

  论文使用公司季度财报作为示例。作者收集了道琼斯工业指数中30家公司的600次季度财报公告。财报被分为好消息、普通消息和坏消息。然后，作者比较三类财报发布前后的异常收益和累计异常收益。

- 项目中借鉴的观点：

  | **Event Study 的观点**                                       | **对 MarketStream 的启发**                                   |
  | ------------------------------------------------------------ | ------------------------------------------------------------ |
  | 异常收益应通过实际收益与正常预期收益的差值来判断。市场收益可以用于估计个股的正常表现。 | MarketStream 加入了 `market_residual` 因子，用个股收益减去市场收益，避免把市场整体上涨或下跌误认为个股异常。 |

- 报告修改：`market_residual = r_i-r_m` 持续标为轻量近似，不称为正式 abnormal return。

### [6] Tetlock — Giving Content to Investor Sentiment: The Role of Media in the Stock Market

- 来源：https://onlinelibrary.wiley.com/doi/10.1111/j.1540-6261.2007.01232.x

  https://www.uts.edu.au/globalassets/sites/default/files/adg_cons2015_tetlock-journal-of-finance-2007.pdf

- 简介：该论文研究新闻媒体中的悲观情绪是否与短期市场收益和交易量有关。作者提出了三种可能的解释。第一，媒体报道包含新的基本面信息，因此会对价格产生较长期的影响。第二，媒体情绪影响投资者行为，从而造成短期买卖压力。第三，媒体只是在描述已经发生的市场变化，并没有提供额外的预测信息。  

  作者分析了《华尔街日报》的每日市场评论，并检查媒体情绪、市场收益和交易量之间的时间关系。结果显示，当媒体内容异常悲观时，股票市场在下一个交易日通常面临下跌压力，但这部分影响会在之后几天逐渐反转。同时，之前的市场下跌也会使后续报道变得更加悲观。论文因此认为，媒体情绪与市场变化存在双向关系。媒体悲观情绪更接近短期投资者情绪和交易压力，而不能简单理解为长期基本面信息。

- 项目中借鉴的观点：

  | **Media Sentiment 对 MarketStream 的启发**                   | **项目中的对应方式**                                         |
  | ------------------------------------------------------------ | ------------------------------------------------------------ |
  | **新闻情绪可以作为市场异常的辅助信息**：论文发现，媒体悲观程度与短期价格压力和交易活动有关。 | 项目加入新闻情绪因子，用来补充价格、成交量和订单流信息。但是，项目采用简化的词典评分，并没有复现论文的情绪计算方法。 |
  | **新闻情绪不能单独解释价格变化**：媒体情绪可能影响投资者，但市场下跌也可能使后续报道更加悲观。论文还发现部分价格影响随后会反转。 | 项目不把负面新闻直接当作异常结论，而是结合价格、成交量或订单流进行确认。系统只能识别时间上的共同变化，不能证明新闻导致了价格变化。 |

## 文献核实后的总体修改

1. 把所有“文献证明 MarketStream 设计正确”的句子改为“文献提供设计动机”。
2. NISTIR 8219 使用“demonstrated”，不写成生产部署。
3. Cont 的严格 OFI 与当前简化 imbalance 明确区分。
4. MacKinlay 的 abnormal return 与简单 `r_i-r_m` 明确区分。
5. Bhattacharya 的 BA 与本项目一对一事件匹配明确区分。
6. MEDOS、ViEWS、StreamSpot 和 ICU 告警的指标不跨领域迁移。
7. 六个金融 pattern 的窗口和阈值属于项目参数，不能归因于上述论文。

