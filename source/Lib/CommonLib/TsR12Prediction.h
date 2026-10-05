// R12-POS-01: bounded V0 expert selection, no target value or live CABAC access.
#pragma once
#include "TsR10Prediction.h"

namespace TsFixedPrediction
{
constexpr int R12_WEIGHTS[5]={2,2,1,1,1}; // L,U,D,LL,UU, never compressed nz indices.
constexpr int64_t R12_Q=int64_t(1)<<SCALE_BITS;
using R12Loss=std::array<std::array<int64_t,4>,5>;
inline bool r12WeightedC(int m) { return m==7 || m==8 || m==11 || m==12; }
struct R12Inner
{
  int current=0,oldRaw=0,oldC=0,raw=0,n=0,maxSlot=-1,softSlot=-1;
  int64_t gain=0,oldGain=0,full=0,soft=0;
  std::array<int64_t,5> delta{};
  int predictor(int mode) const
  { return gain>(mode==8?full:mode==11?soft:0) ? raw : current; }
};
// Shared cost cache for the integer B/C candidate matrix. At most 1+2*5
// distinct remapped levels (1,a_j,a_j+1), independent of the magnitude range.
template<class Cost>
R12Inner r12Integer(const int (&h)[5],const Cost &cost,const int *weights=R12_WEIGHTS)
{
  int levels[12]{},used=0,nz[5]{}; int64_t values[12]{};
  const auto memo=[&](int level) {
    for(int k=0;k<used;++k) { if(levels[k]==level) { return values[k]; } }
    CHECK(used>=12,"R12 cost matrix overflow");
    levels[used]=level; values[used]=cost(level); return values[used++];
  };
  R12Inner out; out.current=canonicalAction(std::max(h[0],h[1])).predictor;
  for(int a:h) { if(a) { nz[out.n++]=a; } }
  const auto original=rateDecision(out.current,nz,out.n,memo);
  out.oldRaw=canonicalAction(original.winner).predictor;
  out.oldC=canonicalAction(original.predictor).predictor; out.oldGain=original.gain;
  out.raw=out.current;
  if(out.n<3) { return out; }
  int64_t best=0;
  for(int k=0;k<original.count;++k)
  {
    const int p=original.candidates[k]; int64_t score=0;
    for(int j=0;j<5;++j) { if(h[j]) { score+=weights[j]*memo(remap(h[j],p)); } }
    if(!k || score<best) { best=score; out.raw=canonicalAction(p).predictor; }
  }
  for(int j=0;j<5;++j) if(h[j])
  {
    const int64_t d=memo(remap(h[j],out.current))-memo(remap(h[j],out.raw));
    out.delta[j]=d; out.gain+=weights[j]*d;
    if(weights[j]*d>out.full) { out.full=weights[j]*d; out.maxSlot=j; }
    if(d>out.soft) { out.soft=d; out.softSlot=j; }
  }
  return out;
}
template<class Fractional,class Integer>
R10Actions r12Experts(int mode,const int (&h)[5],int limit,const Fractional &cf,const Integer &ci,
                     R12Inner *inner=nullptr)
{
  if(r12WeightedC(mode))
  {
    const auto d=r12Integer(h,ci); if(inner) { *inner=d; }
    return {{r9Decision(12,h,limit,cf).action,canonicalAction(d.oldRaw),
             canonicalAction(d.predictor(mode)),canonicalAction(std::max(h[0],h[1]))}};
  }
  auto actions=r10Experts(3,h,limit,cf,ci);
  if(mode==3) { actions[3]=canonicalAction(std::max(h[0],h[1])); }
  return actions;
}
struct R12Decision
{
  R10Actions actions{};
  R12Inner inner;
  R12Loss ciRows{},cfRows{};
  std::array<int,5> slots{},scan{},support{};
  std::array<bool,5> informative{};
  std::array<int64_t,4> ci{},cf{},weightedCI{},weightedCF{};
  int count=3,validation=0,effective=0,rawExpert=0,baseExpert=0,expert=0,ciTies=0;
  int n=0,n1=0,direct=0,nearMask=0,looMask=0,legalDeletes=0,directWinner=-1;
  int64_t ciGap=0;
  MagnitudeAction action() const { return actions[expert]; }
};
inline int r12Lex(const std::array<int64_t,4> &ci,const std::array<int64_t,4> &cf)
{
  int best=0;
  for(int e=1;e<3;++e) { if(ci[e]<ci[best] || (ci[e]==ci[best] && cf[e]<cf[best])) { best=e; } }
  return best;
}
// Caller supplies already eligible causal V0 rows. No action deduplication:
// strategies with the same query action can have different historical losses.
inline void r12Select(int mode,R12Decision &d)
{
  CHECK(mode<0 || mode>12,"Invalid R12 selector"); // 0 is diagnostic R10-3, not a BD mode.
  for(int j=0;j<d.validation;++j)
  {
    CHECK(d.slots[j]<0 || d.slots[j]>=5,"R12 lost spatial slot");
    d.effective+=d.informative[j];
    for(int e=0;e<d.count;++e)
    {
      d.ci[e]+=d.ciRows[j][e]; d.cf[e]+=d.cfRows[j][e];
      d.weightedCI[e]+=R12_WEIGHTS[d.slots[j]]*d.ciRows[j][e];
      d.weightedCF[e]+=R12_WEIGHTS[d.slots[j]]*d.cfRows[j][e];
    }
  }
  d.baseExpert=r12Lex(d.ci,d.cf); d.expert=d.baseExpert;
  for(int e=1;e<3;++e) { if(d.ci[e]<d.ci[d.rawExpert]) { d.rawExpert=e; } }
  const int w=d.rawExpert;
  for(int e=0;e<3;++e) { d.ciTies+=d.ci[e]==d.ci[w]; }
  if(d.ciTies==1)
  {
    d.ciGap=INT64_MAX;
    for(int e=0;e<3;++e) if(e!=w)
    {
      const auto gap=d.ci[e]-d.ci[w]; d.ciGap=std::min(d.ciGap,gap);
      if(gap>0 && gap<=R12_Q) { d.nearMask|=1<<e; }
    }
  }
  // Diagnostic nearMask is the mode-eligible near set, not unrelated ABC gaps.
  if(mode==2 || mode==6) { d.nearMask &= 1<<2; }
  if(mode==3)
  {
    const auto gap=d.ci[3]-d.ci[w];
    d.nearMask=d.ciTies==1 && gap>=0 && gap<=R12_Q ? 1<<3 : 0;
  }
  d.looMask=1<<w;
  if(d.effective>=2)
    for(int j=0;j<d.validation;++j) if(d.informative[j])
    {
      ++d.legalDeletes; int64_t best=INT64_MAX;
      for(int e=0;e<3;++e) { best=std::min(best,d.ci[e]-d.ciRows[j][e]); }
      for(int e=0;e<3;++e) { if(d.ci[e]-d.ciRows[j][e]==best) { d.looMask|=1<<e; } }
    }
  std::array<int64_t,4> direct{}; int nDirect=0;
  for(int j=0;j<d.validation;++j) if(d.slots[j]<2)
  { ++nDirect; for(int e=0;e<3;++e) { direct[e]+=d.ciRows[j][e]; } }
  const auto minimum=*std::min_element(direct.begin(),direct.begin()+3);
  if(nDirect && std::count(direct.begin(),direct.begin()+3,minimum)==1)
    d.directWinner=int(std::min_element(direct.begin(),direct.begin()+3)-direct.begin());
  if(!d.validation) { d.expert=0; return; }
  if(mode==9 || mode==12) { d.expert=r12Lex(d.weightedCI,d.weightedCF); return; }
  if(mode==10) { d.expert=r12Lex(d.ci,d.weightedCF); return; }
  if(mode==5) { if(d.directWinner>=0) { d.expert=d.directWinner; } return; }
  if(mode==0 || r12WeightedC(mode) || d.ciTies>1) { return; }
  int pool=1<<w;
  if(mode==1) { pool|=d.nearMask; }
  if(mode==2 || mode==6) { pool|=d.nearMask & (1<<2); }
  if(mode==3) { pool|=d.nearMask; }
  if(mode==4 || mode==6) { pool|=d.looMask; }
  // Strict CF improvement preserves incumbent ties; improving challengers tie A,B,C,D.
  for(int e=0;e<d.count;++e)
    if((pool & (1<<e)) && d.cf[e]<d.cf[d.expert]) { d.expert=e; }
}
}
