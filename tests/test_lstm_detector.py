from ml.detectors.lstm_detector import LSTMDetector


def test_returns_zero_before_buffer_full():
    d = LSTMDetector(sequence_length=5, hidden_dim=16)
    features = {"ticker": "AAPL", "price_change_rate": 0.01, "total_volume": 500,
                "avg_sentiment": 0.0, "sentiment_shift": 0.0}
    for _ in range(4):
        d.update(features)
    assert d.score(features) == 0.0


def test_scores_after_buffer_full():
    d = LSTMDetector(sequence_length=5, hidden_dim=16)
    features = {"ticker": "AAPL", "price_change_rate": 0.01, "total_volume": 500,
                "avg_sentiment": 0.0, "sentiment_shift": 0.0}
    for _ in range(5):
        d.update(features)
    score = d.score(features)
    assert score <= 0.0


def test_per_ticker_buffers():
    d = LSTMDetector(sequence_length=3, hidden_dim=8)
    for _ in range(3):
        d.update({"ticker": "AAPL", "price_change_rate": 0.01, "total_volume": 500,
                  "avg_sentiment": 0.0, "sentiment_shift": 0.0})
        d.update({"ticker": "TSLA", "price_change_rate": 0.02, "total_volume": 1000,
                  "avg_sentiment": 0.1, "sentiment_shift": 0.05})
    assert len(d._buffers["AAPL"]) == 3
    assert len(d._buffers["TSLA"]) == 3
