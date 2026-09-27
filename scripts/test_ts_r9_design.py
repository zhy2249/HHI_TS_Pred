"""Independent finite-domain implementation of R9's frozen scoring equations."""
import random
import subprocess
import tempfile
import unittest
from pathlib import Path
from ts_predictor_naming import R9_MODE_NUMBERS, directory_name

ROOT=Path(__file__).resolve().parents[1]
def canonical(p,k=0): return (0,0) if p<=k+1 else (p,k)
def mapping(a,action):
    p,k=action
    return a if p<=k+1 or a<=k else k+1 if a==p else a+1 if a<p else a
def objective(h,c,action,mode):
    loss=[c[mapping(a,action)] for a in h if a]
    base=[c[a] for a in h if a]
    s=sum(loss); b=max([0]+[x-y for x,y in zip(base,loss)])
    n=sum(a!=0 for a in h); n1=h.count(1); n2=sum(a>=2 for a in h)
    if mode==4: return 2*s+b
    if mode in (5,13): return n*s+n2*b
    return s+b+(n1*max(0,c[2]-c[1]) if mode==6 and action[0]>=2 else 0)
def reference(mode,h,c):
    n=sum(a!=0 for a in h); cur=canonical(max(h[:2]))[0]
    smax=cur if n==2 and all(h[:2]) else 0
    axis=n==2 and (h[0]>=2 and h[0]==h[3] and h[1]==0 or h[1]>=2 and h[1]==h[4] and h[0]==0)
    hit=mode in (3,13) and axis; passed=hit and c[cur]>c[1]
    if n<3:
        p=cur if mode==1 or passed else smax
        action=canonical(p,1 if mode==7 else 0)
        if mode==8:
            alt=canonical(p,1)
            if objective(h,c,alt,2)<objective(h,c,action,2): action=alt
    else:
        complete=mode in (1,2,7,8)
        ps={0,cur}|{a for a in h if a}
        if complete: ps|={a+1 for a in h if 0<a<len(c)-1}
        def best(k):
            actions={canonical(p,k) for p in ps}; cp=canonical(cur,k)[0]
            def key(a):
                tie=(0 if a[0]==cp else 1 if a[0]==0 else 2,a[0])
                return (objective(h,c,a,mode), a[0]) if mode==8 and k else (objective(h,c,a,mode),tie)
            return min(actions,key=key)
        action=best(1 if mode==7 else 0)
        if mode==8:
            alt=best(1)
            if objective(h,c,alt,2)<objective(h,c,action,2): action=alt
    return action+(objective(h,c,action,mode),n,int(hit),int(passed))

class R9Design(unittest.TestCase):
    def test_permutation_and_up(self):
        for limit in (2,3,8,32):
            for p in range(limit+1):
                for k in (0,1):
                    ys=[mapping(a,canonical(p,k)) for a in range(limit+1)]
                    self.assertEqual(sorted(ys),list(range(limit+1)))
                    if p>k+1: self.assertEqual(ys[p],k+1)
    def test_cpp_reference(self):
        rng=random.Random(20260927); cases=[]
        for _ in range(800):
            limit=16; h=[rng.choice([0,0,1,1,2,3,4,8,16]) for _ in range(5)]
            cost=[0]+[rng.randrange(1,800000) for _ in range(limit)]
            for m in range(1,14): cases.append((m,limit,h,cost))
        with tempfile.TemporaryDirectory() as tmp:
            exe=str(Path(tmp)/'probe')
            subprocess.run(['g++','-std=c++17','-O2','-Isource/Lib','scripts/ts_r9_formula_probe.cpp','-o',exe],cwd=ROOT,check=True)
            data=''.join(' '.join(map(str,[m,lim,*h,*c]))+'\n' for m,lim,h,c in cases)
            result=subprocess.run([exe],input=data,text=True,capture_output=True,check=True)
        rows=result.stdout.splitlines(); self.assertEqual(len(rows),len(cases))
        for row,(m,lim,h,c) in zip(rows,cases):
            got=tuple(map(int,row.split())); self.assertEqual(got,reference(m,h,c),(m,h,c))
            if m==8:
                self.assertLessEqual(got[2],reference(2,h,c)[2])
                self.assertLessEqual(got[2],reference(7,h,c)[2])
            if m==13: self.assertEqual(got[:2],reference(3 if got[3]<3 else 5,h,c)[:2])
    def test_registry(self):
        import batch_test
        self.assertEqual(set(R9_MODE_NUMBERS.values()),set(range(1,14)))
        for name,n in R9_MODE_NUMBERS.items():
            self.assertIn(name,batch_test._TS_PREDICTOR_MODES)
            self.assertTrue(directory_name(name).startswith(f'r9_{n}_'))
    def test_activity_parser(self):
        from ts_r9_activity import parse,write
        header='mode,cutoff,remap_vs_r8_12,regular_count,regular_nonzero'
        self.assertEqual(parse('TS_R9_STATS_HEADER '+header+'\nTS_R9_STATS 3,10,2,4,3',3,'STATS')[0]['regular_count'],4)
        for bad in ('3,0,1,0,0','3,8,0,0,0','3,10,0,1,2','3,10,2,2,1','4,10,0,1,1','3,10,0'):
            with self.assertRaises(ValueError): parse('TS_R9_STATS_HEADER '+header+'\nTS_R9_STATS '+bad,3,'STATS')
        with self.assertRaises(ValueError): parse('TS_R9_SEARCH_HEADER mode,local_gain_sum\nTS_R9_SEARCH 11,-1',11,'SEARCH')
        with self.assertRaises(ValueError): parse('TS_R9_SEARCH_HEADER mode,local_gain_sum\nTS_R9_SEARCH 11,nan',11,'SEARCH')
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'output.csv'; path.write_text('stale data')
            write(path,[]); self.assertEqual(path.read_text(),'')

if __name__=='__main__': unittest.main()
