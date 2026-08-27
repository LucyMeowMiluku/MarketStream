# =========================================================================
# function：验证并冻结的真实历史事件标签注册表
# 贡献：标签 schema、12+12 约束、外部证据要求、摘要和冻结工作流
# 参考：防止评测偏差的原则来自时序异常检测评测研究   [R08][R09]
# 关键设计：检测器输出不能参与标签审批；冻结后以hash绑定数据的采集和评测
# 问题：候选事件可能被直接当作 ground truth，标签还可能在查看结果后被修改
# 解决方法：要求检查，全部通过后生成冻结文件，并用摘要检测后续变化
# ==========================================================================
"""校验标签是否合格 & 将检测通过的冻结为ground truth
标签标明了每个时间段哪只股票异常,哪只正常,最后成一注册表。
benchmark中有12异常+12正常。

Validation and freezing for independently reviewed replay labels."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from replay.models import ReviewedInterval, canonical_sha256


@dataclass(slots=True)
class LabelRegistry:
    # 目标：记录“什么是真实异常”，不根据 detector的输出生成标签
    # 关键设计：同时保存数据集身份、来源覆盖、审阅区间、审批信息和冻结状态
    schema_version: str  # 标签文件结构版本
    dataset_id: str  # 必须与采集 manifest 对应
    data_kind: str  # 正式benchmark必须为real_historical
    provider: str  # v1固定为 alpaca
    feed: str  # v1 固定为 iex
    timezone: str  # 人工审阅区间采用的时区
    frozen: bool  # 是否已经成为不可修改的正式标签
    intervals: list[ReviewedInterval]  # anomaly和 normal 审阅区间
    frozen_at: datetime | None = None  # 正式冻结时间
    notes: str = ""

    def validate(
        self,
        *,
        require_frozen: bool = False,
        expected_anomalies: int | None = None,
        expected_normals: int | None = None,
    ) -> None:
        # 目标：只有来源明确、证据和审批完整的标签才能进入正式评测。
        # 关键设计：依次检查 schema、真实来源、唯一性、样本组成、外部证据和审批状态。
        if self.schema_version != "marketstream-reviewed-labels-v1":
            # 防止用旧结构或其他项目的标签进入当前评估器。
            raise ValueError("unsupported label schema_version")
        if self.data_kind != "real_historical":
            # synthetic/soak 标签不能冒充真实市场 ground truth。
            raise ValueError(
                "reviewed benchmark labels must use data_kind=real_historical"
            )
        if self.provider != "alpaca" or self.feed != "iex":
            raise ValueError("v1 reviewed benchmark must be Alpaca IEX")
        ids = [item.interval_id for item in self.intervals]
        if len(ids) != len(set(ids)):
            # 区间 ID 重复会导致 manifest 映射和匹配结果相互覆盖。
            raise ValueError("interval_id values must be unique")
        event_ids = [item.event_id for item in self.intervals if item.event_id]
        if len(event_ids) != len(set(event_ids)):
            raise ValueError("event_id values must be unique")
        anomalies = sum(item.kind == "anomaly" for item in self.intervals)
        normals = sum(item.kind == "normal" for item in self.intervals)
        if expected_anomalies is not None and anomalies != expected_anomalies:
            raise ValueError(
                f"expected {expected_anomalies} anomaly intervals, found {anomalies}"
            )
        if expected_normals is not None and normals != expected_normals:
            raise ValueError(
                f"expected {expected_normals} normal intervals, found {normals}"
            )
        if expected_anomalies == 12 and expected_normals == 12:
            # 正式 12+12 benchmark 必须覆盖全部五个跟踪标的
            required_tickers = {"AAPL", "TSLA", "NVDA", "QQQ", "SPY"}
            present_tickers = {item.ticker for item in self.intervals}
            missing = sorted(required_tickers.difference(present_tickers))
            if missing:
                raise ValueError(
                    "12+12 benchmark must cover all tracked tickers; missing: "
                    + ", ".join(missing)
                )
        for item in self.intervals:
            if item.kind == "anomaly" and not item.evidence_urls:
                # 异常标签必须能够通过外部来源独立复核
                raise ValueError(
                    f"interval {item.interval_id}: anomaly requires evidence_urls"
                )
            if any(not url.startswith("https://") for url in item.evidence_urls):
                raise ValueError(
                    f"interval {item.interval_id}: evidence URLs must use https"
                )
        # 参考：[R08：TSB-AD；R09：Towards Unbiased Evaluation] 标签质量会影响test评价的可信度
        # 问题：部分注册表不能被误当成最终 ground truth
        # 解决方法：frozen 注册表必须有冻结时间，且所有区间都已经独立批准
        if require_frozen or self.frozen:
            if not self.frozen or self.frozen_at is None:
                raise ValueError("label registry is not frozen")
            unapproved = [
                item.interval_id for item in self.intervals if not item.approved
            ]
            if unapproved:
                raise ValueError(
                    "frozen label registry contains unapproved intervals: "
                    + ", ".join(unapproved)
                )

    @property
    def digest(self) -> str:
        # 目标：发现标签在数据采集或评测前后是否发生变化
        # 关键设计：对规范化注册表计算摘要，并由 dataset manifest 保存和核对该摘要
        return canonical_sha256(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "dataset_id": self.dataset_id,
            "data_kind": self.data_kind,
            "provider": self.provider,
            "feed": self.feed,
            "timezone": self.timezone,
            "frozen": self.frozen,
            "frozen_at": self.frozen_at.isoformat() if self.frozen_at else None,
            "notes": self.notes,
            "intervals": [item.to_dict() for item in self.intervals],
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> LabelRegistry:
        frozen_at = value.get("frozen_at")
        return cls(
            schema_version=value["schema_version"],
            dataset_id=value["dataset_id"],
            data_kind=value["data_kind"],
            provider=value["provider"],
            feed=value["feed"],
            timezone=value.get("timezone", "America/New_York"),
            frozen=bool(value.get("frozen", False)),
            frozen_at=datetime.fromisoformat(frozen_at) if frozen_at else None,
            notes=str(value.get("notes", "")),
            intervals=[ReviewedInterval.from_dict(item) for item in value["intervals"]],
        )


def load_label_registry(path: Path) -> LabelRegistry:
    registry = LabelRegistry.from_dict(json.loads(path.read_text()))
    registry.validate()
    return registry


def freeze_registry(source: Path, output: Path) -> LabelRegistry:
    # 解决的问题：直接覆盖草稿会丢失审阅过程，也无法证明冻结前后的内容
    # 解决方法：只有全部 approved 才生成新的冻结文件，原草稿保持不变
    registry = load_label_registry(source)
    unapproved = [item.interval_id for item in registry.intervals if not item.approved]
    if unapproved:
        # 任何未审批区间存在时都不能生成 frozen ground truth。
        raise ValueError(
            "cannot freeze until every interval is independently approved: "
            + ", ".join(unapproved)
        )
    registry.frozen = True  # 从草稿状态切换为正式标签
    registry.frozen_at = datetime.now(timezone.utc)  # 使用 UTC 记录冻结时刻
    registry.validate(require_frozen=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(registry.to_dict(), indent=2) + "\n")
    return registry


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate or freeze reviewed replay labels"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate = subparsers.add_parser("validate")
    validate.add_argument("path", type=Path)
    validate.add_argument("--require-frozen", action="store_true")
    validate.add_argument("--expected-anomalies", type=int, default=12)
    validate.add_argument("--expected-normals", type=int, default=12)
    freeze = subparsers.add_parser("freeze")
    freeze.add_argument("source", type=Path)
    freeze.add_argument("output", type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.command == "validate":
        registry = load_label_registry(args.path)
        registry.validate(
            require_frozen=args.require_frozen,
            expected_anomalies=args.expected_anomalies,
            expected_normals=args.expected_normals,
        )
        print(
            json.dumps({"status": "valid", "labels_sha256": registry.digest}, indent=2)
        )
    else:
        registry = freeze_registry(args.source, args.output)
        print(
            json.dumps({"status": "frozen", "labels_sha256": registry.digest}, indent=2)
        )


if __name__ == "__main__":
    main()
