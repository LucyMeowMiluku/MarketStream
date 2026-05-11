import numpy as np
import pytest

from ml.detector import AnomalyDetector, FEATURE_COLUMNS


@pytest.fixture
def trained_detector(tmp_path):
    rng = np.random.RandomState(42)
    normal_data = rng.normal(0, 1, (200, len(FEATURE_COLUMNS)))
    detector = AnomalyDetector()
    detector.fit(normal_data)
    return detector


class TestAnomalyDetector:
    def test_normal_data_not_anomaly(self, trained_detector):
        features = {col: 0.1 for col in FEATURE_COLUMNS}
        score, is_anomaly = trained_detector.predict(features)
        assert not is_anomaly
        assert score > 0

    def test_extreme_data_is_anomaly(self, trained_detector):
        features = {col: 100.0 for col in FEATURE_COLUMNS}
        score, is_anomaly = trained_detector.predict(features)
        assert is_anomaly
        assert score < 0

    def test_save_load(self, trained_detector, tmp_path):
        path = str(tmp_path / "model.joblib")
        trained_detector.save(path)
        loaded = AnomalyDetector(model_path=path)
        features = {col: 0.1 for col in FEATURE_COLUMNS}
        s1, a1 = trained_detector.predict(features)
        s2, a2 = loaded.predict(features)
        assert s1 == s2
        assert a1 == a2
