#!/usr/bin/env python3
"""Apply conservative terminology fixes to the local machine translation."""

from __future__ import annotations

import re
import sys
from pathlib import Path


REPLACEMENTS = [
    ("call the police", "raise an alert"),
    ("abnormal detection", "anomaly detection"),
    ("abnormal alarm", "anomaly alert"),
    ("abnormal alarms", "anomaly alerts"),
    ("abnormal pattern", "anomaly pattern"),
    ("abnormal patterns", "anomaly patterns"),
    ("abnormal event", "anomalous event"),
    ("abnormal events", "anomalous events"),
    ("market anomalies detection", "market anomaly detection"),
    ("complex event handling", "complex event processing"),
    ("flow processing", "stream processing"),
    ("historical playback", "historical replay"),
    ("K-lines", "price bars"),
    ("K-line", "price bar"),
    ("quotations", "quotes"),
    ("quotation", "quote"),
    ("tracking subjects", "tracked assets"),
    ("five subjects", "five assets"),
    ("different subjects", "different assets"),
    ("single subject", "single asset"),
    ("the subject", "the asset"),
    ("weight removal", "deduplication"),
    ("cooling merger", "cooldown merging"),
    ("determinal", "deterministic"),
    ("de-keying", "deduplication"),
    ("regular design", "rule design"),
    ("accuracy rate 0.750", "precision 0.750"),
    ("single calculation speed", "per-window computation time"),
    ("stream data", "streaming events"),
    ("time stamp", "timestamp"),
    ("reporting missing", "false negative"),
    ("missing report", "false negative"),
    ("false report", "false positive"),
    ("Abnormal mode", "Anomaly pattern"),
    ("Roles in CEP", "Role in CEP"),
    ("Bear fruit", "Result"),
    ("Decintal number", "Percentile"),
    ("Negative contrast alarm rate", "Negative-control alert rate"),
    ("Average calculation delay", "Mean computation latency"),
    ("P99 Calculation delay", "p99 computation latency"),
]


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("usage: polish_translation.py INPUT.md OUTPUT.md")
    text = Path(sys.argv[1]).read_text(encoding="utf-8")
    for old, new in REPLACEMENTS:
        text = re.sub(re.escape(old), new, text, flags=re.I)
    text = re.sub(r"`([^`\n]+)[’']", r"`\1`", text)
    text = re.sub(r"[ \t]+\*\*", "**", text)
    text = text.replace("# Reference\n", "# References\n")
    text = text.replace("F1 score to be inverted", "F1 score to be overstated")
    text = text.replace("favorable or short direction", "positive or negative direction")
    text = text.replace("painting door", "sharp reversal")
    text = text.replace("market accumulation", "order-book pressure")
    text = text.replace("cross-plates", "cross-sector")
    text = text.replace(r"\Log(", r"\log(")
    text = text.replace("Methodology: Lightness Factor and CEP", "Methodology: Lightweight Factors and CEP")
    text = text.replace("Abnormal threshold threshold", "Anomaly threshold")
    text = text.replace("Control method of abnormal warning", "Anomaly alert controls")
    text = text.replace("Conclusion and Future Work: Conclusion and Future Work", "Conclusion and Future Work")
    text = text.replace("Factor group deletes the experimental results", "Factor-group ablation results")
    text = text.replace("Comparison of ML with factor detection effect and Mean computation latency", "Comparison of ML and factor-based detection performance and mean computation latency")
    text = text.replace("The historical scope and completion conditions of six types of CEP models", "Historical scope and completion conditions of six CEP patterns")
    text = text.replace("Detection effect indicators", "Detection performance metrics")
    text = text.replace("Alarm quality index", "Alert quality metrics")
    text = text.replace("System operation indicators", "System operation metrics")
    text = text.replace("Number of event matches", "Event matching counts")
    text = text.replace("Proportion of detection effect", "Detection performance")
    text = text.replace("Delay in the first detection", "Time to first detection")
    text = text.replace("Complete link event processing results", "End-to-end event processing results")
    text = text.replace("Alpaca IEX running results", "Alpaca IEX operational results")
    text = text.replace("| Classify           |", "| Category           |")
    text = text.replace("| Model                         | Historical scope", "| Pattern                       | Historical scope")
    text = text.replace("| Target", "| Metric")
    text = text.replace("| Set up", "| Setting")
    text = text.replace("| Test                               | Precision", "| Experiment                         | Precision")
    text = text.replace("| Way              | Precision", "| Method           | Precision")
    text = text.replace("| Project               |   Quantity |", "| Item                  |   Count    |")
    Path(sys.argv[2]).write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
