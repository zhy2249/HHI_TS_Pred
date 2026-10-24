#!/usr/bin/env python3
"""Pair read-only R13 stage SSE observations; never compute BD from short runs."""
import argparse
import csv
import math
from pathlib import Path


def parse(path):
    headers, tables = {}, {'FRAME': {}, 'FRAME_TILE': {}}
    for line in path.read_text(errors='replace').splitlines():
        for name in tables:
            if line.startswith(f'TS_R13_{name}_HEADER '):
                if name in headers:
                    raise ValueError('Duplicate stage table header')
                headers[name] = line.split(' ', 1)[1].split(',')
            elif line.startswith(f'TS_R13_{name} '):
                values = line.split(' ', 1)[1].split(',')
                if name not in headers or len(values) != len(headers[name]):
                    raise ValueError('Missing/truncated stage table header or row')
                row = dict(zip(headers[name], values))
                row = {k: v if k == 'stage' else int(v) for k, v in row.items()}
                key = (row['poc'], row['layer'], row['stage'], row['component'])
                if name == 'FRAME_TILE':
                    key += (row['x'], row['y'])
                if key in tables[name]:
                    raise ValueError('Duplicate stage observation')
                tables[name][key] = row
    if not all(tables.values()):
        raise ValueError('No stage diagnostics; TS_R13_DIAG defaults OFF')
    totals = {}
    for key, row in tables['FRAME_TILE'].items():
        group = totals.setdefault(key[:4], [0, 0])
        group[0] += row['samples']
        group[1] += row['sse']
    if set(totals) != set(tables['FRAME']):
        raise ValueError('Frame/tile populations differ')
    for key, (samples, sse) in totals.items():
        row = tables['FRAME'][key]
        if row['samples'] != samples or row['sse'] != sse:
            raise ValueError('Tile/frame SSE or population mismatch')
    return tables


def compare(reference, test):
    result = {'FRAME': [], 'FRAME_TILE': []}
    for name in result:
        if reference[name].keys() != test[name].keys():
            raise ValueError('Unpaired stage observations')
        for key, base in reference[name].items():
            row = test[name][key]
            for field in ('samples', 'bitdepth', 'original_hash', 'true_original',
                          'width', 'height', 'clip_pending'):
                if base[field] != row[field]:
                    raise ValueError(f'Incomparable stage input/domain: {field}')
            record = {k: row[k] for k in ('poc', 'layer', 'stage', 'component', 'bitdepth',
                                          'width', 'height', 'clip_pending', 'samples')}
            if name == 'FRAME_TILE':
                record.update(x=row['x'], y=row['y'])
            record.update(reference_sse=base['sse'], test_sse=row['sse'],
                          delta_sse=row['sse']-base['sse'],
                          delta_sse_percent=100*(row['sse']/base['sse']-1) if base['sse'] else '',
                          delta_psnr_db=-10*math.log10(row['sse']/base['sse'])
                          if base['sse'] and row['sse'] else '',
                          reconstruction_hash_equal=int(base['reconstruction_hash'] == row['reconstruction_hash']))
            result[name].append(record)
    return result


def write(path, rows):
    if rows:
        with path.open('w', newline='') as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference', required=True, type=Path)
    parser.add_argument('--test', required=True, type=Path)
    parser.add_argument('--output-dir', required=True, type=Path)
    args = parser.parse_args()
    paired = compare(parse(args.reference), parse(args.test))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    # Retain both signs, rank by absolute effect within frame/stage/component.
    groups = {}
    for row in paired['FRAME_TILE']:
        key = tuple(row[k] for k in ('poc', 'layer', 'stage', 'component'))
        groups.setdefault(key, []).append(row)
    top = []
    for frame in paired['FRAME']:
        key = tuple(frame[k] for k in ('poc', 'layer', 'stage', 'component'))
        tiles = groups[key]
        frame['tiles'] = len(tiles)
        frame['changed_hash_tiles'] = sum(not t['reconstruction_hash_equal'] for t in tiles)
        frame['positive_delta_sse_sum'] = sum(max(0, t['delta_sse']) for t in tiles)
        frame['negative_delta_sse_sum'] = sum(min(0, t['delta_sse']) for t in tiles)
        top.extend(sorted(tiles, key=lambda t: abs(t['delta_sse']), reverse=True)[:8])
    write(args.output_dir / 'frame_stage.csv', paired['FRAME'])
    write(args.output_dir / 'top_tiles.csv', top)
    print(f"Paired {len(paired['FRAME'])} frame stages; tile SSE conservation verified")


if __name__ == '__main__':
    main()
