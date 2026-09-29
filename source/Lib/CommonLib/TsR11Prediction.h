// R11: bounded causal validation on native scan geometry. No persistent learning state.
#pragma once
#include "TsR10Prediction.h"
#include <tuple>

namespace TsFixedPrediction
{
constexpr int R11_MAX_TARGETS=8;
using R11Loss=std::array<std::array<int64_t,4>,R11_MAX_TARGETS>;
inline int r11Scope(int m) { return m==4 || m==8 ? 2 : m==3 ? 1 : 0; }
inline bool r11Fallback(int m) { return m==1 || m==7 || m==8; }
inline bool r11Query(int m) { return m==2 || m==7; }
inline int r11ExpertCount(int m) { return m==5 || m==6 ? 4 : 3; }
struct R11Targets
{
  std::array<int,R11_MAX_TARGETS> scan{};
  int count=0,base=0,same=0;
};
// scope=0 V0, 1 V3, 2 V4. Check existence and native scan BEFORE amplitude access.
template<class BlockPos,class ScanIndex,class Magnitude>
R11Targets r11Targets(int scope,int i,int w,int h,int log2CG,const BlockPos &blockPos,
                      const ScanIndex &scanIndex,const Magnitude &magnitude)
{
  R11Targets out;
  const int pos=blockPos(i),x=pos%w,y=pos/w,cg=i>>log2CG;
  const auto index=[&](int xx,int yy) { return xx<0 || yy<0 || xx>=w || yy>=h ? -1 : scanIndex(xx+yy*w); };
  const int dx[]={-1,0,-1,-2,0},dy[]={0,-1,-1,0,-2};
  for(int k=0;k<5;++k)
  {
    const int j=index(x+dx[k],y+dy[k]);
    if(j>=0 && j<i && (j>>log2CG)==cg && magnitude(j)>0) { out.scan[out.count++]=j; }
  }
  out.base=out.same=out.count;
  if(!scope) { return out; }
  // 24 geometric offsets, not the full CG/TU prefix; no amplitude-based ordering.
  using Entry=std::tuple<int,int,int,int,int>; // distance, -scan, y, x, scan
  for(int phase=0;phase<scope;++phase)
  {
    std::array<Entry,24> extra{}; int n=0;
    if(out.count<R11_MAX_TARGETS)
      for(int yy=y-3;yy<=y+3;++yy) for(int xx=x-3;xx<=x+3;++xx)
      {
        const int radius=std::abs(xx-x)+std::abs(yy-y);
        if(!radius || radius>3) { continue; }
        const int j=index(xx,yy);
        if(j<0 || j>=i || (phase==0 ? (j>>log2CG)!=cg : (j>>log2CG)>=cg)) { continue; }
        if(std::find(out.scan.begin(),out.scan.begin()+out.count,j)!=out.scan.begin()+out.count) { continue; }
        if(magnitude(j)>0) { extra[n++]=Entry{radius,-j,yy,xx,j}; }
      }
    std::sort(extra.begin(),extra.begin()+n);
    for(int k=0;k<n && out.count<R11_MAX_TARGETS;++k) { out.scan[out.count++]=std::get<4>(extra[k]); }
    if(phase==0) { out.same=out.count; }
  }
  return out;
}
template<class Fractional,class Integer>
R10Actions r11Experts(int mode,const int (&h)[5],int limit,const Fractional &cf,const Integer &ci)
{
  auto actions=r10Experts(3,h,limit,cf,ci); // A=R8-12, B=integer raw, C=integer R3.
  if(mode==5) { actions[3]=canonicalAction(std::max(h[0],h[1])); }
  if(mode==6) { actions[3]=canonicalAction(0); }
  return actions;
}
struct R11Decision
{
  R10Actions actions{};
  R11Targets targets;
  int count=3,expert=0,rawExpert=0,distinct=1,effective=0,ciTies=0;
  int n=0,n1=0,direct=0;
  bool fallback=false;
  std::array<int64_t,4> ci{},cf{};
  MagnitudeAction action() const { return actions[expert]; }
};
// Identical current actions shortcut only after counting ALL active experts.
// Equal CI is not structural no-evidence: effective comes from mapped levels.
inline void r11Select(int mode,R11Decision &d,const R11Loss &ci,const R11Loss &cf)
{
  for(int j=0;j<d.targets.count;++j)
    for(int e=0;e<d.count;++e) { d.ci[e]+=ci[j][e]; }
  for(int e=1;e<d.count;++e) { if(d.ci[e]<d.ci[d.rawExpert]) { d.rawExpert=e; } }
  for(int e=0;e<d.count;++e)
    if(d.ci[e]==d.ci[d.rawExpert])
    {
      ++d.ciTies;
      for(int j=0;j<d.targets.count;++j) { d.cf[e]+=cf[j][e]; }
    }
  if(d.distinct==1) { return; }
  if(r11Fallback(mode) && !d.effective) { d.expert=2; d.fallback=true; return; }
  if(!d.targets.count) { return; }
  d.expert=d.rawExpert;
  for(int e=0;e<d.count;++e)
    if(d.ci[e]==d.ci[d.rawExpert] && d.cf[e]<d.cf[d.expert]) { d.expert=e; }
}
}
