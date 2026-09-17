# Git 与版本证据

## 当前基线

- 分支：`codex/core-simplification`
- HEAD：`bb0df67fad42ef6cf4c544b5e3711d57cd32f3fd`
- HEAD 日期：2026-09-10 15:28:46 +08:00
- HEAD 说明：`chore: snapshot project before core simplification`
- 当前工作树：非 clean；83 个 tracked files 发生变化，另有 core、baseline、evaluation、replay、report 和 tests 等未跟踪文件。

当前 HEAD 是简化前快照，不是最终实现快照。因此所有材料同时记录 base commit 和工作树状态。最终审核后应创建新的 evidence snapshot commit；在此之前不能假装现有代码已由某个 commit 完整固定。

## Git 身份说明

历史中出现：

- `LucyMeowMiluku`；
- `Demo0102`。

学生确认这两个身份均为本人使用的不同 Git 身份。公开证据包不列出私人邮箱。历史中存在相同内容、不同作者身份的平行提交，因此 Git 只能证明内容进入不同引用/分支的时间，不能单独证明逐行手写来源。

## 核心历史提交

| Commit | 日期 | 内容 | 证据用途 |
|---|---|---|---|
| `91d6b8f` | 2026-08-27 | MarketEvent 数据协议和接入 | 统一合同的历史节点 |
| `b6b9686` | 2026-08-27 | 数据质量和八因子 | 因子主线的历史节点 |
| `b112b08` | 2026-08-27 | CEP 模式与告警 | CEP 主线的历史节点 |
| `ae1373e` | 2026-08-27 | replay 检测模块 | replay 的历史节点 |
| `5f1f856` | 2026-08-27 | processing tests | 因子测试节点 |
| `67715af` | 2026-08-27 | CEP tests | CEP 测试节点 |
| `bb0df67` | 2026-09-10 | 简化前快照 | 当前工作树的 base commit |

## 当前未提交核心变化

- 旧四模型 ensemble、通用 NFA、旧 feature 链和若干 dashboard 页面被删除；
- 新增六个显式状态机；
- 新增 baseline epoch、repository、writer、checkpoint、backfill 和 startup；
- 新增严格 real replay validation、Isolation Forest 公平 baseline 和 HTML trace；
- 当前测试集合从旧版本的约 160 项缩减为 62 项，测试范围也随主线简化发生变化。

这些变化属于当前证据包的实现基线，但在最终 snapshot commit 创建前，必须继续标记为 working-tree evidence。

## 作者证据的使用边界

Git 可以支持：

- 代码和文档在什么时间进入仓库；
- 哪些模块在同一阶段出现；
- 项目从 ML ensemble 到 factor+CEP 的演进；
- 失败实验、测试和文档是否被保留。

Git 不能单独支持：

- 每一行都由学生纯手写；
- AI 没有参与；
- commit author 等于唯一设计者；
- 当前未提交工作已经形成可恢复的正式版本。

