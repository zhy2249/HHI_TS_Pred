// R10 pure experts and local validation. No target coefficient or live CABAC access.
#pragma once
#include "TsR9Prediction.h"
#include "TsRateCost.h"
#include <array>

namespace TsFixedPrediction
{
using R10Actions=std::array<MagnitudeAction,4>;
inline int r10Pool(int mode) { return mode==1 || mode==7 ? 3 : mode==2 ? 2 : 12; }
inline int r10State(const int (&h)[5])
{
  int n=0; for(int v:h) { n+=v!=0; }
  return 3*(n<3)+(h[0]!=0)+(h[1]!=0);
}
template<class Fractional,class Integer>
R10Actions r10Experts(int mode,const int (&h)[5],int limit,const Fractional &cf,const Integer &ci)
{
  int nz[5],n=0; for(int v:h) { if(v) { nz[n++]=v; } }
  const auto raw=rateDecision(std::max(h[0],h[1]),nz,n,ci);
  return {{r9Decision(r10Pool(mode),h,limit,cf).action,canonicalAction(raw.winner),
    canonicalAction(raw.predictor),mode==6?r9Decision(7,h,limit,cf).action:MagnitudeAction{0,0}}};
}
struct R10CacheEntry
{
  std::array<int,5> support{};
  R10Actions actions{};
  int pool=-1; // 0..7 full mode; reset on each probability snapshot / CG.
};
struct R10Decision
{
  R10Actions actions{};
  int count=3,expert=0,rawExpert=0,distinct=1,validation=0,effective=0,ciTies=0;
  int n=0,n1=0,direct=0;
  bool guardRejected=false;
  int64_t ci[4]{},cf[4]{},gain=0,margin=0;
  MagnitudeAction action() const { return actions[expert]; }
};
// Losses are <=5 local validation rows, never a cumulative CG prefix.
inline void r10Select(int mode,R10Decision &d,const int64_t (&ci)[5][4],const int64_t (&cf)[5][4],const int (&weights)[5])
{
  for(int j=0;j<d.validation;++j)
    for(int e=0;e<d.count;++e) { d.ci[e]+=ci[j][e]*weights[j]; }
  for(int e=1;e<d.count;++e) { if(d.ci[e]<d.ci[d.rawExpert]) { d.rawExpert=e; } }
  for(int e=0;e<d.count;++e) { d.ciTies+=d.ci[e]==d.ci[d.rawExpert]; }
  if(d.distinct==1 || !d.validation) { return; } // Observation rows do not create a decision.
  d.expert=d.rawExpert;
  if(mode==3 || mode==7)
  {
    // Only evaluate CF for the minimum-CI subset. Final tie order A,B,C,D.
    for(int e=0;e<d.count;++e) if(d.ci[e]==d.ci[d.rawExpert])
      for(int j=0;j<d.validation;++j) { d.cf[e]+=cf[j][e]; }
    for(int e=0;e<d.count;++e)
      if(d.ci[e]==d.ci[d.rawExpert] && d.cf[e]<d.cf[d.expert]) { d.expert=e; }
  }
  if(mode==5 && d.expert)
  {
    int64_t maxPositive=0;
    for(int j=0;j<d.validation;++j) { maxPositive=std::max(maxPositive,ci[j][0]-ci[j][d.expert]); }
    d.gain=d.ci[0]-d.ci[d.expert]; d.margin=d.gain-maxPositive;
    if(d.margin<=0) { d.expert=0; d.guardRejected=true; }
  }
}
}
