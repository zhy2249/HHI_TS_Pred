// Exact integer-cost engineering path for R3-local and R6. No new predictor.
#pragma once
#include "TsR6Prediction.h"

namespace TsFixedPrediction
{
// A support has at most five nonzero positions. Equal magnitudes may share
// costs and SUM multiplicities; they must NOT multiply the maximum guard term.
struct R36ScoreTable
{
  int values[5], multiplicity[5], base[5], raised[5];
  int count=0, identity=0;
  R36ScoreTable(int current,const int *nz,int n,unsigned rice,int range)
  {
    std::copy_n(nz,n,values);
    // Bounded insertion sort avoids a general introsort for a <=5 item list.
    for(int i=1;i<n;++i)
    {
      const int v=values[i]; int j=i;
      while(j && values[j-1]>v) { values[j]=values[j-1]; --j; }
      values[j]=v;
    }
    const int largest=std::max(current,values[n-1]);
    for(int i=0;i<n;)
    {
      const int v=values[i]; int end=i+1;
      while(end<n && values[end]==v) { ++end; }
      values[count]=v; multiplicity[count]=end-i;
      base[count]=syntaxCost(v,rice,range);
      // With no larger candidate, v+1 cannot occur in any remapping.
      raised[count]=v<largest ? syntaxCost(v+1,rice,range) : base[count];
      identity+=multiplicity[count]*base[count]; ++count; i=end;
    }
  }
  int mappedCost(int i,int p) const
  { return values[i]==p ? 1 : values[i]<p ? raised[i] : base[i]; }
  int score(int p) const
  {
    int sum=0;
    for(int i=0;i<count;++i) { sum+=multiplicity[i]*mappedCost(i,p); }
    return sum;
  }
};

inline LocalGuardResult r36Guard(int current,const int *nz,int n,unsigned rice,int range)
{
  LocalGuardResult out{current,current};
  if(n<3) { return out; }
  const R36ScoreTable t(current,nz,n,rice,range);
  out.winner=current<=1?0:current;
  const int currentScore=t.score(out.winner);
  int best=currentScore;
  if(t.identity<best) { best=t.identity; out.winner=0; }
  int prefix=0;
  for(int i=0;i<t.count;++i)
  {
    // S(p)=S(identity)+sum_{a<p} count(a)*(C(a+1)-C(a))
    //                    +count(p)*(C(1)-C(p)). Exact even for nonmonotone C.
    if(t.values[i]>1)
    {
      const int score=t.identity+prefix+t.multiplicity[i]*(1-t.base[i]);
      if(score<best) { best=score; out.winner=t.values[i]; }
    }
    prefix+=t.multiplicity[i]*(t.raised[i]-t.base[i]);
  }
  if(equivalentPredictors(current,out.winner)) { return out; }
  out.gain=currentScore-best;
  for(int i=0;i<t.count;++i)
    out.bestPositive=std::max(out.bestPositive,t.mappedCost(i,current)-t.mappedCost(i,out.winner));
  if(out.margin()>0) { out.predictor=out.winner; }
  return out;
}

// Unlike diagnostic r6Predict, this returns only the observable action. No
// current-hit counts, parent diagnostics or unused original guard are built.
inline int r36Predict(int policy,const int (&h)[5],unsigned rice,int range)
{
  const int current=std::max(h[0],h[1]);
  int nz[5],n=0;
  for(int v:h) { if(v) { nz[n++]=v; } }
  if(n<3)
  {
    if(policy<29) { return current; }
    if(n!=2 || !h[0] || !h[1]) { return 0; }
    return policy==29 ? current : policy==30 ? int((int64_t(h[0])+h[1]+1)/2) : std::min(h[0],h[1]);
  }
  if(policy!=27 && policy!=28)
  {
    const auto d=r36Guard(current,nz,n,rice,range);
    if(policy==25 && d.margin()<=0) { return 0; }
    if(policy==26 && !equivalentPredictors(d.winner,current) && d.margin()<=0) { return 0; }
    return d.predictor;
  }
  const R36ScoreTable t(current,nz,n,rice,range);
  const auto score=[&](int p) {
    int sum=0,minimum=INT32_MAX,saving=0;
    for(int i=0;i<t.count;++i)
    {
      const int c=t.mappedCost(i,p);
      sum+=t.multiplicity[i]*c;
      minimum=std::min(minimum,c); saving=std::max(saving,t.base[i]-c);
    }
    return policy==27 ? sum-minimum : sum+saving;
  };
  int best=current,bestScore=score(current);
  const auto consider=[&](int p) {
    if(equivalentPredictors(p,current)) { return; }
    const int value=score(p);
    if(value<bestScore) { best=p; bestScore=value; }
  };
  consider(0);
  for(int i=0;i<t.count;++i) { if(t.values[i]>1) { consider(t.values[i]); } }
  return best;
}
}
