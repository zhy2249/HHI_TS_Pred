"""Schema-2 statistics for the read-only R13 decoder audit.

Population estimates use only the two-stage uniform sample. Every estimate has
an explicit coverage gate; disagreement and extreme examples are diagnostic.
"""
from collections import defaultdict
import csv
import io
import json
from pathlib import Path
import random

POLICIES = ['CURRENT', 'STATIC_EQ', 'STATIC_SP', 'KEEP_EQ', 'KEEP_SP', 'KEEP_EQ_H', 'KEEP_SP_H']
SCALE = 32768


def save(path, obj):
    Path(path).write_text(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False)+'\n')


def read_json(path):
    return json.loads(Path(path).read_text())


def csv_write(path, rows, fields=None):
    fields = fields or (list(rows[0]) if rows else ['status'])
    with Path(path).open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields, lineterminator='\n')
        w.writeheader(); w.writerows(rows)


def read_csv(path):
    with Path(path).open(newline='') as f:
        return list(csv.DictReader(f))


def hash_frames(path):
    if not path.exists(): return {}
    out = {}
    with path.open() as stream:
        for row in csv.reader(stream):
            if len(row) != 4 or int(row[0]) in out:
                raise ValueError('Missing/duplicate reconstruction hash record')
            out[int(row[0])] = row[1:]
    return out


def percentile(values, p):
    if not values: return None
    x = sorted(values); f = (len(x)-1)*p; i = int(f)
    return x[i]+(x[min(i+1,len(x)-1)]-x[i])*(f-i)


def weighted_quantile(values, weights, p):
    """Inverse weighted empirical CDF, same inclusion weights as the means."""
    total = sum(weights)
    if not total: return None
    acc = 0
    for value, weight in sorted(zip(values, weights)):
        acc += weight
        if acc >= p*total: return value
    return max(values)


def point_weight(p):
    return p['tu_population']/p['tu_selected']*p['position_population']/p['position_selected']


def point_metrics(points, mode):
    eligible = [p for p in points if p['distinguishable_plus' if mode >= 5 else 'distinguishable']]
    w = [point_weight(p) for p in eligible]
    r = [p['regret_frac'][mode]/SCALE for p in eligible]
    den = sum(w)
    positive = sum(v for v, cost in zip(w, r) if cost > 0)
    total = sum(v*cost for v,cost in zip(w,r))
    return dict(sample_positions=len(points), sample_distinguishable=len(eligible),
        ht_distinguishable_population=den,
        ht_correct=sum(v for p,v in zip(eligible,w) if p['regret_frac'][mode] == 0),
        ht_regret_frac=total*SCALE, ht_positive_population=positive,
        accuracy=sum(v for cost,v in zip(r,w) if cost == 0)/den if den else None,
        mean_regret_bits=total/den if den else None,
        positive_regret_mean_bits=total/positive if positive else None,
        regret_median_bits=weighted_quantile(r,w,.5), regret_p95_bits=weighted_quantile(r,w,.95),
        sample_unweighted_regret_median_bits=percentile(r,.5),
        sample_unweighted_regret_p95_bits=percentile(r,.95),
        sample_unweighted_positive_regret_mean_bits=sum(r)/sum(x>0 for x in r) if positive else None)


ESTIMATES = ('accuracy','mean_regret_bits','positive_regret_mean_bits','regret_median_bits','regret_p95_bits')


def gated_metrics(points, mode, complete):
    values = point_metrics(points,mode)
    # Retain descriptive observed-sample quantities even when population
    # inference is prohibited. Names distinguish them from HT estimates.
    out = {'coverage_complete':complete, 'sample_positions':values['sample_positions'],
           'sample_distinguishable':values['sample_distinguishable']}
    for name,value in values.items():
        if name.startswith('sample_'): out[name] = value
        elif name.startswith('ht_'):
            out[name] = value if complete else None
            out['observed_weighted_'+name[3:]] = value
        else:
            out[name] = value if complete else None
            out['sample_weighted_'+name] = value
    return out


def csv_value(value):
    return json.dumps(value, separators=(',',':')) if isinstance(value,(dict,list)) else value


class BoundedExports:
    """Keep space for final validation/run metadata, including on truncation."""
    def __init__(self, root, limit):
        self.root = root
        exports={'tu_policy_matrix.csv','census.csv','frame_summary.csv','strata.csv','regret_distribution.csv',
                 'history_summary.csv','score_effects.csv','examples.jsonl'}
        self.used = sum(p.stat().st_size for p in root.iterdir() if p.is_file() and p.name not in exports|{'decode.log','off.log'})
        self.remaining = max(0,limit-self.used-128*1024)
        self.truncated = []; self.dropped = 0

    def csv(self, name, rows):
        fields = list(rows[0]) if rows else ['status']
        with (self.root/name).open('w') as out:
            buf = io.StringIO(); writer = csv.DictWriter(buf,fieldnames=fields,lineterminator='\n'); writer.writeheader()
            header = buf.getvalue()
            if len(header.encode()) > self.remaining:
                self.truncated.append(name); self.dropped += len(rows); return
            out.write(header); self.remaining -= len(header.encode()); self.used += len(header.encode())
            for i,row in enumerate(rows):
                buf.seek(0);buf.truncate(0);writer.writerow({k:csv_value(v) for k,v in row.items()})
                line = buf.getvalue(); count = len(line.encode())
                if count > self.remaining:
                    self.truncated.append(name); self.dropped += len(rows)-i; break
                out.write(line);self.remaining -= count;self.used += count

    def jsonl(self,name,rows):
        with (self.root/name).open('w') as out:
            for i,row in enumerate(rows):
                line = json.dumps(row,ensure_ascii=False,allow_nan=False)+'\n'; count = len(line.encode())
                if count > self.remaining:
                    self.truncated.append(name);self.dropped += len(rows)-i;break
                out.write(line);self.remaining -= count;self.used += count


def strata_dimensions(p):
    margins = []
    for mode in (3,4):
        scores = sorted(p['scores168'][mode])
        gap = (scores[1]-scores[0])/(168*p['weight_sum'][mode]) if len(scores)>1 else None
        margins.append('single' if gap is None else '0' if gap==0 else '<=1/64' if gap<=1/64 else '<=1/16' if gap<=1/16 else '<=1/4' if gap<=1/4 else '<=1' if gap<=1 else '>1')
    conflict = max(p['H'][:2])>1 and sum(a==1 for a in p['H'][2:])>=2
    return dict(amplitude=str(p['a']) if p['a']<=2 else '3-4' if p['a']<=4 else '>=5',
        support=str(p['n']), slice_type=p['slice_type'],
        cu_prediction='intra' if p['is_intra_cu'] else 'inter' if p['is_inter_cu'] else 'other',
        slice_cu=p['slice_type']+(' / intra' if p['is_intra_cu'] else ' / inter' if p['is_inter_cu'] else ' / other'),
        native_path='regular' if p['regular_active'] else 'bypass',missing_neighbors=str(p['missing_neighbors']),
        area='<=16' if p['area']<=16 else '<=64' if p['area']<=64 else '<=256' if p['area']<=256 else '>256',
        margin_EQ=margins[0],margin_SP=margins[1],near_far_conflict=str(conflict),
        low_n_conflict_margin=f'{min(p["a"],3)}|{p["n"]}|{int(conflict)}|{margins[1]}')


def summarize(out, identity):
    records = [json.loads(line) for line in (out/'audit.jsonl').read_text().splitlines()]
    native = read_json(out/'native_validation.json')
    if native.get('schema') != 2: raise ValueError('Schema-2 observations required; legacy Slice labels cannot be inferred')
    frames = [r for r in records if r['kind']=='frame']
    tus = [r for r in records if r['kind']=='tu']; points = [r for r in records if r['kind']=='point']
    if len({(r['poc'],r['component']) for r in frames}) != len(frames): raise ValueError('Duplicate census frame')
    if len({r['id'] for r in tus}) != len(tus): raise ValueError('Duplicate sampled TU')
    if len({(r['tu'],r['scan']) for r in points}) != len(points): raise ValueError('Repeated point samples')
    common = dict(schema=2,pair_id=identity['pair_id'],origin=identity['origin'],nominal_qp=identity['nominal_qp'])
    writer = BoundedExports(out,identity['limits']['core_bytes'])
    all_output = native['valid'] and native['output_complete']
    matrix = []
    for t in tus:
        row = {**common,**{k:v for k,v in t.items() if k not in ('kind','rates_frac')}}
        row['inclusion_probability'] = t['tu_selected']/t['tu_population']
        for m,name in enumerate(POLICIES): row[name+'_frac'] = t['rates_frac'][m]
        row['SP_minus_EQ_frac'] = t['rates_frac'][4]-t['rates_frac'][3] if all(t['policy_complete'][m] for m in (3,4)) else None
        matrix.append(row)
    writer.csv('tu_policy_matrix.csv',matrix)
    census = []; frame_rows = []; frame_ok = {}
    for f in frames:
        key = (f['poc'],f['component']); cv = f['coverage']
        pop = [t for t in tus if (t['poc'],t['component'])==key]
        sample = [p for p in points if (p['poc'],p['component'])==key and p['sample']=='uniform']
        family_ok = (all_output and identity['profile']!='summary' and f['capture_skipped']==0
            and len(pop)==f['selected_tu'] and all(t['all_policy_complete'] and t['native_replay_complete'] for t in pop)
            and (not f['eligible_tu'] or f['selected_tu']>0))
        uniform_ok = family_ok and cv['point_requested'][0]==cv['point_done'][0]==len(sample)
        frame_ok[key] = (family_ok,uniform_ok)
        row = {**common,**{k:v for k,v in f.items() if k not in ('kind','coverage','amplitude','support')}}
        row.update(amplitude_counts=f['amplitude'],support_counts=f['support'])
        row.update(cv)
        census.append(row)
        types = [name for i,name in enumerate(('B','P','I','L')) if sum(f['slice_cu_counts'][3*i:3*i+3])]
        for m,name in enumerate(POLICIES):
            known = [t for t in pop if t['policy_complete'][m]]
            estimates = gated_metrics(sample,m,uniform_ok and identity['profile']=='standard')
            frame_rows.append({**common,'poc':f['poc'],'component':f['component'],'policy':name,
                'slice_type':types[0] if len(types)==1 else 'mixed' if types else 'no_TS',
                'intra_cu_tu':sum(f['slice_cu_counts'][::3]),'inter_cu_tu':sum(f['slice_cu_counts'][1::3]),
                'seen_tu':f['tu'],'seen_coeff':f['coeff'],'seen_nz':f['nz'],'target_tu':f['target_tu'],'target_nz':f['target_nz'],
                'eligible_tu':f['eligible_tu'],'eligible_nz':f['eligible_nz'],'scoring_eligible_tu':f['scoring_eligible_tu'],
                'scoring_eligible_nz':f['scoring_eligible_nz'],'unsupported_tu':f['unsupported_tu'],'bdpcm_tu':f['bdpcm_tu'],
                'selected_tu':f['selected_tu'],'native_verified_tu':cv['native_verified_tu'],'policy_done_tu':cv['policy_done_tu'][m],
                'uniform_requested':cv['point_requested'][0],'uniform_done':cv['point_done'][0],
                'rate_complete':family_ok and identity['profile']=='standard',
                'score_complete':uniform_ok and identity['profile']=='standard',
                'oracle_set':'Cplus' if m>=5 else 'C0',**estimates,
                'ht_policy_rate_frac':sum(t['rates_frac'][m]*t['tu_population']/t['tu_selected'] for t in pop) if family_ok and identity['profile']=='standard' else None,
                'ht_minus_eq_frac':sum((t['rates_frac'][m]-t['rates_frac'][3])*t['tu_population']/t['tu_selected'] for t in pop) if family_ok and identity['profile']=='standard' else None,
                'sample_known_policy_rate_frac':sum(t['rates_frac'][m] for t in known),
                'sample_known_policy_tu':len(known)})
    writer.csv('census.csv',census);writer.csv('frame_summary.csv',frame_rows)
    # An incomplete sampled TU anywhere in this component excludes primary
    # component-wide point estimates. Preserve observed sample descriptions.
    component_ok = {c:all(ok[1] for key,ok in frame_ok.items() if key[1]==c) and any(key[1]==c for key in frame_ok)
                    for c in range(3)}
    grouped = defaultdict(list)
    for p in points:
        for dimension,bucket in strata_dimensions(p).items():
            grouped[(p['sample'],p['component'],dimension,bucket)].append(p)
    strata = []; distributions = []; history = []; effects = []
    for (sample,c,dimension,bucket),members in sorted(grouped.items()):
        qualified = component_ok[c] and identity['profile']=='standard' and sample=='uniform'
        for m,name in enumerate(POLICIES):
            strata.append({**common,'sample':sample,'component':c,'policy':name,'oracle_set':'Cplus' if m>=5 else 'C0',
                'dimension':dimension,'bucket':bucket,**gated_metrics(members,m,qualified)})
    for c in range(3):
        for sample in ('uniform','disagreement'):
            group = [p for p in points if p['component']==c and p['sample']==sample]
            qualified = component_ok[c] and identity['profile']=='standard' and sample=='uniform'
            for m,name in enumerate(POLICIES):
                valid = [p for p in group if p['distinguishable_plus' if m>=5 else 'distinguishable']]
                for label,low,high in [('0',-1,0),('(0,1/64]',0,1/64),('(1/64,1/4]',1/64,1/4),('(1/4,1]',1/4,1),('>1',1,float('inf'))]:
                    chosen = [p for p in valid if low<p['regret_frac'][m]/SCALE<=high]
                    weight = sum(point_weight(p) for p in chosen)
                    distributions.append({**common,'component':c,'sample':sample,'policy':name,'oracle_set':'Cplus' if m>=5 else 'C0',
                        'regret_bits_bin':label,'sample_count':len(chosen),'observed_weighted_count':weight,
                        'ht_count':weight if qualified else None,'coverage_complete':qualified})
            for m in (5,6):
                def maps(p, key): return {1 if p['a']==v else p['a']+1 if p['a']<v else p['a'] for v in p[key]}
                tests = dict(history_valid=lambda p:p['history_nz']>0,history_one=lambda p:p['hist']==1,
                    candidate_added=lambda p:len(p['cplus'])>len(p['c0']),new_mapping_added=lambda p:bool(maps(p,'cplus')-maps(p,'c0')),
                    selected_new=lambda p:p['pred'][m] not in p['c0'],
                    coverage_gain_frac=lambda p:p['coverage_frac'],
                    selection_minus_parent_frac=lambda p:p['cost_frac'][m]-p['cost_frac'][m-2])
                for name,fn in tests.items():
                    val = sum(point_weight(p)*fn(p) for p in group)
                    history.append({**common,'component':c,'sample':sample,'policy':POLICIES[m],'metric':name,
                        'sample_count':len(group),'observed_weighted_numerator':val,
                        'ht_numerator':val if qualified else None,'ht_denominator':sum(point_weight(p) for p in group) if qualified else None,
                        'coverage_complete':qualified})
            contrasts = [(2,1,'spatial_on_static'),(3,1,'KeepHit_on_EQ'),(4,2,'KeepHit_on_SP'),(4,3,'spatial_on_KeepHit'),(5,3,'history_on_EQ'),(6,4,'history_on_SP')]
            for a,b,label in contrasts:
                delta = [(p['cost_frac'][a]-p['cost_frac'][b],point_weight(p)) for p in group]
                den = sum(w for _,w in delta)
                weighted = sum(d*w for d,w in delta)
                effects.append({**common,'component':c,'sample':sample,'contrast':label,'test':POLICIES[a],'reference':POLICIES[b],
                    'sample_count':len(group),'ht_population':den if qualified else None,
                    'mean_delta_bits':weighted/den/SCALE if qualified and den else None,
                    'improve_fraction':sum(w for d,w in delta if d<0)/den if qualified and den else None,
                    'worsen_fraction':sum(w for d,w in delta if d>0)/den if qualified and den else None,
                    'tie_fraction':sum(w for d,w in delta if d==0)/den if qualified and den else None,
                    'sample_weighted_delta_bits':weighted/den/SCALE if den else None,'coverage_complete':qualified})
    writer.csv('strata.csv',strata);writer.csv('regret_distribution.csv',distributions)
    writer.csv('history_summary.csv',history);writer.csv('score_effects.csv',effects)
    # Random examples are drawn only from retained uniform positions. Extremes
    # may include enrichment, but their original sample tag is never erased.
    rng = random.Random(identity['limits']['seed']); uniform = [p for p in points if p['sample']=='uniform']
    examples = [dict(p,example_kind='random_uniform_sample_description') for p in rng.sample(uniform,min(128,len(uniform)))]
    for c in range(3):
        for sign in (-1,1):
            eligible = [p for p in points if p['component']==c and sign*(p['cost_frac'][4]-p['cost_frac'][3])>0]
            eligible.sort(key=lambda p:sign*(p['cost_frac'][4]-p['cost_frac'][3]),reverse=True)
            examples.extend(dict(p,example_kind='negative_extreme' if sign<0 else 'positive_extreme') for p in eligible[:32])
    writer.jsonl('examples.jsonl',[{**common,**p} for p in examples])
    return dict(final_tu=sum(f['tu'] for f in frames),sampled_tu=len(tus),points=len(points),examples=len(examples),
        output_complete=not writer.truncated,output_truncated_files=writer.truncated,output_dropped_rows=writer.dropped,
        core_bytes=writer.used,observed_frames=sorted({f['poc'] for f in frames}),
        estimator='two-stage inclusion weights; population inference only for complete uniform sample',
        uncertainty='POC-block bootstrap conditional on retained TU/position samples, not full two-stage sampling uncertainty')


def truth(value):
    return value is True or value == 'True'


def number(value):
    return None if value in (None,'') else float(value)


def paired_frame_intervals(summaries, common, components_complete, seed=20261025, draws=2000):
    result = []
    for c in range(3):
        indexed = [{int(r['poc']):r for r in rows if r['policy']=='KEEP_SP' and int(r['component'])==c} for rows in summaries]
        support = [sum(int(rows.get(p,{}).get('eligible_nz',0))>0 for p in common) for rows in indexed]
        samples = [[],[],[]]; rng = random.Random(seed)
        if components_complete[c] and common and min(support)>=2:
            for _ in range(draws):
                positions = []
                while len(positions)<len(common):
                    start = rng.randrange(len(common));positions.extend(common[(start+j)%len(common)] for j in range(8))
                ratios = []
                for origin in range(2):
                    rows = [indexed[origin][p] for p in positions[:len(common)]]
                    den = sum(int(r['eligible_nz']) for r in rows)
                    value = sum(float(r['ht_minus_eq_frac']) for r in rows)/den/SCALE if den else None
                    ratios.append(value)
                    if value is not None: samples[origin].append(value)
                if None not in ratios:samples[2].append(sum(ratios)/2)
        for origin,values in zip(('R13-1','R13-2','balanced'),samples):
            result.append(dict(component=c,origin=origin,metric='SP_minus_EQ_bits_per_eligible_nonzero',
                method='paired circular POC blocks, length 8; conditional on retained samples',seed=seed,
                includes_two_stage_sampling_uncertainty=False,includes_cross_content_uncertainty=False,
                valid_draws=len(values),requested_draws=draws,support_frames=support,
                ci95=[percentile(values,.025),percentile(values,.975)] if values else None,
                status='conditional_small_content_sample' if values else 'insufficient_support_or_incomplete'))
    return result


def compare(reference,test,output):
    r,t = read_json(reference/'run.json'),read_json(test/'run.json')
    if r['origin']=='R13-2': reference,test,r,t = test,reference,t,r
    if r['origin']!='R13-1' or t['origin']!='R13-2' or r['pair_id']!=t['pair_id']:
        raise ValueError('Compare requires matched EQ/SP origin pair')
    for key in ('schema','implementation_revision','decoder_sha256','first_poc','last_poc','component','tu_filter','profile','policies','limits'):
        if r.get(key)!=t.get(key):raise ValueError('Asymmetric observation settings: '+key)
    if r.get('schema')!=2:raise ValueError('Legacy observations require a fresh schema-2 decode, not relabelling')
    validations = [read_json(p/'decode_validation.json') for p in (reference,test)]
    hashes = [hash_frames(p/'reconstruction.csv') for p in (reference,test)]
    common_decoded = sorted(set(hashes[0])&set(hashes[1]))
    common = [p for p in common_decoded if r['first_poc']<=p<=r['last_poc']]
    summaries = [read_csv(p/'frame_summary.csv') for p in (reference,test)]
    for rows in summaries:
        if len({(x['poc'],x['component'],x['policy']) for x in rows}) != len(rows):raise ValueError('Duplicate policy/frame summary')
    indexed = [{(int(x['poc']),int(x['component']),x['policy']):x for x in rows} for rows in summaries]
    rate_table = []; score_table = []; eq_sp = []; intervals_complete = {}
    for c in range(3):
        chosen = [[index.get((p,c,'KEEP_SP')) for p in common] for index in indexed]
        rate_ok = [bool(common) and r['profile']=='standard' and v['decode_complete'] and v['output_complete']
                   and all((p,c,name) in index and truth(index[(p,c,name)]['rate_complete']) for p in common for name in POLICIES)
                   for v,rows,index in zip(validations,chosen,indexed)]
        score_ok = [bool(common) and r['profile']=='standard' and v['decode_complete'] and v['output_complete']
                   and all((p,c,name) in index and truth(index[(p,c,name)]['score_complete']) for p in common for name in POLICIES)
                   for v,rows,index in zip(validations,chosen,indexed)]
        intervals_complete[c] = all(rate_ok)
        eq_sp_origins = []
        for origin,index,valid,ok,sok in zip(('R13-1','R13-2'),indexed,validations,rate_ok,score_ok):
            rows = [index[(p,c,'KEEP_SP')] for p in common if (p,c,'KEEP_SP') in index]
            den = sum(int(x['eligible_nz']) for x in rows); tu = sum(int(x['eligible_tu']) for x in rows)
            eq = sum(float(x['ht_policy_rate_frac']) for x in (index[(p,c,'KEEP_EQ')] for p in common)) if ok else None
            sp = sum(float(x['ht_policy_rate_frac']) for x in rows) if ok else None
            delta = (sp-eq)/SCALE if ok else None
            entry = dict(pair_id=r['pair_id'],origin=origin,component=c,common_frames=len(common),seen_tu=tu,seen_nz=den,
                excluded_unsupported_tu=sum(int(x['unsupported_tu']) for x in rows),
                EQ_estimated_frac=eq,SP_estimated_frac=sp,SP_minus_EQ_estimated_bits=delta,
                bits_per_nonzero=delta/den if ok and den else None,bits_per_tu=delta/tu if ok and tu else None,
                comparison_complete=ok,status='complete_eligible_TS_population' if ok else 'missing_or_incomplete_common_coverage')
            eq_sp_origins.append(entry);eq_sp.append(entry)
            for m,name in enumerate(POLICIES):
                group = [index[(p,c,name)] for p in common if (p,c,name) in index]
                rate = sum(float(x['ht_policy_rate_frac']) for x in group) if ok else None
                difference = (rate-eq)/SCALE if ok else None
                rate_table.append(dict(pair_id=r['pair_id'],component=c,origin=origin,policy=name,
                    eligible_tu=tu,eligible_nz=den,estimated_rate_frac=rate,
                    minus_EQ_bits=difference,minus_EQ_bits_per_tu=difference/tu if ok and tu else None,
                    minus_EQ_bits_per_nonzero=difference/den if ok and den else None,coverage_complete=ok))
                population = sum(float(x['ht_distinguishable_population']) for x in group) if sok else None
                correct = sum(float(x['ht_correct']) for x in group) if sok else None
                regret = sum(float(x['ht_regret_frac']) for x in group) if sok else None
                positive = sum(float(x['ht_positive_population']) for x in group) if sok else None
                score_table.append(dict(pair_id=r['pair_id'],component=c,policy=name,origin=origin,
                    oracle_set='Cplus' if m>=5 else 'C0',ht_distinguishable_population=population,
                    accuracy=correct/population if sok and population else None,
                    mean_regret_bits=regret/population/SCALE if sok and population else None,
                    positive_regret_mean_bits=regret/positive/SCALE if sok and positive else None,
                    coverage_complete=sok,status='complete_uniform_sample' if sok else 'missing_or_incomplete_common_coverage'))
        def mean2(values): return sum(values)/2 if all(x is not None for x in values) else None
        eq_sp.append(dict(pair_id=r['pair_id'],origin='balanced',component=c,common_frames=len(common),seen_tu=None,seen_nz=None,
            excluded_unsupported_tu=None,EQ_estimated_frac=None,SP_estimated_frac=None,SP_minus_EQ_estimated_bits=None,
            bits_per_nonzero=mean2([x['bits_per_nonzero'] for x in eq_sp_origins]),bits_per_tu=mean2([x['bits_per_tu'] for x in eq_sp_origins]),
            comparison_complete=all(rate_ok),status='equal_origin_mean' if all(rate_ok) else 'missing_origin_coverage'))
        for name in POLICIES:
            rows = [x for x in rate_table if x['component']==c and x['policy']==name]
            rate_table.append(dict(pair_id=r['pair_id'],component=c,origin='balanced',policy=name,eligible_tu=None,eligible_nz=None,
                estimated_rate_frac=None,minus_EQ_bits=None,
                minus_EQ_bits_per_tu=mean2([x['minus_EQ_bits_per_tu'] for x in rows]),
                minus_EQ_bits_per_nonzero=mean2([x['minus_EQ_bits_per_nonzero'] for x in rows]),coverage_complete=all(rate_ok)))
            rows = [x for x in score_table if x['component']==c and x['policy']==name]
            score_table.append(dict(pair_id=r['pair_id'],component=c,policy=name,origin='balanced',oracle_set=rows[0]['oracle_set'],
                ht_distinguishable_population=None,accuracy=mean2([x['accuracy'] for x in rows]),mean_regret_bits=mean2([x['mean_regret_bits'] for x in rows]),
                positive_regret_mean_bits=mean2([x['positive_regret_mean_bits'] for x in rows]),coverage_complete=all(score_ok),
                status='equal_origin_mean' if all(score_ok) else 'missing_origin_coverage'))
    matrix = [read_csv(p/'tu_policy_matrix.csv') for p in (reference,test)]
    geometry = [{(x['poc'],x['component'],x['x'],x['y'],x['w'],x['h']):x for x in rows if x.get('id') and int(x['poc']) in common} for rows in matrix]
    shared = set(geometry[0])&set(geometry[1])
    report = dict(schema=2,pair_id=r['pair_id'],population='FINAL_SELECTED eligible TS',common_observed_frames=common,
        common_decoded_frames=common_decoded,origin_only_frames=[sorted(set(f)-set(common_decoded)) for f in hashes],
        encoding_identity_status=r['pairing_status'],sampled_geometry_intersection=len(shared),
        sampled_geometry_only_EQ=len(set(geometry[0])-shared),sampled_geometry_only_SP=len(set(geometry[1])-shared),
        shared_q_and_entry=sum(geometry[0][k]['q_hash']==geometry[1][k]['q_hash'] and geometry[0][k]['entry_hash']==geometry[1][k]['entry_hash'] for k in shared),
        rows=eq_sp,limitations=['Fixed-q, final-selected TS only; no BD-rate.',
            'Primary comparisons require all seven policies on the original sampled TU population.',
            'Unknown server encoding/input identity remains unverified.',
            'Balanced is equal-origin, not pooled coefficients; missing is never zero.',
            'Bootstrap is conditional on retained samples; it omits two-stage sampling and cross-content uncertainty.'])
    output.mkdir(parents=True,exist_ok=True)
    save(output/'pair_comparison.json',report);csv_write(output/'pair_comparison.csv',eq_sp)
    csv_write(output/'policy_comparison.csv',rate_table);csv_write(output/'score_comparison.csv',score_table)
    save(output/'pair_uncertainty.json',paired_frame_intervals(summaries,common,intervals_complete,r['limits']['seed']))
    return report
