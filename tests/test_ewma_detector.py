from ml.detectors.ewma_detector import EWMADetector


def test_cold_start_returns_zero():
    d = EWMADetector(span=20)
    score = d.score({"ticker": "AAPL", "price_change_rate": 0.01, "total_volume": 1000})
    assert score == 0.0


def test_normal_then_extreme():
    d = EWMADetector(span=10)
    normal = {"ticker": "AAPL", "price_change_rate": 0.001, "total_volume": 500,
              "avg_sentiment": 0.0, "sentiment_shift": 0.0}
    for _ in range(50):
        d.update(normal)

    normal_score = d.score(normal)

    extreme = {**normal, "price_change_rate": 0.5, "total_volume": 100_000}
    extreme_score = d.score(extreme)

    assert extreme_score < normal_score


def test_update_changes_stats():
    d = EWMADetector(span=5)
    features = {"ticker": "TSLA", "price_change_rate": 0.01, "total_volume": 100,
                "avg_sentiment": 0.1, "sentiment_shift": 0.0}
    d.update(features)
    assert "TSLA" in d._stats
    assert "price_change_rate" in d._stats["TSLA"]
