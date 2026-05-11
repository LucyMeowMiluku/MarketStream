from unittest.mock import MagicMock

from ml.online_scorer import build_anomaly_reason, get_recent_sentiment


class TestBuildAnomalyReason:
    def test_large_price_move(self):
        features = {"price_change_rate": 0.05, "total_volume": 500_000, "sentiment_shift": 0.1}
        result = build_anomaly_reason(features, -0.5)
        assert "large price move" in result
        assert "high volume" not in result

    def test_high_volume(self):
        features = {"price_change_rate": 0.001, "total_volume": 5_000_000, "sentiment_shift": 0.0}
        result = build_anomaly_reason(features, -0.3)
        assert "high volume" in result
        assert "large price move" not in result

    def test_sentiment_shift(self):
        features = {"price_change_rate": 0.0, "total_volume": 100, "sentiment_shift": 0.5}
        result = build_anomaly_reason(features, -0.2)
        assert "sentiment shift" in result

    def test_multiple_reasons(self):
        features = {"price_change_rate": 0.1, "total_volume": 2_000_000, "sentiment_shift": 0.8}
        result = build_anomaly_reason(features, -0.6)
        assert "large price move" in result
        assert "high volume" in result
        assert "sentiment shift" in result

    def test_no_specific_reason_uses_score(self):
        features = {"price_change_rate": 0.001, "total_volume": 100, "sentiment_shift": 0.01}
        result = build_anomaly_reason(features, -0.15)
        assert "anomaly score=" in result

    def test_missing_features_use_defaults(self):
        result = build_anomaly_reason({}, -0.1)
        assert "anomaly score=" in result


class TestGetRecentSentiment:
    def _make_mock_session(self, scores: list[float]):
        rows = []
        for s in scores:
            mock = MagicMock()
            mock.sentiment_score = s
            rows.append(mock)

        session = MagicMock()
        query = session.query.return_value
        query.filter.return_value = query
        query.order_by.return_value = query
        query.limit.return_value = query
        query.all.return_value = rows
        return session

    def test_no_rows_returns_zeros(self):
        session = self._make_mock_session([])
        avg, shift, count = get_recent_sentiment(session, "AAPL")
        assert avg == 0.0
        assert shift == 0.0
        assert count == 0

    def test_fewer_than_split_index(self):
        session = self._make_mock_session([0.5, 0.3, 0.4])
        avg, shift, count = get_recent_sentiment(session, "AAPL")
        assert count == 3
        assert avg == round(sum([0.5, 0.3, 0.4]) / 3, 4)
        assert shift == 0.0

    def test_with_older_data(self):
        scores = [0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5,
                  0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        session = self._make_mock_session(scores)
        avg, shift, count = get_recent_sentiment(session, "AAPL")
        assert avg == 0.5
        assert shift == 0.5
        assert count == 10

    def test_negative_sentiment(self):
        scores = [-0.8, -0.6, -0.7] + [0.2, 0.3, 0.1] * 3 + [0.0] * 2
        session = self._make_mock_session(scores)
        avg, shift, count = get_recent_sentiment(session, "TSLA")
        assert count == 10
        assert avg < 0
