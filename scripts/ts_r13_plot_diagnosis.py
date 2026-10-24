#!/usr/bin/env python3
"""Plot three observed filter-stage contrasts from the R13 anomaly short runs."""
import argparse
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from ts_r13_frame_diagnosis import compare, parse
from ts_r13_log_diagnosis import write_csv


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', type=Path, default=Path('runs/r13_diagnosis_20261024'))
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    cases = [
        ('Johnny QP32 / POC0 / U', 'diag_probe/current', 'diag_probe/spatial_all', 0, 1),
        ('Johnny QP27 / POC8 / V', 'diag_followup/johnny_q27_f17_current',
         'diag_followup/johnny_q27_f17_r13_keep_hit_spatial', 8, 2),
        ('KristenAndSara QP32 / POC0 / U', 'diag_followup/kristenandsara_q32_f1_current',
         'diag_followup/kristenandsara_q32_f1_r13_keep_hit_spatial', 0, 1),
    ]
    stages = ['before_dbf', 'after_dbf', 'after_sao_bif', 'after_ccsao_clip',
              'after_alf', 'after_lfcccm', 'final_clip']
    labels = ['Pre-DBF', 'DBF', 'SAO/BIF*', 'CCSAO\n+clip', 'ALF/\nCCALF', 'LFCCCM', 'Final']
    figure, axes = plt.subplots(1, 3, figsize=(14, 4), sharey=True, layout='constrained')
    data = []
    for axis, (title, reference, test, poc, component) in zip(axes, cases):
        logs = []
        for folder in (reference, test):
            matches = list((args.run_dir / folder).rglob('*.encode.log'))
            if len(matches) != 1:
                raise ValueError(f'Expected exactly one source log: {folder}')
            logs.append(matches[0])
        rows = compare(parse(logs[0]), parse(logs[1]))['FRAME']
        selected = {row['stage']: row for row in rows if row['poc'] == poc and row['component'] == component}
        values = [selected[s]['delta_psnr_db'] for s in stages]
        if any(not isinstance(v, float) for v in values):
            raise ValueError('Undefined stage dB contrast')
        axis.axhline(0, color='#6b7280', linewidth=1)
        axis.plot(range(len(stages)), values, marker='o', color='#2563eb', linewidth=2)
        axis.set_xticks(range(len(stages)), labels, fontsize=8, rotation=35)
        axis.set_title(title, fontsize=11)
        axis.grid(axis='y', alpha=.2)
        for stage in stages:
            data.append(dict(case=title, **selected[stage]))
    axes[0].set_ylabel('R13-2 minus Current (dB; positive = lower SSE)')
    figure.suptitle('Same-frame stage contrasts: onset and filtering response differ by case', fontsize=12)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    figure.savefig(args.output_dir / 'stage_deltas.png', dpi=160)
    plt.close(figure)
    write_csv(args.output_dir / 'plot_stage_deltas.csv', data)
    print('Three panels saved; *SAO/BIF is pre-joint-clip; no standalone filter ablation or BD-rate claim')


if __name__ == '__main__':
    main()
