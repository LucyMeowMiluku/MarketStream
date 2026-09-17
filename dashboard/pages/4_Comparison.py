import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd
import streamlit as st

st.set_page_config(page_title="Method Comparison — MarketStream", page_icon=":bar_chart:", layout="wide")
st.title("CEP vs Isolation Forest")
st.caption("Both methods must use the same factor snapshots, test interval and event-level metrics.")

default_path = Path("data/evaluation/detector_comparison.json")
path_text = st.text_input("Frozen comparison JSON", str(default_path))
path = Path(path_text)

if not path.exists():
    st.warning(
        "No formal comparison is available. This is expected until the independently reviewed labels are frozen."
    )
    st.stop()

try:
    result = json.loads(path.read_text())
except (OSError, json.JSONDecodeError) as exc:
    st.error(f"Cannot read comparison artifact: {exc}")
    st.stop()

if result.get("labels_frozen") is not True or result.get("data_kind") != "real_historical":
    st.error("This artifact is not eligible for a formal real-market comparison.")
    st.stop()

rows = []
for method, metrics in result.get("methods", {}).items():
    rows.append(
        {
            "Method": method,
            "Precision": metrics.get("precision"),
            "Recall": metrics.get("recall"),
            "F1": metrics.get("f1"),
            "TP": metrics.get("true_positives"),
            "FP": metrics.get("false_positives"),
            "FN": metrics.get("false_negatives"),
        }
    )
st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
st.json(result.get("config", {}), expanded=False)
