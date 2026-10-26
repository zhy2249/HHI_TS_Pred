#!/usr/bin/env python3
import unittest,random,json
from pathlib import Path
import rule_suite as R
import ts_learning as L

ROOT=Path(__file__).resolve().parent
class Rules(unittest.TestCase):
 def setUp(self):
  self.tu=json.loads((ROOT/'ce01_tu.json').read_text());self.rules=R.catalogue()
 def test_catalogue(self):
  self.assertEqual(len(self.rules),61);self.assertLessEqual(len(self.rules),64)
  self.assertEqual(len(set(c['id'] for c in self.rules)),61)
 def test_cached_rows_identical(self):
  rows=list(L.causal_rows(self.tu))
  for c in self.rules:self.assertEqual(R.predict(self.tu,c),R.predict(self.tu,c,prepared=rows))
 def test_old_actions_unchanged(self):
  rows=list(L.causal_rows(self.tu))
  for a in range(10):self.assertEqual(R.predict(self.tu,self.rules[a])[0],[r['pred'][a] for r in rows])
 def test_every_output_legal(self):
  rng=random.Random(20261025)
  t=dict(self.tu);t.update(w=4,h=4,scan=[0,4,1,8,5,2,12,9,6,3,13,10,7,14,11,15])
  for _ in range(12):
   t['q']=[rng.randrange(-6,7) for _ in range(16)]
   rows=list(L.causal_rows(t))
   for c in self.rules:
    p,_,_=R.predict(t,c,prepared=rows)
    for i,v in enumerate(p):
     pool=rows[i]['cplus'] if c['id'].endswith('_H') else rows[i]['c0']
     if sum(x>0 for x in rows[i]['h'])<3:self.assertEqual(v,max(rows[i]['h'][:2]))
     else:self.assertIn(0 if v<=1 else v,pool)
 def test_state_unit_steps(self):
  rng=random.Random(42)
  t=dict(self.tu);t.update(w=4,h=4,scan=[0,4,1,8,5,2,12,9,6,3,13,10,7,14,11,15])
  for _ in range(10):
   t['q']=[rng.randrange(5) for _ in range(16)]
   rows=list(L.causal_rows(t))
   for c in self.rules:
    if c['kind']!='state':continue
    _,_,tr=R.predict(t,c,True,prepared=rows)
    for e in tr:
     self.assertLessEqual(abs(e['state_after']-e['state_before']),1)
     self.assertLessEqual(abs(e['weight_after']-e['weight_before']),1)
     self.assertTrue(0<=e['state_after']<=(c['k']+1)*c['phase']-1)
 def test_current_and_future_no_leak(self):
  rng=random.Random(19)
  t=dict(self.tu);t.update(w=4,h=4,scan=[0,4,1,8,5,2,12,9,6,3,13,10,7,14,11,15])
  t['q']=[rng.randrange(4) for _ in range(16)]
  rows=list(L.causal_rows(t));base={c['id']:R.predict(t,c,prepared=rows)[0] for c in self.rules}
  for i in range(16):
   changed=dict(t);changed['q']=list(t['q'])
   for j in range(i,16):changed['q'][t['scan'][j]]=rng.randrange(1,7)
   rr=list(L.causal_rows(changed))
   for c in self.rules:self.assertEqual(base[c['id']][:i+1],R.predict(changed,c,prepared=rr)[0][:i+1],(c['id'],i))
 def test_metadata_not_features(self):
  a=dict(self.tu,sequence='Johnny',origin='R13-1',poc=16,x=856,y=384)
  b=dict(a,sequence='other',origin='R13-2',poc=9999,x=0,y=0)
  for c in self.rules:self.assertEqual(R.predict(a,c)[0],R.predict(b,c)[0])
 def test_ce01_three_signatures(self):
  s={R.signature(self.tu,R.predict(self.tu,c)[0]) for c in self.rules}
  self.assertEqual(len(s),3)
 def test_hit_missing_identity_feedback(self):
  c=next(c for c in self.rules if c['id']=='S_K4_zero_P1_hit')
  _,_,tr=R.predict(self.tu,c,True)
  self.assertEqual(sum(e['direction']!=0 for e in tr),0)
 def test_cost_is_late(self):
  c=next(c for c in self.rules if c['id']=='S_K4_zero_P1_cost')
  p,_,tr=R.predict(self.tu,c,True)
  self.assertEqual(p[31],2);self.assertEqual(tr[31]['state_before'],0)
  self.assertEqual(tr[31]['state_after'],1);self.assertEqual(p[67],0)
 def test_guard_is_additional_acceptance_not_weight_change(self):
  c=next(c for c in self.rules if c['id']=='HYBRID_K4_zero_P1')
  p,_,tr=R.predict(self.tu,c,True)
  self.assertEqual(tr[31]['weight_before'],0);self.assertEqual(p[31],0)
  self.assertTrue(tr[31]['guarded'])
 def test_ce01_index_and_history(self):
  rows=list(L.causal_rows(self.tu))
  self.assertEqual([r['scan'] for r in rows if r['a'] and sum(v>0 for v in r['h'])>=3],[30,31,38,42,64,65,67])
  self.assertEqual(rows[31]['x'][L.FEATURES.index('hist_mode')],1)
  self.assertEqual(rows[31]['x'][L.FEATURES.index('prefix_ones1024')],1024*5//6)

if __name__=='__main__':unittest.main(verbosity=2)
