from unittest.mock import MagicMock

from producers.news_producer import score_sentiment, fetch_news, _mark_seen, seen_titles


class TestScoreSentiment:
    def _make_mock_model(self, label: str, score: float):
        model = MagicMock()
        model.return_value = [{"label": label, "score": score}]
        return model

    def test_positive(self):
        model = self._make_mock_model("positive", 0.9)
        label, score = score_sentiment(model, "Stock soars to record high")
        assert label == "positive"
        assert score == 0.9

    def test_negative_inverts_score(self):
        model = self._make_mock_model("negative", 0.85)
        label, score = score_sentiment(model, "Company faces lawsuit")
        assert label == "negative"
        assert score == -0.85

    def test_neutral_returns_zero(self):
        model = self._make_mock_model("neutral", 0.6)
        label, score = score_sentiment(model, "Company releases report")
        assert label == "neutral"
        assert score == 0.0


class TestMarkSeen:
    def setup_method(self):
        seen_titles.clear()

    def test_first_title_not_seen(self):
        assert _mark_seen("New headline") is False

    def test_duplicate_title_is_seen(self):
        _mark_seen("Duplicate headline")
        assert _mark_seen("Duplicate headline") is True

    def test_bounded_size(self):
        for i in range(1100):
            _mark_seen(f"headline {i}")
        assert len(seen_titles) <= 1001
        assert _mark_seen("headline 0") is False


class TestFetchNews:
    def test_empty_news(self, monkeypatch):
        mock_ticker = MagicMock()
        mock_ticker.news = []
        monkeypatch.setattr("producers.news_producer.yf.Ticker", lambda t: mock_ticker)

        seen_titles.clear()
        result = fetch_news("AAPL")
        assert result == []

    def test_deduplication(self, monkeypatch):
        mock_ticker = MagicMock()
        mock_ticker.news = [
            {"content": {"title": "Same Title", "provider": {"displayName": "Reuters"}}},
            {"content": {"title": "Same Title", "provider": {"displayName": "Bloomberg"}}},
        ]
        monkeypatch.setattr("producers.news_producer.yf.Ticker", lambda t: mock_ticker)

        seen_titles.clear()
        result = fetch_news("AAPL")
        assert len(result) == 1
        assert result[0]["title"] == "Same Title"

    def test_skips_empty_title(self, monkeypatch):
        mock_ticker = MagicMock()
        mock_ticker.news = [
            {"content": {"title": "", "provider": {"displayName": "Reuters"}}},
            {"content": {"title": "Real Title", "provider": {"displayName": "AP"}}},
        ]
        monkeypatch.setattr("producers.news_producer.yf.Ticker", lambda t: mock_ticker)

        seen_titles.clear()
        result = fetch_news("TSLA")
        assert len(result) == 1
        assert result[0]["title"] == "Real Title"
