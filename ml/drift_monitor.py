from datetime import datetime, timezone

from river.drift import ADWIN

from config.logging_config import get_logger
from storage.db import get_session
from storage.models import DriftEvent

log = get_logger("drift_monitor")

MONITORED_FEATURES = ["price_change_rate", "total_volume", "avg_sentiment", "sentiment_shift"]


class DriftMonitor:
    """Monitors feature distributions for concept drift using ADWIN."""

    def __init__(self, delta: float = 0.002):
        self._delta = delta
        self._detectors: dict[str, dict[str, ADWIN]] = {}

    def _get_detectors(self, ticker: str) -> dict[str, ADWIN]:
        if ticker not in self._detectors:
            self._detectors[ticker] = {
                feat: ADWIN(delta=self._delta) for feat in MONITORED_FEATURES
            }
        return self._detectors[ticker]

    def update(self, features: dict) -> list[str]:
        """Feed new observation. Returns list of features where drift was detected."""
        ticker = features.get("ticker", "_default")
        detectors = self._get_detectors(ticker)
        drifted = []

        for feat_name, detector in detectors.items():
            val = float(features.get(feat_name, 0.0))
            detector.update(val)
            if detector.drift_detected:
                drifted.append(feat_name)
                self._record_drift(ticker, feat_name)

        return drifted

    def _record_drift(self, ticker: str, feature_name: str) -> None:
        log.warning("drift_detected", ticker=ticker, feature=feature_name)
        try:
            session = get_session()
            event = DriftEvent(
                detected_at=datetime.now(timezone.utc),
                ticker=ticker,
                feature_name=feature_name,
                drift_type="adwin",
                details={"delta": self._delta},
            )
            session.add(event)
            session.commit()
            session.close()
        except Exception as e:
            log.error("drift_record_failed", error=str(e))
