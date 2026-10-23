// R13-KH-168-v1: quantization-aware keep-hit surrogate, NOT CABAC fractional bits.
#pragma once
#include "TsFixedPrediction.h"
#include <cstdint>

namespace TsFixedPrediction
{
inline int64_t r13DownScore(int c)
{
  // c >= 1. The final entry is the saturated tail of the down branch.
  static constexpr uint16_t table[23] = {
    0,168,332,488,636,776,908,1032,1148,1256,1356,1448,
    1532,1608,1676,1736,1788,1832,1868,1896,1916,1928,1932
  };
  return table[std::min(c,22)];
}

inline int64_t r13UpScore(int c)
{
  // Unlike the down branch, the up tail must NOT saturate.
  return c<=11 ? r13DownScore(c) : int64_t(84)*c+525;
}

inline int64_t r13CachedLoss168(int m,int p,int base,int raised)
{
  // Identity must precede near-hit tests: m=2,p=1 is NOT a down reward.
  if(p<=1) { return int64_t(168)*base; }
  if(p==m) { return 168; }
  const int64_t distance=int64_t(p)-m;
  if(distance==-1) { return r13DownScore(base); }
  if(distance==1) { return r13UpScore(raised); }
  return int64_t(168)*(p<m ? base : raised);
}

inline int64_t r13Loss168(int m,int p,unsigned rice,int range)
{
  const int base=syntaxCost(unsigned(m),rice,range);
  // At the largest representable magnitude, no larger candidate can exist.
  const int raised=p>m ? syntaxCost(unsigned(m)+1u,rice,range) : base;
  return r13CachedLoss168(m,p,base,raised);
}

struct R13Decision
{
  int n=0,weightSum=0,current=0,predictor=0,candidateCount=0;
  int candidates[6]{};
  int64_t scores[6]{},bestScore=-1,secondScore=-1;
  bool scored=false,tiedBest=false;
  int hit=0,down=0,up=0,weightedHit=0,weightedDown=0,weightedUp=0;
};

// Physical slot order is L,U,D,LL,UU; zero samples are skipped AFTER assigning
// weights. Duplicate magnitudes share cached costs but retain their support.
// Diagnostics are compiled out of the actual predictor hot path.
template<bool diagnostics>
inline int r13Evaluate(int mode,const int (&h)[5],unsigned rice,int range,R13Decision *out)
{
  const int current=std::max(h[0],h[1]);
  int n=0,weightSum=0;
  int values[5],weights[5],unique=0;
  for(int j=0;j<5;++j)
  {
    if(!h[j]) { continue; }
    const int weight=mode==2 && j<2 ? 2 : 1;
    ++n; weightSum+=weight;
    int i=0;
    while(i<unique && values[i]<h[j]) { ++i; }
    if(i<unique && values[i]==h[j]) { weights[i]+=weight; continue; }
    for(int k=unique;k>i;--k) { values[k]=values[k-1]; weights[k]=weights[k-1]; }
    values[i]=h[j]; weights[i]=weight; ++unique;
  }
  if(diagnostics) { out->n=n; out->weightSum=weightSum; out->current=current; }
  int best=current;
  if(n>=3)
  {
    const int largest=values[unique-1];
    int base[5],raised[5];
    for(int i=0;i<unique;++i)
    {
      base[i]=syntaxCost(unsigned(values[i]),rice,range);
      raised[i]=values[i]<largest ? syntaxCost(unsigned(values[i])+1u,rice,range) : base[i];
    }
    // Current first, identity next, then increasing values. Strict improvement
    // preserves the existing R2-2 tie policy and the p=0/p=1 equivalence.
    best=current<=1 ? 0 : current;
    int candidates[6],count=1;
    candidates[0]=best;
    if(best) { candidates[count++]=0; }
    for(int i=0;i<unique;++i)
      if(values[i]>1 && values[i]!=best) { candidates[count++]=values[i]; }
    int64_t bestScore=INT64_MAX;
    int bestIndex=0;
    for(int c=0;c<count;++c)
    {
      int64_t score=0;
      for(int i=0;i<unique;++i)
        score+=weights[i]*r13CachedLoss168(values[i],candidates[c],base[i],raised[i]);
      if(score<bestScore) { bestScore=score; best=candidates[c]; bestIndex=c; }
      if(diagnostics) { out->candidates[c]=candidates[c]; out->scores[c]=score; }
    }
    if(diagnostics)
    {
      out->scored=true; out->candidateCount=count; out->bestScore=bestScore;
      for(int c=0;c<count;++c)
        if(c!=bestIndex && (out->secondScore<0 || out->scores[c]<out->secondScore))
          out->secondScore=out->scores[c];
      out->tiedBest=out->secondScore>=0 && out->secondScore==bestScore;
    }
  }
  if(diagnostics)
  {
    out->predictor=best;
    if(best>1)
      for(int j=0;j<5;++j) if(h[j])
      {
        const int weight=mode==2 && j<2 ? 2 : 1;
        const int64_t distance=int64_t(best)-h[j];
        if(!distance) { ++out->hit; out->weightedHit+=weight; }
        if(distance==-1) { ++out->down; out->weightedDown+=weight; }
        if(distance==1) { ++out->up; out->weightedUp+=weight; }
      }
  }
  return best;
}

inline int r13Predict(int mode,const int (&h)[5],unsigned rice,int range)
{
  return r13Evaluate<false>(mode,h,rice,range,nullptr);
}

inline R13Decision r13Decision(int mode,const int (&h)[5],unsigned rice,int range)
{
  R13Decision out;
  r13Evaluate<true>(mode,h,rice,range,&out);
  return out;
}
}
