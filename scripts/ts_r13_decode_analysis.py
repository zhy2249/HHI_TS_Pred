#!/usr/bin/env python3
"""Summarize the preregistered R13 decoder diagnosis pairs, without BD-rate."""
import argparse
from collections import Counter
import json
from pathlib import Path

from ts_r13_decode_diagnosis import records, compare_rows, sha, validate_stages, write_rows
from ts_r13_frame_diagnosis import parse as encoder_stages

PAIRS = [('j32_eq_p16', 'j32_sp_p16'), ('j32_c0_p0', 'j32_sp_p0'),
         ('j27_c0_p8', 'j27_sp_p8'), ('j27_eq_p8', 'j27_sp_p8'),
         ('ks32_c0_p0', 'ks32_sp_p0'), ('ks32_eq_p0', 'ks32_sp_p0')]
EDGES = [('after_sao_bif', 'after_sao_bif_clip_only', 'clip_only_private_metric'),
         ('after_sao_bif', 'after_ccsao_before_clip', 'CCSAO'),
         ('after_ccsao_before_clip', 'after_ccsao_clip', 'joint_clip'),
         ('after_ccsao_clip', 'after_ordinary_alf', 'ordinary_ALF'),
         ('after_ordinary_alf', 'after_alf', 'CCALF'),
         ('after_alf', 'after_lfcccm', 'LFCCCM'),
         ('after_lfcccm', 'final_clip', 'adapted_luma_clip')]


def collect(root, output):
    rows, metadata, stages, filters, effects, validation, ctu_effects = {}, [], [], [], [], [], []
    for path in sorted(root.glob('*/case.json')):
        name = path.parent.name
        case = json.loads(path.read_text())
        case.setdefault('source_snapshot_scope', 'runtime worktree snapshot, not an attestation of all binary compilation inputs')
        log = path.parent / 'decode.log'
        if sha(log) != case['output_log_sha256'] or not case['observer_off_checked_frames']:
            raise ValueError(f'Missing observer validation or log changed: {path}')
        data = records(log)
        validate_stages(data)
        rows[name] = data
        metadata.append(dict(case=name, **case))
        frame = {(r['poc'], r['stage'], r['component']): r for r in data if r['kind'] == 'frame'}
        marker = json.loads(Path(case['source_done']).read_text())
        encoder = encoder_stages(Path(marker['result']['encode_log']))['FRAME'].values()
        encoder = {(int(r['poc']), r['stage'], int(r['component'])): r for r in encoder}
        common = 0
        for key, row in frame.items():
            stages.append(dict(case=name, **row))
            if key in encoder:
                for f in ('samples', 'sse', 'original_hash', 'reconstruction_hash'):
                    if row[f] != int(encoder[key][f]):
                        raise ValueError(f'Encoder/decoder stage mismatch: {name}, {key}, {f}')
                common += 1
        if common != 21:  # seven original stages * YUV for one selected POC
            raise ValueError(f'Unexpected common-stage population: {name}: {common}')
        filters.extend(dict(case=name, **r) for r in data if r['kind'] == 'filter')
        # Only map tiles to CTUs where the recorded component geometry agrees
        # exactly. Do not silently assume a 128-luma CTU for other bitstreams.
        ctu_geometry = {(r['component'],r['x'],r['y'],r['w'],r['h']):r['ctu']
                        for r in data if r['kind']=='CTU' and r['component']>0}
        tile = {(r['stage'],r['component'],r['x'],r['y']):r for r in data if r['kind']=='tile'}
        for before, after, tool in EDGES:
            for geometry, ctu in ctu_geometry.items():
                c,x,y,w,h=geometry
                a,b=tile.get((before,c,x,y)),tile.get((after,c,x,y))
                if not a or not b or (a['width'],a['height'])!=(w,h) or (b['width'],b['height'])!=(w,h):
                    continue
                ctu_effects.append(dict(case=name,ctu=ctu,component=c,operation=tool,
                                       input_sse=a['sse'],output_sse=b['sse'],
                                       own_sse_reduction=a['sse']-b['sse']))
        for before, after, tool in EDGES:
            for (poc, stage, c), first in frame.items():
                if stage != before:
                    continue
                second = frame[(poc, after, c)]
                if first['original_hash'] != second['original_hash']:
                    raise ValueError('Original reference changed across stage')
                effects.append(dict(case=name, poc=poc, component=c, operation=tool,
                                    before=before, after=after, input_sse=first['sse'], output_sse=second['sse'],
                                    own_sse_reduction=first['sse']-second['sse'],
                                    changed_reconstruction=first['reconstruction_hash'] != second['reconstruction_hash']))
        validation.append(dict(case=name, decoded_frames=case['checked_frames'],
                               off_decoded_frames=case['observer_off_checked_frames'],
                               encoder_decoder_exact_stage_components=common))
    differences, summaries, paired_stages = [], [], []
    for ref, test in PAIRS:
        diff, counts = compare_rows(rows[ref], rows[test])
        pair = dict(reference_case=ref, test_case=test)
        summaries.append(dict(**pair, counts=counts))
        # Keep early witnesses and every changed CTU; full logs remain local.
        for kind in ('CU', 'TU', 'CTU', 'filter'):
            items = [r for r in diff if r['kind'] == kind]
            items.sort(key=lambda r: min(r['reference_line'] or 10**12, r['test_line'] or 10**12))
            differences.extend(dict(**pair, **r) for r in (items if kind == 'CTU' else items[:8]))
        l = {(r['stage'], r['component']):r for r in rows[ref] if r['kind']=='frame'}
        r = {(r['stage'], r['component']):r for r in rows[test] if r['kind']=='frame'}
        for key in l:
            a,b=l[key],r[key]
            if a['original_hash'] != b['original_hash']:
                raise ValueError('Paired stage originals differ')
            paired_stages.append(dict(**pair, poc=a['poc'], stage=key[0], component=key[1],
                                      reference_sse=a['sse'], test_sse=b['sse'], delta_sse=b['sse']-a['sse'],
                                      same_reconstruction=a['reconstruction_hash']==b['reconstruction_hash']))
    output.mkdir(parents=True, exist_ok=True)
    for filename, data in [('decoder_stages', stages), ('filter_controls', filters),
                           ('filter_stage_split', effects), ('paired_stages', paired_stages),
                           ('chroma_ctu_self_gains', ctu_effects),
                           ('first_retained_blocks', differences), ('decoder_validation', validation)]:
        write_rows(output / (filename + '.csv'), data)
    (output/'decoder_cases.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2)+'\n')
    (output/'decoder_comparisons.json').write_text(json.dumps(summaries, indent=2)+'\n')
    print(json.dumps(dict(cases=len(rows), stage_rows=len(stages),
                         common_encoder_stages=sum(r['encoder_decoder_exact_stage_components'] for r in validation))))


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a=p.parse_args()
    collect(a.root,a.output)
