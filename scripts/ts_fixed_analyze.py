#!/usr/bin/env python3
"""Audit closed-loop LB CE runs; weight component BD-rates 6:1:1 AFTER integration.

Pure Python PCHIP (primary) and four-point cubic (sensitivity); no Excel formula cache.
"""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import random
import statistics as st
import zipfile

import xlsm_table_fill as xl
from batch_test import _parse_encoder_summary

SEQUENCES = {'BasketballDrill': ('C', 250), 'BQMall': ('C', 300),
             'PartyScene': ('C', 250), 'RaceHorsesC': ('C', 150),
             'FourPeople': ('E', 300), 'Johnny': ('E', 300), 'KristenAndSara': ('E', 300)}
ALL_SEQUENCES = {'MarketPlace': ('B', 300), 'RitualDance': ('B', 300),
                 'Cactus': ('B', 250), 'BasketballDrive': ('B', 250), 'BQTerrace': ('B', 300),
                 **SEQUENCES}
MODES = ('nopred', 'gradient', 'directional')
QPS = (22, 27, 32, 37)


def pchip_integral(x, y, lo, hi):
    h = [b - a for a, b in zip(x, x[1:])]
    delta = [(b - a) / dx for a, b, dx in zip(y, y[1:], h)]
    slopes = [0.0] * len(x)
    for k in range(1, len(x) - 1):
        if delta[k-1] * delta[k] > 0:
            w1, w2 = 2*h[k] + h[k-1], h[k] + 2*h[k-1]
            slopes[k] = (w1 + w2) / (w1/delta[k-1] + w2/delta[k])
    def edge(a, b, da, db):
        d = ((2*a + b)*da - a*db) / (a+b)
        if d*da <= 0:
            return 0.0
        if da*db < 0 and abs(d) > 3*abs(da):
            return 3*da
        return d
    slopes[0] = edge(h[0], h[1], delta[0], delta[1])
    slopes[-1] = edge(h[-1], h[-2], delta[-1], delta[-2])
    total = 0.0
    for k, width in enumerate(h):
        a, b = max(lo, x[k]), min(hi, x[k+1])
        if a >= b:
            continue
        c0, c1 = y[k], slopes[k]
        c2 = (3*delta[k] - 2*slopes[k] - slopes[k+1]) / width
        c3 = (slopes[k] + slopes[k+1] - 2*delta[k]) / width**2
        def primitive(t):
            return c0*t + c1*t*t/2 + c2*t**3/3 + c3*t**4/4
        total += primitive(b-x[k]) - primitive(a-x[k])
    return total


def cubic_integral(x, y, lo, hi):
    # Integrate the four-point Lagrange interpolant after centering x.
    center = (lo + hi)/2
    xs = [v-center for v in x]
    total = 0.0
    for i in range(len(xs)):
        poly, denominator = [1.0], 1.0
        for j in range(len(xs)):
            if i == j:
                continue
            new = [0.0] * (len(poly)+1)
            for k, value in enumerate(poly):
                new[k] -= value*xs[j]
                new[k+1] += value
            poly = new
            denominator *= xs[i]-xs[j]
        area = sum(c*((hi-center)**(k+1)-(lo-center)**(k+1))/(k+1) for k, c in enumerate(poly))
        total += y[i]*area/denominator
    return total


def bd_rate(anchor, test, method='pchip'):
    # Each point is (quality in dB, rate in kbps).
    a, b = sorted(anchor), sorted(test)
    for curve in (a, b):
        assert len(curve) == 4 and all(r > 0 and math.isfinite(q+r) for q, r in curve)
        assert all(q1 < q2 and r1 < r2 for (q1,r1),(q2,r2) in zip(curve,curve[1:])), curve
    lo, hi = max(a[0][0], b[0][0]), min(a[-1][0], b[-1][0])
    assert hi > lo, 'No overlapping quality interval'
    integrate = pchip_integral if method == 'pchip' else cubic_integral
    area = []
    for curve in (a,b):
        area.append(integrate([q for q,r in curve], [math.log(r) for q,r in curve], lo, hi))
    return 100*math.expm1((area[1]-area[0])/(hi-lo)), lo, hi


def self_test():
    curve = [(30+i*2, math.exp(0.3*i+4)) for i in range(4)]
    for method in ('pchip', 'cubic'):
        assert abs(bd_rate(curve, curve, method)[0]) < 1e-10
        assert abs(bd_rate(curve, [(q,r*0.9) for q,r in curve], method)[0]+10) < 1e-9
        assert abs(bd_rate(curve, [(q+2,r) for q,r in curve], method)[0]-100*math.expm1(-0.3)) < 1e-9
    assert abs(pchip_integral([0,1,2,3], [0,1,2,3], .5, 2.5)-3) < 1e-12


def workbook_bdrate(a, b):
    """Independent translation of workbook Module1 bdrate/bdrint, output percent.

    Workbook uses descending-quality 4-point input, log10 and explicit primitives.
    This reference check is for the strictly monotonic curves audited here.
    """
    a, b = sorted(a), sorted(b)
    low, high = max(a[0][0],b[0][0]), min(a[-1][0],b[-1][0])
    def integral(curve):
        x = [q for q,r in curve]
        y = [math.log10(r) for q,r in curve]
        h = [x[i+1]-x[i] for i in range(3)]
        delta = [(y[i+1]-y[i])/h[i] for i in range(3)]
        def end(h1,h2,d1,d2):
            d = ((2*h1+h2)*d1-h1*d2)/(h1+h2)
            return 0 if d*d1<0 else 3*d1 if d1*d2<0 and abs(d)>abs(3*d1) else d
        d = [end(h[0],h[1],delta[0],delta[1])]
        for i in (1,2):
            d.append((3*h[i-1]+3*h[i])/((2*h[i]+h[i-1])/delta[i-1]+(h[i]+2*h[i-1])/delta[i]))
        d.append(end(h[2],h[1],delta[2],delta[1]))
        total = 0
        for i in range(3):
            s0, s1 = min(max(x[i],low),high)-x[i], min(max(x[i+1],low),high)-x[i]
            c = (3*delta[i]-2*d[i]-d[i+1])/h[i]
            k = (d[i]-2*delta[i]+d[i+1])/h[i]**2
            total += (s1-s0)*y[i] + (s1*s1-s0*s0)*d[i]/2 + (s1**3-s0**3)*c/3 + (s1**4-s0**4)*k/4
        return total
    return 100*(10**((integral(b)-integral(a))/(high-low))-1)


def sheet_values(path, sheet):
    with zipfile.ZipFile(path) as z:
        strings = xl._load_shared_strings(z)
        return {k: xl._get_cell_value(v, strings) for k,v in
                xl._build_cell_map(xl._read_xml(z, xl._get_sheet_xml_by_name(z, sheet))).items()}


def reference_points(path):
    vals = sheet_values(path, 'Reference')
    out = {}
    for cell, value in vals.items():
        if not cell.startswith('A') or not isinstance(value, str):
            continue
        for seq in SEQUENCES:
            for qp in QPS:
                if value == f'{seq}.Q{qp}.ecm.lb':
                    n = ''.join(c for c in cell if c.isdigit())
                    assert vals['J'+n] == 'pass', value
                    out[seq,qp] = {key: float(vals[col+n]) for col,key in
                                  [('B','kbps'),('C','ypsnr'),('D','upsnr'),('E','vpsnr')]}
    assert len(out) == len(SEQUENCES)*len(QPS)
    return out


def audit(root, template):
    rows = []
    anchor_values = sheet_values(template, 'Reference')
    for mode in MODES:
        markers = list((root/mode).rglob('*.done.json'))
        # Other classes may have been appended to the same experiment directory.
        markers = [m for m in markers if json.loads(m.read_text())['sequence'] in SEQUENCES]
        assert len(markers) == len(SEQUENCES)*len(QPS), (mode,len(markers))
        seen = set()
        assert sheet_values(root/mode/'JVET-hhi.xlsm', 'Reference') == anchor_values, mode
        test_sheet = sheet_values(root/mode/'JVET-hhi.xlsm', 'Test')
        for marker in markers:
            m = json.loads(marker.read_text())
            r = m['result']
            seq, qp = r['sequence'], r['qp']
            assert seq in SEQUENCES and qp in QPS and (seq,qp) not in seen
            seen.add((seq,qp))
            assert r['fixed_predictor'] == mode == m['fixed_predictor']
            assert r['encode_status'] == r['decode_status'] == 'ok' and r['error_info'] == 'pass'
            assert r['frames'] == r['encoded_frames'] == SEQUENCES[seq][1]
            assert Path(r['bitstream']).stat().st_size == m['bitstream_bytes'] > 0
            enc = Path(r['encode_log']).read_text(errors='replace')
            dec = Path(r['decode_log']).read_text(errors='replace')
            banner = f'EXPERIMENT: TS_FIXED_PREDICTOR={mode}; syntax=experimental-v1'
            assert banner in enc and banner in dec
            assert 'RETURNCODE: 0' in enc and 'RETURNCODE: 0' in dec
            assert dec.count('(OK)') == r['frames'] and 'ERROR' not in dec and 'MISMATCH' not in dec
            parsed = _parse_encoder_summary(enc)
            key = f'{seq}.Q{qp}.ecm.lb'
            cell = next(c for c,v in test_sheet.items() if c.startswith('A') and v == key)
            n = ''.join(c for c in cell if c.isdigit())
            for col,k in [('B','kbps'),('C','ypsnr'),('D','upsnr'),('E','vpsnr')]:
                assert parsed[k] == r[k] == test_sheet[col+n], (mode,seq,qp,k)
            rows.append(r)
    return rows


def weighted(p):
    return (6*p['ypsnr']+p['upsnr']+p['vpsnr'])/8


def write_csv(path, rows):
    with path.open('w',newline='') as f:
        writer = csv.DictWriter(f,fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main():
    global SEQUENCES, MODES
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run',type=Path,default=Path('runs/ts_fixed_LB_CE_half'))
    p.add_argument('--anchor',type=Path,default=Path('scripts/JVET-hhi.xlsm'))
    p.add_argument('--out',type=Path,default=Path('runs/ts_fixed_LB_CE_half/analysis_611'))
    p.add_argument('--classes',default='C,E',help='C,E or B,C,E; sequence-weighted averages')
    p.add_argument('--modes',default='nopred,gradient,directional',help='Completed fixed modes to audit')
    args = p.parse_args()
    classes = args.classes.split(',')
    selected_modes = args.modes.split(',')
    if not classes or len(set(classes))!=len(classes) or not set(classes)<=set('BCE'):
        p.error('classes must be distinct B,C,E')
    if not selected_modes or len(set(selected_modes))!=len(selected_modes) or not set(selected_modes)<=set(MODES):
        p.error('modes must be distinct nopred,gradient,directional')
    MODES = tuple(selected_modes)
    SEQUENCES = {s:v for s,v in ALL_SEQUENCES.items() if v[0] in classes}
    overall = ''.join(classes)
    self_test()
    rows = audit(args.run,args.anchor)
    anchor = reference_points(args.anchor)
    test = {(r['fixed_predictor'],r['sequence'],r['qp']):r for r in rows}
    points, results, aggregates = [], [], []
    vba_max_difference_pp = 0.0
    for mode in MODES:
        for seq,(cls,frames) in SEQUENCES.items():
            a = [anchor[seq,qp] for qp in QPS]
            t = [test[mode,seq,qp] for qp in QPS]
            result = {'mode':mode,'sequence':seq,'class':cls}
            for metric in ('weighted_psnr_diagnostic','Y','U','V'):
                get = weighted if metric == 'weighted_psnr_diagnostic' else lambda r,k=metric: r[{'Y':'ypsnr','U':'upsnr','V':'vpsnr'}[k]]
                for method in ('pchip','cubic'):
                    rate,lo,hi = bd_rate([(get(r),r['kbps']) for r in a],[(get(r),r['kbps']) for r in t],method)
                    result[f'{metric}_{method}_pct'] = rate
                    if method == 'pchip':
                        result[f'{metric}_overlap_low_db'] = lo
                        result[f'{metric}_overlap_high_db'] = hi
                        vba_result = workbook_bdrate([(get(r),r['kbps']) for r in a],[(get(r),r['kbps']) for r in t])
                        vba_max_difference_pp = max(vba_max_difference_pp, abs(rate-vba_result))
                        assert abs(rate-vba_result) < 1e-9
            for method in ('pchip','cubic'):
                result[f'YUV611_{method}_pct'] = (6*result[f'Y_{method}_pct']+
                                                result[f'U_{method}_pct']+result[f'V_{method}_pct'])/8
            results.append(result)
            for qp, ar,tr in zip(QPS,a,t):
                points.append({'mode':mode,'sequence':seq,'class':cls,'QP':qp,'frames':frames,
                               'anchor_kbps':ar['kbps'],'test_kbps':tr['kbps'],
                               'anchor_YUV611':weighted(ar),'test_YUV611':weighted(tr),
                               'same_QP_rate_delta_pct':100*(tr['kbps']/ar['kbps']-1),
                               'same_QP_quality_delta_db':weighted(tr)-weighted(ar)})
        for cls in ([overall,*classes] if len(classes)>1 else classes):
            subset = [r for r in results if r['mode']==mode and (cls==overall or r['class']==cls)]
            vals = [r['YUV611_pchip_pct'] for r in subset]
            rng = random.Random(20260913)
            samples = sorted(st.mean(rng.choices(vals,k=len(vals))) for _ in range(10000))
            aggregates.append({'mode':mode,'class':cls,'sequences':len(vals),'mean_pct':st.mean(vals),
                               'median_pct':st.median(vals),'sd_pp':st.stdev(vals),
                               'best_pct':min(vals),'worst_pct':max(vals),'improved_sequences':sum(v<0 for v in vals),
                               'bootstrap_low_pct':samples[249],'bootstrap_high_pct':samples[9749],
                               'cubic_mean_pct':st.mean(r['YUV611_cubic_pct'] for r in subset),
                               **{f'{c}_mean_pct':st.mean(r[f'{c}_pchip_pct'] for r in subset) for c in ('Y','U','V')}})
    args.out.mkdir(parents=True,exist_ok=True)
    write_csv(args.out/'rd_points_611.csv',points)
    write_csv(args.out/'bd_rate_by_sequence.csv',results)
    write_csv(args.out/'bd_rate_summary.csv',aggregates)
    data = {'weighting':'BD_YUV=(6*BD_Y+BD_U+BD_V)/8 AFTER separate component integration, as requested',
            'primary_method':'PCHIP log(rate) vs each component PSNR; component-specific common quality intervals; no extrapolation',
            'workbook_method':'Inspected xl/vbaProject.bin Module1: bdrate uses PCHIP, bdrateOld uses cubic; bdrate formula replicated mathematically (not executing Excel macros)',
            'diagnostic_only':'weighted_psnr_diagnostic is NOT the primary BD-rate metric',
            'negative_is_better':True,'audit_jobs':len(rows),'decoded_frames':sum(r['frames'] for r in rows),
            'workbook_formula_max_difference_percentage_points':vba_max_difference_pp,
            'anchor_sha256':hashlib.sha256(args.anchor.read_bytes()).hexdigest(),
            'anchor_provenance':'User-supplied historical Reference; half frames confirmed by user; full build/config provenance not independently available',
            'sequence_results':results,'aggregates':aggregates}
    (args.out/'analysis.json').write_text(json.dumps(data,indent=2))
    for row in aggregates:
        print(row)
    print('Per-sequence:',[(r['mode'],r['sequence'],round(r['YUV611_pchip_pct'],5)) for r in results])
    print('Same QP mean:',[(m,q,round(st.mean(r['same_QP_rate_delta_pct'] for r in points if r['mode']==m and r['QP']==q),5),
          round(st.mean(r['same_QP_quality_delta_db'] for r in points if r['mode']==m and r['QP']==q),5)) for m in MODES for q in QPS])


if __name__=='__main__':
    main()
