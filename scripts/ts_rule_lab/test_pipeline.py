"""Protocol tests use synthetic records, never measured video rates."""
import copy,gzip,json,tempfile,unittest
from pathlib import Path
import benchmark_rules as B
import rule_suite as R
import ts_corpus as P
import ts_learning as L
import integrate

class Pipeline(unittest.TestCase):
 def manifest(self,root):
  pairs=[]
  for q in (22,27,32,37):
   pairs.append(dict(pair_id=f'Demo_QP{q}',sequence='Demo',nominal_qp=q,origins={o:dict(path=f'{o}.bin',sha256='0'*64,bytes=1,native_policy=n,scope='all') for o,n in P.origins().items()}))
  p=root/'manifest.json';P.save(p,dict(pairs=pairs));return p
 def index(self,root):
  records=[];fixture=json.loads((Path(__file__).parent/'ce01_tu.json').read_text())
  for q in (22,27,32,37):
   for origin,native in P.origins().items():
    key=f'Demo_QP{q}__{origin}'
    tu=dict(fixture,poc=0,kind='tu',q_hash='111',entry_hash='222',native_verified=True,nonzero=14,rates_frac=[1000]*10,model_rates_frac=[1000]*61)
    tu['model_rates_frac'][10]=900;tu['model_rates_frac'][11]=1100
    data=root/(key+'.jsonl.gz')
    footer=dict(kind='footer',complete=True,verified_tu=1,labeled_positions=0)
    with gzip.open(data,'wt') as f:
     f.write(json.dumps(tu)+'\n'+json.dumps(footer)+'\n')
    records.append(dict(task=dict(key=key,sequence='Demo',nominal_qp=q,origin=origin,native_policy=native),
      request=dict(method_ids=[c['id'] for c in R.catalogue()],catalogue_sha256=B.catalogue_hash()),complete=True,footer=footer,
      data=str(data),data_sha256=P.sha(data),frames=1,sei_status='synthetic',on_off_equal=True))
  out=root/'index.json';P.save(out,dict(revision=L.REV,sequences=['Demo'],expected_streams=8,completed_streams=8,complete=True,records=records))
  return out
 def test_plan_is_complete_cartesian_grid(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);p=P.plan(self.manifest(root),root/'plan.json',1)
   self.assertEqual(p['streams'],8);self.assertEqual(len(p['tasks']),8)
 def test_plan_rejects_duplicate_content_qp(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);m=self.manifest(root);x=P.readj(m);v=copy.deepcopy(x['pairs'][0]);v['pair_id']='alias';x['pairs'].append(v);P.save(m,x)
   with self.assertRaisesRegex(ValueError,'Duplicate content/QP'):P.plan(m,root/'p.json',1)
 def test_full_index_rejects_missing_cell(self):
  with tempfile.TemporaryDirectory() as d:
   p=self.index(Path(d));x=P.readj(p);x['records'].pop();x['expected_streams']=x['completed_streams']=7;P.save(p,x)
   with self.assertRaisesRegex(ValueError,'Cartesian'):P.complete_index(p)
 def test_fingerprint_failure(self):
  with tempfile.TemporaryDirectory() as d:
   p=self.index(Path(d));x=P.readj(p);Path(x['records'][0]['data']).write_bytes(b'wrong')
   with self.assertRaisesRegex(ValueError,'changed'):P.complete_index(p)
 def test_schedules_bind_catalogue_and_inputs(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);index=self.index(root);proof=B.make_schedules(index,root/'schedules')
   self.assertEqual(len(proof),8)
   pred=next((root/'schedules').glob('*.pred'));self.assertEqual(pred.read_text().splitlines()[0],'TSCPRED 1 61')
   meta=P.readj(pred.with_suffix('.json'));self.assertEqual(meta['catalogue_sha256'],B.catalogue_hash());self.assertEqual(meta['schedule_sha256'],P.sha(pred))
 def test_aggregate_uses_full_tu_not_point_deltas(self):
  with tempfile.TemporaryDirectory() as d:
   index=self.index(Path(d));_,rows=B.aggregate(index)
   row=next(r for r in rows if r['component']=='all' and r['method']=='GUARD_EXTRA_NEAR')
   self.assertEqual(row['rate_frac'],900);self.assertEqual(row['gain_vs_current_bits'],100/32768)
   self.assertEqual(row['cheaper_tu_vs_current'],1)
 def test_catalogue_order_mismatch_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   index=self.index(Path(d));x=P.readj(index);x['records'][0]['request']['method_ids'].reverse();P.save(index,x)
   with self.assertRaisesRegex(ValueError,'identities'):B.aggregate(index)
 def test_complete_result_report_and_top_losses(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);index=self.index(root);B.report(index,root/'report')
   scope=P.readj(root/'report/report_scope.json');self.assertTrue(scope['no_BDrate']);self.assertEqual(scope['best_descriptive'],'GUARD_EXTRA_NEAR')
   self.assertTrue((root/'report/worst_TU_cases.csv').exists())
   self.assertEqual(len(P.readj(root/'report/run_receipts.json')['streams']),8)
 def test_exact_anchor_rejects_ambiguous_source(self):
  with self.assertRaises(ValueError):integrate.one('xx','x','y')
  self.assertEqual(integrate.one('axb','x','z'),'azb')
 def test_no_encoder_or_shell_launch(self):
  for mod in (P,B,integrate):
   text=Path(mod.__file__).read_text()
   self.assertNotIn("['EncoderApp'",text);self.assertNotIn('shell=True',text)

if __name__=='__main__':unittest.main(verbosity=2)
