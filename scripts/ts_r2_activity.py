#!/usr/bin/env python3
"""Extract online R2/R3/R4/R5/R6 activity aggregates from encoder logs (NOT an RD gain estimator)."""
import argparse
import csv
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('logs', type=Path, nargs='+', help='Encoder log files or directories')
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--revision', choices=('r2', 'r3', 'r4', 'r5', 'r6'), default='r2')
    args = parser.parse_args()
    prefix = 'TS_' + args.revision.upper() + '_STATS'
    files = set()
    for path in args.logs:
        files.update(path.rglob('*.log') if path.is_dir() else [path])
    args.out.parent.mkdir(parents=True, exist_ok=True)
    fields = None
    total = 0
    with args.out.open('w', newline='') as output:
        writer = None
        for path in sorted(files):
            header = None
            with path.open(errors='replace') as source:
                for line in source:
                    if line.startswith(prefix + '_HEADER '):
                        header = line.strip().split(' ', 1)[1].split(',')
                        if fields is None:
                            fields = header
                            writer = csv.writer(output)
                            writer.writerow(['log', *fields])
                        if header != fields:
                            raise ValueError(f'Mixed statistics columns: {path}')
                    elif line.startswith(prefix + ' '):
                        values = line.strip().split(' ', 1)[1].split(',')
                        if header is None or len(values) != len(header):
                            raise ValueError(f'Malformed statistics: {path}')
                        writer.writerow([str(path), *map(int, values)])
                        total += 1
    if not total:
        raise SystemExit(f'No {args.revision} aggregates found; check effective mode and completed encoder logs')
    print(f'{total} aggregate rows -> {args.out}; conditional final-TS activity only, not BD-rate')


if __name__ == '__main__':
    main()
