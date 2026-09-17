# MarketStream 当前代码边界与AI使用说明

## 可主张的项目工作

- 统一live/replay事件合同及可追溯身份；
- 八因子在三种cadence下的组合、窗口化和baseline隔离；
- 六类金融CEP状态机的条件、方向和时间窗口；
- 数据质量抑制、cooldown和告警追溯；
- 标签冻结、checksum、严格向前一对一匹配和Replay评测流程。

MAD、Isolation Forest、订单流失衡、市场残差和CEP概念来自公开方法，不能写成个人发明。
Kafka、TimescaleDB、Alpaca和scikit-learn属于第三方平台或工具。

## AI使用边界

当前Git历史只能证明代码何时进入仓库，不能证明每一行由谁手写。最终提交应同时保存：

1. Claude及其他AI工具的完整对话导出；
2. 对话时间、需求、涉及模块、人工修改和测试结果的索引；
3. 人工能够解释并现场修改的核心代码清单；
4. 无法确认来源或无法解释的内容不得声称为个人原创。

建议答辩表述：

> 我负责研究问题、系统边界、因子和CEP规则定义、实验协议以及结果验证；开发中使用AI辅助部分实现和文档整理，并通过测试、Replay和真实数据链路核验保留内容。

具体源码与练习见 [CORE_WALKTHROUGH_CN.md](CORE_WALKTHROUGH_CN.md)。
