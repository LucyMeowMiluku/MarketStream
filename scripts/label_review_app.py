"""Local label review app (docs/LABELING_CRITERIA.md).

Run:  uv run streamlit run scripts/label_review_app.py

Shows market data, reference statistics and news for one interval at a time,
blind to the draft label by default.  It reads only the prepared workbench and
never any detector output.  Candidate intervals stay locked until the criteria
document is approved; the demo mode uses disjoint 2023 examples.
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from replay.review_export import criteria_status, review_csv, reviewed_registry  # noqa: E402
from replay.review_metrics import ETF_FLOOR, SINGLE_STOCK_FLOOR, THRESHOLDS  # noqa: E402

WORKBENCH = Path(os.environ.get("LABEL_REVIEW_WORKBENCH", ROOT / "data/replay/review/workbench"))
DEMO = Path(os.environ.get("LABEL_REVIEW_DEMO_WORKBENCH", ROOT / "data/replay/review/workbench_demo"))
OUTPUT = Path(os.environ.get("LABEL_REVIEW_OUTPUT", ROOT / "data/replay/review/annotations"))
CRITERIA = Path(os.environ.get("LABEL_REVIEW_CRITERIA", ROOT / "docs/LABELING_CRITERIA.md"))
DRAFT = Path(os.environ.get("LABEL_REVIEW_DRAFT", ROOT / "data/replay/labels/iex_benchmark_v1.draft.json"))
EVENT_TYPES = ["earnings", "company_news", "macro_release", "market_wide_shock", "other"]


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "reviewer"


def _load_items(directory: Path) -> dict[str, dict]:
    index = directory / "index.json"
    if not index.exists():
        return {}
    entries = json.loads(index.read_text())["items"]
    return {entry["display_id"]: json.loads((directory / entry["file"]).read_text()) for entry in entries}


def _records_path(mode: str, reviewer: str) -> Path:
    return OUTPUT / f"{'demo-' if mode == 'demo' else ''}{_slug(reviewer)}.json"


def _load_records(path: Path) -> dict[str, dict]:
    return json.loads(path.read_text()) if path.exists() else {}


def _save_records(path: Path, records: dict[str, dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(records, indent=2) + "\n")
    tmp.replace(path)


def _pct(value) -> str:
    return "–" if value is None else f"{value:+.2%}"


def _x(value) -> str:
    return "–" if value is None else f"{value:.2f}×"


def _check(ok) -> str:
    return "–" if ok is None else ("✓" if ok else "✗")


def _criteria_rows(rules: dict, ticker: str, volume_required: bool | None) -> list[dict]:
    floor = ETF_FLOOR if ticker in {"SPY", "QQQ"} else SINGLE_STOCK_FLOOR
    move, volume, rng = rules["move_ratio"], rules["volume_ratio"], rules["range_ratio"]
    quiet = THRESHOLDS["normal_ratio"]
    coverage_ok = all(v >= THRESHOLDS["min_coverage"] for v in rules["coverage"].values())
    market = rules["market_move_ratios"]
    volume_role = {True: "required", False: "supporting only", None: "pending approval"}[volume_required]
    return [
        {"rule": "A1 move", "measured": f"{_x(move)}, |M| {rules['abs_total_move']:.2%}",
         "threshold": f"≥ {THRESHOLDS['anomaly_move_ratio']:g}× and ≥ {floor:.1%}",
         "meets": _check(move is not None and move >= THRESHOLDS["anomaly_move_ratio"]
                         and rules["abs_total_move"] >= floor)},
        {"rule": f"A2 volume ({volume_role})", "measured": _x(volume),
         "threshold": f"≥ {THRESHOLDS['anomaly_volume_ratio']:g}×",
         "meets": _check(volume is not None and volume >= THRESHOLDS["anomaly_volume_ratio"])},
        {"rule": "A4 no direction conflict", "measured": f"gap {_pct(rules['gap'])}, in-window {_pct(rules['in_window'])}",
         "threshold": f"not (opposite signs and |W| ≥ {THRESHOLDS['gap_retrace']:g}·|G|)",
         "meets": _check(not rules["direction_conflict"])},
        {"rule": "A5 / N6 data complete", "measured": ", ".join(f"{k} {v:.0%}" for k, v in rules["coverage"].items()),
         "threshold": f"≥ {THRESHOLDS['min_coverage']:.0%} each", "meets": _check(coverage_ok)},
        {"rule": "N1 quiet price", "measured": f"move {_x(move)}, range {_x(rng)}",
         "threshold": f"both ≤ {quiet:g}×",
         "meets": _check(move is not None and rng is not None and move <= quiet and rng <= quiet)},
        {"rule": "N2 quiet volume", "measured": _x(volume), "threshold": f"≤ {quiet:g}×",
         "meets": _check(volume is not None and volume <= quiet)},
        {"rule": "N3 quiet market", "measured": ", ".join(f"{k} {_x(v)}" for k, v in market.items()),
         "threshold": f"each ≤ {quiet:g}×",
         "meets": _check(all(v is not None and v <= quiet for v in market.values()))},
    ]


def _price_chart(item: dict) -> go.Figure:
    figure = go.Figure()
    for symbol, bars in item["chart"].items():
        info = item["measurement"]["symbols"].get(symbol, {})
        if not bars or not info.get("available"):
            continue
        reference = info["today"]["reference_price"]
        times = [bar[0] for bar in bars]
        values = [bar[4] / reference - 1 for bar in bars]
        figure.add_trace(go.Scatter(
            x=times, y=values, name=symbol, mode="lines",
            line={"width": 3 if symbol == item["ticker"] else 1.5},
        ))
    figure.add_hline(y=0, line_dash="dash", annotation_text="reference price",
                     annotation_position="bottom right")
    figure.update_layout(
        title="Change from reference price (a jump at the first minute is the gap)", yaxis_tickformat=".1%",
        height=340, margin={"l": 10, "r": 10, "t": 40, "b": 10}, legend={"orientation": "h"},
    )
    return figure


def _volume_chart(item: dict) -> go.Figure:
    bars = item["chart"].get(item["ticker"], [])
    figure = go.Figure()
    figure.add_trace(go.Bar(x=[bar[0] for bar in bars], y=[bar[5] for bar in bars], name="today"))
    figure.add_trace(go.Scatter(
        x=[row[0] for row in item["typical_minute_volume"]],
        y=[row[1] for row in item["typical_minute_volume"]],
        name="typical (20-session median)", mode="lines",
    ))
    figure.update_layout(title=f"{item['ticker']} volume per minute", height=280,
                         margin={"l": 10, "r": 10, "t": 40, "b": 10}, legend={"orientation": "h"})
    return figure


def _news_rows(item: dict) -> list[dict]:
    reference = datetime.fromisoformat(item["window"]["reference_time"])
    start = datetime.fromisoformat(item["window"]["start"])
    end = datetime.fromisoformat(item["window"]["end"])
    rows = []
    for news in item["news"]:
        published = datetime.fromisoformat(news["created_at"].replace("Z", "+00:00")).astimezone(start.tzinfo)
        if published < reference:
            position = "before reference (does not count)"
        elif published < start:
            position = "after reference, before window"
        elif published < end:
            position = "inside window"
        else:
            position = "after window end (does not count)"
        updated = news.get("updated_at") and news["updated_at"] != news["created_at"]
        rows.append({
            "published (ET)": published.strftime("%Y-%m-%d %H:%M"), "position": position,
            "headline": news["headline"], "source": news.get("source"), "url": news.get("url"),
            "symbols": ", ".join(news.get("symbols", [])), "later update": "yes" if updated else "",
        })
    # Items that count for A3/N4 first, then context before and after.
    order = ["after reference, before window", "inside window",
             "before reference (does not count)", "after window end (does not count)"]
    return sorted(rows, key=lambda row: (order.index(row["position"]), row["published (ET)"]))


def main() -> None:
    st.set_page_config(page_title="Label review", layout="wide")
    status = criteria_status(CRITERIA)
    volume_required = {1: True, 2: False}.get(status["volume_option"]) if status["approved"] else None

    with st.sidebar:
        st.header("Label review")
        if status["approved"]:
            st.success(status["line"].strip("*"))
        else:
            st.warning("Criteria not approved yet: candidate intervals are locked. Demo mode only.")
        mode = "review" if status["approved"] and st.radio(
            "Mode", ["Review candidates", "Demo (2023 examples)"]) == "Review candidates" else "demo"
        reviewer = st.text_input("Reviewer name", key="reviewer")
        items = _load_items(WORKBENCH if mode == "review" else DEMO)
        if not items:
            st.error("No prepared data. Run scripts/prepare_review_workbench.py first.")
            return
        records = _load_records(_records_path(mode, reviewer)) if reviewer else {}
        main_ids = [key for key, value in items.items() if value["group"] == "review"]
        pool_ids = [key for key, value in items.items() if value["group"] == "pool"]
        labels = {key: f"{key} {'✓' if key in records else '·'} {items[key]['ticker']}" for key in items}
        st.caption(f"{sum(key in records for key in main_ids)}/{len(main_ids)} reviewed")
        selected = st.selectbox("Interval", main_ids, format_func=labels.get)
        if pool_ids:
            with st.expander("Replacement pool (use only after an exclusion)"):
                pool_choice = st.selectbox("Pool interval", ["—"] + pool_ids,
                                           format_func=lambda key: labels.get(key, key))
                if pool_choice != "—":
                    selected = pool_choice
        reveal = st.toggle("Show draft candidate info (breaks blinding)", value=False)

    item = items[selected]
    rules = item["rule_inputs"]
    start = datetime.fromisoformat(item["window"]["start"])
    end = datetime.fromisoformat(item["window"]["end"])
    reference = datetime.fromisoformat(item["window"]["reference_time"])
    st.title(f"{selected} · {item['ticker']} · {start:%Y-%m-%d} {start:%H:%M}–{end:%H:%M} ET")
    st.caption(f"Reference time {reference:%Y-%m-%d %H:%M} ET · SIP minute bars, split-adjusted · "
               f"typical = median of the same window over {len(item['measurement']['reference_sessions'])} previous sessions")
    if reveal:
        st.session_state.setdefault("revealed", set()).add(selected)
        with st.expander("Draft candidate (not evidence; anchoring risk)", expanded=True):
            st.json(item["candidate"])

    if not rules.get("available"):
        st.error("No market data for this window: exclude it (A5/N6).")
    else:
        own = item["measurement"]["symbols"][item["ticker"]]
        columns = st.columns(5)
        for column, label, value, ratio in (
            (columns[0], "Total move M", _pct(own["today"]["total"]), rules["move_ratio"]),
            (columns[1], "Gap G", _pct(rules["gap"]), None),
            (columns[2], "In-window W", _pct(rules["in_window"]), None),
            (columns[3], "Range R", f"{own['today']['range']:.2%}", rules["range_ratio"]),
            (columns[4], "Volume", f"{own['today']['volume']:,.0f}", rules["volume_ratio"]),
        ):
            column.metric(label, value)
            if ratio is not None:
                column.caption(f"{_x(ratio)} the typical value")
        left, right = st.columns(2)
        left.plotly_chart(_price_chart(item), use_container_width=True)
        right.plotly_chart(_volume_chart(item), use_container_width=True)
        st.subheader("Criteria (market data)")
        st.dataframe(_criteria_rows(rules, item["ticker"], volume_required), hide_index=True,
                     use_container_width=True)
        excess = item["measurement"].get("excess_vs_qqq")
        if excess:
            st.caption(f"Excess move vs QQQ {_pct(excess['today'])} ({_x(excess['ratio'])} typical): "
                       "scope is stock-specific if ≥ 4×.")
        st.caption(f"Direction rule: sign of total move → **{rules['total_move_sign']}**")
        with st.expander("Typical values (median of the same window over the previous sessions)"):
            st.dataframe([
                {"symbol": symbol,
                 **{name: (f"{typical[name]:,.0f}" if name == "volume" else f"{typical[name]:.2%}")
                    if typical.get(name) is not None else "–"
                    for name in ("total", "gap", "in_window", "range", "volume")}}
                for symbol, value in item["measurement"]["symbols"].items()
                if (typical := value.get("typical"))
            ], hide_index=True, use_container_width=True)

    st.subheader("News for the ticker (A3 cause / N4 company news)")
    st.caption("Counts only if published after the reference time and before the window end. "
               "Open primary sources where possible (company IR, SEC, Fed, BLS/BEA).")
    st.dataframe(_news_rows(item), hide_index=True, use_container_width=True,
                 column_config={"url": st.column_config.LinkColumn("url")})
    st.markdown(
        f"**Macro calendar (N5):** [BLS schedule {start:%Y-%m}](https://www.bls.gov/schedule/{start:%Y}/{start:%m}_sched.htm) · "
        "[FOMC calendars](https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm) · "
        "[BEA release schedule](https://www.bea.gov/news/schedule)"
    )

    st.subheader("Your decision")
    locked = mode == "review" and not status["approved"]
    existing = records.get(selected, {})
    with st.form(f"decision-{selected}"):
        decision = st.radio("Label", ["— choose —", "anomaly", "normal", "exclude"],
                            index=["— choose —", "anomaly", "normal", "exclude"].index(existing.get("decision", "— choose —")),
                            horizontal=True)
        columns = st.columns(4)
        direction = columns[0].radio("Direction (anomaly)", ["up", "down"], horizontal=True,
                                     index=["up", "down"].index(existing.get("direction") or "up"))
        event_type = columns[1].selectbox("Event type (anomaly)", EVENT_TYPES,
                                          index=EVENT_TYPES.index(existing.get("event_type") or "other"))
        scope = columns[2].selectbox("Scope", ["stock-specific", "market-wide", "n/a"],
                                     index=["stock-specific", "market-wide", "n/a"].index(existing.get("scope") or "n/a"))
        confidence = columns[3].radio("Confidence", [0.9, 0.7], horizontal=True,
                                      index=[0.9, 0.7].index(existing.get("confidence") or 0.7))
        cause_urls = st.text_area("A3 cause: https sources, one per line", "\n".join(existing.get("cause_urls", [])))
        cause_published_at = st.text_input("A3 cause publication time (ET)", existing.get("cause_published_at", ""))
        columns = st.columns(3)
        company_news_found = columns[0].checkbox("N4: material company news found", existing.get("company_news_found", False))
        macro_release_found = columns[1].checkbox("N5: tier-1 macro release found", existing.get("macro_release_found", False))
        calendar_checked = columns[2].checkbox("I checked the macro calendars", existing.get("calendar_checked", False))
        company_news_note = st.text_input("N4 note", existing.get("company_news_note", ""))
        macro_release_note = st.text_input("N5 note", existing.get("macro_release_note", ""))
        exclusion_reason = st.text_input("Exclusion reason (if excluded)", existing.get("exclusion_reason", ""))
        reasoning = st.text_area("Reasoning (which rules hold or fail, and why)", existing.get("reasoning", ""))
        not_seen = st.checkbox("I have not seen CEP / Isolation Forest outputs for this interval",
                               existing.get("detector_outputs_not_seen", False))
        submitted = st.form_submit_button("Save decision", disabled=locked)
    if submitted:
        urls = [line.strip() for line in cause_urls.splitlines() if line.strip()]
        errors = []
        if not reviewer:
            errors.append("Enter your reviewer name in the sidebar.")
        if decision == "— choose —":
            errors.append("Choose a label.")
        if not reasoning.strip():
            errors.append("Write your reasoning.")
        if decision == "anomaly" and not urls:
            errors.append("An anomaly needs at least one https source (A3).")
        if any(not url.startswith("https://") for url in urls):
            errors.append("Sources must start with https://")
        if decision == "normal" and not calendar_checked:
            errors.append("A normal label needs the macro calendar check (N5).")
        if decision == "exclude" and not exclusion_reason.strip():
            errors.append("Give the exclusion reason.")
        if errors:
            for error in errors:
                st.error(error)
        else:
            candidate = item["candidate"]
            records[selected] = {
                "display_id": selected, "interval_id": candidate["interval_id"], "group": item["group"],
                "ticker": item["ticker"], "started_at": candidate["started_at"], "ended_at": candidate["ended_at"],
                "decision": decision, "direction": direction if decision == "anomaly" else None,
                "event_type": event_type if decision == "anomaly" else None, "scope": scope,
                "confidence": confidence, "exclusion_reason": exclusion_reason, "cause_urls": urls,
                "cause_published_at": cause_published_at, "company_news_found": company_news_found,
                "company_news_note": company_news_note, "macro_release_found": macro_release_found,
                "macro_release_note": macro_release_note, "calendar_checked": calendar_checked,
                "move_ratio": rules.get("move_ratio"), "volume_ratio": rules.get("volume_ratio"),
                "range_ratio": rules.get("range_ratio"), "gap": rules.get("gap"),
                "in_window": rules.get("in_window"), "direction_conflict": rules.get("direction_conflict"),
                "market_move_ratios": rules.get("market_move_ratios"), "coverage": rules.get("coverage"),
                "reasoning": reasoning.strip(), "reviewer": reviewer,
                "reviewed_at": datetime.now(timezone.utc).isoformat(),
                "criteria_version": status["line"].strip("*"),
                "draft_revealed_before_decision": selected in st.session_state.get("revealed", set()),
                "detector_outputs_not_seen": not_seen,
            }
            _save_records(_records_path(mode, reviewer), records)
            st.success(f"Saved {selected}.")

    st.divider()
    st.subheader("Export")
    if st.button("Write export files", disabled=not reviewer or not records):
        slug = ("demo-" if mode == "demo" else "") + _slug(reviewer)
        csv_text = review_csv(records)
        (OUTPUT / f"{slug}_review.csv").write_text(csv_text)
        if mode == "review":
            draft = json.loads(DRAFT.read_text())
            candidates = {value["candidate"]["interval_id"]: value["candidate"] for value in items.values()}
            registry, problems = reviewed_registry(draft, candidates, records)
            (OUTPUT / f"{slug}_reviewed_labels.json").write_text(json.dumps(registry, indent=2) + "\n")
            for problem in problems:
                st.warning(problem)
            if not problems:
                st.success("Reviewed labels pass validation; next: replay.labels freeze.")
        st.success(f"Wrote {OUTPUT / (slug + '_review.csv')}")
        st.download_button("Download review CSV", csv_text, f"{slug}_review.csv", "text/csv")


main()
