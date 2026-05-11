from collections import defaultdict, deque

import numpy as np
import torch
import torch.nn as nn

from ml.base_detector import BaseDetector

FEATURE_KEYS = ["price_change_rate", "total_volume", "avg_sentiment", "sentiment_shift"]


class LSTMAutoencoder(nn.Module):
    def __init__(self, input_dim: int = 4, hidden_dim: int = 32):
        super().__init__()
        self.encoder = nn.LSTM(input_dim, hidden_dim, batch_first=True)
        self.decoder = nn.LSTM(hidden_dim, hidden_dim, batch_first=True)
        self.output_layer = nn.Linear(hidden_dim, input_dim)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        _, (h, c) = self.encoder(x)
        seq_len = x.size(1)
        decoder_input = h.transpose(0, 1).repeat(1, seq_len, 1)
        decoder_out, _ = self.decoder(decoder_input, (h, c))
        return self.output_layer(decoder_out)


class LSTMDetector(BaseDetector):
    """LSTM Autoencoder anomaly detector.

    Maintains a sliding buffer of feature vectors per ticker.
    Anomaly = high reconstruction error (MSE).
    Returns 0.0 (neutral) until buffer is full.
    """

    def __init__(
        self,
        model_path: str | None = None,
        sequence_length: int = 12,
        hidden_dim: int = 32,
    ):
        self._seq_len = sequence_length
        self._hidden_dim = hidden_dim
        self._buffers: dict[str, deque] = defaultdict(
            lambda: deque(maxlen=sequence_length)
        )
        self._model = LSTMAutoencoder(input_dim=len(FEATURE_KEYS), hidden_dim=hidden_dim)
        if model_path:
            self._model.load_state_dict(torch.load(model_path, weights_only=True))
        self._model.eval()

        self._mean: np.ndarray | None = None
        self._std: np.ndarray | None = None

    @property
    def name(self) -> str:
        return "lstm_ae"

    def _extract(self, features: dict) -> list[float]:
        return [float(features.get(k, 0.0)) for k in FEATURE_KEYS]

    def _normalize(self, arr: np.ndarray) -> np.ndarray:
        if self._mean is not None and self._std is not None:
            return (arr - self._mean) / (self._std + 1e-8)
        return arr

    def score(self, features: dict) -> float:
        key = features.get("ticker", "_default")
        buf = self._buffers[key]
        if len(buf) < self._seq_len:
            return 0.0

        seq = np.array(list(buf), dtype=np.float32)
        seq = self._normalize(seq)
        x = torch.tensor(seq).unsqueeze(0)

        with torch.no_grad():
            reconstructed = self._model(x)
            mse = float(nn.functional.mse_loss(reconstructed, x).item())

        return -mse

    def update(self, features: dict) -> None:
        key = features.get("ticker", "_default")
        self._buffers[key].append(self._extract(features))
