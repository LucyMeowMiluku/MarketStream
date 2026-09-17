# =============================================================================
# function：定义本项目的数据合同，包括上游接入数据、因子、CEP、真实 replay 与存储使用的数据结构。
# 贡献：三层事件合同、字段约束、确定性身份和端到端 provenance 设计。
# 参考边界：Kafka/Alpaca 只提供传输与上游字段语义，本文件未复制其实现。[R01][R02]
# 关键设计：live/replay 共用相同 JSON 语义，且结果可反查因子和原始事件。
# 需要解决的问题：不同数据源结构不一致，容易产生重复分支，并使时间、载荷和身份含义混乱。
# 解决方法：把不同来源统一为 MarketEvent，再用 FactorSnapshot 和 DetectionResult 连接因子与告警结果。
# =============================================================================
"""由传入数据、因子计算、CEP、replay和存储共同使用的数据协议。
后续使用json字典输出,保证Kafka topic相同。
首先确定了整个项目的四种市场事件

Stable contracts shared by ingestion, factors, CEP, replay, and storage.
The wire representation intentionally uses plain JSON-compatible dictionaries so
that live and replay traffic can traverse the exact same Kafka topics.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any


def as_utc(value: datetime | str) -> datetime:
    """Return an aware UTC datetime from an ISO string or datetime."""
    parsed = (
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        if isinstance(value, str)
        else value
    )
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


# 四种市场事件：交易、报价、行情、新闻
class EventType(StrEnum):
    TRADE = "trade"  # 成交价&量
    QUOTE = "quote"  # 买卖价
    BAR = "bar"  # k线
    NEWS = "news"  # 新闻


# 用于下一步data quality 评估的参数
class QualityFlag(StrEnum):
    DUPLICATE = "duplicate"  # 重复
    OUT_OF_ORDER = "out_of_order"  # 时间顺序错误
    STALE = "stale"  # 过期
    ZERO_VOLUME = "zero_volume"  # 零成交量
    CROSSED_QUOTE = "crossed_quote"  # 交叉报价
    INVALID_PRICE = "invalid_price"  # 无效价格
    FEED_GAP = "feed_gap"  # 数据缺失


# 目标：让 MarketEvent 成为唯一的原始事件入口，使 live 和 replay 在进入质量门后不再分叉。
# 关键设计：一条事件只允许携带一种 typed payload，但共享身份、来源、时间和 provenance 字段。
# 参考内容：[R02：Alpaca Real-time Stock Data] 仅参考 trade、quote、bar 等上游字段语义；
# MarketEvent 的统一合同和字段组合是为了解决多数据源分叉问题而设计的。
@dataclass(slots=True)
class MarketEvent:
    # 身份信息
    event_id: str  # 上游 ID，或根据事件内容生成的确定性 ID
    source: str  # 数据提供方，例如 alpaca
    feed: str  # 数据覆盖，例如 iex 或 benzinga_news
    event_type: EventType  # 事件类型
    ticker: str  # 股票代码
    # 时间信息
    event_time: datetime  # 事件发生时间
    received_at: datetime  # 事件接收时间
    # payload信息,四种类型event对应各自的信息
    trade: dict[str, Any] | None = None
    quote: dict[str, Any] | None = None
    bar: dict[str, Any] | None = None
    news: dict[str, Any] | None = None
    quality_flags: tuple[str, ...] = ()  # 质量门发现的问题
    run_id: str | None = None  # 一次运行的身份
    dataset_id: str | None = None  # 数据集版本身份
    mode: str | None = None  # live、replay_real、synthetic 或 soak
    provenance: dict[str, Any] = field(default_factory=dict)  # 区间和采集来源

    # 目标：对象创建后立即统一事件类型、股票代码、UTC 时间和质量标记。
    # 解决的问题：下游无需在每个模块中重复修复格式或判断时区。
    def __post_init__(self) -> None:
        self.event_type = EventType(self.event_type)
        self.ticker = self.ticker.upper()
        # 时间必须统一转时区
        self.event_time = as_utc(self.event_time)
        self.received_at = as_utc(self.received_at)
        self.quality_flags = tuple(
            dict.fromkeys(str(flag) for flag in self.quality_flags)
        )
        # 关键设计：一个事件必须且只能携带一种 typed payload，并与 event_type 对应。
        # 解决的问题：防止同一消息被解释成多种事件，或在因子计算时进入错误分支。
        payloads = [self.trade, self.quote, self.bar, self.news]
        if sum(payload is not None for payload in payloads) != 1:
            raise ValueError("MarketEvent requires exactly one typed payload")
        if getattr(self, self.event_type.value) is None:
            raise ValueError(
                f"event_type={self.event_type.value} does not match payload"
            )

    @classmethod
    def create(
        cls,
        *,
        source: str,
        feed: str,
        event_type: EventType | str,
        ticker: str,
        event_time: datetime | str,
        received_at: datetime | str | None = None,
        event_id: str | None = None,
        quality_flags: tuple[str, ...] = (),
        run_id: str | None = None,
        dataset_id: str | None = None,
        mode: str | None = None,
        provenance: dict[str, Any] | None = None,
        **payload: Any,
    ) -> MarketEvent:
        kind = EventType(event_type)  # 把字符串统一成 EventType
        event_dt = as_utc(event_time)  # 事件发生时间
        received_dt = as_utc(received_at or datetime.now(timezone.utc))  # 系统收到时间
        typed_payload = payload.get(kind.value, payload)  # 取出对应事件类型的内容
        # 目标：上游没有稳定 ID 时仍能得到可重复的事件身份。
        # 关键设计：对来源、类型、ticker、时间和 payload 做确定性哈希；相同输入始终得到相同 ID
        # 解决的问题：数据质量门可以在 live/replay 中识别同一事件，而不是每次重放都生成新身份
        if event_id is None:
            identity = {
                "source": source,
                "feed": feed,
                "event_type": kind.value,
                "ticker": ticker.upper(),
                "event_time": event_dt.isoformat(),
                "payload": typed_payload,
            }
            raw = json.dumps(
                identity, sort_keys=True, separators=(",", ":"), default=str
            )
            event_id = hashlib.sha256(raw.encode()).hexdigest()[:32]
        kwargs = {name: None for name in ("trade", "quote", "bar", "news")}
        kwargs[kind.value] = typed_payload  # 只填充当前事件对应的一种 payload
        return cls(
            event_id=event_id,
            source=source,
            feed=feed,
            event_type=kind,
            ticker=ticker,
            event_time=event_dt,
            received_at=received_dt,
            quality_flags=quality_flags,
            run_id=run_id,
            dataset_id=dataset_id,
            mode=mode,
            provenance=provenance or {},
            **kwargs,
        )

    @property
    def payload(self) -> dict[str, Any]:
        return getattr(self, self.event_type.value) or {}

    # 目标：让线上 Kafka 消息与离线 JSONL 使用同一种 JSON 表示
    # 参考内容：[R01：Apache Kafka Design] 参考了事件流传输思想，但在本项目自行定义了序列化字段
    # 解决的问题：序列化时保留时间、质量标记和 provenance，避免 replay 丢失上下文
    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["event_type"] = self.event_type.value
        result["event_time"] = self.event_time.isoformat()
        result["received_at"] = self.received_at.isoformat()
        result["quality_flags"] = list(self.quality_flags)
        return result

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> MarketEvent:
        return cls(**value)


# 目标：把八个因子按价格、活跃度、流动性、市场背景和新闻分组
# 关键设计：CEP 可以要求不同证据组共同确认，避免把同类信号重复当作独立证据
FACTOR_GROUPS: dict[str, str] = {
    "return_surprise": "price",
    "volatility_burst": "price",
    "relative_volume": "activity",
    "spread_stress": "liquidity",
    "quote_imbalance": "liquidity",
    "signed_trade_imbalance": "liquidity",
    "market_residual": "market_context",
    "news_shock": "news",
}


# 目标：用 FactorSnapshot 连接因子引擎和 CEP
# 关键设计：同时保存因子数值、历史相对状态、数据质量、暖机状态和原始事件 ID
# 解决的问题：CEP 无需重新计算阈值，并且告警可以回查到参与计算的输入事件
@dataclass(slots=True)
class FactorSnapshot:
    ticker: str  # 快照对应的股票
    event_time: datetime  # 窗口结束时间
    cadence: str  # 窗口大小：10s、1m 或 5m
    factor_values: dict[str, float]  # 八个因子的实际数值
    factor_states: dict[str, dict[str, Any]]  # 相对于历史baseline的宏观解释
    baseline_version: str  # 生成状态时使用的 baseline 版本
    data_quality: dict[str, Any]  # 窗口内输入数据的质量摘要
    warmup_status: str  # ready 或 warming_up
    source_event_ids: list[str] = field(default_factory=list)  # 原始事件引用
    window_start: datetime | None = None  # 窗口开始时间
    input_summary: dict[str, Any] = field(default_factory=dict)
    run_id: str | None = None
    dataset_id: str | None = None
    mode: str | None = None
    provenance: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.ticker = self.ticker.upper()
        self.event_time = as_utc(self.event_time)
        if self.window_start is not None:
            self.window_start = as_utc(self.window_start)

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["event_time"] = self.event_time.isoformat()
        result["window_start"] = (
            self.window_start.isoformat() if self.window_start else None
        )
        return result

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> FactorSnapshot:
        return cls(**value)


@dataclass(slots=True)
class AtomicEvent:
    name: str
    group: str  # price、liquidity、news...
    direction: str  # up 或 down
    event_time: datetime
    factor: str
    value: float
    robust_z: float  # 因子距离历史 baseline 的分数
    source_event_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["event_time"] = self.event_time.isoformat()
        return value


@dataclass(slots=True)
class PatternMatch:
    name: str  # 六类 CEP 模式之一
    direction: str  # 模式的整体方向
    status: str  # completed、in_progress 或 merged
    started_at: datetime  # 第一条证据出现时间
    completed_at: datetime | None  # 模式完成时间，未完成时为 None
    evidence: list[str] = field(default_factory=list)  # 触发模式的因子

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["started_at"] = self.started_at.isoformat()
        value["completed_at"] = (
            self.completed_at.isoformat() if self.completed_at else None
        )
        return value


# 目标：DetectionResult 显示异常事件类型，不是机器学习的分数，具可解释性
# 关键设计：保存原子事件、模式、方向、证据、检测时间、抑制信息和去重
# 解决的问题：用户和评测程序可以解释异常报警原因，并追溯警报的开始、完成与检测时间
@dataclass(slots=True)
class DetectionResult:
    ticker: str
    event_time: datetime
    detected_at: datetime
    cadence: str
    score: float  # 为兼容旧检测器保留的负异常分数
    severity: str  # none、medium、high
    is_alert: bool  # 是否通过质量、暖机和 cooldown 检查
    direction: str | None
    atomic_events: list[AtomicEvent]
    patterns: list[PatternMatch]
    factor_evidence: dict[str, dict[str, Any]]
    source_event_ids: list[str]
    data_quality: dict[str, Any]
    explanation: str  # 面向用户的异常警报解释
    dedupe_key: str | None  # 防止重复写入db
    run_id: str | None = None
    dataset_id: str | None = None
    mode: str | None = None
    provenance: dict[str, Any] = field(default_factory=dict)

    # 转成json格式便于Kafka处理
    def to_dict(self) -> dict[str, Any]:
        return {
            "ticker": self.ticker,
            "event_time": self.event_time.isoformat(),
            "detected_at": self.detected_at.isoformat(),
            "cadence": self.cadence,
            "score": self.score,
            "severity": self.severity,
            "is_alert": self.is_alert,
            "direction": self.direction,
            "atomic_events": [event.to_dict() for event in self.atomic_events],
            "patterns": [pattern.to_dict() for pattern in self.patterns],
            "factor_evidence": self.factor_evidence,
            "source_event_ids": self.source_event_ids,
            "data_quality": self.data_quality,
            "explanation": self.explanation,
            "dedupe_key": self.dedupe_key,
            "run_id": self.run_id,
            "dataset_id": self.dataset_id,
            "mode": self.mode,
            "provenance": self.provenance,
        }

    # 从 JSON 恢复成初始 DetectionResult，保证存储或消息回读后的对象与内存中对象一致
    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> DetectionResult:
        parsed = dict(value)
        parsed["event_time"] = as_utc(parsed["event_time"])
        parsed["detected_at"] = as_utc(parsed["detected_at"])
        parsed["atomic_events"] = [
            AtomicEvent(
                **{
                    **event,
                    "event_time": as_utc(event["event_time"]),
                }
            )
            for event in parsed.get("atomic_events", [])
        ]
        parsed["patterns"] = [
            PatternMatch(
                **{
                    **pattern,
                    "started_at": as_utc(pattern["started_at"]),
                    "completed_at": (
                        as_utc(pattern["completed_at"])
                        if pattern.get("completed_at")
                        else None
                    ),
                }
            )
            for pattern in parsed.get("patterns", [])
        ]
        return cls(**parsed)
