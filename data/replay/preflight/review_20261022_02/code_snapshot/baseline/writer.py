"""Bounded, retrying single-writer queue for factor persistence."""

from __future__ import annotations

import queue
import threading
from dataclasses import dataclass
from time import monotonic

from baseline.repository import BaselineRepository, OffsetPosition, PersistenceUnit


@dataclass(frozen=True, slots=True)
class WriterAck:
    offsets: tuple[OffsetPosition, ...]
    revision: int


class BaselineWriter:
    def __init__(
        self,
        repository: BaselineRepository,
        epoch_id: str,
        *,
        max_queue: int = 5_000,
        batch_size: int = 100,
        flush_seconds: float = 0.25,
        logger=None,
    ) -> None:
        if max_queue < 1 or batch_size < 1 or flush_seconds <= 0:
            raise ValueError("writer queue, batch, and flush limits must be positive")
        self.repository = repository
        self.epoch_id = epoch_id
        self.batch_size = batch_size
        self.flush_seconds = flush_seconds
        self.log = logger
        self._capacity = max_queue
        self.queue: queue.Queue[PersistenceUnit] = queue.Queue(maxsize=max_queue)
        self.acks: queue.SimpleQueue[WriterAck] = queue.SimpleQueue()
        self._depth_lock = threading.Lock()
        self._inflight = 0
        self._stop = threading.Event()
        self._idle = threading.Event()
        self._idle.set()
        self._thread = threading.Thread(
            target=self._run, name="baseline-db-writer", daemon=True
        )
        self._degraded = False
        self._retry_count = 0
        self._last_error: str | None = None

    @property
    def depth(self) -> int:
        with self._depth_lock:
            return self.queue.qsize() + self._inflight

    @property
    def capacity(self) -> int:
        return self._capacity

    @property
    def degraded(self) -> bool:
        return self._degraded

    @property
    def retry_count(self) -> int:
        return self._retry_count

    @property
    def last_error(self) -> str | None:
        return self._last_error

    def start(self) -> None:
        self._thread.start()

    def submit_nowait(self, unit: PersistenceUnit) -> bool:
        with self._depth_lock:
            if self.queue.qsize() + self._inflight >= self._capacity:
                return False
            try:
                self.queue.put_nowait(unit)
            except queue.Full:
                return False
        self._idle.clear()
        return True

    def poll_acks(self) -> list[WriterAck]:
        values = []
        while True:
            try:
                values.append(self.acks.get_nowait())
            except queue.Empty:
                return values

    def wait_idle(self, timeout: float) -> bool:
        return self._idle.wait(timeout)

    def stop(self, timeout: float) -> bool:
        self._stop.set()
        self._thread.join(timeout)
        return not self._thread.is_alive()

    def _run(self) -> None:
        retry_seconds = 1.0
        while not self._stop.is_set() or not self.queue.empty():
            batch = self._take_batch()
            if not batch:
                self._idle.set()
                continue
            while True:
                try:
                    revision = self.repository.persist_units(self.epoch_id, batch)
                    offsets = tuple(
                        position for unit in batch for position in unit.offsets
                    )
                    self.acks.put(WriterAck(offsets, revision))
                    for _ in batch:
                        self.queue.task_done()
                    with self._depth_lock:
                        self._inflight -= len(batch)
                    if self._degraded:
                        self._emit(
                            "info",
                            "baseline_persistence_recovered",
                            queue_depth=self.depth,
                            revision=revision,
                            retry_count=self._retry_count,
                        )
                    self._degraded = False
                    self._retry_count = 0
                    retry_seconds = 1.0
                    if self.depth == 0:
                        self._idle.set()
                    break
                except Exception as exc:
                    self._degraded = True
                    self._retry_count += 1
                    self._last_error = str(exc)
                    self._emit(
                        "error",
                        "baseline_persistence_degraded",
                        error=self._last_error,
                        queue_depth=self.depth,
                        retry_count=self._retry_count,
                        retry_seconds=retry_seconds,
                    )
                    if self._stop.is_set():
                        return
                    self._stop.wait(retry_seconds)
                    retry_seconds = min(retry_seconds * 2, 30.0)

    def _take_batch(self) -> list[PersistenceUnit]:
        try:
            first = self.queue.get(timeout=0.1)
        except queue.Empty:
            return []
        batch = [first]
        with self._depth_lock:
            self._inflight += 1
        deadline = monotonic() + self.flush_seconds
        while len(batch) < self.batch_size:
            remaining = deadline - monotonic()
            if remaining <= 0:
                break
            try:
                batch.append(self.queue.get(timeout=remaining))
                with self._depth_lock:
                    self._inflight += 1
            except queue.Empty:
                break
        return batch

    def _emit(self, level: str, event: str, **values) -> None:
        if self.log is not None:
            getattr(self.log, level)(event, **values)
