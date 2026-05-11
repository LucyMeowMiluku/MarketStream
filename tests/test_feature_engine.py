from processing.feature_engine import (
    price_change_rate,
    volume_surge_ratio,
    sentiment_shift,
    compute_window_features,
)


class TestPriceChangeRate:
    def test_positive_change(self):
        assert price_change_rate(100.0, 105.0) == 0.05

    def test_negative_change(self):
        assert price_change_rate(100.0, 95.0) == -0.05

    def test_no_change(self):
        assert price_change_rate(100.0, 100.0) == 0.0

    def test_zero_first(self):
        assert price_change_rate(0.0, 100.0) == 0.0


class TestVolumeSurgeRatio:
    def test_normal(self):
        assert volume_surge_ratio(1000, 1000.0) == 1.0

    def test_surge(self):
        assert volume_surge_ratio(5000, 1000.0) == 5.0

    def test_zero_baseline(self):
        assert volume_surge_ratio(1000, 0.0) == 0.0


class TestSentimentShift:
    def test_positive_shift(self):
        assert sentiment_shift(0.5, 0.2) == 0.3

    def test_negative_shift(self):
        assert sentiment_shift(-0.3, 0.2) == -0.5


class TestComputeWindowFeatures:
    def test_basic_window(self):
        window_value = {
            "ticker": "AAPL",
            "prices": [100.0, 101.0, 102.0, 103.0, 104.0],
            "volumes": [1000, 1200, 1100, 1300, 1400],
        }
        result = compute_window_features(window_value, "AAPL", 1000, 2000)

        assert result["ticker"] == "AAPL"
        assert result["first_close"] == 100.0
        assert result["last_close"] == 104.0
        assert result["price_change_rate"] == 0.04
        assert result["total_volume"] == 6000
        assert result["tick_count"] == 5

    def test_empty_window(self):
        window_value = {"ticker": "TSLA", "prices": [], "volumes": []}
        result = compute_window_features(window_value, "TSLA", 0, 0)

        assert result["avg_close"] == 0.0
        assert result["total_volume"] == 0
