"""Kafka runner for the durable, source-independent factor engine."""

from __future__ import annotations

import json
import signal
import time
from collections import deque
from dataclasses import dataclass, field, replace
from datetime import datetime, time as wall_time, timedelta, timezone

from confluent_kafka import Consumer, Producer, TopicPartition
from sqlalchemy.exc import SQLAlchemyError

from baseline.checkpoints import CheckpointManager
from baseline.contracts import StateUpdateBatch
from baseline.repository import BaselineRepository, OffsetPosition, PersistenceUnit
from baseline.startup import StartupConfiguration, coordinate_startup
from baseline.writer import BaselineWriter
from config.logging_config import get_logger
from config.settings import settings
from processing.data_quality import EventQualityGate
from processing.event_models import FactorSnapshot, MarketEvent
from processing.factor_state import NY

log = get_logger("factor_stream")
running = True


def shutdown(sig, frame) -> None:
    del frame
    global running
    log.info("shutting_down", signal=sig)
    running = False


signal.signal(signal.SIGINT, shutdown)
signal.signal(signal.SIGTERM, shutdown)


def _message_mode(headers: list[tuple[str, bytes | None]] | None) -> str:
    for name, value in headers or []:
        if name == "marketstream-mode" and value:
            return value.decode()
    return "live"


@dataclass(slots=True)
class DeliveryState:
    unit: PersistenceUnit
    remaining: int
    failed: deque[FactorSnapshot] = field(default_factory=deque)
    submitted: bool = False


def _commit_acks(consumer: Consumer, writer: BaselineWriter) -> None:
    highest: dict[tuple[str, int], int] = {}
    for ack in writer.poll_acks():
        for offset in ack.offsets:
            key = (offset.topic, offset.partition)
            highest[key] = max(highest.get(key, -1), offset.next_offset)
    if highest:
        consumer.commit(
            offsets=[
                TopicPartition(topic, partition, next_offset)
                for (topic, partition), next_offset in highest.items()
            ],
            asynchronous=False,
        )


def _coordinate_with_db_retry(config: StartupConfiguration):
    delay = 1.0
    while running:
        try:
            return coordinate_startup(config)
        except SQLAlchemyError as exc:
            log.error(
                "baseline_startup_db_unavailable",
                error=str(exc),
                retry_seconds=delay,
            )
            time.sleep(delay)
            delay = min(delay * 2, 30.0)
    raise RuntimeError("shutdown requested before baseline startup completed")


def _assignment_callback(
    restored_offsets: tuple[OffsetPosition, ...],
    *,
    verify_consumer_offsets: bool,
    allow_consumer_offset_replay: bool,
):
    positions = {
        (item.topic, item.partition): item.next_offset for item in restored_offsets
    }

    def on_assign(consumer: Consumer, partitions: list[TopicPartition]) -> None:
        if verify_consumer_offsets:
            committed = consumer.committed(partitions, timeout=10.0)
            for partition in committed:
                broker_offset = partition.offset
                if broker_offset < 0:
                    continue
                durable_offset = positions.get(
                    (partition.topic, partition.partition)
                )
                if durable_offset is None:
                    raise RuntimeError(
                        "Kafka has a consumer offset but the selected baseline "
                        f"epoch has none for {partition.topic}[{partition.partition}]: "
                        f"kafka={broker_offset}, db={durable_offset}"
                    )
                if broker_offset > durable_offset:
                    if not allow_consumer_offset_replay:
                        raise RuntimeError(
                            "Kafka consumer offset is ahead of the selected baseline "
                            f"epoch for {partition.topic}[{partition.partition}]: "
                            f"kafka={broker_offset}, db={durable_offset}"
                        )
                    log.warning(
                        "baseline_checkpoint_kafka_replay_required",
                        topic=partition.topic,
                        partition=partition.partition,
                        kafka_offset=broker_offset,
                        restored_offset=durable_offset,
                    )
        for partition in partitions:
            restored = positions.get((partition.topic, partition.partition))
            if restored is not None:
                partition.offset = restored
        consumer.assign(partitions)

    return on_assign


def _checkpoint_due(last_date) -> bool:
    local = datetime.now(timezone.utc).astimezone(NY)
    return local.time() >= wall_time(16, 5) and last_date != local.date()


def main() -> None:
    config = StartupConfiguration.from_settings()
    context = _coordinate_with_db_retry(config)
    repository = BaselineRepository()
    checkpoint_manager = CheckpointManager(
        config.checkpoint_dir, retention=config.checkpoint_retention
    )
    writer = BaselineWriter(
        repository,
        context.epoch_id,
        max_queue=settings.factor_persistence_queue_max,
        batch_size=settings.factor_persistence_batch_size,
        flush_seconds=settings.factor_persistence_flush_ms / 1_000,
        logger=log,
    )
    writer.start()
    consumer = Consumer(
        {
            "bootstrap.servers": settings.kafka_bootstrap_servers,
            "group.id": settings.factor_consumer_group,
            "auto.offset.reset": "earliest",
            "enable.auto.commit": False,
        }
    )
    consumer.subscribe(
        [settings.raw_market_events_topic],
        on_assign=_assignment_callback(
            context.offsets,
            verify_consumer_offsets=context.verify_consumer_offsets,
            allow_consumer_offset_replay=context.allow_consumer_offset_replay,
        ),
    )
    producer = Producer({"bootstrap.servers": settings.kafka_bootstrap_servers})
    quality = EventQualityGate(
        stale_after=timedelta(seconds=settings.factor_stale_after_seconds),
        gap_after=timedelta(seconds=settings.factor_gap_after_seconds),
    )
    engine = context.engine
    delivery_states: list[DeliveryState] = []
    ready_units: deque[PersistenceUnit] = deque()
    paused = False
    last_checkpoint_date = None
    log.info(
        "baseline_startup_complete",
        mode=context.mode.value,
        epoch_id=context.epoch_id,
        restored_from_checkpoint=context.restored_from_checkpoint,
        baseline_cells=engine.state_size["baselines"],
        restored_offsets=len(context.offsets),
    )

    def send_snapshot(snapshot: FactorSnapshot, state: DeliveryState) -> bool:
        def delivered(error, _message) -> None:
            if error is not None:
                state.failed.append(snapshot)
                log.error("factor_snapshot_delivery_failed", error=str(error))
            else:
                state.remaining -= 1

        try:
            producer.produce(
                settings.factor_snapshots_topic,
                key=snapshot.ticker.encode(),
                value=json.dumps(snapshot.to_dict()).encode(),
                on_delivery=delivered,
            )
            return True
        except BufferError:
            state.failed.append(snapshot)
            return False

    try:
        while running:
            producer.poll(0)
            for state in delivery_states:
                while state.failed:
                    if not send_snapshot(state.failed.popleft(), state):
                        break
            # Preserve source order: a later Kafka message may not advance the
            # durable checkpoint while an earlier delivery is still pending.
            while delivery_states and delivery_states[0].remaining == 0:
                state = delivery_states.pop(0)
                ready_units.append(state.unit)
                state.submitted = True

            while ready_units:
                if not writer.submit_nowait(ready_units[0]):
                    break
                ready_units.popleft()
            _commit_acks(consumer, writer)

            saturated = bool(ready_units) or (
                writer.depth >= writer.capacity
                or len(delivery_states) + writer.depth >= writer.capacity
            )
            if saturated and not paused:
                assignments = consumer.assignment()
                if assignments:
                    consumer.pause(assignments)
                paused = True
                log.warning("factor_consumer_paused", queue_depth=writer.depth)
            elif (
                paused
                and not ready_units
                and len(delivery_states) + writer.depth <= writer.capacity // 2
            ):
                assignments = consumer.assignment()
                if assignments:
                    consumer.resume(assignments)
                paused = False
                log.info("factor_consumer_resumed", queue_depth=writer.depth)

            if (
                _checkpoint_due(last_checkpoint_date)
                and not delivery_states
                and not ready_units
                and writer.wait_idle(0)
            ):
                assignments = consumer.assignment()
                if assignments and not paused:
                    consumer.pause(assignments)
                try:
                    path = checkpoint_manager.create(context.epoch_id)
                    last_checkpoint_date = datetime.now(timezone.utc).astimezone(NY).date()
                    log.info("baseline_checkpoint_committed", path=str(path))
                except Exception as exc:
                    log.error("baseline_checkpoint_failed", error=str(exc))
                finally:
                    if assignments and not paused:
                        consumer.resume(assignments)

            message = consumer.poll(0.25)
            if message is None:
                continue
            if message.error():
                log.error("consumer_error", error=str(message.error()))
                continue
            try:
                transport_mode = _message_mode(message.headers())
                event = MarketEvent.from_dict(json.loads(message.value().decode()))
                event = replace(event, mode=event.mode or transport_mode)
                if transport_mode != "live" or event.mode != "live":
                    log.warning(
                        "non_live_event_skipped", event_id=event.event_id, mode=event.mode
                    )
                    delivery_states.append(
                        DeliveryState(
                            unit=PersistenceUnit(
                                None,
                                [],
                                StateUpdateBatch(),
                                [
                                    OffsetPosition(
                                        settings.factor_consumer_group,
                                        message.topic(),
                                        message.partition(),
                                        message.offset() + 1,
                                    )
                                ],
                            ),
                            remaining=0,
                        )
                    )
                    continue
                if event.event_time < context.activation_cutoff:
                    log.warning(
                        "pre_epoch_event_skipped",
                        event_id=event.event_id,
                        event_time=event.event_time.isoformat(),
                        activation_cutoff=context.activation_cutoff.isoformat(),
                    )
                    delivery_states.append(
                        DeliveryState(
                            unit=PersistenceUnit(
                                None,
                                [],
                                StateUpdateBatch(),
                                [
                                    OffsetPosition(
                                        settings.factor_consumer_group,
                                        message.topic(),
                                        message.partition(),
                                        message.offset() + 1,
                                    )
                                ],
                            ),
                            remaining=0,
                        )
                    )
                    continue
                event = quality.assess(event, mode="live")
                snapshots = engine.process(event)
                for snapshot in snapshots:
                    snapshot.data_quality["mode"] = "live"
                unit = PersistenceUnit(
                    event=event,
                    snapshots=snapshots,
                    updates=engine.drain_state_updates(),
                    offsets=[
                        OffsetPosition(
                            consumer_group=settings.factor_consumer_group,
                            topic=message.topic(),
                            partition=message.partition(),
                            next_offset=message.offset() + 1,
                        )
                    ],
                )
                state = DeliveryState(unit=unit, remaining=len(snapshots))
                delivery_states.append(state)
                if snapshots:
                    for snapshot in snapshots:
                        send_snapshot(snapshot, state)
            except Exception as exc:
                log.error("factor_processing_failed", error=str(exc))
                raise
    finally:
        producer.flush(settings.factor_persistence_shutdown_seconds)
        # Only release the contiguous delivered prefix. A later successful
        # delivery must never allow its DB/Kafka offset to overtake an earlier
        # failed snapshot during shutdown.
        while delivery_states and delivery_states[0].remaining == 0:
            state = delivery_states.pop(0)
            ready_units.append(state.unit)
            state.submitted = True
        deadline = time.monotonic() + settings.factor_persistence_shutdown_seconds
        while ready_units and time.monotonic() < deadline:
            if writer.submit_nowait(ready_units[0]):
                ready_units.popleft()
            else:
                time.sleep(0.05)
        idle = writer.wait_idle(max(0.0, deadline - time.monotonic()))
        _commit_acks(consumer, writer)
        if idle and not ready_units and last_checkpoint_date is None:
            try:
                path = checkpoint_manager.create(context.epoch_id)
                log.info("baseline_shutdown_checkpoint_committed", path=str(path))
            except Exception as exc:
                log.error("baseline_shutdown_checkpoint_failed", error=str(exc))
        writer.stop(max(0.0, deadline - time.monotonic()))
        consumer.close()
        log.info("stopped", state=engine.state_size, queue_depth=writer.depth)


if __name__ == "__main__":
    main()
