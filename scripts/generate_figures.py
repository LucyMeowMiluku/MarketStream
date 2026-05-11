"""Generate backtest comparison figures for ensemble optimization."""

import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import numpy as np
from pathlib import Path

OUTPUT_DIR = Path("Figure")
OUTPUT_DIR.mkdir(exist_ok=True)

# ---------- Color Palette (matches project Plotly dark theme) ----------
BG_COLOR = "#0e1117"
CARD_BG = "#1a1f2e"
TEXT_COLOR = "#e2e8f0"
GRID_COLOR = "#314158"
BLUE = "#60a5fa"
GREEN = "#34d399"
YELLOW = "#fbbf24"
PINK = "#f472b6"
RED = "#ef4444"
ORANGE = "#fb923c"
CYAN = "#22d3ee"
PURPLE = "#a78bfa"
DIM = "#64748b"

# ---------- Data ----------

# Backtest 1: Before optimization (from plan diagnosis)
B1 = {
    "precision": 0.0835,
    "recall": 1.0,
    "f1": 0.154,
    "fp_rate": 0.6197,
    "cohens_d": 0.51,
    "tp": 225,
    "fp": 2469,
    "fn": 0,
    "total_det": 2694,
    "ground_truth": 225,
    "threshold": -0.3,
    "det_recall": {"EWMA": 0.9936, "HST": 0.03, "IF": 0.0, "LSTM": 0.62},
    "det_precision": {"EWMA": 0.054, "HST": 0.14, "IF": 0.0, "LSTM": 0.056},
    "det_f1": {"EWMA": 0.102, "HST": 0.058, "IF": 0.0, "LSTM": 0.103},
    "per_type": {
        "sentiment_crash": 1.0,
        "volume_surge": 1.0,
        "price_spike": 1.0,
        "multi_feature": 1.0,
        "subtle_drift": 1.0,
    },
    "score_range": {
        "EWMA": (-40, 0),
        "HST": (-0.3, 0),
        "IF": (0.1, 0.2),
        "LSTM": (-100, 0),
    },
    "weights": [0.2, 0.3, 0.3, 0.2],
}

# Backtest 2: After optimization (from best run, threshold -0.28)
B2 = {
    "precision": 0.5067,
    "recall": 0.6711,
    "f1": 0.5774,
    "fp_rate": 0.0369,
    "cohens_d": 1.78,
    "tp": 151,
    "fp": 147,
    "fn": 74,
    "total_det": 298,
    "ground_truth": 225,
    "threshold": -0.28,
    "det_recall": {"EWMA": 0.79, "HST": 0.22, "IF": 0.45, "LSTM": 0.32},
    "det_precision": {"EWMA": 0.29, "HST": 0.04, "IF": 0.49, "LSTM": 0.06},
    "det_f1": {"EWMA": 0.43, "HST": 0.06, "IF": 0.47, "LSTM": 0.10},
    "per_type": {
        "sentiment_crash": 1.0,
        "volume_surge": 0.7593,
        "price_spike": 0.5070,
        "multi_feature": 0.6757,
        "subtle_drift": 0.0667,
    },
    "score_stats": {
        "ensemble_mean": -0.14,
        "anomaly_mean": -0.35,
        "normal_mean": -0.12,
    },
    "weights": [0.40, 0.05, 0.45, 0.10],
}

DET_NAMES = ["EWMA", "HST", "IF", "LSTM"]
DET_COLORS = {"EWMA": BLUE, "HST": GREEN, "IF": YELLOW, "LSTM": PINK}
TYPE_NAMES = ["sentiment_crash", "volume_surge", "price_spike", "multi_feature", "subtle_drift"]
TYPE_LABELS = ["Sentiment\nCrash", "Volume\nSurge", "Price\nSpike", "Multi-\nFeature", "Subtle\nDrift"]


def apply_style(fig):
    fig.patch.set_facecolor(BG_COLOR)


def style_ax(ax, title="", xlabel="", ylabel=""):
    ax.set_facecolor(CARD_BG)
    ax.set_title(title, color=TEXT_COLOR, fontsize=13, fontweight="bold", pad=10)
    ax.set_xlabel(xlabel, color=DIM, fontsize=10)
    ax.set_ylabel(ylabel, color=DIM, fontsize=10)
    ax.tick_params(colors=DIM, labelsize=9)
    for spine in ax.spines.values():
        spine.set_color(GRID_COLOR)
    ax.grid(axis="y", color=GRID_COLOR, alpha=0.3, linewidth=0.5)


def add_value_labels(ax, bars, fmt="{:.1%}", color=TEXT_COLOR, fontsize=9):
    for bar in bars:
        h = bar.get_height()
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            h + 0.015,
            fmt.format(h),
            ha="center",
            va="bottom",
            color=color,
            fontsize=fontsize,
            fontweight="bold",
        )


# =========================================================================
# Figure 1: Backtest 1 — Before Optimization
# =========================================================================
def plot_backtest1():
    fig = plt.figure(figsize=(18, 14))
    apply_style(fig)
    fig.suptitle(
        "Backtest 1 — Before Optimization",
        color=TEXT_COLOR,
        fontsize=20,
        fontweight="bold",
        y=0.97,
    )
    fig.text(
        0.5, 0.935,
        "Ensemble is dysfunctional: catches everything but floods with false positives",
        ha="center", color=DIM, fontsize=12, style="italic",
    )

    gs = gridspec.GridSpec(2, 3, hspace=0.38, wspace=0.32, top=0.90, bottom=0.06, left=0.06, right=0.96)

    # (0,0) Precision / Recall / F1
    ax = fig.add_subplot(gs[0, 0])
    vals = [B1["precision"], B1["recall"], B1["f1"]]
    colors = [RED, GREEN, ORANGE]
    bars = ax.bar(["Precision", "Recall", "F1"], vals, color=colors, width=0.55, edgecolor="none")
    add_value_labels(ax, bars)
    ax.set_ylim(0, 1.15)
    style_ax(ax, title="Overall Metrics")

    # (0,1) Confusion matrix style
    ax = fig.add_subplot(gs[0, 1])
    categories = ["True Pos", "False Pos", "False Neg"]
    counts = [B1["tp"], B1["fp"], B1["fn"]]
    colors_cm = [GREEN, RED, YELLOW]
    bars = ax.bar(categories, counts, color=colors_cm, width=0.55, edgecolor="none")
    for bar, c in zip(bars, counts):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + 30,
            f"{c:,}",
            ha="center", va="bottom", color=TEXT_COLOR, fontsize=11, fontweight="bold",
        )
    ax.set_ylim(0, max(counts) * 1.18)
    style_ax(ax, title="Detection Counts")

    # (0,2) Score ranges — the root cause
    ax = fig.add_subplot(gs[0, 2])
    for i, name in enumerate(DET_NAMES):
        lo, hi = B1["score_range"][name]
        ax.barh(i, hi - lo, left=lo, height=0.55, color=DET_COLORS[name], alpha=0.85, edgecolor="none")
        ax.text(
            hi + 1.5, i,
            f"[{lo}, {hi}]",
            va="center", color=DIM, fontsize=9,
        )
    ax.set_yticks(range(len(DET_NAMES)))
    ax.set_yticklabels(DET_NAMES)
    ax.axvline(x=B1["threshold"], color=RED, linestyle="--", linewidth=1.2, alpha=0.7)
    ax.text(B1["threshold"] + 0.5, 3.5, f"threshold={B1['threshold']}", color=RED, fontsize=8)
    style_ax(ax, title="Raw Score Ranges (Root Cause)", xlabel="Score")
    ax.set_xlim(-110, 5)

    # (1,0) Per-detector Recall
    ax = fig.add_subplot(gs[1, 0])
    det_rec = [B1["det_recall"][n] for n in DET_NAMES]
    colors_det = [DET_COLORS[n] for n in DET_NAMES]
    bars = ax.bar(DET_NAMES, det_rec, color=colors_det, width=0.55, edgecolor="none")
    add_value_labels(ax, bars)
    ax.set_ylim(0, 1.15)
    style_ax(ax, title="Per-Detector Recall")

    # (1,1) Per-type Recall
    ax = fig.add_subplot(gs[1, 1])
    type_rec = [B1["per_type"][t] for t in TYPE_NAMES]
    bars = ax.bar(TYPE_LABELS, type_rec, color=CYAN, width=0.55, edgecolor="none")
    add_value_labels(ax, bars)
    ax.set_ylim(0, 1.15)
    style_ax(ax, title="Per-Type Recall")

    # (1,2) Key stats card
    ax = fig.add_subplot(gs[1, 2])
    ax.set_facecolor(CARD_BG)
    ax.axis("off")
    stats_text = [
        ("FP Rate", f"{B1['fp_rate']:.1%}", RED),
        ("Cohen's d", f"{B1['cohens_d']:.2f}", YELLOW),
        ("Total Detections", f"{B1['total_det']:,}", BLUE),
        ("Ground Truth", f"{B1['ground_truth']}", DIM),
        ("Threshold", f"{B1['threshold']}", DIM),
        ("Weights", str(B1["weights"]), DIM),
    ]
    for i, (label, val, color) in enumerate(stats_text):
        y = 0.88 - i * 0.15
        ax.text(0.08, y, label, transform=ax.transAxes, color=DIM, fontsize=12, va="center")
        ax.text(0.92, y, val, transform=ax.transAxes, color=color, fontsize=14, va="center", ha="right", fontweight="bold")
    ax.set_title("Key Statistics", color=TEXT_COLOR, fontsize=13, fontweight="bold", pad=10)

    fig.savefig(OUTPUT_DIR / "backtest1_before.png", dpi=180, facecolor=BG_COLOR)
    plt.close(fig)
    print(f"Saved {OUTPUT_DIR / 'backtest1_before.png'}")


# =========================================================================
# Figure 2: Backtest 2 — After Optimization
# =========================================================================
def plot_backtest2():
    fig = plt.figure(figsize=(18, 14))
    apply_style(fig)
    fig.suptitle(
        "Backtest 2 — After Optimization",
        color=TEXT_COLOR,
        fontsize=20,
        fontweight="bold",
        y=0.97,
    )
    fig.text(
        0.5, 0.935,
        "Score normalization to [-1, 0] + StandardScaler + tuned weights/threshold",
        ha="center", color=DIM, fontsize=12, style="italic",
    )

    gs = gridspec.GridSpec(2, 3, hspace=0.38, wspace=0.32, top=0.90, bottom=0.06, left=0.06, right=0.96)

    # (0,0) Precision / Recall / F1
    ax = fig.add_subplot(gs[0, 0])
    vals = [B2["precision"], B2["recall"], B2["f1"]]
    colors = [BLUE, GREEN, ORANGE]
    bars = ax.bar(["Precision", "Recall", "F1"], vals, color=colors, width=0.55, edgecolor="none")
    add_value_labels(ax, bars)
    ax.set_ylim(0, 1.15)
    style_ax(ax, title="Overall Metrics")

    # (0,1) Confusion matrix counts
    ax = fig.add_subplot(gs[0, 1])
    categories = ["True Pos", "False Pos", "False Neg"]
    counts = [B2["tp"], B2["fp"], B2["fn"]]
    colors_cm = [GREEN, RED, YELLOW]
    bars = ax.bar(categories, counts, color=colors_cm, width=0.55, edgecolor="none")
    for bar, c in zip(bars, counts):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + 2,
            f"{c:,}",
            ha="center", va="bottom", color=TEXT_COLOR, fontsize=11, fontweight="bold",
        )
    ax.set_ylim(0, max(counts) * 1.2)
    style_ax(ax, title="Detection Counts")

    # (0,2) Per-detector P/R/F1
    ax = fig.add_subplot(gs[0, 2])
    x = np.arange(len(DET_NAMES))
    w = 0.22
    p_vals = [B2["det_precision"][n] for n in DET_NAMES]
    r_vals = [B2["det_recall"][n] for n in DET_NAMES]
    f_vals = [B2["det_f1"][n] for n in DET_NAMES]
    ax.bar(x - w, p_vals, w, label="Precision", color=BLUE, edgecolor="none")
    ax.bar(x, r_vals, w, label="Recall", color=GREEN, edgecolor="none")
    ax.bar(x + w, f_vals, w, label="F1", color=ORANGE, edgecolor="none")
    ax.set_xticks(x)
    ax.set_xticklabels(DET_NAMES)
    ax.set_ylim(0, 1.0)
    ax.legend(loc="upper right", fontsize=8, facecolor=CARD_BG, edgecolor=GRID_COLOR, labelcolor=TEXT_COLOR)
    style_ax(ax, title="Per-Detector Metrics")

    # (1,0) Per-type Recall
    ax = fig.add_subplot(gs[1, 0])
    type_rec = [B2["per_type"][t] for t in TYPE_NAMES]
    colors_type = [GREEN if v >= 0.5 else YELLOW if v >= 0.2 else RED for v in type_rec]
    bars = ax.bar(TYPE_LABELS, type_rec, color=colors_type, width=0.55, edgecolor="none")
    add_value_labels(ax, bars)
    ax.set_ylim(0, 1.15)
    style_ax(ax, title="Per-Type Recall")

    # (1,1) Ensemble weights pie chart
    ax = fig.add_subplot(gs[1, 1])
    ax.set_facecolor(CARD_BG)
    wedge_colors = [DET_COLORS[n] for n in DET_NAMES]
    wedges, texts, autotexts = ax.pie(
        B2["weights"],
        labels=DET_NAMES,
        autopct="%1.0f%%",
        colors=wedge_colors,
        textprops={"color": TEXT_COLOR, "fontsize": 11},
        wedgeprops={"edgecolor": CARD_BG, "linewidth": 2},
        startangle=90,
    )
    for at in autotexts:
        at.set_fontweight("bold")
        at.set_fontsize(10)
    ax.set_title("Ensemble Weights", color=TEXT_COLOR, fontsize=13, fontweight="bold", pad=10)

    # (1,2) Key stats card
    ax = fig.add_subplot(gs[1, 2])
    ax.set_facecolor(CARD_BG)
    ax.axis("off")
    stats_text = [
        ("FP Rate", f"{B2['fp_rate']:.1%}", GREEN),
        ("Cohen's d", f"{B2['cohens_d']:.2f}", GREEN),
        ("Total Detections", f"{B2['total_det']:,}", BLUE),
        ("Ground Truth", f"{B2['ground_truth']}", DIM),
        ("Threshold", f"{B2['threshold']}", DIM),
        ("Weights", str(B2["weights"]), DIM),
    ]
    for i, (label, val, color) in enumerate(stats_text):
        y = 0.88 - i * 0.15
        ax.text(0.08, y, label, transform=ax.transAxes, color=DIM, fontsize=12, va="center")
        ax.text(0.92, y, val, transform=ax.transAxes, color=color, fontsize=14, va="center", ha="right", fontweight="bold")
    ax.set_title("Key Statistics", color=TEXT_COLOR, fontsize=13, fontweight="bold", pad=10)

    fig.savefig(OUTPUT_DIR / "backtest2_after.png", dpi=180, facecolor=BG_COLOR)
    plt.close(fig)
    print(f"Saved {OUTPUT_DIR / 'backtest2_after.png'}")


# =========================================================================
# Figure 3: Comparison — Before vs After
# =========================================================================
def plot_comparison():
    fig = plt.figure(figsize=(20, 16))
    apply_style(fig)
    fig.suptitle(
        "Ensemble Optimization — Before vs After",
        color=TEXT_COLOR,
        fontsize=22,
        fontweight="bold",
        y=0.97,
    )
    fig.text(
        0.5, 0.935,
        "Normalizing detector scores to [-1, 0] + StandardScaler for IF + tuned weights & threshold",
        ha="center", color=DIM, fontsize=12, style="italic",
    )

    gs = gridspec.GridSpec(3, 3, hspace=0.42, wspace=0.34, top=0.90, bottom=0.05, left=0.06, right=0.96)

    # (0,0) Precision / Recall / F1 grouped
    ax = fig.add_subplot(gs[0, 0])
    labels = ["Precision", "Recall", "F1"]
    b1_vals = [B1["precision"], B1["recall"], B1["f1"]]
    b2_vals = [B2["precision"], B2["recall"], B2["f1"]]
    x = np.arange(len(labels))
    w = 0.30
    bars1 = ax.bar(x - w / 2, b1_vals, w, label="Before", color=RED, alpha=0.75, edgecolor="none")
    bars2 = ax.bar(x + w / 2, b2_vals, w, label="After", color=BLUE, alpha=0.90, edgecolor="none")
    add_value_labels(ax, bars1, fontsize=8)
    add_value_labels(ax, bars2, fontsize=8)
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_ylim(0, 1.18)
    ax.legend(fontsize=9, facecolor=CARD_BG, edgecolor=GRID_COLOR, labelcolor=TEXT_COLOR)
    style_ax(ax, title="Precision / Recall / F1")

    # (0,1) FP Rate comparison
    ax = fig.add_subplot(gs[0, 1])
    vals = [B1["fp_rate"], B2["fp_rate"]]
    colors = [RED, GREEN]
    bars = ax.bar(["Before", "After"], vals, color=colors, width=0.45, edgecolor="none")
    add_value_labels(ax, bars)
    ax.set_ylim(0, 0.75)
    ax.axhline(y=0.10, color=YELLOW, linestyle="--", linewidth=1, alpha=0.6)
    ax.text(1.4, 0.105, "Target: <10%", color=YELLOW, fontsize=8, va="bottom")
    style_ax(ax, title="False Positive Rate")

    # (0,2) Cohen's d comparison
    ax = fig.add_subplot(gs[0, 2])
    vals = [B1["cohens_d"], B2["cohens_d"]]
    colors = [ORANGE, GREEN]
    bars = ax.bar(["Before", "After"], vals, color=colors, width=0.45, edgecolor="none")
    for bar, v in zip(bars, vals):
        ax.text(
            bar.get_x() + bar.get_width() / 2, v + 0.04,
            f"{v:.2f}", ha="center", va="bottom", color=TEXT_COLOR, fontsize=11, fontweight="bold",
        )
    ax.set_ylim(0, 2.5)
    ax.axhline(y=1.5, color=YELLOW, linestyle="--", linewidth=1, alpha=0.6)
    ax.text(1.4, 1.53, "Target: >1.5", color=YELLOW, fontsize=8, va="bottom")
    style_ax(ax, title="Cohen's d (Score Separation)")

    # (1,0) Detection counts comparison
    ax = fig.add_subplot(gs[1, 0])
    cats = ["TP", "FP", "FN"]
    b1_c = [B1["tp"], B1["fp"], B1["fn"]]
    b2_c = [B2["tp"], B2["fp"], B2["fn"]]
    x = np.arange(len(cats))
    w = 0.30
    bars1 = ax.bar(x - w / 2, b1_c, w, label="Before", color=RED, alpha=0.75, edgecolor="none")
    bars2 = ax.bar(x + w / 2, b2_c, w, label="After", color=BLUE, alpha=0.90, edgecolor="none")
    for bar, c in zip(bars1, b1_c):
        ax.text(bar.get_x() + bar.get_width() / 2, c + 30, f"{c:,}", ha="center", va="bottom", color=RED, fontsize=8, fontweight="bold")
    for bar, c in zip(bars2, b2_c):
        ax.text(bar.get_x() + bar.get_width() / 2, c + 30, f"{c:,}", ha="center", va="bottom", color=BLUE, fontsize=8, fontweight="bold")
    ax.set_xticks(x)
    ax.set_xticklabels(cats)
    ax.set_ylim(0, max(b1_c) * 1.15)
    ax.legend(fontsize=9, facecolor=CARD_BG, edgecolor=GRID_COLOR, labelcolor=TEXT_COLOR)
    style_ax(ax, title="Detection Counts")

    # (1,1) Per-detector Recall comparison
    ax = fig.add_subplot(gs[1, 1])
    x = np.arange(len(DET_NAMES))
    w = 0.30
    b1_r = [B1["det_recall"][n] for n in DET_NAMES]
    b2_r = [B2["det_recall"][n] for n in DET_NAMES]
    bars1 = ax.bar(x - w / 2, b1_r, w, label="Before", color=RED, alpha=0.75, edgecolor="none")
    bars2 = ax.bar(x + w / 2, b2_r, w, label="After", color=BLUE, alpha=0.90, edgecolor="none")
    add_value_labels(ax, bars1, fontsize=7, color=RED)
    add_value_labels(ax, bars2, fontsize=7, color=BLUE)
    ax.set_xticks(x)
    ax.set_xticklabels(DET_NAMES)
    ax.set_ylim(0, 1.18)
    ax.legend(fontsize=9, facecolor=CARD_BG, edgecolor=GRID_COLOR, labelcolor=TEXT_COLOR)
    style_ax(ax, title="Per-Detector Recall")

    # (1,2) Per-detector Precision comparison
    ax = fig.add_subplot(gs[1, 2])
    x = np.arange(len(DET_NAMES))
    b1_p = [B1["det_precision"][n] for n in DET_NAMES]
    b2_p = [B2["det_precision"][n] for n in DET_NAMES]
    bars1 = ax.bar(x - w / 2, b1_p, w, label="Before", color=RED, alpha=0.75, edgecolor="none")
    bars2 = ax.bar(x + w / 2, b2_p, w, label="After", color=BLUE, alpha=0.90, edgecolor="none")
    add_value_labels(ax, bars1, fontsize=7, color=RED)
    add_value_labels(ax, bars2, fontsize=7, color=BLUE)
    ax.set_xticks(x)
    ax.set_xticklabels(DET_NAMES)
    ax.set_ylim(0, 0.65)
    ax.legend(fontsize=9, facecolor=CARD_BG, edgecolor=GRID_COLOR, labelcolor=TEXT_COLOR)
    style_ax(ax, title="Per-Detector Precision")

    # (2,0) Per-type Recall comparison
    ax = fig.add_subplot(gs[2, 0:2])
    x = np.arange(len(TYPE_NAMES))
    w = 0.30
    b1_t = [B1["per_type"][t] for t in TYPE_NAMES]
    b2_t = [B2["per_type"][t] for t in TYPE_NAMES]
    bars1 = ax.bar(x - w / 2, b1_t, w, label="Before", color=RED, alpha=0.75, edgecolor="none")
    bars2 = ax.bar(x + w / 2, b2_t, w, label="After", color=BLUE, alpha=0.90, edgecolor="none")
    add_value_labels(ax, bars1, fontsize=8, color=RED)
    add_value_labels(ax, bars2, fontsize=8, color=BLUE)
    ax.set_xticks(x)
    ax.set_xticklabels(TYPE_LABELS)
    ax.set_ylim(0, 1.18)
    ax.legend(fontsize=10, facecolor=CARD_BG, edgecolor=GRID_COLOR, labelcolor=TEXT_COLOR)
    style_ax(ax, title="Per-Type Recall Comparison")

    # (2,2) Improvement summary card
    ax = fig.add_subplot(gs[2, 2])
    ax.set_facecolor(CARD_BG)
    ax.axis("off")

    improvements = [
        ("Precision", B1["precision"], B2["precision"], True),
        ("F1 Score", B1["f1"], B2["f1"], True),
        ("FP Rate", B1["fp_rate"], B2["fp_rate"], False),
        ("Cohen's d", B1["cohens_d"], B2["cohens_d"], True),
        ("IF Recall", B1["det_recall"]["IF"], B2["det_recall"]["IF"], True),
        ("HST Recall", B1["det_recall"]["HST"], B2["det_recall"]["HST"], True),
    ]

    ax.set_title("Improvement Summary", color=TEXT_COLOR, fontsize=14, fontweight="bold", pad=12)
    for i, (label, before, after, higher_is_better) in enumerate(improvements):
        y = 0.88 - i * 0.145
        if before == 0:
            change_str = "NEW"
            color = GREEN
        else:
            ratio = after / before if higher_is_better else before / after
            change_str = f"{ratio:.1f}x"
            color = GREEN if ratio > 1 else RED

        ax.text(0.03, y, label, transform=ax.transAxes, color=DIM, fontsize=11, va="center")
        ax.text(0.55, y, f"{before:.1%}" if before <= 1 else f"{before:.2f}",
                transform=ax.transAxes, color=RED, fontsize=10, va="center", ha="center")
        ax.text(0.7, y, ">>", transform=ax.transAxes, color=DIM, fontsize=10, va="center", ha="center", fontweight="bold")
        ax.text(0.85, y, f"{after:.1%}" if after <= 1 else f"{after:.2f}",
                transform=ax.transAxes, color=GREEN, fontsize=10, va="center", ha="center", fontweight="bold")
        ax.text(0.97, y, change_str, transform=ax.transAxes, color=color, fontsize=10,
                va="center", ha="right", fontweight="bold")

    fig.savefig(OUTPUT_DIR / "comparison.png", dpi=180, facecolor=BG_COLOR)
    plt.close(fig)
    print(f"Saved {OUTPUT_DIR / 'comparison.png'}")


if __name__ == "__main__":
    plt.rcParams["font.family"] = "sans-serif"
    plt.rcParams["font.sans-serif"] = ["Helvetica Neue", "Arial", "DejaVu Sans"]

    plot_backtest1()
    plot_backtest2()
    plot_comparison()
    print("All figures generated.")
