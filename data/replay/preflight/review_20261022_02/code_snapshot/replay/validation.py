"""Eligibility and integrity checks for formal reviewed replay."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterator

from processing.event_models import MarketEvent
from replay.labels import LabelRegistry, load_label_registry
from replay.models import ReplayRunConfig


def resolve_artifact(manifest_path: Path, value: str) -> Path:
    path = Path(value)
    if path.is_absolute() or path.exists():
        return path
    candidate = manifest_path.parent / path
    if candidate.exists():
        return candidate
    raise FileNotFoundError(value)


def iter_events(path: Path) -> Iterator[MarketEvent]:
    previous: tuple | None = None
    with path.open() as source:
        for line_number, line in enumerate(source, 1):
            if not line.strip():
                continue
            try:
                event = MarketEvent.from_dict(json.loads(line))
            except (TypeError, ValueError, json.JSONDecodeError) as exc:
                raise ValueError(f"invalid MarketEvent at {path}:{line_number}: {exc}") from exc
            key = (event.event_time, event.event_id)
            if previous is not None and key < previous:
                raise ValueError(f"{path}:{line_number}: events are not chronologically sorted")
            previous = key
            yield event


def validate_replay_inputs(config: ReplayRunConfig) -> tuple[dict, LabelRegistry]:
    """Reject any dataset that is not real, complete, matched and frozen."""

    manifest = json.loads(config.dataset_manifest.read_text())
    if manifest.get("schema_version") != "marketstream-real-replay-dataset-v1":
        raise ValueError("unsupported replay dataset manifest")
    if manifest.get("data_kind") != "real_historical":
        raise ValueError("real evaluation refuses non-real dataset manifests")
    if manifest.get("provider") != "alpaca" or manifest.get("feed") != "iex":
        raise ValueError("v1 real replay requires Alpaca IEX")
    if int(manifest.get("baseline_days", 0)) != config.baseline_days:
        raise ValueError("dataset baseline_days does not match ReplayRunConfig")

    registry = load_label_registry(config.labels_path)
    registry.validate(
        require_frozen=config.require_frozen_labels,
        expected_anomalies=12,
        expected_normals=12,
    )
    if manifest.get("dataset_id") != registry.dataset_id:
        raise ValueError("dataset_id differs between manifest and labels")
    if manifest.get("labels_sha256") != registry.digest:
        raise ValueError("labels changed after data collection; recollect or restore frozen labels")
    manifest_ids = {item["interval_id"] for item in manifest.get("intervals", [])}
    label_ids = {item.interval_id for item in registry.intervals}
    if manifest_ids != label_ids:
        raise ValueError("dataset and label interval sets differ")

    for item in manifest["intervals"]:
        requests = item.get("requests")
        if not requests or any(request.get("complete") is not True for request in requests):
            raise ValueError(
                f"interval {item['interval_id']}: pagination manifest is missing or incomplete"
            )
        for phase in ("baseline", "evaluation"):
            artifact = item.get(phase, {})
            if not artifact.get("path") or not artifact.get("sha256"):
                raise ValueError(
                    f"interval {item['interval_id']}: {phase} artifact metadata is incomplete"
                )
            if not isinstance(artifact.get("events"), int) or artifact["events"] <= 0:
                raise ValueError(
                    f"interval {item['interval_id']}: {phase} event count is invalid"
                )
    return manifest, registry
