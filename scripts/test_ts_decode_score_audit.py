import copy
import json
from pathlib import Path
import tempfile
import unittest
import ts_decode_score_audit as a
import ts_audit_stats as stats


def point(scan=0,regret=0,weight=1,**overrides):
    p=dict(kind='point',tu='0_0_0_0_4_4',poc=0,component=0,scan=scan,a=1,n=3,
        slice_type='B',is_intra_cu=1,is_inter_cu=0,area=16,sample='uniform',
        regular_active=True,missing_neighbors=0,H=[2,1,1,0,0],scores168=[[]]+[[10,12]]*6,
        weight_sum=[0]+[3]*6,distinguishable=1,distinguishable_plus=1,
        regret_frac=[regret*32768]*7,hist=3,hist_count=2,history_nz=5,
        c0=[2,0],cplus=[2,0,3],pred=[0]*5+[3,3],cost_frac=[100]*5+[90,90],coverage_frac=10,
        tu_population=1,tu_selected=1,position_population=weight,position_selected=1,
        direct_sp_eq_frac=0,propagation_sp_eq_frac=0)
    p.update(overrides);return p


def fixture(root,origin='R13-1',delta=32768,nz=10,tu=2,incomplete=False,points=None,frames=(0,1)):
    root.mkdir()
    identity=dict(schema=2,implementation_revision=a.REV,decoder_sha256='same',origin=origin,pair_id='test',
        nominal_qp=32,first_poc=0,last_poc=1,component=-1,tu_filter=None,profile='standard',
        policies=a.POLICIES,limits=a.DEFAULTS,pairing_status='unknown')
    a.save(root/'run.json',identity)
    a.save(root/'native_validation.json',dict(schema=2,valid=True,output_complete=True))
    a.save(root/'decode_validation.json',dict(decode_complete=True,output_complete=True,audit_complete=not incomplete))
    (root/'reconstruction.csv').write_text(''.join(f'{p},y,u,v\n' for p in frames))
    raw=[]
    if points is None:points=[point(regret=1)] if tu else []
    for p in frames:
        for c in range(3):
            active=p==0 and c==0 and bool(tu)
            cv=dict(selected_tu=int(active),selected_coeff=16 if active else 0,selected_nz=nz if active else 0,
                native_verified_tu=int(active),all_policy_tu=int(active and not incomplete),
                policy_done_tu=[int(active)]*7,point_requested=[len(points) if active else 0,0],
                point_done=[len(points) if active and not incomplete else 0,0],snapshots_saved=int(active),
                native_skipped_budget=0,policy_group_skipped_budget=int(active and incomplete),point_skipped_budget=0,
                snapshot_skipped_budget=0,replays=int(active),coefficient_visits=48 if active else 0)
            if active and incomplete:cv['policy_done_tu'][6]=0
            raw.append(dict(kind='frame',schema=2,poc=p,component=c,tu=tu if active else 0,coeff=16*tu if active else 0,nz=nz if active else 0,
                target_tu=tu if active else 0,target_nz=nz if active else 0,target_coeff=16*tu if active else 0,
                bdpcm_tu=0,eligible_tu=tu if active else 0,eligible_coeff=16*tu if active else 0,eligible_nz=nz if active else 0,
                scoring_eligible_tu=tu if active else 0,scoring_eligible_nz=nz if active else 0,sampling_population_tu=tu if active else 0,
                unsupported_tu=0,capture_skipped=0,selected_tu=int(active),slice_cu_counts=[tu if active else 0]+[0]*11,
                coverage=cv,amplitude=[14,2,0,0,0] if active else [0]*5,support=[16,0,0,0,0,0] if active else [0]*6))
            if active:
                rates=[100000]*7;rates[4]+=delta
                if incomplete:rates[6]=None
                raw.append(dict(kind='tu',id='0_0_0_0_4_4',poc=0,component=0,x=0,y=0,w=4,h=4,qp=32,
                    slice_type='B',is_intra_cu=1,is_inter_cu=0,q_hash='q',entry_hash='ctx',nz=nz,coeff=16,
                    tu_population=tu,tu_selected=1,native_replay_complete=True,policy_complete=[r is not None for r in rates],
                    all_policy_complete=not incomplete,point_oracle_complete=not incomplete,point_requested=[len(points),0],
                    point_done=[len(points) if not incomplete else 0,0],snapshot_complete=True,snapshot='test.tsa',rates_frac=rates))
                if not incomplete:raw.extend(points)
    (root/'audit.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in raw))
    a.summarize(root,identity)
    return raw,identity


class AuditTests(unittest.TestCase):
    def test_equal_source_not_pooled_and_order_invariant(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);fixture(p/'eq',delta=32768,nz=10,tu=2);fixture(p/'sp','R13-2',delta=-32768,nz=100,tu=20)
            r=a.compare(p/'eq',p/'sp',p/'out')
            self.assertAlmostEqual(r['rows'][2]['bits_per_nonzero'],(.2-.2)/2)
            self.assertAlmostEqual(r['rows'][2]['bits_per_tu'],(1-1)/2)
            self.assertEqual(r,a.compare(p/'sp',p/'eq',p/'flip'))
            self.assertEqual(r['common_observed_frames'],[0,1])

    def test_missing_denominator_is_null(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);fixture(p/'eq',nz=0,tu=0);fixture(p/'sp','R13-2')
            r=a.compare(p/'eq',p/'sp',p/'out');self.assertIsNone(r['rows'][2]['bits_per_nonzero'])

    def test_late_policy_incomplete_blocks_all_primary_comparisons(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);fixture(p/'eq',incomplete=True);fixture(p/'sp','R13-2')
            r=a.compare(p/'eq',p/'sp',p/'out')
            self.assertIsNone(r['rows'][2]['bits_per_nonzero'])
            self.assertFalse(r['rows'][0]['comparison_complete'])
            for row in a.read_csv(p/'out/policy_comparison.csv'):
                if row['origin']=='balanced':self.assertEqual(row['minus_EQ_bits_per_tu'],'')
            matrix=a.read_csv(p/'eq/tu_policy_matrix.csv')[0]
            self.assertEqual(matrix['KEEP_SP_H_frac'],'');self.assertNotEqual(matrix['KEEP_EQ_frac'],'')

    def test_missing_non_anchor_policy_row_is_incomplete(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);fixture(p/'eq');fixture(p/'sp','R13-2')
            rows=a.read_csv(p/'sp/frame_summary.csv');rows=[r for r in rows if not (r['poc']=='0' and r['component']=='0' and r['policy']=='KEEP_SP_H')]
            a.csv_write(p/'sp/frame_summary.csv',rows)
            r=a.compare(p/'eq',p/'sp',p/'out');self.assertIsNone(r['rows'][2]['bits_per_nonzero'])

    def test_actual_slice_and_cu_mode_are_independent(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'eq';fixture(p)
            rows=a.read_csv(p/'strata.csv')
            self.assertTrue(any(r['dimension']=='slice_type' and r['bucket']=='B' for r in rows))
            self.assertFalse(any(r['dimension']=='slice_type' and r['bucket']=='I' for r in rows))
            self.assertTrue(any(r['dimension']=='cu_prediction' and r['bucket']=='intra' for r in rows))
            self.assertEqual(a.read_csv(p/'tu_policy_matrix.csv')[0]['slice_type'],'B')

    def test_positive_mean_and_quantiles_use_inclusion_weights(self):
        result=a.point_metrics([point(0,1,1),point(1,3,9),point(2,0,10)],3)
        self.assertAlmostEqual(result['accuracy'],.5)
        self.assertAlmostEqual(result['mean_regret_bits'],1.4)
        self.assertAlmostEqual(result['positive_regret_mean_bits'],2.8)
        self.assertEqual(result['sample_unweighted_positive_regret_mean_bits'],2)
        self.assertEqual(result['regret_median_bits'],0);self.assertEqual(result['regret_p95_bits'],3)

    def test_enrichment_never_enters_primary_accuracy(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'eq';records,ident=fixture(p,points=[point()])
            extra=point(2,1000,1000,sample='disagreement');records.append(extra)
            (p/'audit.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in records));a.summarize(p,ident)
            row=next(r for r in a.read_csv(p/'frame_summary.csv') if r['poc']=='0' and r['component']=='0' and r['policy']=='KEEP_EQ')
            self.assertEqual(float(row['accuracy']),1);self.assertEqual(float(row['mean_regret_bits']),0)
            enriched=[r for r in a.read_csv(p/'strata.csv') if r['sample']=='disagreement']
            self.assertTrue(all(r['accuracy']=='' and r['coverage_complete']=='False' for r in enriched))

    def test_history_uses_expanded_oracle(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'eq';fixture(p,points=[point(distinguishable=0,distinguishable_plus=1)])
            rows=a.read_csv(p/'strata.csv')
            self.assertTrue(all(r['accuracy']!='' and r['oracle_set']=='Cplus' for r in rows if r['policy'].endswith('_H')))
            self.assertTrue(all(r['accuracy']=='' and r['oracle_set']=='C0' for r in rows if not r['policy'].endswith('_H')))

    def test_output_budget_truncation_is_explicit(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'eq';_,identity=fixture(p);identity['limits']=dict(a.DEFAULTS,core_bytes=1)
            result=a.summarize(p,identity)
            self.assertFalse(result['output_complete']);self.assertGreater(result['output_dropped_rows'],0)

    def test_asymmetric_budget_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);fixture(p/'eq');fixture(p/'sp','R13-2')
            x=a.read_json(p/'sp/run.json');x['limits']['replays_per_frame']=1;a.save(p/'sp/run.json',x)
            with self.assertRaisesRegex(ValueError,'Asymmetric'):a.compare(p/'eq',p/'sp',p/'out')

    def test_missing_observation_frame_is_not_silently_intersected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);fixture(p/'eq');fixture(p/'sp','R13-2')
            rows=a.read_csv(p/'sp/frame_summary.csv');a.csv_write(p/'sp/frame_summary.csv',[r for r in rows if r['poc']!='1'])
            r=a.compare(p/'eq',p/'sp',p/'out')
            self.assertEqual(r['common_observed_frames'],[0,1]);self.assertIsNone(r['rows'][2]['bits_per_tu'])

    def test_duplicate_frame_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'hash';path.write_text('0,y,u,v\n0,y,u,v\n')
            with self.assertRaises(ValueError):a.hash_frames(path)

    def test_no_nan(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):a.save(Path(tmp)/'bad.json',{'x':float('nan')})

    def test_bootstrap_discloses_omitted_sampling_uncertainty(self):
        rows=stats.paired_frame_intervals([[],[]],[],{0:False,1:False,2:False})
        self.assertTrue(all(r['ci95'] is None and not r['includes_two_stage_sampling_uncertainty'] for r in rows))

if __name__=='__main__':unittest.main()
