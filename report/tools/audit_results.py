"""Freeze evaluation sources and emit a scenario-level reconciliation (no services)."""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import tarfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from evaluation.metrics import DetectedEvent, GroundTruthEvent, match_events
from evaluation.run_synthetic import run_evaluation_suite, run_protocol

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'report/ownership_evidence/reproduction_outputs/audit_20261022'
RUN_ID = 'audit-synthetic-20261022'


def dump(name, value):
    (OUT / name).write_text(json.dumps(value, indent=2, default=str) + '\n')


def main():
    global OUT, RUN_ID
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=OUT)
    parser.add_argument('--run-id', default=RUN_ID)
    args = parser.parse_args()
    OUT, RUN_ID = args.output.resolve(), args.run_id
    OUT.mkdir(parents=True, exist_ok=True)
    files = sorted(p for folder in ('baseline', 'cep', 'config', 'dashboard', 'evaluation',
                                  'ml', 'processing', 'producers', 'replay', 'scripts',
                                  'storage', 'tests')
                   for p in (ROOT / folder).rglob('*.py'))
    files += [ROOT / p for p in ('pyproject.toml', 'uv.lock', 'report/tools/audit_results.py')]
    hashes = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    snapshot = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()
    with tarfile.open(OUT / 'source_snapshot.tar.gz', 'w:gz') as archive:
        for p in files:
            archive.add(p, arcname=str(p.relative_to(ROOT)))
    dump('provenance.json', {
        'run_id': RUN_ID, 'generated_at': datetime.now(timezone.utc),
        'base_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        'dirty_tree': bool(subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=no'],
                                                   cwd=ROOT, text=True).strip()),
        'source_manifest_sha256': snapshot, 'source_files': hashes,
        'archive': 'source_snapshot.tar.gz', 'python': platform.python_version(),
        'command': f'.venv/bin/python -m report.tools.audit_results --output {OUT.relative_to(ROOT)} --run-id {RUN_ID}',
        'data_source': 'evaluation/synthetic_scenarios.py; no external market data',
        'labels': 'generated expected_pattern/direction; generator hash above',
        'parameters': {'seeds': 20, 'intensities': {'low': 4.5, 'medium': 6.5, 'high': 9.0},
                       'cooldown_seconds': 0, 'require_pattern': True, 'grace_after_seconds': 0},
        'scope': 'controlled factor-sequence validation; not market effectiveness',
    })
    records = []
    result = run_protocol(20, scenario_records=records)
    dump('factor_cep_traced.json', result)
    # Count independently from retained rows; do not infer alert counts from alerting cases.
    totals = Counter()
    details = Counter()
    all_truth, all_detections = [], []
    for row in records:
        truth = [GroundTruthEvent(**v) for v in row['truth']]
        detections = [DetectedEvent(**v) for v in row['detections']]
        matches, fp, fn = match_events(truth, detections)
        row['tp'], row['fp'], row['fn'] = len(matches), len(fp), len(fn)
        row['unmatched_detections'] = [v.detection_id for v in fp]
        kind = row['kind']
        totals[f'{kind}_cases'] += 1
        totals[f'{kind}_alerts'] += len(detections)
        totals[f'{kind}_alerting_cases'] += bool(detections)
        totals[f'{kind}_tp'] += len(matches)
        totals[f'{kind}_fp'] += len(fp)
        totals[f'{kind}_fn'] += len(fn)
        details[(kind, row['name'], row['intensity'])] += len(fp)
        all_truth.extend(truth)
        all_detections.extend(detections)
    global_matches, global_fp, global_fn = match_events(all_truth, all_detections)
    assert len(global_matches) == sum(row['tp'] for row in records)
    assert len(global_fp) == sum(row['fp'] for row in records) == result['metrics']['false_positives']
    assert len(global_fn) == sum(row['fn'] for row in records)
    assert totals['negative_control_alerting_cases'] == result['negative_controls']['alerts']
    dump('scenarios.json', records)
    dump('reconciliation.json', {'counts': dict(totals), 'fp_by_scenario_and_intensity': [
        {'kind': k[0], 'scenario': k[1], 'intensity': k[2], 'fp': v}
        for k, v in sorted(details.items())], 'global_matches_equal_partitioned_matches': True})
    dump('factor_cep_suite.json', run_evaluation_suite(20))
    print(json.dumps({'run_id': RUN_ID, 'counts': dict(totals)}))


if __name__ == '__main__':
    main()
