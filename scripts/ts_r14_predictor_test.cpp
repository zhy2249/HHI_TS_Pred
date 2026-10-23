// Standalone pure-function verification; no codec state, pixels, or video I/O.
#include "CommonLib/TsR14Prediction.h"
#include <array>
#include <iostream>
#include <random>
#include <stdexcept>
#include <tuple>
#include <vector>

namespace T=TsFixedPrediction;
static const int modes[]={1,4,7,10,13,16,19,20,21,22,23,24,25,26,27};
static void require(bool condition,const char *message)
{ if(!condition) { throw std::runtime_error(message); } }

// Independent limited-prefix Rice length: no production cost/loss calls.
static int referenceCost(int magnitude,unsigned rice,int range)
{
  if(magnitude<2) { return magnitude; }
  int total=2;
  for(int threshold: {2,4,6,8}) { total+=magnitude>=threshold; }
  if(magnitude<10) { return total; }
  const uint64_t value=(uint64_t(magnitude)-10)/2;
  if(value<(uint64_t(5)<<rice)) { return total+int(value>>rice)+1+int(rice); }
  const int cap=27-range;
  const uint64_t code=(value>>rice)-5;
  if(code>=(uint64_t(1)<<cap)-1) { return total+5+cap+range; }
  int prefix=0;
  while(code+2>(uint64_t(1)<<(prefix+1))) { ++prefix; }
  return total+5+2*prefix+int(rice)+1;
}
static int64_t referenceLoss(int m,int p,unsigned rice,int range)
{
  const auto down=[](int c)->int64_t { return c<=22?int64_t(168)*c-4LL*(c-1)*(c-1):1932; };
  if(p<=1) { return int64_t(168)*referenceCost(m,rice,range); }
  if(p==m) { return 168; }
  const int c=referenceCost(m+(p>m),rice,range);
  if(p==m-1) { return down(c); }
  if(int64_t(p)==int64_t(m)+1) { return c<=11?down(c):84LL*c+525; }
  return int64_t(168)*c;
}
static int64_t referenceScore(const int (&h)[5],int k,int r,int p,unsigned rice,int range)
{
  int64_t value=0;
  for(int j=0;j<5;++j) { if(h[j]) { value+=(j<2?k:r)*referenceLoss(h[j],p,rice,range); } }
  return value;
}
static int referenceWinner(const int (&h)[5],int k,int r,unsigned rice,int range)
{
  int n=0; for(int v:h) { n+=v>0; }
  int current=std::max(h[0],h[1]);
  if(n<3) { return current; }
  current=current<=1?0:current;
  std::vector<int> pool{0};
  for(int v:h) { if(v>1) { pool.push_back(v); } }
  std::sort(pool.begin(),pool.end()); pool.erase(std::unique(pool.begin(),pool.end()),pool.end());
  int best=current;
  int64_t bestCost=referenceScore(h,k,r,current,rice,range);
  for(int p:pool)
  {
    const int64_t cost=referenceScore(h,k,r,p,rice,range);
    if(cost<bestCost) { bestCost=cost; best=p; }
  }
  return best;
}
static int referenceFeedback(int a,int p,unsigned rice,int range)
{
  if(!a) { return 0; }
  const int mapped=p<=1?a:p==a?1:a+(p>a);
  return referenceCost(mapped,rice,range);
}
static uint64_t decisions=0,updates=0;
static void check(const T::R14Config &c,int state,const int (&h)[5],unsigned rice,int range,int a)
{
  const auto d=T::r14Prepare(c,state,h,rice,range);
  const int r=c.dynamic?(c.pair?state/2:state):c.fixedR;
  int n=0,near=0,far=0;
  for(int j=0;j<5;++j) { n+=h[j]>0; if(j<2) { near+=h[j]>0; } else { far+=h[j]>0; } }
  require(d.n==n && d.nearCount==near && d.farCount==far,"support counts");
  require(d.r==r && d.k==c.k && d.current==std::max(h[0],h[1]),"decision metadata");
  require(d.scored==(n>=3),"dense flag");
  require(d.predictor==referenceWinner(h,c.k,r,rice,range),"predictor mismatch");
  for(int t=0;t<5;++t)
  {
    const int expected=t<=c.k && (c.dynamic || t==r)?referenceWinner(h,c.k,t,rice,range):-1;
    require(d.winners[t]==expected,"grid winner mismatch");
  }
  // Ratio 1 = R13-1; ratio 1/2 = R13-2, including sparse Current and ties.
  if(c.dynamic)
  {
    require(d.winners[c.k]==T::r13Predict(1,h,rice,range),"uniform endpoint differs from R13-1");
    require(d.winners[c.k/2]==T::r13Predict(2,h,rice,range),"half endpoint differs from R13-2");
  }
  auto after=T::r14Commit(c,state,d,a,rice,range);
  const bool eligible=c.dynamic && a>0 && n>=3 && near>0 && far>0;
  require(after.eligible==eligible,"feedback eligibility");
  int target=r;
  if(eligible)
    for(int t=0;t<=c.k;++t)
    {
      const auto key=std::make_tuple(referenceFeedback(a,d.winners[t],rice,range),std::abs(t-r),-t);
      const auto best=std::make_tuple(referenceFeedback(a,d.winners[target],rice,range),std::abs(target-r),-target);
      if(key<best) { target=t; }
    }
  const int direction=(target>r)-(target<r);
  const int expectedState=std::max(0,std::min(c.pair?2*c.k+1:c.k,state+direction));
  require(after.target==target && after.direction==direction,"feedback target/tie mismatch");
  require(after.state==expectedState,"microstate update mismatch");
  require(after.beforeR==r && after.afterR==T::r14Output(c,expectedState),"output transition mismatch");
  for(int p:{0,1,2,a,std::max(0,a-1),a<INT_MAX?a+1:a})
    require(T::r14FeedbackCost(a,p,rice,range)==referenceFeedback(a,p,rice,range),"feedback cost mismatch");
  ++decisions; ++updates;
}
static void exhaustive()
{
  for(int code=0;code<3125;++code)
  {
    int v=code,h[5]; for(int &x:h) { x=v%5; v/=5; }
    for(unsigned rice:{0u,1u,4u,8u})
      for(int mode:modes)
      {
        const auto c=T::r14Config(mode);
        check(c,c.initialState,h,rice,15,(code+mode)%7);
      }
  }
}
static void randomCases()
{
  std::mt19937 rng(20261023);
  for(int i=0;i<18000;++i)
  {
    const auto c=T::r14Config(modes[i%15]);
    const int range=i%2?15:20;
    const int limit=1<<range;
    int h[5];
    for(int &v:h) { v=int(rng()%(unsigned(limit)+1u)); if(rng()%5==0) { v=0; } }
    const int state=c.dynamic?int(rng()%unsigned(c.pair?2*c.k+2:c.k+1)):c.initialState;
    check(c,state,h,unsigned(rng()%9),range,int(rng()%(unsigned(limit)+1u)));
  }
  for(int range:{15,20})
    for(unsigned rice=0;rice<=8;++rice)
      for(int mode:modes)
      {
        const int h[5]{(1<<range)-2,1<<range,(1<<range)-1,0,1};
        const auto c=T::r14Config(mode);
        check(c,c.initialState,h,rice,range,1<<range);
      }
}
static void stateCases()
{
  for(int mode:modes)
  {
    const auto c=T::r14Config(mode);
    if(!c.dynamic) { continue; }
    const int cap=c.pair?2*c.k+1:c.k;
    for(int s=0;s<=cap;++s)
      for(int target=0;target<=c.k;++target)
      {
        T::R14Decision d; d.k=c.k; d.r=T::r14Output(c,s);
        d.n=3; d.nearCount=2; d.farCount=1; d.scored=true;
        for(int t=0;t<=c.k;++t) { d.winners[t]=t==target?7:0; }
        const auto u=T::r14Commit(c,s,d,7,1,15);
        const int direction=(target>d.r)-(target<d.r);
        require(u.target==target && u.state==std::max(0,std::min(cap,s+direction)),"all state/target pairs");
        const auto neutral=T::r14Commit(c,s,d,0,1,15);
        require(!neutral.eligible && neutral.state==s,"zero must preserve phase");
        for(int t=0;t<=c.k;++t) { d.winners[t]=7; }
        const auto identical=T::r14Commit(c,s,d,7,1,15);
        require(identical.sameWinners && identical.target==d.r && identical.state==s,"equal actions preserve phase");
        for(int topology=0;topology<3;++topology)
        {
          auto ineligible=d;
          if(topology==0) { ineligible.n=2; }
          if(topology==1) { ineligible.nearCount=0; }
          if(topology==2) { ineligible.farCount=0; }
          require(T::r14Commit(c,s,ineligible,7,1,15).state==s,"ineligible topology preserves phase");
        }
        updates+=6;
      }
  }
  // Symmetric target distance selects larger r; current ties always win.
  auto c=T::r14Config(10); T::R14Decision d;
  d.k=4; d.r=2; d.n=3; d.nearCount=2; d.farCount=1; d.scored=true;
  for(int t=0;t<=4;++t) { d.winners[t]=(t==1 || t==3)?7:0; }
  require(T::r14Commit(c,2,d,7,1,15).target==3,"equidistant target tie");
  d.winners[2]=7;
  require(T::r14Commit(c,2,d,7,1,15).state==2,"current target tie");
  // Two outward evidences cross PAIR2 at endpoint; neutral preserves half phase.
  c=T::r14Config(22); d.k=2; d.r=2; d.winners[0]=7; d.winners[1]=d.winners[2]=0;
  auto first=T::r14Commit(c,5,d,7,1,15); require(first.state==4 && first.afterR==2,"PAIR2 endpoint first");
  auto neutral=T::r14Commit(c,4,d,0,1,15); require(neutral.state==4,"PAIR2 neutral phase");
  auto second=T::r14Commit(c,4,d,7,1,15); require(second.state==3 && second.afterR==1,"PAIR2 endpoint second");
}
static void regressions()
{
  const auto c=T::r14Config(19);
  const int h[5]{25,26,1,0,0};
  require(referenceScore(h,2,0,25,1,15)==3400 && referenceScore(h,2,0,26,1,15)==3402,"25/26 exact scores");
  require(T::r14Prepare(c,0,h,1,15).predictor==25,"R14-19 is not Current");
  const int far[5]{4094,4096,4095,0,0};
  require(T::r14Prepare(c,0,far,1,15).predictor==4095,"far sample remains candidate at weight zero");
  const int tie[5]{2,3,1,0,0};
  require(T::r14Prepare(c,0,tie,1,15).predictor==3,"Current-first tie");
  const int support[5]{0,0,1,1,1};
  const auto d=T::r14Prepare(c,0,support,1,15);
  require(d.n==3 && d.scored && d.predictor==0,"n counts physical far support");
  bool rejected=false; try { (void)T::r14Config(2); } catch(const std::exception &) { rejected=true; }
  require(rejected,"retired config must fail");
}
static void query()
{
  int mode,state,range,a,h[5]; unsigned rice;
  while(std::cin>>mode>>state>>rice>>range>>a>>h[0]>>h[1]>>h[2]>>h[3]>>h[4])
  {
    const auto c=T::r14Config(mode); const auto d=T::r14Prepare(c,state,h,rice,range);
    const auto u=T::r14Commit(c,state,d,a,rice,range);
    std::cout<<"{\"n\":"<<d.n<<",\"r\":"<<d.r<<",\"predictor\":"<<d.predictor<<",\"winners\":[";
    for(int t=0;t<5;++t) { std::cout<<(t?",":"")<<d.winners[t]; }
    std::cout<<"],\"target\":"<<u.target<<",\"state\":"<<u.state<<",\"eligible\":"<<(u.eligible?"true":"false")<<"}\n";
  }
}
int main(int argc,char **argv)
{
  try
  {
    const std::string action=argc>1?argv[1]:"all";
    if(action=="query") { query(); return 0; }
    if(action=="all" || action=="exhaustive") { exhaustive(); }
    if(action=="all" || action=="random") { randomCases(); }
    if(action=="all" || action=="state") { stateCases(); regressions(); }
    std::cout<<"{\"pass\":true,\"decisions\":"<<decisions<<",\"updates\":"<<updates<<"}\n";
  }
  catch(const std::exception &e) { std::cerr<<e.what()<<'\n'; return 1; }
}
