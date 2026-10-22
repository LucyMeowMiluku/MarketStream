import ast
import json
from datetime import date, time, timedelta
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from replay.review_metrics import interval_measurements, regular_bars, rule_inputs
from tests.test_review_metrics import _session

APP = Path(__file__).resolve().parents[1] / "scripts" / "label_review_app.py"
REVIEW_MODULES = [APP, APP.parent / "prepare_review_workbench.py",
                  APP.parents[1] / "replay" / "review_metrics.py",
                  APP.parents[1] / "replay" / "review_export.py"]


def _workbench(directory: Path, prefix: str, group: str = "review") -> None:
    days = [date(2023, 8, 1) + timedelta(days=offset) for offset in range(22)]
    bars = {symbol: [] for symbol in ("AAPL", "SPY", "QQQ")}
    for day in days:
        for symbol in bars:
            bars[symbol] += _session(day, [100.0] * 5 + [101.0 if symbol == "AAPL" else 100.0])
    sessions = {symbol: regular_bars(items) for symbol, items in bars.items()}
    measurement = interval_measurements(sessions, "AAPL", days[-1], time(9, 30), time(11, 0))
    start = f"{days[-1].isoformat()}T09:30:00-04:00"
    item = {
        "display_id": f"{prefix}01", "group": group, "ticker": "AAPL",
        "candidate": {"interval_id": "hidden-candidate-id", "kind": "normal", "ticker": "AAPL",
                      "started_at": "2023-08-22T13:30:00Z", "ended_at": "2023-08-22T15:00:00Z"},
        "window": {"start": start, "end": f"{days[-1].isoformat()}T11:00:00-04:00",
                   "reference_time": f"{days[-2].isoformat()}T16:00:00-04:00"},
        "measurement": measurement, "rule_inputs": rule_inputs(measurement),
        "chart": {symbol: [[bar.start.isoformat(), bar.open, bar.high, bar.low, bar.close, bar.volume]
                           for bar in sessions[symbol][days[-1]][:90]] for symbol in sessions},
        "typical_minute_volume": [[start, 100.0]],
        "news": [{"headline": "Example headline", "source": "test", "url": "https://example.com/a",
                  "symbols": ["AAPL"], "created_at": f"{days[-1].isoformat()}T13:45:00Z",
                  "updated_at": f"{days[-1].isoformat()}T13:45:00Z"}],
    }
    directory.mkdir(parents=True)
    (directory / f"{prefix}01.json").write_text(json.dumps(item))
    (directory / "index.json").write_text(json.dumps(
        {"items": [{"display_id": f"{prefix}01", "group": group, "file": f"{prefix}01.json"}]}))


@pytest.fixture
def app(tmp_path, monkeypatch):
    _workbench(tmp_path / "review", "R")
    _workbench(tmp_path / "demo", "D")
    criteria = tmp_path / "criteria.md"
    criteria.write_text("**Status: PROPOSED — awaiting approval.**\n")
    monkeypatch.setenv("LABEL_REVIEW_WORKBENCH", str(tmp_path / "review"))
    monkeypatch.setenv("LABEL_REVIEW_DEMO_WORKBENCH", str(tmp_path / "demo"))
    monkeypatch.setenv("LABEL_REVIEW_OUTPUT", str(tmp_path / "out"))
    monkeypatch.setenv("LABEL_REVIEW_CRITERIA", str(criteria))
    return tmp_path, criteria


def test_candidates_are_locked_until_criteria_are_approved(app):
    tmp_path, criteria = app
    at = AppTest.from_file(str(APP), default_timeout=30).run()
    assert not at.exception
    assert "D01" in at.title[0].value  # demo only
    assert not [radio for radio in at.sidebar.radio if radio.label == "Mode"]
    criteria.write_text("**Status: APPROVED (2026-10-23), volume option 2**\n")
    at = AppTest.from_file(str(APP), default_timeout=30).run()
    assert "R01" in at.title[0].value
    # Blind by default: the draft's interval id is not shown.
    shown = [element.value for group in (at.title, at.caption, at.markdown, at.json, at.subheader)
             for element in group]
    assert not any("hidden-candidate-id" in str(value) for value in shown)


def test_decision_is_saved_and_exported(app):
    tmp_path, _ = app
    at = AppTest.from_file(str(APP), default_timeout=30).run()
    at.sidebar.text_input(key="reviewer").input("Test Reviewer").run()
    next(radio for radio in at.radio if radio.label == "Label").set_value("normal")
    next(box for box in at.checkbox if box.label == "I checked the macro calendars").check()
    next(area for area in at.text_area if area.label.startswith("Reasoning")).input("quiet on all rules")
    next(button for button in at.button if button.label == "Save decision").click().run()
    assert not at.exception
    saved = json.loads((tmp_path / "out" / "demo-test-reviewer.json").read_text())
    assert saved["D01"]["decision"] == "normal"
    assert saved["D01"]["draft_revealed_before_decision"] is False
    next(button for button in at.button if button.label == "Write export files").click().run()
    assert (tmp_path / "out" / "demo-test-reviewer_review.csv").exists()


@pytest.mark.parametrize("path", REVIEW_MODULES, ids=lambda path: path.name)
def test_review_code_never_imports_detector_modules(path):
    tree = ast.parse(path.read_text())
    imported = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module}
    imported |= {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
    forbidden = ("cep", "evaluation", "storage", "processing.factor_engine", "replay.evaluator")
    assert not [name for name in imported if name.startswith(forbidden)]
