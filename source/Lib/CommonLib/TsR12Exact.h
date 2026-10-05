// Exact engineering path for R12-POS-01. No new model, guard, or state.
#pragma once
#include "TsR12Prediction.h"

namespace TsFixedPrediction
{
// Same Current-first, then ascending canonical P0 as rateDecision. A uses
// the same set, but its explicit r8TieLess rule is retained independently.
struct R12ActionCosts
{
  int candidates[6]{}, count=1;
  int64_t loss[6][5]{};
  explicit R12ActionCosts(const int (&h)[5])
  {
    candidates[0]=r8Canonical(std::max(h[0],h[1]));
    int sorted[6]={0}; std::copy_n(h,5,sorted+1); std::sort(sorted,sorted+6);
    for(int v:sorted)
    {
      const int p=r8Canonical(v);
      if(std::find(candidates,candidates+count,p)==candidates+count) { candidates[count++]=p; }
    }
  }
  template<class Cost> void fill(const int (&h)[5],const Cost &cost)
  {
    const int64_t hit=cost(1);
    const int largest=*std::max_element(candidates,candidates+count);
    for(int j=0;j<5;++j) if(h[j])
    {
      const auto same=cost(h[j]);
      // No candidate exceeds largest; h[j]+1 is unreachable at the maximum.
      const auto incremented=h[j]<largest ? cost(h[j]+1) : same;
      for(int k=0;k<count;++k)
      {
        const int p=candidates[k];
        loss[k][j]=h[j]==p ? hit : h[j]<p ? incremented : same;
      }
    }
  }
};

// Action-only counterpart of r12Experts. Both cost models use immutable
// caller snapshots. CI is shared by B/C; CF is never replaced by CI.
template<class Fractional,class Integer>
R10Actions r12FastExperts(int mode,const int (&h)[5],int limit,
                         const Fractional &cf,const Integer &ci)
{
  const auto current=canonicalAction(std::max(h[0],h[1]));
  int n=0;
  for(int v:h) { CHECK(v<0 || v>limit,"R12 magnitude range"); n+=v!=0; }
  R10Actions out{{current,current,current,current}};
  if(n<3)
  {
    out[0]=n==2 && h[0] && h[1] ? current : canonicalAction(0);
    return out;
  }
  R12ActionCosts table(h);
  table.fill(h,ci);
  int raw=0,weightedRaw=0;
  int64_t sums[6]{},weighted[6]{};
  const bool weightedC=r12WeightedC(mode);
  for(int k=0;k<table.count;++k)
  {
    for(int j=0;j<5;++j)
    {
      sums[k]+=table.loss[k][j];
      if(weightedC) { weighted[k]+=R12_WEIGHTS[j]*table.loss[k][j]; }
    }
    if(sums[k]<sums[raw]) { raw=k; }
    if(weightedC && weighted[k]<weighted[weightedRaw]) { weightedRaw=k; }
  }
  out[1]=canonicalAction(table.candidates[raw]);
  const int c=weightedC?weightedRaw:raw;
  const int64_t gain=weightedC ? weighted[0]-weighted[c] : sums[0]-sums[c];
  int64_t penalty=0;
  if(!weightedC || mode==8 || mode==11)
    for(int j=0;j<5;++j)
    {
      const auto delta=table.loss[0][j]-table.loss[c][j];
      penalty=std::max(penalty,delta*(mode==8?R12_WEIGHTS[j]:1));
    }
  if(gain>penalty) { out[2]=canonicalAction(table.candidates[c]); }

  // A = R9 internal mode12 (=R8-12), empirical P0, k=0, S+identity-trim.
  // No parent/base/diagnostic score is needed to determine this action.
  table.fill(h,cf);
  int identity=0,best=0; int64_t scores[6]{};
  for(int k=0;k<table.count;++k) { if(table.candidates[k]==0) { identity=k; break; } }
  for(int k=0;k<table.count;++k)
  {
    int64_t positive=0;
    for(int j=0;j<5;++j)
    {
      scores[k]+=table.loss[k][j];
      positive=std::max(positive,table.loss[identity][j]-table.loss[k][j]);
    }
    scores[k]+=positive;
    if(scores[k]<scores[best] || (scores[k]==scores[best] &&
       r8TieLess(table.candidates[k],table.candidates[best],current.predictor))) { best=k; }
  }
  out[0]=canonicalAction(table.candidates[best]);
  return out;
}

// CF callback returns FULL-V0 loss for one expert (weighted only in 9/10/12).
// The legal CI pool is constructed first. CF is never evaluated for excluded
// experts and is not needed when only one expert remains. Expert identities
// are not merged even when some query actions coincide.
template<class FractionalSum>
int r12FastSelect(int mode,int rows,const R12Loss &ciRows,const int *slots,
                  const bool *informative,const FractionalSum &cf)
{
  CHECK(mode<0 || mode>12,"Invalid R12 exact selector");
  if(!rows) { return 0; }
  const int count=mode==3?4:3;
  int64_t ci[4]{};
  for(int j=0;j<rows;++j)
    for(int e=0;e<count;++e)
      ci[e]+=ciRows[j][e]*((mode==9 || mode==12)?R12_WEIGHTS[slots[j]]:1);
  if(mode==5)
  {
    int64_t direct[3]{}; int nDirect=0;
    for(int j=0;j<rows;++j) if(slots[j]<2)
    { ++nDirect; for(int e=0;e<3;++e) { direct[e]+=ciRows[j][e]; } }
    const auto best=std::min_element(direct,direct+3);
    if(nDirect && std::count(direct,direct+3,*best)==1) { return int(best-direct); }
  }
  const int w=int(std::min_element(ci,ci+3)-ci);
  int pool=0,ties=0;
  for(int e=0;e<3;++e) { if(ci[e]==ci[w]) { pool|=1<<e; ++ties; } }
  if(ties==1 && mode>=1 && mode<=6 && mode!=5)
  {
    for(int e=0;e<count;++e)
    {
      const auto gap=ci[e]-ci[w];
      if((mode==1 || ((mode==2 || mode==6) && e==2)) && gap>0 && gap<=R12_Q) { pool|=1<<e; }
      if(mode==3 && e==3 && gap>=0 && gap<=R12_Q) { pool|=1<<e; }
    }
    if((mode==4 || mode==6) && std::count(informative,informative+rows,true)>=2)
      for(int j=0;j<rows;++j) if(informative[j])
      {
        int64_t best=INT64_MAX;
        for(int e=0;e<3;++e) { best=std::min(best,ci[e]-ciRows[j][e]); }
        for(int e=0;e<3;++e) { if(ci[e]-ciRows[j][e]==best) { pool|=1<<e; } }
      }
  }
  if(pool==(1<<w)) { return w; }
  int chosen=w; auto bestCF=cf(w);
  for(int e=0;e<count;++e) if(e!=w && (pool & (1<<e)))
  {
    const auto value=cf(e);
    if(value<bestCF) { chosen=e; bestCF=value; }
  }
  return chosen;
}
}
