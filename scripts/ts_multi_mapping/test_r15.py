import copy,csv,itertools,json,random,subprocess,sys,tempfile,unittest
from types import SimpleNamespace
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import reference as R
import run as M


class MappingTests(unittest.TestCase):
    def test_public_numbers(self):
        self.assertEqual([m[0] for m in R.METHODS if m[0]],list(range(1,19)))
        self.assertEqual({m[1] for m in R.METHODS if not m[0]},{0,2,3})
    def test_inverse(self):
        for size in range(4):
            for p in itertools.permutations(range(1,8),size):
                self.assertEqual(sorted(R.mapping(a,p) for a in range(8)),list(range(8)))
                for a in range(8):
                    self.assertEqual(R.inverse(R.mapping(a,p),p),a)
                    self.assertEqual(R.mapping(a,R.canonical(p)),R.mapping(a,p))
    def test_examples(self):
        h=(4,5,5,6,1)
        self.assertEqual([R.choose(h,m)[1] for m in R.METHODS[3:6]],[18,13,12])
        self.assertEqual(R.choose((1,2,2,6,8),R.METHODS[5])[1],15)
        self.assertEqual(R.choose((1,2,2,6,8),R.METHODS[9])[1],14)
        self.assertEqual(R.choose((0,2,1,0,1),R.METHODS[1]),((),5))
    def test_static_control(self):
        rng=random.Random(26)
        for _ in range(300):
            h=[rng.randrange(20) for _ in range(5)];current=max(h[:2])
            candidates=[current if current>1 else 0]+([0] if current>1 else [])+sorted(set(h)-{0,1,current})
            for idx in (1,2):
                cost=lambda p:sum((2 if idx==2 and j<2 else 1)*R.cost(R.mapping(a,(p,) if p else ())) for j,a in enumerate(h) if a)
                old=min(candidates,key=cost) if sum(v!=0 for v in h)>=3 else current
                self.assertEqual(R.choose(h,R.METHODS[idx])[0],R.canonical((old,) if old else ()))
    def test_parser_missing_method(self):
        a=M.Aggregate();a.accept(dict(kind='header',revision=R.REV,action_protocol='TS-MG-ACTION-v1',method_mg_ids=M.IDS,rate_scale=32768))
        with self.assertRaisesRegex(ValueError,'Missing method'):a.accept(dict(kind='tu',rates_frac=[0]*20,scores=[0]*21,action_hashes=[0]*21))
    def test_incomplete_is_not_zero(self):
        a=M.Aggregate()
        a.footer=dict(complete=False,methods_complete=20)
        with self.assertRaisesRegex(ValueError,'Incomplete'):a.finish()
    def test_header_versions(self):
        with self.assertRaises(ValueError):M.Aggregate().accept(dict(kind='header',revision='TS-RULE-LAB-v1',action_protocol='TSCPRED',method_mg_ids=M.IDS,rate_scale=32768))
    def test_current_not_selection_input(self):
        self.assertEqual(list(__import__('inspect').signature(R.choose).parameters),['h','method','rice','dynamic_range'])
    def test_loss_percentile_bounds(self):
        self.assertEqual(M.percentile_bounds([0]*32,.9),(None,None))
        hist=[0]*32;hist[15]=9;hist[31]=1
        self.assertEqual(M.percentile_bounds(hist,.9),(1,2))
        self.assertEqual(M.percentile_bounds(hist,.99),(65536,None))
    def test_missing_source_plan(self):
        plan=dict(revision=R.REV,methods_sha256=M.digest(M.catalog()),streams=1,scope='paired_prefix17',tasks=[
            dict(key='prefix__R13-1',sequence='Johnny',nominal_qp=32,origin='R13-1',native_policy='r13_keep_hit_uniform',expected_frames=17)])
        with self.assertRaisesRegex(ValueError,'Incomplete prefix'):M.validate_plan(plan)
    def test_duplicate_source_plan(self):
        t=dict(key='a',sequence='Johnny',nominal_qp=32,origin='R13-1',native_policy='r13_keep_hit_uniform',expected_frames=17)
        plan=dict(revision=R.REV,methods_sha256=M.digest(M.catalog()),streams=2,scope='paired_prefix17',tasks=[t,dict(t,key='b')])
        with self.assertRaisesRegex(ValueError,'Duplicate sequence'):M.validate_plan(plan)
    def test_balancing_uses_source_nz_not_pooled_nz(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);records=[];tasks=[]
            for s in range(12):
                for qp in (22,27,32,37):
                    for origin in ('R13-1','R13-2'):
                        n=2 if origin=='R13-1' else 8;gain=32768 if n==2 else 65536
                        key=f's{s}_{qp}_{origin}'
                        task=dict(key=key,sequence=f's{s}',nominal_qp=qp,origin=origin,native_policy=M.P.origins()[origin]);tasks.append(task)
                        footer=dict(complete=True,target_tu=1,positions=16,nonzero=n)
                        rows=[]
                        for method in M.CATALOG:
                            a=M.metric();a.update(tu=1,positions=16,nonzero=n,rate_frac=655360-gain,current_frac=983040,static_eq_frac=655360,static_sp_frac=655360)
                            rows.append(dict(dimension='component',value='0',mg=method['mg'],**a))
                        path=root/(key+'.json');M.P.save(path,dict(aggregates=rows,mapping_activity=[],worst_cases=[]))
                        records.append(dict(task=task,complete=True,frames=1,footer=footer,on_off_equal=None,sei_status='not-applicable',summary=str(path),data_sha256=M.P.sha(path)))
            plan=dict(revision=R.REV,methods_sha256=M.digest(M.catalog()),scope='full96_EOF',streams=96,tasks=tasks)
            index=root/'index.json';M.P.save(index,dict(complete=True,revision=R.REV,methods_sha256=M.digest(M.catalog()),scope='full96_EOF',plan=plan,expected_streams=96,records=records))
            M.report(SimpleNamespace(index=index,output=root/'out'))
            with (root/'out/method_summary.csv').open() as f:row=next(csv.DictReader(f))
            self.assertAlmostEqual(float(row['static_eq_balanced_bits_per_nz']),0.375)
            self.assertAlmostEqual(float(row['static_eq_pooled_saving_bits']),144)


def cross_language(executable,count=512):
    rng=random.Random(20261026);cases=[]
    for i in range(count):
        depth=(8,15,20)[i%3];bound=(12,256,1<<depth)[i%3]
        cases.append(([rng.randrange(bound+1) for _ in range(5)],i%9,depth))
    cases += [([4,5,5,6,1],1,15),([1,2,2,6,8],1,15),([1,1,1,6,6],1,15),([0,2,1,0,1],1,15)]
    payload=''.join(' '.join(map(str,[*h,r,d]))+'\n' for h,r,d in cases)
    out=subprocess.check_output([str(executable),'--cases'],input=payload,text=True).splitlines()
    assert len(out)==len(cases)*21
    for i,(h,r,d) in enumerate(cases):
        for j,m in enumerate(R.METHODS):
            got=list(map(int,out[21*i+j].split()));action,score=R.choose(h,m,r,d)
            assert got==[m[1],score,len(action),*action],(h,r,d,m,got,action,score)
    return dict(neighborhoods=len(cases),method_checks=len(out),failures=0)

if __name__=='__main__':unittest.main()
