#!/usr/bin/env python3
"""R10 target-level final-Writer observations; not CABAC replay rate or BD-rate."""
import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from ts_predictor_naming import R10_MODE_NUMBERS
from ts_r9_activity import write

DIMENSIONS = ('mode component width height cu_qp intra bdpcm cg_count cg_index n n1 d cutoff '
              'validation_size effective_samples distinct_actions selected_expert best_target_ci best_target_cf').split()

def parse(text, mode):
    header = None
    rows = []
    for line in text.splitlines():
        if line.startswith('TS_R10_STATS_HEADER '):
            if header is not None:
                raise ValueError('Duplicate R10 section')
            header = line.split(' ', 1)[1].split(',')
        elif line.startswith('TS_R10_STATS '):
            values = line.split(' ', 1)[1].split(',')
            if header is None or len(header) != len(values):
                raise ValueError('Malformed R10 statistics')
            r = dict(zip(header, map(int, values)))
            if r['mode'] != mode or r['cutoff'] not in (-1, 0, 2, 10):
                raise ValueError('Invalid R10 mode/cutoff')
            if r['regular_nonzero'] > r['regular_count'] or r['remap_vs_r9_9'] > r['regular_nonzero']:
                raise ValueError('Invalid R10 denominator')
            if (r['cutoff'] == 0 or r['bdpcm']) and r['regular_count']:
                raise ValueError('No predictor observations allowed for pure bypass / BDPCM')
            if r['regular_count']:
                if not 0 <= r['effective_samples'] <= r['validation_size'] <= 5:
                    raise ValueError('Invalid local validation set')
                if not 0 <= r['selected_expert'] < (4 if mode == 6 else 3):
                    raise ValueError('Invalid expert')
            if any(v < 0 for k, v in r.items() if k not in DIMENSIONS):
                raise ValueError('Losses/regrets/counts cannot be negative')
            rows.append(r)
    return rows

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('root', type=Path)
    p.add_argument('--out', type=Path, required=True)
    args = p.parse_args()
    jobs = {}
    for summary in args.root.rglob('summary.csv'):
        with summary.open(newline='') as f:
            for r in csv.DictReader(f):
                if r.get('fixed_predictor') in R10_MODE_NUMBERS and r.get('error_info') == 'pass':
                    jobs[Path(r['encode_log']).resolve()] = r
    detailed, totals, status = [], [], []
    for log, j in sorted(jobs.items()):
        text = log.read_text(errors='replace')
        mode = R10_MODE_NUMBERS[j['fixed_predictor']]
        if f'TS R10 revision=R10-20260928-v1; mode={mode};' not in text:
            raise ValueError(f'Wrong executable: {log}')
        rows = parse(text, mode)
        meta = dict(job=j['name'], sequence=j['sequence'], qp=j['qp'], runtime=j['fixed_predictor'], encode_log=str(log))
        detailed.extend({**meta, **r} for r in rows)
        status.append({**meta, 'stats_present': bool(rows)})
        if rows:
            total = Counter()
            for r in rows:
                total.update({k: v for k, v in r.items() if k not in DIMENSIONS})
            totals.append({**meta, **dict(total)})
    args.out.mkdir(parents=True, exist_ok=True)
    write(args.out / 'final_by_stratum.csv', detailed)
    write(args.out / 'final_by_job.csv', totals)
    write(args.out / 'log_status.csv', status)
    audit = dict(jobs=len(jobs), rows=len(detailed), bdrate_measured=False,
                 input_log_bytes=sum(p.stat().st_size for p in jobs),
                 warnings=['Selected-final-TS population only', 'All cost fields Q15; CF is CG-entry-frozen local approximation',
                           'Actual cutoff is observation only; hypothetical candidates do not update budget/contexts',
                           'D fields absent unless mode=6; zero D fields are not zero-loss expert evidence',
                           'No rows means disabled statistics or no TS, not measured zero activity'])
    (args.out / 'audit.json').write_text(json.dumps(audit, indent=2) + '\n')
    print(json.dumps(audit, indent=2))

if __name__ == '__main__':
    main()
