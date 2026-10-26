"""Independent exhaustive/naive R15 specification. No decoder or video I/O."""
from itertools import permutations

REV = 'TS-MG-STATIC-FAST-v1'
METHODS = [
    (0, 0, 'CURRENT', 'C', 1, False), (0, 2, 'STATIC_EQ', 'B', 1, False),
    (0, 3, 'STATIC_SP', 'B', 1, True), (1, 1, 'IDENTITY', 'I', 0, False),
    *[(i+2, i+4, f'G_EQ_K{k}', 'G', k, False) for i,k in enumerate((2,3,4,6))],
    *[(i+6, i+8, f'N_EQ_K{k}', 'N', k, False) for i,k in enumerate((2,3,4,6))],
    *[(i+10, i+12, f'P_EQ_K{k}', 'P', k, False) for i,k in enumerate((2,3,6))],
    (13,15,'D_EQ_K2','D',2,False),(14,16,'D_EQ_K3','D',3,False),
    (15,17,'X_EQ_K2','X',2,False),(16,18,'X_EQ_K3','X',3,False),
    (17,19,'G_SP_K3','G',3,True),(18,20,'N_SP_K3','N',3,True),
]


def mapping(a, p):
    if not a:return 0
    if a in p:return p.index(a)+1
    return a+len(p)-sum(v<a for v in p)


def inverse(y,p):
    if not y:return 0
    if y<=len(p):return p[y-1]
    a=y-len(p)
    for q in sorted(p):
        if a>=q:a+=1
    return a


def canonical(p):
    p=tuple(p)
    while p and mapping(p[-1],p[:-1])==len(p):p=p[:-1]
    return p


def cost(a,rice=1,dynamic_range=15):
    if a<2:return a
    c=2+sum(a>=v for v in (2,4,6,8))
    if a>=10:
        v=(a-10)//2;cutoff=5
        if v<(cutoff<<rice):c+=(v>>rice)+1+rice
        else:
            cap=32-cutoff-dynamic_range;code=(v>>rice)-cutoff
            if code>=(1<<cap)-1:c+=cutoff+cap+dynamic_range
            else:
                p=0
                while code>(2<<p)-2:p+=1
                c+=cutoff+2*p+rice+1
    return c


def choose(h,method,rice=1,dynamic_range=15):
    _,_,_,kind,k,spatial=method
    current=max(h[:2]);n=sum(a!=0 for a in h)
    priority=([current] if current>1 else [])+[1]+sorted(set(h)-{0,1,current})
    def score(p):return sum((2 if spatial and j<2 else 1)*cost(mapping(a,p),rice,dynamic_range) for j,a in enumerate(h) if a)
    if kind=='I':p=()
    elif kind=='C' or n<3:p=(current,) if current else ()
    else:
        b=min(((q,) for q in priority),key=score)
        def greedy(root,neutral=False):
            p=best=root
            while len(p)<min(k,len(priority)):
                q=min((q for q in priority if q not in p),key=lambda q:score(p+(q,)))
                new=p+(q,)
                if score(new)>score(p) or (not neutral and score(new)==score(p)):break
                p=new
                if score(p)<score(best):best=p
            return best
        if kind=='B':p=b
        elif kind in ('G','N'):p=greedy(b,kind=='N')
        elif kind=='P':p=greedy((1,))
        elif kind=='D':p=min((greedy(b),greedy((1,))),key=score)
        elif kind=='X':
            def key(p):
                c=canonical(p)
                return score(p),c!=canonical(b),len(c),tuple(priority.index(v) for v in c)
            p=min((p for size in range(min(k,len(priority))+1) for p in permutations(priority,size)),key=key)
        else:raise ValueError(kind)
    return canonical(p),score(p)
