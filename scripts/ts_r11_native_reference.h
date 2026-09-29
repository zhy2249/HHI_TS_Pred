// Independent reference: old public expert APIs and an exhaustive native prefix
// scan used ONLY in tests. Production uses 24 geometric offsets, never this loop.
static uint64_t r11CrossTargets=0,r11NoEvidence=0,r11DistinctD=0;
static void r11Reference(const CoeffCodingContext &ctx,int s,const std::vector<TCoeff> &q,int rice,int range)
{
  using namespace TsFixedPrediction;
  const int m=r11PublicMode(mode()),count=r11ExpertCount(m),w=ctx.width(),lg=ctx.log2CGSize();
  const auto support=[&](int j) {
    const int p=ctx.blockPos(j),x=p%w,y=p/w;
    return std::array<int,5>{{x?std::abs(q[p-1]):0,y?std::abs(q[p-w]):0,
      x&&y?std::abs(q[p-w-1]):0,x>=2?std::abs(q[p-2]):0,y>=2?std::abs(q[p-2*w]):0}};
  };
  const auto experts=[&](int j) {
    const auto h=support(j);
    return R10Actions{{canonicalAction(ctx.r8PredictionTS(12,j,q.data()).predictor),
      canonicalAction(ctx.magnitudePredictorModeTS(10,j,q.data())),
      canonicalAction(ctx.magnitudePredictorModeTS(13,j,q.data())),
      m==5?canonicalAction(std::max(h[0],h[1])):canonicalAction(0)}};
  };
  const int p=ctx.blockPos(s),x=p%w,y=p/w;
  std::vector<int> base;
  const int dx[]={-1,0,-1,-2,0},dy[]={0,-1,-1,0,-2};
  for(int t=0;t<5;++t) if(x+dx[t]>=0 && y+dy[t]>=0)
    for(int j=ctx.minSubPos();j<s;++j)
      if(int(ctx.blockPos(j))==p+dx[t]+dy[t]*w && q[ctx.blockPos(j)]) { base.push_back(j); }
  auto selected=base;
  for(int phase=0;phase<r11Scope(m);++phase)
  {
    std::vector<std::tuple<int,int,int,int,int>> extra;
    for(int j=0;j<s;++j)
    {
      const int b=ctx.blockPos(j),xx=b%w,yy=b/w,dist=std::abs(x-xx)+std::abs(y-yy);
      if(!dist || dist>3 || !q[b] || (phase==0 ? (j>>lg)!=(s>>lg) : (j>>lg)>=(s>>lg))) { continue; }
      if(std::find(selected.begin(),selected.end(),j)==selected.end()) { extra.emplace_back(dist,-j,yy,xx,j); }
    }
    std::sort(extra.begin(),extra.end());
    for(const auto &e:extra) { if(selected.size()<8) { selected.push_back(std::get<4>(e)); } }
  }
  const auto actual=ctx.r11PredictionTS(m,s,q.data()); const auto actions=experts(s);
  require(actual.targets.base==int(base.size()) && actual.targets.count==int(selected.size()));
  require(std::equal(selected.begin(),selected.end(),actual.targets.scan.begin()));
  for(int e=0;e<count;++e) { require(actual.actions[e]==actions[e]); }
  int64_t ci[4]{},cf[4]{}; int effective=0;
  for(int j:selected)
  {
    const auto past=experts(j); const auto h=support(r11Query(m)?s:j);
    const int a=std::abs(q[ctx.blockPos(j)]); bool different=false;
    for(int e=0;e<count;++e)
    {
      const int v=remap(a,past[e]); different |= v!=remap(a,past[0]);
      ci[e]+=int64_t(syntaxCost(v,rice,range))<<SCALE_BITS;
      cf[e]+=ctx.tsRateTable((h[0]!=0)+(h[1]!=0)).cost(v,rice,range);
    }
    effective+=different; r11CrossTargets+=(j>>lg)<(s>>lg);
  }
  int winner=0,raw=0,distinct=1,ties=0;
  for(int e=1;e<count;++e)
  {
    if(ci[e]<ci[raw]) { raw=e; }
    bool unique=true; for(int k=0;k<e;++k) { unique &= actions[e]!=actions[k]; } distinct+=unique;
  }
  winner=raw;
  for(int e=0;e<count;++e)
  {
    require(ci[e]==actual.ci[e]); ties+=ci[e]==ci[raw];
    if(ci[e]==ci[raw] && cf[e]<cf[winner]) { winner=e; }
  }
  bool fallback=false;
  if(distinct==1 || selected.empty()) { winner=0; }
  if(distinct>1 && r11Fallback(m) && effective==0) { winner=2; fallback=true; }
  require(actual.distinct==distinct && actual.effective==effective && actual.ciTies==ties);
  require(actual.expert==winner && actual.fallback==fallback && actual.action()==actions[winner]);
  require(ctx.r11PredictionTS(0,s,q.data()).action()==ctx.r10PredictionTS(3,s,q.data()).action());
  if(m==1 && effective>0) { require(actual.action()==ctx.r10PredictionTS(3,s,q.data()).action()); }
  if(m==2 && ties==1) { require(actual.action()==ctx.r10PredictionTS(3,s,q.data()).action()); }
  const auto v0=ctx.r11TargetsTS(0,s,q.data()),v3=ctx.r11TargetsTS(1,s,q.data()),v4=ctx.r11TargetsTS(2,s,q.data());
  require(std::equal(v0.scan.begin(),v0.scan.begin()+v0.count,v3.scan.begin()));
  require(std::equal(v3.scan.begin(),v3.scan.begin()+v3.count,v4.scan.begin()));
  r11NoEvidence+=effective==0;
  r11DistinctD+=count==4 && actions[0]==actions[1] && actions[0]==actions[2] && actions[0]!=actions[3];
}
