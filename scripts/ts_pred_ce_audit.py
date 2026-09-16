#!/usr/bin/env python3
"""Audit the frozen C/E pilot and decompose causal gains without fitting new selectors."""
import argparse
from collections import Counter, defaultdict
import csv
import json
from pathlib import Path
import random

from ts_pred_analyze import SELECTORS, SCALE, write_csv, quantile

C = {'BasketballDrill', 'BQMall', 'PartyScene', 'RaceHorsesC'}
E = {'FourPeople', 'Johnny', 'KristenAndSara'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, default=Path('runs/ts_CE'))
    parser.add_argument('--out', type=Path, default=Path('runs/ts_CE/ce_audit'))
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    expected = {(seq, cfg, qp) for seq in C | E for cfg in ('ai', 'lb') for qp in (22, 27, 32, 37)}
    observed = set()
    totals = defaultdict(Counter)
    mode_counts = defaultdict(Counter)
    jobs, digest = [], []
    # Paired frame-cluster sums, kept jointly across nominal QPs/configurations for sequence review.
    clusters = defaultdict(lambda: [0] * 13)
    for cfg in ('AI', 'LB'):
        with (args.run / cfg / 'summary.csv').open(encoding='utf-8', newline='') as f:
            summary = list(csv.DictReader(f))
        assert len(summary) == 28
        for row in summary:
            assert row['encode_status'] in ('ok', 'skipped_exists'), row
            assert row['decode_status'] in ('ok', 'skipped_exists'), row
            assert int(row['encoded_frames']) == 16, row
    for marker_file in sorted((args.run / 'stats').rglob('*.done.json')):
        marker = json.loads(marker_file.read_text(encoding='utf-8'))
        key = marker['sequence'], marker['configuration'], marker['QP']
        assert key in expected and key not in observed, key
        observed.add(key)
        file = marker_file.with_suffix('').with_suffix('.csv')
        assert file.stat().st_size == marker['stats_bytes'], file
        census_file = Path(str(file) + '.tu.csv')
        assert census_file.stat().st_size == marker['census_bytes'], file
        command = marker['command']
        bitstream = Path(command[command.index('-b') + 1])
        assert bitstream.stat().st_size == marker['bitstream_bytes'], bitstream
        assert command[command.index('-f') + 1] == '16' and '--TemporalSubsampleRatio=1' in command
        decode_log = bitstream.with_suffix('.decode.log').read_text(encoding='utf-8')
        assert decode_log.count('(OK)') == 16 and 'ERROR' not in decode_log, bitstream
        local = Counter()
        prior_informative, prior_positive, prior_nz, last_tu = False, False, False, None
        seen_tu, seen_poc = set(), set()
        with file.open(encoding='utf-8', newline='') as f:
            for row in csv.DictReader(f):
                for k in ('TU_id', 'CG_index', 'CG_count_in_TU', 'num_nonzero', 'num_coeff', 'oracle_tie_mask',
                          'oracle_mode', 'POC', 'TU_width', 'TU_height', 'bdpcm'):
                    row[k] = int(row[k])
                assert (row['sequence'], row['configuration'], int(row['QP'])) == key
                if row['TU_id'] != last_tu:
                    prior_informative = prior_positive = prior_nz = False
                    assert row['CG_index'] == 0
                    last_tu = row['TU_id']
                seen_tu.add(row['TU_id']); seen_poc.add(row['POC'])
                rates = [int(row[f'pred{m}_rate']) for m in range(6)]
                a, oracle, mask = rates[1], min(rates), row['oracle_tie_mask']
                assert a == int(row['current_pred_rate']) == int(row['pred1_path_rate'])
                assert oracle == int(row['oracle_rate'])
                d = Counter(cg=1, tu=int(row['CG_index'] == 0), coefficients=row['num_coeff'], nonzero=row['num_nonzero'],
                            zero_cg=int(row['num_nonzero'] == 0), anchor=a, oracle=oracle, oracle_saving=a - oracle,
                            informative=int(max(rates) != oracle), current_in_oracle=int(bool(mask & 2)),
                            current_strictly_beaten=int(a > oracle), unique_oracle=int(mask.bit_count() == 1),
                            all_six_tie=int(mask == 63), bdpcm_cg=int(row['bdpcm'] != 0))
                for m in range(6):
                    d[f'fixed{m}'] = rates[m]
                    d[f'path_fixed{m}'] = int(row[f'pred{m}_path_rate'])
                    d[f'candidate{m}_beats_current_cg'] = int(rates[m] < a)
                    d[f'candidate{m}_win_saving'] = max(0, a - rates[m])
                    d[f'candidate{m}_loss_cost'] = max(0, rates[m] - a)
                    d[f'candidate{m}_unique_oracle'] = int(mask == 1 << m)
                for s, name in enumerate(SELECTORS):
                    mode = int(row[f'{name}_mode'])
                    gain = a - rates[mode]
                    d[f'{name}_gain'] = gain
                    d[f'{name}_path_gain'] = a - int(row[f'selector{s}_path_rate'])
                    d[f'{name}_selected_alternative'] = int(mode != 1)
                    d[f'{name}_positive_cg'] = int(gain > 0)
                    d[f'{name}_negative_cg'] = int(gain < 0)
                    d[f'{name}_zero_cg'] = int(gain == 0)
                    d[f'{name}_positive_bits'] = max(gain, 0)
                    d[f'{name}_negative_bits'] = max(-gain, 0)
                    mode_counts[name][mode] += 1
                d['simple_recency_agreement'] = int(row['simple_mode'] == row['recency_mode'])
                d['simple_recency_either_alt'] = int(row['simple_mode'] != '1' or row['recency_mode'] != '1')
                d['simple_recency_agree_either_alt'] = int(row['simple_mode'] == row['recency_mode'] and row['simple_mode'] != '1')
                if row['CG_index'] == 0:
                    assert all(int(row[f'{name}_mode']) == 1 for name in SELECTORS)
                if not prior_positive:
                    assert all(int(row[f'{name}_mode']) == 1 for name in SELECTORS[:4]), (file, row['TU_id'])
                class_name = 'C' if key[0] in C else 'E'
                labels = ['overall', f'class:{class_name}', f'config:{key[1]}', f'class_config:{class_name}/{key[1]}',
                          f'job:{key[0]}/{key[1]}/{key[2]}', f'seq_config:{key[0]}/{key[1]}',
                          f'cg_position:{"first" if row["CG_index"] == 0 else "history"}',
                          f'prior_informative:{int(prior_informative)}', f'prior_positive:{int(prior_positive)}',
                          f'prior_nonzero:{int(prior_nz)}',
                          f'group_nonzero:{int(row["num_nonzero"] != 0)}',
                          f'size:{row["TU_width"]}x{row["TU_height"]}']
                for label in labels:
                    totals[label].update(d)
                local.update(d)
                cl = clusters[(key[0], key[1], key[2], row['POC'])]
                cl[0] += a; cl[1] += oracle
                cl[2] += (a - oracle) if row['CG_index'] else 0
                for s, name in enumerate(SELECTORS):
                    cl[3 + s] += d[f'{name}_gain']
                    cl[8 + s] += d[f'{name}_path_gain']
                prior_informative |= max(rates) != oracle
                prior_positive |= a > oracle
                prior_nz |= row['num_nonzero'] > 0
        with census_file.open(encoding='utf-8', newline='') as f:
            census = list(csv.DictReader(f))
        assert len(census) == len(seen_tu)
        assert all(r['tsrc_enabled'] == '1' for r in census)
        total_bits = bitstream.stat().st_size * 8
        jobs.append(dict(sequence=key[0], configuration=key[1], QP=key[2], cg=local['cg'], tu=local['tu'],
                         pocs_with_ts=len(seen_poc), encoded_pocs=16, total_bits=total_bits,
                         anchor_bits=local['anchor'] / SCALE, oracle_saving_bits=local['oracle_saving'] / SCALE,
                         recency_saving_bits=local['recency_gain'] / SCALE,
                         oracle_gain=local['oracle_saving'] / local['anchor'] if local['anchor'] else None,
                         recency_gain=local['recency_gain'] / local['anchor'] if local['anchor'] else None))
        digest.append(dict(marker=str(marker_file), fingerprint=marker['fingerprint'], stats_bytes=marker['stats_bytes']))
    assert observed == expected, sorted(expected - observed)
    verified_file = args.run / 'review_verified' / 'analysis.json'
    if verified_file.is_file():
        verified = json.loads(verified_file.read_text(encoding='utf-8'))['overall']
        for raw, reference in [('cg', 'cg_count'), ('tu', 'ts_tu_count'), ('coefficients', 'coefficient_count'),
                               ('nonzero', 'nonzero_count')]:
            assert totals['overall'][raw] == verified[reference]
        assert totals['overall']['anchor'] == verified['pred1_rate'] * SCALE
        assert totals['overall']['oracle'] == verified['oracle_rate'] * SCALE
        for s, name in enumerate(SELECTORS):
            assert totals['overall'][name + '_gain'] == (verified['pred1_rate'] - verified[f'selector{s}_rate']) * SCALE
    rows = []
    for group, raw in sorted(totals.items()):
        row = dict(group=group, **raw)
        for name in ['oracle_saving', *[f'{s}_gain' for s in SELECTORS], *[f'{s}_path_gain' for s in SELECTORS]]:
            row[name + '_relative'] = raw[name] / raw['anchor'] if raw['anchor'] else None
            row[name + '_bits'] = raw[name] / SCALE
        rows.append(row)
    write_csv(args.out / 'ce_decomposition.csv', rows)
    write_csv(args.out / 'ce_jobs.csv', jobs)
    # Sequence-cluster bootstrap preserves QP/configuration and all frame dependencies inside each sequence.
    sequence_blocks = defaultdict(lambda: [0] * 13)
    for key, value in clusters.items():
        for i, x in enumerate(value): sequence_blocks[key[0]][i] += x
    rng = random.Random(20260911)
    samples = list(sequence_blocks.values())
    ci_draws = defaultdict(list)
    for _ in range(2000):
        draw = rng.choices(samples, k=len(samples))
        sumv = [sum(x[i] for x in draw) for i in range(13)]
        ci_draws['oracle_gain'].append((sumv[0] - sumv[1]) / sumv[0])
        for s, name in enumerate(SELECTORS):
            ci_draws[name + '_gain'].append(sumv[3 + s] / sumv[0])
            ci_draws[name + '_path_gain'].append(sumv[8 + s] / sumv[0])
            ci_draws[name + '_capture'].append(sumv[3 + s] / (sumv[0] - sumv[1]))
    ci = {name: [quantile(values, .025), quantile(values, .975)] for name, values in ci_draws.items()}
    result = dict(tasks=len(jobs), frame_encodings=len(jobs) * 16, total_bitstream_bits=sum(j['total_bits'] for j in jobs),
                  totals={k: dict(v) for k, v in totals.items()}, selector_mode_counts={k: dict(v) for k, v in mode_counts.items()},
                  rate_units='raw counters: fractional bits / 32768', sequence_bootstrap_2000=ci,
                  markers=digest, note='Descriptive CE audit, no predictor/threshold fitting and no new encoding')
    (args.out / 'ce_audit.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps({k: result[k] for k in ('tasks', 'frame_encodings', 'total_bitstream_bits', 'sequence_bootstrap_2000')}, indent=2))


if __name__ == '__main__':
    main()
