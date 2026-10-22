# 来源归属（2026-10-22）：XI LU 主导方案选择与具体约束，AI 按确认方案生成／重构实现。
# 本注释不声明全部代码由本人手写；逐项原日志与未确认范围见
# docs/CORE_CODE_AUTHORSHIP_AND_REFERENCES_CN.md 及 report/ownership_evidence/08_Contribution_Attribution_Matrix_CN.md。
# =============================================================================
# function：在因子计算前为 live/replay MarketEvent 添加数据质量标记。
#   比如，在计算因子前显式标记 duplicate、out-of-order、stale、zero-volume、invalid-price、crossed-quote 和 feed-gap。
#   有问题的事件仍然保留，由下游决定是否跳过计算或告警。
# 贡献：实现有边界的质量状态、检查组合及质量标记向下游传播。
# 参考边界：行情字段和 minute bar 时间语义参考 Alpaca 官方文档。[R02][R03]
# 关键设计：先标记问题，不静默修复或丢弃，再由因子和 CEP 按严重程度处理。
# 需要解决的问题：重复/乱序事件污染窗口、坏价格进入计算、正常 minute bar 被误判为 stale。
# 解决方法：使用有界 ID/时间状态检查事件；bar 以完成时间为 event_time，与逐笔事件共用 stale 阈值。
# =============================================================================
"""Bounded, explicit data-quality checks for live and replay market events."""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from processing.event_models import MarketEvent, QualityFlag, as_utc


# 目标：在进入因子引擎前检查事件质量，同时保证服务长期运行时内存有上限。
# 关键设计：只维护有限数量的事件 ID 和时间状态，并把检查结果放入事件副本传给下游。
class EventQualityGate:
    def __init__(
        self,
        *,
        max_seen_ids: int = 100_000,
        max_state_keys: int = 10_000,
        stale_after: timedelta = timedelta(seconds=30),
        gap_after: timedelta = timedelta(seconds=90),
    ) -> None:
        self.max_seen_ids = max_seen_ids  # 最多保留多少个近期事件 ID
        self.max_state_keys = max_state_keys  # 最多跟踪多少 ticker/type 组合
        self.stale_after = stale_after  # 逐笔事件允许的最大年龄
        self.gap_after = gap_after  # 超过该间隔即标记 feed gap
        self._seen: OrderedDict[str, None] = OrderedDict()  # 有界去重集合
        self._last_event_time: OrderedDict[tuple[str, str], datetime] = OrderedDict()

    def assess(
        self,
        event: MarketEvent,
        *,
        mode: str = "live",
        now: datetime | None = None,
    ) -> MarketEvent:
        # 目标：使用 MarketEvent 统一生成的 event_id 识别重复事件。
        # 关键设计：记录达到上限后淘汰最旧 ID，在有限内存中保留近期去重能力。
        flags = set(event.quality_flags)
        if event.event_id in self._seen:
            # 同一 ID 再次出现，不让它重复进入因子窗口。
            flags.add(QualityFlag.DUPLICATE.value)
        else:
            self._seen[event.event_id] = None
            if len(self._seen) > self.max_seen_ids:
                # 删除最早记录，保持去重集合大小固定。
                self._seen.popitem(last=False)

        # 关键设计：不同（ticker，event_id)分别维护 max event_time
        # 解决的问题：避免低频 bar 与高频 quote 相互触发乱序或 feed-gap 标记
        key = (event.ticker, event.event_type.value)
        previous = self._last_event_time.get(key)
        if previous is not None:
            if event.event_time < previous:
                flags.add(QualityFlag.OUT_OF_ORDER.value)
            elif (
                event.event_time - previous > self.gap_after
            ):  # 相邻事件间隔过大，数据源中间可能缺失消息
                flags.add(QualityFlag.FEED_GAP.value)
        # 更新最大时间
        if previous is None or event.event_time > previous:
            self._last_event_time[key] = event.event_time
            self._last_event_time.move_to_end(key)
            if len(self._last_event_time) > self.max_state_keys:
                self._last_event_time.popitem(last=False)

        current = as_utc(now or datetime.now(timezone.utc))  # 检查 stale 的参照时间
        stale_limit = self.stale_after

        # 参考：[R02：Alpaca Real-time Stock Data；R03：Alpaca Market Data FAQ]
        # Alpaca minute bar 的 t 是一分钟区间左端，bar 在区间结束后才发布。
        # 解决方法：MarketEvent 的 bar event_time 已是区间结束（完成）时间，
        # 因此 bar 与逐笔事件使用同一 stale 阈值，不再需要单独的窗口结束宽限。
        if mode == "live" and current - event.event_time > stale_limit:
            # replay 使用历史事件时间，不应用真实时钟判断 stale。
            flags.add(QualityFlag.STALE.value)

        # 目标：检查价格、成交量和 bid/ask 的基本可用性。
        # 关键设计：只添加质量标记，不猜测或填补价格，避免下游把人工修复值当作真实观测。
        payload = event.payload
        prices = [
            float(payload[name])
            for name in (
                "price",
                "open",
                "high",
                "low",
                "close",
                "bid_price",
                "ask_price",
            )
            if payload.get(name) is not None
        ]
        if any(price <= 0 for price in prices):
            # 价格必须为正；0 和负数不能进入收益、价差等公式。
            flags.add(QualityFlag.INVALID_PRICE.value)

        if event.event_type.value in {"trade", "bar"}:
            size = payload.get("size", payload.get("volume", 0))
            if float(size or 0) <= 0:
                # trade/bar 没有正成交量时保留事件，但标记为低质量。
                flags.add(QualityFlag.ZERO_VOLUME.value)

        if event.event_type.value == "quote":
            bid = float(payload.get("bid_price", 0) or 0)
            ask = float(payload.get("ask_price", 0) or 0)
            if bid > 0 and ask > 0 and bid > ask:
                # 正常报价应满足 bid <= ask，反向时为 crossed quote
                flags.add(QualityFlag.CROSSED_QUOTE.value)

        # 关键设计：返回 dataclass 副本而不是直接修改原事件
        # 解决的问题：同一输入可以在测试和 replay 中重复使用，并保留原始内容用于后续
        return replace(event, quality_flags=tuple(sorted(flags)))

    @property
    def seen_count(self) -> int:
        return len(self._seen)

    @property
    def state_key_count(self) -> int:
        return len(self._last_event_time)
