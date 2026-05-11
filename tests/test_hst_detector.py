from ml.detectors.hst_detector import HSTDetector


def test_name():
    d = HSTDetector()
    assert d.name == "hst"


def test_score_after_warmup():
    d = HSTDetector(n_trees=10, height=4, window_size=20)
    normal = {"price_change_rate": 0.001, "total_volume": 500,
              "avg_sentiment": 0.0, "sentiment_shift": 0.0}

    for _ in range(30):
        d.update(normal)

    normal_score = d.score(normal)

    outlier = {"price_change_rate": 0.5, "total_volume": 100_000,
               "avg_sentiment": -0.9, "sentiment_shift": -0.8}
    outlier_score = d.score(outlier)

    assert outlier_score < normal_score


def test_incremental_update():
    d = HSTDetector(n_trees=5, height=3, window_size=10)
    features = {"price_change_rate": 0.01, "total_volume": 100,
                "avg_sentiment": 0.1, "sentiment_shift": 0.0}
    d.update(features)
    assert d._n_seen == 1
    d.update(features)
    assert d._n_seen == 2
