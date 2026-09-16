#!/usr/bin/env python3
"""Recover completed fixed-predictor reports without launching any codec process."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re

from batch_test import _parse_encoder_summary, _write_summary
from xlsm_table_fill import fill_jvet_hhi_test_sheet


def identity(path):
    p = Path(path)
    st = p.stat()
    return [str(p), st.st_size, st.st_mtime_ns]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run', type=Path, required=True)
    p.add_argument('--modes', default='nopred,gradient')
    p.add_argument('--template', type=Path, default=Path('scripts/JVET-hhi.xlsm'))
    p.add_argument('--decoder', type=Path, default=Path('build/ts-fixed/bin/DecoderApp'))
    args = p.parse_args()
    root = args.run.resolve()
    template = args.template.resolve()
    template_hash = hashlib.sha256(template.read_bytes()).hexdigest()
    plan = json.loads((root / 'experiment_plan.json').read_text())
    expected = Counter(j['predictor'] for j in plan)
    rows, pending, resumable = [], [], Counter()
    for job in plan:
        bit = Path(job['bitstream'])
        marker_path = bit.with_suffix('.done.json')
        if not marker_path.is_file():
            pending.append(job)
            continue
        marker = json.loads(marker_path.read_text())
        row = marker['result']
        mode = job['predictor']
        assert row['fixed_predictor'] == marker['fixed_predictor'] == mode, marker_path
        assert row['sequence'] == job['sequence'] and row['qp'] == job['qp'], marker_path
        assert row['frames'] == row['encoded_frames'] == job['frames'], marker_path
        assert row['encode_status'] == row['decode_status'] == 'ok', marker_path
        assert row['error_info'] == 'pass', marker_path
        assert bit.stat().st_size == marker['bitstream_bytes'] > 0, marker_path
        enc = Path(row['encode_log']).read_text(errors='replace')
        dec = Path(row['decode_log']).read_text(errors='replace')
        banner = f'EXPERIMENT: TS_FIXED_PREDICTOR={mode}; syntax=experimental-v1'
        assert banner in enc and banner in dec, marker_path
        assert 'RETURNCODE: 0' in enc and 'RETURNCODE: 0' in dec, marker_path
        assert dec.count('(OK)') == job['frames'] and not re.search(r'ERROR|MISMATCH', dec), marker_path
        parsed = _parse_encoder_summary(enc)
        for key in ('encoded_frames', 'kbps', 'ypsnr', 'upsnr', 'vpsnr'):
            assert parsed[key] == row[key], (marker_path, key)
        rows.append(row)
        # Verify the exact resume fingerprint for the documented command defaults.
        cmd = marker['command']
        cfgs = [Path(cmd[i + 1]) for i, v in enumerate(cmd) if v == '-c']
        fp = hashlib.sha256(json.dumps({
            'encoder': identity(cmd[0]), 'input': identity(job['input']),
            'cfgs': [(str(c), c.read_text(encoding='utf-8')) for c in cfgs],
            'qp': job['qp'], 'frames': job['frames'],
            'extra': cmd[cmd.index('-f') + 2:cmd.index('-o')],
            'decode': True, 'decoder_args': ['-dph', '1'], 'decoder': identity(args.decoder.resolve()),
            'fixed_predictor': mode, 'no_recon': True,
        }, sort_keys=True).encode()).hexdigest()
        if fp == marker['fingerprint']:
            resumable[mode] += 1
    modes = args.modes.split(',')
    complete = Counter(r['fixed_predictor'] for r in rows)
    for mode in modes:
        assert expected[mode] and complete[mode] == expected[mode], f'{mode} is not complete'
    for mode in modes:
        selected = [r for r in rows if r['fixed_predictor'] == mode]
        output = root / mode / 'JVET-hhi.xlsm'
        assert not output.exists(), f'Refusing to overwrite existing report: {output}'
        _write_summary(root / mode / 'summary.csv', selected)
        ok, message = fill_jvet_hhi_test_sheet(template_xlsm=template, output_xlsm=output,
                                              results=selected, condition_tag='lb')
        assert ok, message
        print(f'Recovered {mode}: {len(selected)} rows -> {output}')
    assert hashlib.sha256(template.read_bytes()).hexdigest() == template_hash
    for mode in expected:
        print(f'{mode}: verified={complete[mode]}/{expected[mode]}, resume-skip={resumable[mode]}')
    for job in pending:
        print(f"PENDING: {job['predictor']} {job['sequence']} QP{job['qp']}")
    (root / 'report_recovery_audit.json').write_text(json.dumps({
        'verified': dict(complete), 'resume_skip': dict(resumable), 'pending': pending,
        'template_sha256': template_hash, 'reports': modes,
    }, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
