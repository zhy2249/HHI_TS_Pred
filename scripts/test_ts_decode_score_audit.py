import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec=importlib.util.spec_from_file_location('audit',Path(__file__).with_name('ts_decode_score_audit.py'))
a=importlib.util.module_from_spec(spec);spec.loader.exec_module(a)

class AuditTests(unittest.TestCase):
    def build(self,root,origin,delta=32768,nz=10,tu=2,frames=(0,1)):
        root.mkdir()
        a.save(root/'run.json',dict(origin=origin,pair_id='test',first_poc=0,last_poc=1,component=-1,profile='standard',policies=a.POLICIES,limits=a.DEFAULTS,pairing_status='unknown'))
        a.save(root/'decode_validation.json',dict(audit_complete=True))
        (root/'reconstruction.csv').write_text(''.join(f'{p},y,u,v\n' for p in frames))
        rows=[]
        for policy in a.POLICIES:
            rows.append(dict(poc=0,component=0,policy=policy,target_tu=tu,target_nz=nz,ht_policy_rate_frac=100000+(delta if policy=='KEEP_SP' else 0),sampling_complete=True,ht_distinguishable_population=1,ht_correct=1,ht_regret_frac=0))
        a.csv_write(root/'frame_summary.csv',rows)
        a.csv_write(root/'tu_policy_matrix.csv',[dict(poc=0,component=0,x=0,y=0,w=4,h=4,id='sample',q_hash='q',entry_hash='ctx')])

    def test_equal_source_not_pooled(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);self.build(p/'eq','R13-1',32768,10,2);self.build(p/'sp','R13-2',-32768,100,20)
            r=a.compare(p/'eq',p/'sp',p/'out')
            self.assertAlmostEqual(r['rows'][2]['bits_per_nonzero'],(.1-.01)/2)
            self.assertAlmostEqual(r['rows'][2]['bits_per_tu'],(.5-.05)/2)
            self.assertEqual(r['common_observed_frames'],[0]);self.assertEqual(r['common_decoded_frames'],[0,1])
            flipped=a.compare(p/'sp',p/'eq',p/'flip');self.assertEqual(r,flipped)

    def test_missing_denominator_is_null(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);self.build(p/'eq','R13-1',nz=0,tu=0);self.build(p/'sp','R13-2')
            r=a.compare(p/'eq',p/'sp',p/'out');self.assertIsNone(r['rows'][2]['bits_per_nonzero'])

    def test_bdpcm_only_frame_does_not_poison_target_total(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)
            frame=dict(kind='frame',poc=0,component=0,tu=1,coeff=16,nz=2,
                       target_nz=0,target_coeff=0,bdpcm_tu=1,eligible_tu=0,
                       selected_tu=0,amplitude=[14,2,0,0,0],support=[16,0,0,0,0,0])
            (out/'audit.jsonl').write_text(json.dumps(frame)+'\n')
            a.summarize(out,dict(pair_id='test',origin='R13-1',nominal_qp=32))
            rows=a.read_csv(out/'frame_summary.csv')
            self.assertTrue(all(r['ht_policy_rate_frac']=='0' and r['sampling_complete']=='True' for r in rows))
            self.assertTrue(all(r['accuracy']=='' and r['target_nz']=='0' for r in rows))

    def test_asymmetric_sampling_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);self.build(p/'eq','R13-1');self.build(p/'sp','R13-2')
            x=a.read_json(p/'sp/run.json');x['last_poc']=2;a.save(p/'sp/run.json',x)
            with self.assertRaisesRegex(ValueError,'Asymmetric'):a.compare(p/'eq',p/'sp',p/'out')

    def test_duplicate_frame_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'hash';path.write_text('0,y,u,v\n0,y,u,v\n')
            with self.assertRaises(ValueError):a.hash_frames(path)

    def test_history_strata_use_expanded_oracle(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)
            point=dict(kind='point',poc=0,component=0,sample='uniform',a=1,n=3,intra=1,area=16,
                H=[2,1,1,0,0],scores168=[[]]+[[10,12]]*6,weight_sum=[0]+[3]*6,
                distinguishable=0,distinguishable_plus=1,regret_frac=[0]*7,
                hist=3,history_nz=5,c0=[2,0],cplus=[2,0,3],pred=[0]*5+[3,3],
                cost_frac=[100]*5+[90,90],coverage_frac=10)
            (out/'audit.jsonl').write_text(json.dumps(point)+'\n')
            a.summarize(out,dict(pair_id='test',origin='R13-1',nominal_qp=32))
            rows=a.read_csv(out/'strata.csv')
            self.assertTrue(all(r['distinguishable']=='1' and r['oracle_set']=='Cplus' for r in rows if r['policy'].endswith('_H')))
            self.assertTrue(all(r['distinguishable']=='0' and r['oracle_set']=='C0' for r in rows if not r['policy'].endswith('_H')))

    def test_no_nan(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):a.save(Path(tmp)/'bad.json',{'x':float('nan')})

    def test_no_encoder_launch(self):
        source=Path(a.__file__).read_text()
        self.assertNotIn("['EncoderApp'",source)
        self.assertNotIn('shell=True',source)

if __name__=='__main__':unittest.main()
