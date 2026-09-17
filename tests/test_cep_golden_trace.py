import json
from pathlib import Path

from cep.cep_detector import CEPDetector
from evaluation.synthetic_scenarios import PATTERNS, generate_scenario


GOLDEN = Path(__file__).parent / "fixtures" / "cep_golden_trace.json"


def _project(result):
    return {
        "score": result.score,
        "is_alert": result.is_alert,
        "direction": result.direction,
        "dedupe_key": result.dedupe_key,
        "patterns": [
            {
                "name": item.name,
                "direction": item.direction,
                "status": item.status,
                "started_at": item.started_at.isoformat(),
                "completed_at": item.completed_at.isoformat() if item.completed_at else None,
                "evidence": item.evidence,
            }
            for item in result.patterns
        ],
    }


def test_six_pattern_golden_trace_is_stable():
    expected = json.loads(GOLDEN.read_text())
    actual = {}
    for name in PATTERNS:
        scenario = generate_scenario(name, seed=1, intensity="medium")
        detector = CEPDetector(cooldown_seconds=0)
        actual[name] = [
            _project(detector.process(snapshot, detected_at=snapshot.event_time))
            for snapshot in scenario.snapshots
        ]
    assert actual == expected
