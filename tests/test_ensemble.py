from ml.base_detector import BaseDetector
from ml.ensemble import EnsembleDetector


class MockDetector(BaseDetector):
    def __init__(self, name: str, fixed_score: float):
        self._name = name
        self._fixed_score = fixed_score
        self.updated = False

    @property
    def name(self) -> str:
        return self._name

    def score(self, features: dict) -> float:
        return self._fixed_score

    def update(self, features: dict) -> None:
        self.updated = True


def test_weighted_average():
    d1 = MockDetector("a", -0.8)
    d2 = MockDetector("b", -0.2)
    e = EnsembleDetector([d1, d2], weights=[0.6, 0.4])
    score, per = e.score({})
    expected = 0.6 * (-0.8) + 0.4 * (-0.2)
    assert abs(score - expected) < 1e-6
    assert per == {"a": -0.8, "b": -0.2}


def test_is_anomaly():
    d = MockDetector("x", -0.6)
    e = EnsembleDetector([d], threshold=-0.5)
    assert e.is_anomaly(-0.6)
    assert not e.is_anomaly(-0.1)


def test_update_propagates():
    d1 = MockDetector("a", 0.0)
    d2 = MockDetector("b", 0.0)
    e = EnsembleDetector([d1, d2])
    e.update({})
    assert d1.updated
    assert d2.updated


def test_equal_weights_by_default():
    d1 = MockDetector("a", -0.8)
    d2 = MockDetector("b", -0.2)
    e = EnsembleDetector([d1, d2])
    score, _ = e.score({})
    assert abs(score - (-0.5)) < 1e-6
