import json

import pytest

from scripts.collect_label_review_evidence import fetch, review_window


def bar(time, price):
    return {"t": time, "o": price, "h": price, "l": price, "c": price, "v": 10}


def test_review_excludes_post_boundary_minutes_and_extended_close(tmp_path, monkeypatch):
    class Client:
        def request_json(self, endpoint, params):
            if endpoint.endswith("news"):
                return {"news": []}
            if params["timeframe"] == "1Day":
                return {"bars": [bar("2024-05-02T04:00:00Z", 777)]}
            if "15:45" in params["start"]:
                return {"bars": [bar("2024-05-02T19:59:00Z", 100),
                                 bar("2024-05-02T20:00:00Z", 888)]}
            return {"bars": [bar("2024-05-03T13:30:00Z", 101),
                             bar("2024-05-03T14:59:00Z", 102),
                             bar("2024-05-03T15:00:00Z", 999)]}

    monkeypatch.setattr("scripts.collect_label_review_evidence.AlpacaHistoricalClient.from_settings",
                        lambda: Client())
    result = review_window({"interval_id": "boundary", "kind": "anomaly", "ticker": "AAPL",
                            "started_at": "2024-05-03T13:30:00Z",
                            "ended_at": "2024-05-03T15:00:00Z"}, tmp_path)
    target = result["symbols"]["AAPL"]
    assert target["prior_close"] == 100
    assert target["last_close"] == 102
    assert target["bars"] == 2
    assert len(target["missing_minutes"]) == 88
    assert target["end_vs_prior_pct"] == pytest.approx(2)
    assert target["excluded_end_or_outside_bars"] == 1
    assert json.loads((tmp_path/"summaries/boundary.json").read_text())["status"] == "complete"


def test_review_refuses_repeated_pagination_token(tmp_path):
    class Client:
        def request_json(self, endpoint, params):
            return {"bars": [], "next_page_token": "repeated"}

    with pytest.raises(ValueError, match="repeated token"):
        fetch(Client(), tmp_path, "bad", "/bars", {}, "bars")
    assert not (tmp_path/"bad.json").exists()
