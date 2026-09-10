from datetime import datetime, timedelta, timezone

from cep.cep_detector import CEPDetector
from ml.sequence_anomalies import PATTERNS, generate_scenario
from processing.data_quality import EventQualityGate
from processing.event_models import MarketEvent
from processing.factor_engine import LightweightFactorEngine


NOW = datetime(2025, 1, 6, 15, 0, tzinfo=timezone.utc)


def _trade(event_id: str, when: datetime, price: float) -> MarketEvent:
    return MarketEvent.create(
        event_id=event_id,
        source="test",
        feed="iex",
        event_type="trade",
        ticker="AAPL",
        event_time=when,
        received_at=when,
        trade={"price": price, "size": 10, "side": "buy"},
    )


def test_live_and_replay_events_produce_identical_factor_snapshots():
    live_gate = EventQualityGate()
    replay_gate = EventQualityGate()
    live_engine = LightweightFactorEngine(cadences=(10,), min_history_days=1)
    replay_engine = LightweightFactorEngine(cadences=(10,), min_history_days=1)
    events = [_trade("one", NOW, 100), _trade("two", NOW + timedelta(seconds=10), 101)]
    live = []
    replay = []
    for event in events:
        live.extend(live_engine.process(live_gate.assess(event, mode="live", now=event.received_at)))
        wire_copy = MarketEvent.from_dict(event.to_dict())
        replay.extend(
            replay_engine.process(
                replay_gate.assess(wire_copy, mode="replay", now=wire_copy.received_at)
            )
        )
    assert [snapshot.to_dict() for snapshot in live] == [snapshot.to_dict() for snapshot in replay]


def test_replay_of_same_snapshots_produces_identical_cep_decisions():
    for pattern in PATTERNS:
        scenario = generate_scenario(pattern, seed=10, intensity="medium")
        live_detector = CEPDetector(cooldown_seconds=0)
        replay_detector = CEPDetector(cooldown_seconds=0)
        live = [
            live_detector.process(snapshot, detected_at=snapshot.event_time).to_dict()
            for snapshot in scenario.snapshots
        ]
        replay = [
            replay_detector.process(snapshot, detected_at=snapshot.event_time).to_dict()
            for snapshot in scenario.snapshots
        ]
        assert live == replay
