// Test-only independent geometry, weighted C, and outer selector. Existing public
// experts supply A/B/old-C; no r12Integer/r12Experts/r12Select/r9SupportTS calls.
static uint64_t r12References=0,r12DistinctD=0,r12Changed=0;
static void r12Reference(const CoeffCodingContext &ctx,int s,const std::vector<TCoeff> &q,int rice,int range)
{
  using namespace TsFixedPrediction;
  const int m=r12PublicMode(mode()),count=m==3?4:3,w=ctx.width();
  const int dx[5]={-1,0,-1,-2,0},dy[5]={0,-1,-1,0,-2},weights[5]={2,2,1,1,1};
  const auto positions=[&](int j) {
    std::array<int,5> out; out.fill(-1); const int p=ctx.blockPos(j);
    for(int t=0;t<5;++t) if(p%w+dx[t]>=0 && p/w+dy[t]>=0)
      for(int k=0;k<j;++k) if(int(ctx.blockPos(k))==p+dx[t]+w*dy[t]) { out[t]=k; break; }
    return out;
  };
  const auto support=[&](int j) {
    std::array<int,5> h{}; const auto pos=positions(j);
    for(int t=0;t<5;++t) { if(pos[t]>=0) { h[t]=std::abs(q[ctx.blockPos(pos[t])]); } }
    return h;
  };
  const auto integer=[&](int a) { return int64_t(syntaxCost(a,rice,range))<<SCALE_BITS; };
  const auto experts=[&](int j) {
    const auto h=support(j); const int cur=canonicalAction(std::max(h[0],h[1])).predictor;
    R10Actions a{{canonicalAction(ctx.r8PredictionTS(12,j,q.data()).predictor),
      canonicalAction(ctx.magnitudePredictorModeTS(10,j,q.data())),
      canonicalAction(ctx.magnitudePredictorModeTS(13,j,q.data())),canonicalAction(cur)}};
    if(m==7 || m==8 || m==11 || m==12)
    {
      int n=0; for(int v:h) { n+=v!=0; }
      if(n<3) { a[2]=canonicalAction(cur); return a; }
      std::vector<int> candidates{cur}; if(cur) { candidates.push_back(0); }
      auto sorted=h; std::sort(sorted.begin(),sorted.end());
      for(int v:sorted) if(v>1 && v!=cur && std::find(candidates.begin(),candidates.end(),v)==candidates.end())
        candidates.push_back(v);
      const auto loss=[&](int p) {
        int64_t total=0; for(int t=0;t<5;++t) if(h[t]) { total+=weights[t]*integer(remap(h[t],p)); } return total;
      };
      int best=cur; for(int p:candidates) { if(loss(p)<loss(best)) { best=p; } }
      int64_t penalty=0;
      for(int t=0;t<5;++t) if(h[t])
      {
        const auto gain=integer(remap(h[t],cur))-integer(remap(h[t],best));
        if(m==8 || m==11) { penalty=std::max(penalty,gain*(m==8?weights[t]:1)); }
      }
      a[2]=canonicalAction(loss(cur)-loss(best)>penalty?best:cur);
    }
    return a;
  };
  const auto actual=ctx.r12PredictionTS(m,s,q.data()); const auto actions=experts(s); const auto pos=positions(s);
  const auto h=support(s); for(int t=0;t<5;++t) { require(h[t]==actual.support[t]); }
  for(int e=0;e<count;++e) { require(actions[e]==actual.actions[e]); }
  std::vector<std::array<int64_t,4>> rowsI,rowsF;
  std::vector<int> slots; std::vector<bool> effective;
  int64_t ci[4]{},cf[4]{},wi[4]{},wf[4]{},direct[4]{}; int neff=0,ndir=0;
  for(int t=0;t<5;++t)
  {
    const int j=pos[t]; if(j<ctx.minSubPos() || !h[t]) { continue; }
    const auto past=experts(j); const auto old=support(j); const auto &table=ctx.tsRateTable((old[0]!=0)+(old[1]!=0));
    std::array<int64_t,4> ri{},rf{}; bool diff=false;
    for(int e=0;e<count;++e)
    {
      const int v=remap(h[t],past[e]); ri[e]=integer(v); rf[e]=table.cost(v,rice,range);
      ci[e]+=ri[e]; cf[e]+=rf[e]; wi[e]+=weights[t]*ri[e]; wf[e]+=weights[t]*rf[e];
      if(t<2) { direct[e]+=ri[e]; } if(e<3) { diff |= v!=remap(h[t],past[0]); }
    }
    require(actual.scan[slots.size()]==j && actual.slots[slots.size()]==t);
    require(actual.ciRows[slots.size()]==ri && actual.cfRows[slots.size()]==rf);
    rowsI.push_back(ri); rowsF.push_back(rf); slots.push_back(t); effective.push_back(diff);
    neff+=diff; ndir+=t<2;
  }
  const auto lex=[](const int64_t *i,const int64_t *f) {
    int b=0; for(int e=1;e<3;++e) { if(i[e]<i[b] || (i[e]==i[b] && f[e]<f[b])) { b=e; } } return b;
  };
  int winner=lex(ci,cf),raw=int(std::min_element(ci,ci+3)-ci);
  const int ties=int(std::count(ci,ci+3,ci[raw]));
  if(m==9 || m==12) { winner=lex(wi,wf); }
  else if(m==10) { winner=lex(ci,wf); }
  else if(m==5 && ndir && std::count(direct,direct+3,*std::min_element(direct,direct+3))==1)
    winner=int(std::min_element(direct,direct+3)-direct);
  else if(ties==1 && m>=1 && m<=6 && m!=5)
  {
    bool pool[4]{}; pool[raw]=true;
    for(int e=0;e<count;++e)
    {
      const auto gap=ci[e]-ci[raw];
      if((m==1 || ((m==2 || m==6) && e==2)) && gap>0 && gap<=(1<<SCALE_BITS)) { pool[e]=true; }
      if(m==3 && e==3 && gap>=0 && gap<=(1<<SCALE_BITS)) { pool[e]=true; }
    }
    if((m==4 || m==6) && neff>=2)
      for(size_t j=0;j<rowsI.size();++j) if(effective[j])
      {
        int64_t best=INT64_MAX; for(int e=0;e<3;++e) { best=std::min(best,ci[e]-rowsI[j][e]); }
        for(int e=0;e<3;++e) { pool[e] |= ci[e]-rowsI[j][e]==best; }
      }
    for(int e=0;e<count;++e) { if(pool[e] && cf[e]<cf[winner]) { winner=e; } }
  }
  require(actual.validation==int(rowsI.size()) && actual.effective==neff && actual.ciTies==ties);
  require(actual.expert==winner && actual.action()==actions[winner]);
  require(ctx.r12ActionTS(m,s,q.data())==actual.action());
  const auto base=ctx.r10PredictionTS(3,s,q.data()).action();
  require(ctx.r12PredictionTS(0,s,q.data()).action()==base);
  if((ties>1 && (m==1 || m==2 || m==3 || m==4 || m==6)) || (m==10 && ties==1)) { require(actual.action()==base); }
  ++r12References; r12Changed+=actual.action()!=base;
  r12DistinctD+=m==3 && actions[0]==actions[1] && actions[0]==actions[2] && actions[0]!=actions[3];
}
