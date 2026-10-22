# 零 MAD 处理：预先声明的方案与敏感性检验

状态：**协议已声明，结果待补**。本节在查看任何校准结果之前提交；结果与最终配置在下文
“结果”一节追加，不回改本节。

## 1. 问题

`return_surprise` 用同一 `(ticker, cadence, session, slot)` cell 过去最多 20 个交易日的原始
收益做 robust 标准化：

```
z = (r - median) / max(1.4826 × MAD, 1e-6)
```

IEX 成交稀疏，许多 10 秒窗口只有报价，收益恰为 0。当某个 cell 一半以上的历史收益为 0 时，
MAD = 0，尺度退化为 `1e-6`（0.01 个基点），一笔普通的一跳价格变化就会得到上百的 z 值。该值
又写入 `return_surprise` 自身历史，进而决定其 elevated/extreme 阈值。也就是说，在这些 cell 中，
检测结果由一个任意的数值常数决定，而不是由市场数据决定。

## 2. 预先选定的方案（主方案 `mean_ad_tick_1`）

```
spread = 1.4826 × MAD                    若 MAD > 0
       = 1.2533 × mean(|x - median|)     若 MAD = 0 且 MeanAD > 0
scale  = max(spread, 0.01 / reference_price)
```

- **MeanAD 回退**：MAD 为 0 时改用平均绝对偏差（1.2533 = √(π/2)，正态下换算为标准差）。
  这是修正 z 分数在 MAD = 0 时的常用做法（Iglewicz & Hoaglin, 1993；IBM SPSS 的
  robust z 也采用 1.253314 × MeanAD），不引入新的自由参数。
- **一跳下限**：收益无法分辨小于一个最小报价单位（Reg NMS：价格 ≥ $1 的股票为 $0.01）
  的变化，因此尺度不得小于一跳对应的收益 `0.01 / 参考价`（参考价为计算收益所用的前收盘）。
  下限由市场规则给出，不由结果调参。
- 适用范围：只替换 `return_surprise` 的原始收益尺度。各因子分类阶段的 `1e-6` 只作数值保护，
  阈值主要由历史分位数决定；“分类阶段也用 MeanAD”只作探索性变体报告，不进入主方案。

## 3. 数据与隔离

- 校准集：Alpaca IEX，2023-10-02 至 2023-11-10 共 30 个交易日，AAPL/TSLA/NVDA/QQQ/SPY，
  09:30–11:00 与 14:00–15:30（ET）两个时段，与候选评测区间所用时段一致。
- 该期间早于所有候选区间（最早 2024-02-08）及其 20 日 baseline（最早 2024-01），也不触及
  拟议 holdout（2025-05/06）。校准集没有标签，本检验不计算 Precision/Recall。
- 报价逐页完整读取，只保留每秒最后一笔；引擎只使用窗口内最后一笔报价，故 10 秒及以上窗口的
  报价终态不变，仅缺少 side 的成交在推断方向时可能使用至多 1 秒前的中间价。
- 前 20 个交易日只用于建立滚动 baseline，第 21–30 日计量；这与评测器“每个区间使用前 20 日
  冻结 baseline”等价（cell 每日只写入一次，且当日评分只使用严格在先的样本）。

## 4. 变体

| 变体 | 说明 |
|---|---|
| `legacy_fixed_1e-06` | 现行：无回退，下限 1e-6 |
| `fixed_1e-05/5e-05/1e-04` | 只用固定下限（说明“单靠下限”的参数依赖） |
| `tick_1_no_mean_ad` | 只用一跳下限（分离 MeanAD 的作用） |
| `mean_ad_fixed_1e-06` | 只用 MeanAD（显示仍退化的比例） |
| `mean_ad_tick_0.5/1/2/4` | 主方案及下限 ×0.5、×2、×4 |
| `zero_when_mad_zero` | 备选：MAD = 0 时不给分（z = 0） |
| `mean_ad_tick_1_factors_too` | 探索：分类阶段也用 MeanAD |
| `bar_end_*` | 稳健性：分钟线时间戳改为分钟结束时 |

每个变体都运行完整的生产链：质量门 → 因子引擎 → CEP（逐窗口原始检测）与按 ticker 拟合的
Isolation Forest → 与正式评测相同的共享告警策略。

## 5. 预先声明的判据（针对主方案，两个时段合并）

- **C1 普遍性**（只报告）：各 cadence 中 MAD = 0、回退后仍退化、下限生效的窗口比例。
- **C2 下限不主导**：CEP 与 IF 的策略后告警中，来自“尺度等于一跳下限”窗口的比例均 ≤ 5%。
- **C3 稳定**：下限取 0.5 跳和 2 跳时，CEP 与 IF 告警数相对主方案变化均不超过 ±10%，且告警
  集合（会话、ticker、方向、5 分钟桶）的 Jaccard 相似度 ≥ 0.85。
- **C4 无扭曲**：MAD = 0 窗口中 `return_surprise` 原子事件出现率不超过 MAD > 0 窗口的 2 倍。

决策规则：C2–C4 全部通过则采用主方案。若有不通过，不在校准集上继续搜索参数；改为评估
备选 `zero_when_mad_zero` 是否通过，两者都如实报告，并在冻结协议前交由项目负责人决定。

复现：

```bash
uv run python -m scripts.collect_calibration_events
uv run python -m scripts.zero_mad_sensitivity --output report/ownership_evidence/reproduction_outputs/zero_mad_20261023
```

## 6. 结果

（待补）
