"""Train LSTM Autoencoder on historical feature data.

Usage:
    uv run python -m ml.train_lstm
"""

from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset

from config.logging_config import get_logger
from config.settings import settings
from ml.data_utils import download_historical
from ml.detectors.lstm_detector import LSTMAutoencoder

log = get_logger("train_lstm")

FEATURE_KEYS = ["price_change_rate", "total_volume", "avg_sentiment", "sentiment_shift"]


def create_sequences(data: np.ndarray, seq_len: int) -> np.ndarray:
    sequences = []
    for i in range(len(data) - seq_len + 1):
        sequences.append(data[i : i + seq_len])
    return np.array(sequences)


def main():
    model_path = Path(settings.lstm_model_path)
    model_path.parent.mkdir(parents=True, exist_ok=True)

    df = download_historical(settings.tickers, period="30d")
    if df.empty:
        log.error("no_training_data")
        return

    log.info("building_sequences", total_rows=len(df))

    all_sequences = []
    for ticker in settings.tickers:
        ticker_df = df[df["ticker"] == ticker]
        if len(ticker_df) < settings.lstm_sequence_length:
            continue
        values = ticker_df[FEATURE_KEYS].values.astype(np.float32)
        seqs = create_sequences(values, settings.lstm_sequence_length)
        all_sequences.append(seqs)

    if not all_sequences:
        log.error("no_sequences_created")
        return

    sequences = np.concatenate(all_sequences, axis=0)
    mean = sequences.reshape(-1, len(FEATURE_KEYS)).mean(axis=0)
    std = sequences.reshape(-1, len(FEATURE_KEYS)).std(axis=0) + 1e-8
    sequences = (sequences - mean) / std

    log.info("training", sequences=len(sequences), seq_len=settings.lstm_sequence_length)

    dataset = TensorDataset(torch.tensor(sequences))
    loader = DataLoader(dataset, batch_size=32, shuffle=True)

    model = LSTMAutoencoder(
        input_dim=len(FEATURE_KEYS), hidden_dim=settings.lstm_hidden_dim
    )
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)
    criterion = nn.MSELoss()

    model.train()
    for epoch in range(30):
        total_loss = 0.0
        for (batch,) in loader:
            optimizer.zero_grad()
            output = model(batch)
            loss = criterion(output, batch)
            loss.backward()
            optimizer.step()
            total_loss += loss.item() * batch.size(0)
        avg_loss = total_loss / len(sequences)
        if (epoch + 1) % 10 == 0:
            log.info("epoch", epoch=epoch + 1, loss=f"{avg_loss:.6f}")

    torch.save(model.state_dict(), str(model_path))

    norm_path = model_path.parent / "lstm_norm.npz"
    np.savez(str(norm_path), mean=mean, std=std)

    log.info("model_saved", path=str(model_path), norm_path=str(norm_path))


if __name__ == "__main__":
    main()
