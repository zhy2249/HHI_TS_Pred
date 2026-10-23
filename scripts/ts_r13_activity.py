#!/usr/bin/env python3
"""Extract final-Writer R13 shadow aggregates; does not compute BD-rate."""
import argparse
import csv
from pathlib import Path

HEADER = 'TS_R13_STATS_HEADER '
ROW = 'TS_R13_STATS '
REQUIRED = {'trajectory_policy', 'shadow_mode', 'component', 'width', 'height',
            'cu_qp', 'cutoff', 'n', 'weight_sum', 'tu_count', 'cg_count',
            'coeff_count', 'scored_count', 'valid_margin_count', 'margin_sum168'}


def parse(text):
    """Keep sentinel total rows and per-mode denominators separate, without pooling."""
    columns = None
    rows = []
    for line in text.splitlines():
        if line.startswith(HEADER):
            found = line[len(HEADER):].split(',')
            if len(set(found)) != len(found) or not REQUIRED.issubset(found):
                raise ValueError('Invalid R13 statistics header')
            if columns is not None:
                raise ValueError('Multiple R13 reports in one log: split runs before extraction')
            columns = found
        elif line.startswith(ROW):
            if columns is None:
                raise ValueError('R13 row before header')
            fields = line[len(ROW):].split(',')
            if len(fields) != len(columns):
                raise ValueError('Truncated or incompatible R13 statistics row')
            record = dict(zip(columns, map(int, fields)))
            if record['shadow_mode'] not in (1, 2):
                raise ValueError('Unknown R13 shadow mode')
            if record['valid_margin_count'] > record['scored_count']:
                raise ValueError('Invalid margin denominator')
            rows.append(record)
    return rows


def export(inputs, output, sequence='', configuration='', nominal_qp=''):
    if any(path.resolve() == output.resolve() for path in inputs):
        raise ValueError('CSV output must not overwrite an input log')
    records = []
    columns = None
    for path in inputs:
        rows = parse(path.read_text(errors='replace'))
        if not rows:
            raise ValueError(f'{path}: no R13 statistics; default observation is OFF')
        found = tuple(rows[0])
        if columns is not None and found != columns:
            raise ValueError('Input logs have different R13 schema revisions')
        columns = found
        for row in rows:
            count, weight = row['valid_margin_count'], row['weight_sum']
            # No score for n<3; a single distinct candidate has no runner-up.
            margin = row['margin_sum168'] / (168 * weight * count) if count and weight > 0 else ''
            records.append(dict(source_log=str(path), sequence=sequence, configuration=configuration,
                                nominal_qp=nominal_qp, **row, mean_margin_per_weight=margin))
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)
    return len(records)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('logs', type=Path, nargs='+')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--sequence', default='', help='Optional caller label, not inferred from log name')
    parser.add_argument('--configuration', default='')
    parser.add_argument('--nominal-qp', default='', help='Optional job QP; cu_qp is kept separately')
    args = parser.parse_args()
    count = export(args.logs, args.output, args.sequence, args.configuration, args.nominal_qp)
    print(f'{count} R13 aggregate rows -> {args.output}; each shadow mode has its own denominator')


if __name__ == '__main__':
    main()
