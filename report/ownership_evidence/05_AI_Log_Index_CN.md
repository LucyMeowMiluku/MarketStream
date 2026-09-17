# MarketStream AI 使用记录索引

准备日期：2026-09-17  
日志说明：[`AI_Logs/README.md`](AI_Logs/README.md)  
完整性 hash：[`AI_Logs/SHA256SUMS.txt`](AI_Logs/SHA256SUMS.txt)

## 1. 使用原则

我在项目中使用了 Codex、ChatGPT 和 Claude。AI 参与过代码生成、调试、实验脚本、解释和报告写作。以下索引不把 AI 输出写成我的独立手写工作。每条记录分开说明我的问题或约束、AI 的工作、我的核查和最终采用状态。

本轮只读取工作目录明确属于 MarketStream 的 Codex 任务，以及标题明确属于 MarketStream 的一段 ChatGPT 会话。私人聊天和其他项目被排除。Claude 历史目前不可访问，所以只记录缺口，不进行重构。

## 2. 高相关度日志

| Log ID | 日期 | 会话 | 对应模块 | 我提出或确认的内容 | AI 的作用 | 我的核查或修改 | 采用状态 |
|---|---|---|---|---|---|---|---|
| MS-AI-01 | 2026-09-11 | `baseline cell落库计划` | baseline 持久化 | 我先指出进程重启会丢失 20 日 baseline。我提出 DB 状态、五维 key、20 日保留和启动恢复流程。后续计划又明确三种 startup mode、epoch、checksum 和 checkpoint。 | 按这些约束新增 `baseline/`、repository、writer、checkpoint、backfill 和测试。 | 我要求错误空库不能自动当首次部署，状态损坏要 fail closed；当前 7 项 persistence tests 通过。 | 当前工作树采用；尚无生产长期验证 |
| MS-AI-02 | 2026-08-21 | `核查准确率与数据来源` | replay 与评测 | 我直接询问现有 accuracy/recall 是否来自 live data，并要求真实历史 replay、预先标签和 HTML 流水线。 | 检查仓库后指出现有结果来自 synthetic 或 injection，并辅助实现 label registry、manifest、replay evaluator 和报告。 | 我继续要求标签独立确认、冻结、baseline 无泄漏和正常区间；当前 draft 标签会阻止正式指标。 | 采用严格评测门；真实指标未完成 |
| MS-AI-03 | 2026-08-26 | `核查准确率与数据来源 (2)` | 数据质量 | 我追问 live bar 为什么全部出现 stale，是否代表 Alpaca 数据异常。 | 对照时间戳和代码定位 minute bar 是区间开始时间，通用 30 秒阈值错误。 | 修改为 bar close grace 后复查 5 条 bar 均不 stale。 | 已采用并有 IEX 工件 |
| MS-AI-04 | 2026-09-10 | `比较状态机与NFA框架` | CEP 架构 | 我要求解释当前六类状态机与通用 NFA 的差别，并判断项目是否需要 NFA。 | 对照代码说明当前是多个小型显式状态机，给出保留现状的建议。 | 我把结论限制为当前项目规模和可解释性，不把状态机写成算法创新。 | 当前主线采用显式状态机 |
| MS-AI-05 | 2026-09-11 | `澄清报告方法与参数` | 方法与报告 | 我要求逐项核实主动买卖方向、新闻情绪、阈值、六类模式参数、baseline 样本和代码映射。 | 沿源码调用链给出公式、状态转换和应修改的报告位置。 | 我保留了小样本分位数限制；没有把工程参数写成文献最优值。 | 已进入修订稿和证据包 |
| MS-AI-06 | 2026-08-26 | `标注核心代码与参考来源` | ownership 与参考来源 | 我要求区分核心代码、方法来源、演进和修复。 | 梳理文件、提交、公开方法和第三方依赖。 | 本次重新用代码、Git 和日志交叉检查，不把 Git author 等同于纯手写。 | 作为贡献表来源之一 |
| MS-AI-07 | 2026-09-07 | `实验设计部分修改` | 报告实验章 | 我要求修改实验设计和告警控制，语言保持学生化。 | 修改报告结构、实验层级和限制描述。 | 本次重新对照当前 JSON，修正旧 timing、soak 和效果表述。 | 旧稿部分采用，本轮继续修订 |
| MS-AI-08 | 2026-08-19 | `梳理项目并设计轻量异常检测 (2)` | live 与 soak | 我要求复验 Alpaca 实时流、历史数据和 Kafka→DB soak。 | 辅助运行实流、保存 E2E 输出并做 soak。 | 本次区分 88 秒 IEX、synthetic transport 和准确率；保留失败 run。 | 工程证据保留，效果结论降低 |
| MS-AI-09 | 2026-08-26 | `报告` | 报告初稿 | 我要求根据项目和实验结果形成完整中文报告。 | 大量辅助组织和起草文字。 | 本次发现过强结论、数字冲突和本地路径，建立修订稿，不把旧稿直接提交。 | 原稿仅作历史输入 |
| MS-AI-10 | 2026-09-02 | `解释八个因子表达式变量` | 因子解释 | 我要求用较容易理解的方式解释八个因子公式。 | 给出变量含义和因子组合说明。 | 本次回到当前代码核实 trade side、新闻词表和 threshold。 | 解释部分经核对后采用 |
| MS-AI-11 | 2026-08-26 | ChatGPT `冻结median MAD基线` | baseline 与评测 | 我追问 baseline 如何冻结，以及 1.4826 的含义。 | 解释 median/MAD、日内 cell、无泄漏冻结和 normal-consistency constant。 | 后续代码使用 `max(1.4826×MAD,1e-6)`；报告不再称它为无含义数字。 | 理论解释采用；阈值仍是工程参数 |
| MS-AI-12 | 2026-09-09 | `整理 Market Stream 项目证据链` | ownership | 我要求把项目动作、AI 贡献和效果证据分开。 | 生成结构化证据链和简历方向摘要。 | 本证据包重新按导师要求核实，不直接复用宣传性语言。 | 只采用事实框架 |

## 3. 其他已归档 MarketStream Codex 任务

| 日期 | Task ID | 标题 | 主要内容 | Transcript |
|---|---|---|---|---|
| 2026-08-06 | `019fd5c8-19e8-7bd2-998b-65a4c103bcc6` | 梳理项目并设计轻量异常检测 | 早期架构复盘和轻量方案 | `AI_Logs/transcripts/rollout-2026-08-06T14-34-48-019fd5c8-19e8-7bd2-998b-65a4c103bcc6.jsonl` |
| 2026-08-19 | `01a01a83-c93a-71a0-9088-7d82f25e6cb4` | 梳理项目并设计轻量异常检测 (2) | 实流、历史数据与 soak | `AI_Logs/transcripts/rollout-2026-08-19T22-53-59-01a01a83-c93a-71a0-9088-7d82f25e6cb4.jsonl` |
| 2026-08-20 | `01a01cd8-a6d8-7700-94be-b549f8ba4c77` | 项目背景 | 项目学习、提纲和实验设计 | `AI_Logs/transcripts/rollout-2026-08-20T09-45-55-01a01cd8-a6d8-7700-94be-b549f8ba4c77.jsonl` |
| 2026-08-21 | `01a02203-82e0-7f13-893e-9735a23e1dc1` | 项目背景 (2) | 八因子、CEP 和报告提纲 | `AI_Logs/transcripts/rollout-2026-08-21T09-50-50-01a02203-82e0-7f13-893e-9735a23e1dc1.jsonl` |
| 2026-08-21 | `01a02271-2bd1-7e23-aec5-b00a70219645` | 核查准确率与数据来源 | 结果来源和 formal replay | `AI_Logs/transcripts/rollout-2026-08-21T11-50-37-01a02271-2bd1-7e23-aec5-b00a70219645.jsonl` |
| 2026-08-26 | `01a03c25-81c0-7a92-ae2a-cc684add171c` | 标注核心代码与参考来源 | 代码和文献来源 | `AI_Logs/transcripts/rollout-2026-08-26T11-38-06-01a03c25-81c0-7a92-ae2a-cc684add171c.jsonl` |
| 2026-08-26 | `01a03ce9-ecd3-7c63-84a9-9c9b3bfb6b86` | 报告 | 中文报告初稿 | `AI_Logs/transcripts/rollout-2026-08-26T15-12-38-01a03ce9-ecd3-7c63-84a9-9c9b3bfb6b86.jsonl` |
| 2026-08-26 | `01a03d49-73fa-7ae2-8a64-321f7c08ef90` | 核查准确率与数据来源 (2) | stale bar 定位 | `AI_Logs/transcripts/rollout-2026-08-26T16-56-59-01a03d49-73fa-7ae2-8a64-321f7c08ef90.jsonl` |
| 2026-08-27 | `01a04259-7cbc-7282-b198-5fae649ab819` | 规划代码分组提交 GitHub | 提交拆分 | `AI_Logs/transcripts/rollout-2026-08-27T16-32-36-01a04259-7cbc-7282-b198-5fae649ab819.jsonl` |
| 2026-09-01 | `01a05c57-d039-7ce2-b1de-f7bb8e2ff107` | 报告修改 | 引用和参考文献 | `AI_Logs/transcripts/rollout-2026-09-01T17-40-53-01a05c57-d039-7ce2-b1de-f7bb8e2ff107.jsonl` |
| 2026-09-02 | `01a06127-f8b3-7b92-8331-697e0351892d` | 解释八个因子表达式变量 | 因子公式解释 | `AI_Logs/transcripts/rollout-2026-09-02T16-06-44-01a06127-f8b3-7b92-8331-697e0351892d.jsonl` |
| 2026-09-07 | `01a07aba-7000-7c20-9243-cf689191e9e6` | 实验设计部分修改 | 报告实验章 | `AI_Logs/transcripts/rollout-2026-09-07T15-17-13-01a07aba-7000-7c20-9243-cf689191e9e6.jsonl` |
| 2026-09-09 | `01a084d4-2ab4-7a10-83ac-f061a9aafd15` | 整理 Market Stream 项目证据链 | ownership 复盘 | `AI_Logs/transcripts/rollout-2026-09-09T14-21-32-01a084d4-2ab4-7a10-83ac-f061a9aafd15.jsonl` |
| 2026-09-10 | `01a08928-8b70-7be0-a7d0-82649c3ac924` | 查找类似 MarketStream 的项目 | 相似项目和导师选择 | `AI_Logs/transcripts/rollout-2026-09-10T10-32-10-01a08928-8b70-7be0-a7d0-82649c3ac924.jsonl` |
| 2026-09-10 | `01a08a2b-07a3-7523-abd7-a4b36955a409` | 比较状态机与NFA框架 | CEP 选型 | `AI_Logs/transcripts/rollout-2026-09-10T15-14-30-01a08a2b-07a3-7523-abd7-a4b36955a409.jsonl` |
| 2026-09-11 | `01a08e40-d1cd-78a2-9440-7c7a1acb7f35` | 澄清报告方法与参数 | 方法核查 | `AI_Logs/transcripts/rollout-2026-09-11T10-16-47-01a08e40-d1cd-78a2-9440-7c7a1acb7f35.jsonl` |
| 2026-09-11 | `01a08f60-99cb-7f32-9afc-b71139f0f45d` | baseline cell落库计划 | epoch 与持久化 | `AI_Logs/transcripts/rollout-2026-09-11T15-31-07-01a08f60-99cb-7f32-9afc-b71139f0f45d.jsonl` |

## 4. 日志中能看出的开发过程

这些记录并不只显示“AI 给出答案”。它们还保留了几种反复出现的过程：

1. 我先质疑已有数字是不是来自真实数据。
2. AI 检查代码和工件，发现结果属于 synthetic、injected 或 warm-up。
3. 我继续要求更严格的标签、冻结和数据来源证明。
4. AI 辅助实现代码或改报告。
5. 我根据测试、失败输出或新问题继续调整要求。

一个明显例子是 baseline 持久化。我先指出重启后历史会丢失，并给出 DB 和 20 日状态思路。AI 实现后，方案又增加了 epoch、显式 startup mode、checksum 和 fail-closed 恢复。贡献应描述为“我提出问题和约束，AI 辅助实现，我复查设计和测试”，而不是“我完全独立手写持久化系统”。

## 5. 缺失和后续补充

- Claude 日志：目前无法访问。不会伪造。
- ChatGPT 官方导出：本轮内置浏览器无法加载账户页，因此导出请求尚未确认提交。官方路径是 Settings → Data controls → Export data。导出可能需要最多 7 天，下载链接收到后 24 小时过期。本轮只有一段明确的项目会话按 API 可访问内容保存。
- 当前证据包任务：任务还在进行，未进入静态导出。
- 记录中涉及凭据的整行：为安全原因删除。README 说明了过滤规则。

收到官方导出后，应补充文件、更新时间、重新计算 hash，并在本表中增加对应 Log ID。
