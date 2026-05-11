import numpy as np
import pandas as pd

from ml.backtest_anomalies import AnomalyInjector, InjectedAnomaly


def _make_test_df(n_per_ticker=100, tickers=("AAPL", "TSLA")):
    rng = np.random.default_rng(0)
    rows = []
    for ticker in tickers:
        for i in range(n_per_ticker):
            rows.append(
                {
                    "ticker": ticker,
                    "timestamp": pd.Timestamp("2024-01-01") + pd.Timedelta(minutes=5 * i),
                    "avg_close": round(float(rng.uniform(100, 200)), 4),
                    "price_change_rate": round(float(rng.normal(0, 0.005)), 6),
                    "total_volume": float(rng.integers(10000, 100000)),
                    "avg_sentiment": round(float(rng.normal(0, 0.15)), 4),
                    "sentiment_shift": round(float(rng.normal(0, 0.08)), 4),
                }
            )
    return pd.DataFrame(rows)


class TestAnomalyInjector:
    def test_inject_returns_correct_point_count(self):
        df = _make_test_df()
        injector = AnomalyInjector(seed=42, injection_rate=0.05)
        _, gt = injector.inject(df)
        point = [a for a in gt if a.anomaly_type != "subtle_drift"]
        assert len(point) == max(1, int(200 * 0.05))

    def test_drift_block_exists(self):
        df = _make_test_df()
        injector = AnomalyInjector(seed=42, injection_rate=0.05)
        _, gt = injector.inject(df)
        drift = [a for a in gt if a.anomaly_type == "subtle_drift"]
        assert 10 <= len(drift) <= 20

    def test_drift_within_single_ticker(self):
        df = _make_test_df()
        injector = AnomalyInjector(seed=42, injection_rate=0.05)
        _, gt = injector.inject(df)
        drift = [a for a in gt if a.anomaly_type == "subtle_drift"]
        if drift:
            assert len({a.ticker for a in drift}) == 1

    def test_modified_differs_from_original(self):
        df = _make_test_df()
        injector = AnomalyInjector(seed=42, injection_rate=0.05)
        _, gt = injector.inject(df)
        for a in gt:
            assert a.original_features != a.modified_features

    def test_all_point_types_represented(self):
        df = _make_test_df(n_per_ticker=500)
        injector = AnomalyInjector(seed=42, injection_rate=0.10)
        _, gt = injector.inject(df)
        point_types = {a.anomaly_type for a in gt if a.anomaly_type != "subtle_drift"}
        assert len(point_types) >= 3

    def test_deterministic_with_seed(self):
        df = _make_test_df()
        gt1 = AnomalyInjector(seed=99, injection_rate=0.05).inject(df.copy())[1]
        gt2 = AnomalyInjector(seed=99, injection_rate=0.05).inject(df.copy())[1]
        assert [a.index for a in gt1] == [a.index for a in gt2]
        assert [a.anomaly_type for a in gt1] == [a.anomaly_type for a in gt2]


class TestMetrics:
    def _make_results(self, scores, gt_indices):
        from ml.backtest import ScoringResult

        return [
            ScoringResult(
                index=i,
                ticker="AAPL",
                timestamp="2024-01-01",
                ensemble_score=s,
                detector_scores={},
                is_anomaly=s < -0.3,
                reason="",
            )
            for i, s in enumerate(scores)
        ]

    def _make_gt(self, indices):
        return [
            InjectedAnomaly(i, "AAPL", "price_spike", 10.0, {}, {}) for i in indices
        ]

    def test_perfect_detection(self):
        from ml.backtest import compute_metrics

        scores = [0.1] * 20
        scores[5] = -0.5
        results = self._make_results(scores, [5])
        gt = self._make_gt([5])
        m = compute_metrics(results, gt, tolerance=0)
        assert m.precision == 1.0
        assert m.recall == 1.0
        assert m.f1 == 1.0

    def test_no_detection(self):
        from ml.backtest import compute_metrics

        scores = [0.1] * 20
        results = self._make_results(scores, [])
        gt = self._make_gt([5])
        m = compute_metrics(results, gt, tolerance=0)
        assert m.recall == 0.0
        assert m.false_negatives == 1

    def test_false_positive(self):
        from ml.backtest import compute_metrics

        scores = [0.1] * 20
        scores[3] = -0.5
        results = self._make_results(scores, [])
        gt = self._make_gt([10])
        m = compute_metrics(results, gt, tolerance=0)
        assert m.false_positives == 1
        assert m.true_positives == 0

    def test_tolerance_window(self):
        from ml.backtest import compute_metrics

        scores = [0.1] * 20
        scores[6] = -0.5
        results = self._make_results(scores, [])
        gt = self._make_gt([5])
        m = compute_metrics(results, gt, tolerance=2)
        assert m.true_positives == 1
        assert m.recall == 1.0


class TestTemporalSplit:
    def test_preserves_chronological_order(self):
        from ml.backtest import train_test_split_temporal

        df = _make_test_df()
        train, test = train_test_split_temporal(df, train_ratio=0.7)
        for ticker in df["ticker"].unique():
            t_train = train[train["ticker"] == ticker]["timestamp"]
            t_test = test[test["ticker"] == ticker]["timestamp"]
            if len(t_train) > 0 and len(t_test) > 0:
                assert t_train.max() <= t_test.min()

    def test_split_ratio(self):
        from ml.backtest import train_test_split_temporal

        df = _make_test_df(n_per_ticker=100)
        train, test = train_test_split_temporal(df, train_ratio=0.7)
        for ticker in df["ticker"].unique():
            n_train = len(train[train["ticker"] == ticker])
            n_test = len(test[test["ticker"] == ticker])
            assert n_train == 70
            assert n_test == 30
