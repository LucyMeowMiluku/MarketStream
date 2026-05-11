"""Synthetic anomaly injection for backtesting.

Provides ground-truth labels by injecting known anomalies into test data.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class InjectedAnomaly:
    index: int
    ticker: str
    anomaly_type: str
    severity: float
    original_features: dict
    modified_features: dict


POINT_TYPES = ["price_spike", "volume_surge", "sentiment_crash", "multi_feature"]
POINT_WEIGHTS = np.array([0.33, 0.28, 0.22, 0.17])


class AnomalyInjector:
    """Injects synthetic anomalies into a test DataFrame to create ground truth."""

    def __init__(self, seed: int = 42, injection_rate: float = 0.05):
        self._rng = np.random.default_rng(seed)
        self._rate = injection_rate

    def inject(
        self, test_df: pd.DataFrame
    ) -> tuple[pd.DataFrame, list[InjectedAnomaly]]:
        df = test_df.reset_index(drop=True).copy()
        n = len(df)
        n_point = max(1, int(n * self._rate))

        indices = sorted(self._rng.choice(n, size=min(n_point, n), replace=False))
        types = self._rng.choice(POINT_TYPES, size=len(indices), p=POINT_WEIGHTS)

        ground_truth: list[InjectedAnomaly] = []
        for idx, atype in zip(indices, types):
            idx = int(idx)
            original = df.iloc[idx].to_dict()
            severity = self._inject_point(df, idx, str(atype))
            modified = df.iloc[idx].to_dict()
            ground_truth.append(
                InjectedAnomaly(
                    idx, str(original["ticker"]), str(atype), severity, original, modified
                )
            )

        drift_gt = self._inject_drift_block(df, {int(i) for i in indices})
        ground_truth.extend(drift_gt)
        return df, ground_truth

    def _inject_point(self, df: pd.DataFrame, idx: int, atype: str) -> float:
        if atype == "price_spike":
            f = float(self._rng.uniform(5, 15))
            df.at[idx, "price_change_rate"] = float(df.at[idx, "price_change_rate"]) * f
            return f
        if atype == "volume_surge":
            f = float(self._rng.uniform(5, 20))
            df.at[idx, "total_volume"] = float(df.at[idx, "total_volume"]) * f
            return f
        if atype == "sentiment_crash":
            s = float(self._rng.uniform(-0.9, -0.6))
            sh = float(self._rng.uniform(-0.8, -0.5))
            df.at[idx, "avg_sentiment"] = s
            df.at[idx, "sentiment_shift"] = sh
            return abs(s)
        if atype == "multi_feature":
            pf = float(self._rng.uniform(3, 8))
            vf = float(self._rng.uniform(3, 8))
            df.at[idx, "price_change_rate"] = float(df.at[idx, "price_change_rate"]) * pf
            df.at[idx, "total_volume"] = float(df.at[idx, "total_volume"]) * vf
            return (pf + vf) / 2
        return 0.0

    def _inject_drift_block(
        self, df: pd.DataFrame, used: set[int]
    ) -> list[InjectedAnomaly]:
        n = len(df)
        block_size = int(self._rng.integers(10, 21))

        tickers = df["ticker"].unique()
        ticker = str(self._rng.choice(tickers))
        ticker_indices = df[df["ticker"] == ticker].index.tolist()
        if len(ticker_indices) < block_size:
            return []

        mid = len(ticker_indices) // 2
        start = None
        for c in ticker_indices[mid:]:
            block = set(range(c, min(c + block_size, n)))
            if block.issubset(set(ticker_indices)) and not block & used:
                start = c
                break
        if start is None:
            return []

        gt: list[InjectedAnomaly] = []
        for i in range(start, start + block_size):
            original = df.iloc[i].to_dict()
            df.at[i, "price_change_rate"] = float(df.at[i, "price_change_rate"]) + 0.02
            df.at[i, "total_volume"] = float(df.at[i, "total_volume"]) * 1.5
            df.at[i, "avg_sentiment"] = float(df.at[i, "avg_sentiment"]) - 0.2
            modified = df.iloc[i].to_dict()
            gt.append(
                InjectedAnomaly(i, ticker, "subtle_drift", 1.5, original, modified)
            )
        return gt
