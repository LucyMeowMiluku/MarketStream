"""Complex Event Processing (CEP) for streaming anomaly detection.

A lightweight, low-latency alternative to the ML ensemble: each window is
mapped to a set of primitive market events (price jumps, volume surges,
sentiment shifts), and finite-state automata recognise ordered *sequences* of
those events as complex anomalies. No batch training, no model inference —
O(1) per window, so it runs in-line on the stream.
"""

from cep.cep_detector import CEPDetector

__all__ = ["CEPDetector"]
