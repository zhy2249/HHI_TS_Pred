// R15 / TS-MG-STATIC-FAST-v1. Shared pure causal selectors and reversible map.
#pragma once
#include "TsFixedPrediction.h"
#include <array>
#include <cstdint>
#include <limits>
#include <vector>

namespace TsMultiMapping
{
constexpr const char *revision="TS-MG-STATIC-FAST-v1";
constexpr const char *protocol="TS-MG-ACTION-v1";
struct Action
{
  int count=0;
  std::array<int,6> targets{};
  bool operator==(const Action &b) const { return count==b.count && targets==b.targets; }
  bool operator!=(const Action &b) const { return !(*this==b); }
  bool operator<(const Action &b) const { return count!=b.count?count<b.count:targets<b.targets; }
};
inline void validate(const Action &p,int maximum)
{
  CHECK(p.count<0 || p.count>6,"Invalid multi-mapping count");
  for(int j=0;j<6;++j)
  {
    CHECK(j<p.count?(p.targets[j]<1 || p.targets[j]>maximum):p.targets[j]!=0,"Invalid multi-mapping target/padding");
    for(int i=0;i<j && j<p.count;++i) { CHECK(p.targets[i]==p.targets[j],"Duplicate multi-mapping target"); }
  }
}
inline int map(int a,const Action &p)
{
  if(!a) { return 0; }
  int less=0;
  for(int j=0;j<p.count;++j) { if(a==p.targets[j]) { return j+1; } less+=p.targets[j]<a; }
  return a+p.count-less;
}
// ADL adapter for the existing, unchanged replayRateCG template. It receives
// the entire action, never a fictitious single predictor fitted to current a.
inline int remap(int a,const Action &p) { return map(a,p); }
inline int unmap(int y,const Action &p)
{
  if(!y) { return 0; }
  if(y<=p.count) { return p.targets[y-1]; }
  auto sorted=p.targets;std::sort(sorted.begin(),sorted.begin()+p.count);
  int a=y-p.count;
  for(int j=0;j<p.count;++j) { if(a>=sorted[j]) { ++a; } }
  return a;
}
inline Action append(Action p,int q)
{ CHECK(p.count>=6 || q<=0,"Invalid prefix extension");for(int i=0;i<p.count;++i) { CHECK(p.targets[i]==q,"Repeated prefix target"); } p.targets[p.count++]=q;return p; }
inline Action single(int p) { return p>0?append({},p):Action{}; }
inline Action canonical(Action p)
{
  while(p.count)
  {
    Action shorter=p;const int q=shorter.targets[--shorter.count];shorter.targets[shorter.count]=0;
    if(map(q,shorter)!=p.count) { break; } p=shorter;
  }
  return p;
}
enum class Engine { NAIVE, PREFIX, FAST };
struct Method { int number,mg; const char *name; char search; int depth; bool spatial; };
// Existing controls have public number 0. New public subexperiments are 1..18.
inline const std::array<Method,21> &methods()
{
  static const std::array<Method,21> m={{{0,0,"CURRENT",'C',1,false},{0,2,"STATIC_EQ",'B',1,false},
    {0,3,"STATIC_SP",'B',1,true},{1,1,"IDENTITY",'I',0,false},
    {2,4,"G_EQ_K2",'G',2,false},{3,5,"G_EQ_K3",'G',3,false},
    {4,6,"G_EQ_K4",'G',4,false},{5,7,"G_EQ_K6",'G',6,false},
    {6,8,"N_EQ_K2",'N',2,false},{7,9,"N_EQ_K3",'N',3,false},
    {8,10,"N_EQ_K4",'N',4,false},{9,11,"N_EQ_K6",'N',6,false},
    {10,12,"P_EQ_K2",'P',2,false},{11,13,"P_EQ_K3",'P',3,false},{12,14,"P_EQ_K6",'P',6,false},
    {13,15,"D_EQ_K2",'D',2,false},{14,16,"D_EQ_K3",'D',3,false},
    {15,17,"X_EQ_K2",'X',2,false},{16,18,"X_EQ_K3",'X',3,false},
    {17,19,"G_SP_K3",'G',3,true},{18,20,"N_SP_K3",'N',3,true}}};return m;
}
inline const Method &publicMethod(int number)
{
  CHECK(number<1 || number>18,"Invalid R15 public mode");
  const auto &method=methods()[number+2];
  CHECK(method.number!=number,"R15 registry numbering mismatch");
  return method;
}
struct Operations
{
  uint64_t candidates=0,queries=0,hits=0,adds=0,multiplies=0,compares=0,rankUpdates=0,pruned=0,loops=0;
  Operations &operator+=(const Operations &b)
  { candidates+=b.candidates;queries+=b.queries;hits+=b.hits;adds+=b.adds;multiplies+=b.multiplies;compares+=b.compares;rankUpdates+=b.rankUpdates;pruned+=b.pruned;loops+=b.loops;return *this; }
};
struct Trace
{
  Action prefix; int candidate=0; int64_t gain=0;
  bool operator==(const Trace &b) const { return prefix==b.prefix && candidate==b.candidate && gain==b.gain; }
};
struct Result
{
  Action action,returned,searched,root;
  int64_t score=0;
  int n=0,candidates=0,positive=0,neutral=0,negative=0,zeroSteps=0,rootChanged=0;
  bool fallback=false;
  Operations ops;
  std::vector<Trace> trace;
};
struct Input
{
  std::array<int,6> value{},weight{},priority{},priorityIndex{},priorityRank{};
  int size=0,n=0,current=0,maximum=0;
  Input(const std::array<int,5> &h,bool spatial,int range)
  {
    CHECK(range<8 || range>20,"Unsupported mapping dynamic range");maximum=1<<range;current=std::max(h[0],h[1]);
    std::array<int,6> v{{1,0,0,0,0,0}};int used=1;
    for(int j=0;j<5;++j) { CHECK(h[j]<0 || h[j]>maximum,"Invalid causal magnitude");n+=h[j]!=0;if(h[j]) { v[used++]=h[j]; } }
    std::sort(v.begin(),v.begin()+used);size=int(std::unique(v.begin(),v.begin()+used)-v.begin());
    std::copy_n(v.begin(),size,value.begin());
    for(int i=0;i<size;++i) for(int j=0;j<5;++j) if(value[i]==h[j]) { weight[i]+=spatial && j<2?2:1; }
    int k=0;if(current>1) { priority[k++]=current; }priority[k++]=1;
    for(int i=0;i<size;++i) if(value[i]!=1 && value[i]!=current) { priority[k++]=value[i]; }
    CHECK(k!=size,"Candidate priority mismatch");
    for(int i=0;i<size;++i) { priorityIndex[i]=index(priority[i]);priorityRank[priorityIndex[i]]=i; }
  }
  int index(int v) const { return int(std::lower_bound(value.begin(),value.begin()+size,v)-value.begin()); }
  int order(int v) const { return int(std::find(priority.begin(),priority.begin()+size,v)-priority.begin()); }
};
struct Cost
{
  unsigned rice;int range,maximum;Engine engine;Operations &ops;
  // Direct-mapped, bounded cache: collisions only cause a new exact query.
  // No heap, linear cache probing or table indexed by the full amplitude range.
  std::array<int,64> keys{},values{};
  int operator()(int a)
  {
    CHECK(a<0 || a>maximum,"Cost outside legal magnitude domain");
    const unsigned slot=(uint32_t(a)*2654435761u)>>26;
    if(engine!=Engine::NAIVE && keys[slot]==a+1) { ++ops.hits;return values[slot]; }
    ++ops.queries;const int c=TsFixedPrediction::syntaxCost(a,rice,range);
    if(engine!=Engine::NAIVE) { keys[slot]=a+1;values[slot]=c; }return c;
  }
};
inline int64_t score(const Input &in,const Action &p,Cost &cost)
{
  int64_t total=0;
  for(int i=0;i<in.size;++i) if(in.weight[i]) { total+=int64_t(in.weight[i])*cost(map(in.value[i],p));++cost.ops.multiplies;++cost.ops.adds;++cost.ops.loops; }
  return total;
}
struct Ranks
{
  std::array<int,6> rank{};std::array<bool,6> used{};
  Ranks(const Input &in,const Action &p)
  { for(int i=0;i<in.size;++i) { rank[i]=map(in.value[i],p);used[i]=std::find(p.targets.begin(),p.targets.begin()+p.count,in.value[i])!=p.targets.begin()+p.count; } }
  void extend(const Input &in,int q,Operations &ops)
  { const int i=in.index(q);for(int j=0;j<i;++j) if(!used[j]) { ++rank[j];++ops.rankUpdates; }used[i]=true; }
};
inline std::array<int64_t,6> gains(const Input &in,const Action &p,int64_t base,Ranks &r,Cost &c,Result &out,bool trace)
{
  std::array<int64_t,6> g{};int64_t penalty=0;const int target=c(p.count+1);int remaining=in.size-p.count;
  for(int i=0;i<in.size;++i) if(!r.used[i])
  {
    ++out.ops.candidates;++out.ops.loops;
    if(c.engine==Engine::NAIVE) { g[i]=base-score(in,append(p,in.value[i]),c); }
    else
    {
      g[i]=int64_t(in.weight[i])*(c(r.rank[i])-target)-penalty;++out.ops.multiplies;out.ops.adds+=2;
      // In particular do not request C(Amax+1) at the last supported value.
      if(remaining>1 && in.weight[i]) { penalty+=int64_t(in.weight[i])*(c(r.rank[i]+1)-c(r.rank[i]));++out.ops.multiplies;out.ops.adds+=2; }
    }
    --remaining;
    out.positive+=g[i]>0;out.neutral+=g[i]==0;out.negative+=g[i]<0;
  }
  if(trace) for(int j=0;j<in.size;++j) { int i=in.priorityIndex[j];if(!r.used[i]) { out.trace.push_back({p,in.value[i],g[i]}); } }
  return g;
}
inline int bestGain(const Input &in,const Action &p,const Ranks &r,const std::array<int64_t,6> &gain,Cost &c)
{
  std::array<bool,6> keep{};for(int i=0;i<in.size;++i) { keep[i]=!r.used[i]; }
  if(c.engine==Engine::FAST)
  {
    // Per-round plateau representatives only. Never remove observations or
    // prefixes; even a zero-gain target may be a necessary neutral placeholder.
    const int target=c(p.count+1);
    int representative=-1,previousCost=-1;
    for(int i=0;i<in.size;++i) if(keep[i])
    {
      const int nextCost=c(r.rank[i]);
      if(nextCost!=previousCost) { representative=i;previousCost=nextCost;continue; }
      const int j=representative;const bool counts=nextCost>target;
      const bool better=(counts && in.weight[i]!=in.weight[j])?in.weight[i]>in.weight[j]:in.priorityRank[i]<in.priorityRank[j];
      keep[better?j:i]=false;if(better) { representative=i; }++c.ops.pruned;
    }
  }
  int best=-1;
  for(int k=0;k<in.size;++k) { const int i=in.priorityIndex[k];if(keep[i]) { ++c.ops.compares;if(best<0 || gain[i]>gain[best]) { best=i; } } }
  return best;
}
inline Action root(const Input &in,Cost &c,Result &out,bool trace)
{
  Action p;Ranks r(in,p);const auto g=gains(in,p,score(in,p,c),r,c,out,trace);
  const int i=bestGain(in,p,r,g,c);return append({},in.value[i]);
}
inline Action greedy(const Input &in,Action p,int depth,bool neutral,Cost &c,Result &out,bool trace)
{
  auto best=p;int64_t now=score(in,p,c),low=now;Ranks ranks(in,p);
  while(p.count<std::min(depth,in.size))
  {
    auto g=gains(in,p,now,ranks,c,out,trace);const int b=bestGain(in,p,ranks,g,c);
    if(g[b]<0 || (!neutral && g[b]==0)) { break; }
    out.zeroSteps+=g[b]==0;p=append(p,in.value[b]);ranks.extend(in,in.value[b],c.ops);now-=g[b];
    if(now<low) { low=now;best=p; }
  }
  out.searched=p;return best;
}
inline bool tieLess(const Input &in,const Action &a,const Action &b,const Action &base)
{
  const auto x=canonical(a),y=canonical(b),r=canonical(base);
  if((x==r)!=(y==r)) { return x==r; }
  if(x.count!=y.count) { return x.count<y.count; }
  for(int j=0;j<x.count;++j) if(x.targets[j]!=y.targets[j]) { return in.order(x.targets[j])<in.order(y.targets[j]); }
  return false;
}
inline void exhaustive(const Input &in,const Action &p,int depth,const Action &base,Action &best,int64_t &low,Cost &c,Result &out,bool trace)
{
  const auto s=score(in,p,c);++out.ops.compares;
  if(s<low || (s==low && tieLess(in,p,best,base))) { low=s;best=p; }
  if(p.count>=std::min(depth,in.size)) { return; }
  for(int j=0;j<in.size;++j)
  {
    const int q=in.priority[j];if(std::find(p.targets.begin(),p.targets.begin()+p.count,q)!=p.targets.begin()+p.count) { continue; }
    auto next=append(p,q);const auto gain=s-score(in,next,c);++out.ops.candidates;
    out.positive+=gain>0;out.neutral+=gain==0;out.negative+=gain<0;
    if(trace) { out.trace.push_back({p,q,gain}); }
    exhaustive(in,next,depth,base,best,low,c,out,trace);
  }
}
inline Result select(const std::array<int,5> &h,const Method &method,unsigned rice,int range,Engine engine=Engine::PREFIX,bool trace=false)
{
  CHECK(rice>8,"Unsupported multi-mapping Rice parameter");
  Input in(h,method.spatial,range);Result out;out.n=in.n;out.candidates=in.size;
  Cost c{rice,range,in.maximum,engine,out.ops};Action p;
  if(method.search=='I') { p={}; }
  else if(method.search=='C' || in.n<3) { p=single(in.current);out.fallback=in.n<3 && method.search!='C'; }
  else
  {
    auto b=root(in,c,out,trace);out.root=b;
    switch(method.search)
    {
    case 'B':p=b;break;
    case 'G':case 'N':p=greedy(in,b,method.depth,method.search=='N',c,out,trace);break;
    case 'P':p=greedy(in,single(1),method.depth,false,c,out,trace);break;
    case 'D':
      p=greedy(in,b,method.depth,false,c,out,trace);
      if(b!=single(1)) { auto firstTrace=out.searched;auto q=greedy(in,single(1),method.depth,false,c,out,trace);if(score(in,q,c)<score(in,p,c)) { p=q; }else { out.searched=firstTrace; } }break;
    case 'X': { int64_t low=std::numeric_limits<int64_t>::max();exhaustive(in,{},method.depth,b,p,low,c,out,trace);out.searched=p;break; }
    default:CHECK(true,"Unknown multi-mapping search");
    }
    out.rootChanged=p.count && p.targets[0]!=b.targets[0];
  }
  out.returned=p;out.action=canonical(p);out.score=score(in,p,c);validate(out.action,in.maximum);return out;
}
} // namespace TsMultiMapping
