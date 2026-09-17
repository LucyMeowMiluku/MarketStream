# Git 与版本证据

## 当前基线与证据快照

- 分支：`codex/core-simplification`
- 简化前 base：`bb0df67fad42ef6cf4c544b5e3711d57cd32f3fd`
- 证据内容快照：`6bcdd04d42f266c820eebb6e0c28099cd288265f`
- 快照说明：`docs: snapshot MarketStream ownership evidence`
- 快照范围：165 个文件，包含 core simplification、baseline persistence、当前 tests、选定 evaluation/replay 工件、原始学生报告和 ownership evidence package。
- 最终元数据提交：在 Evidence Index 写入上述快照 hash 的后续提交，以当前 `git log -1` 为准。

证据快照固定了本次核对使用的代码与材料。大体积 historical/backtest 数据、模型二进制、演示 PPT、参考报告草稿和 `.playwright-cli` 没有进入该快照。它们仍保留在本地，没有被删除或改写。

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
| `6bcdd04` | 2026-09-17 | core simplification 与 ownership evidence 内容快照 | 本证据包的固定版本 |

## 快照中的核心变化

- 旧四模型 ensemble、通用 NFA、旧 feature 链和若干 dashboard 页面被删除；
- 新增六个显式状态机；
- 新增 baseline epoch、repository、writer、checkpoint、backfill 和 startup；
- 新增严格 real replay validation、Isolation Forest 公平 baseline 和 HTML trace；
- 当前测试集合从旧版本的约 160 项缩减为 62 项，测试范围也随主线简化发生变化。

这些变化已进入 `6bcdd04`。它们是本证据包的实现基线。后续修改应使用新的 commit，并在实验记录中明确版本。

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
- 一个 commit 已经等同于生产部署或长期恢复验证。
