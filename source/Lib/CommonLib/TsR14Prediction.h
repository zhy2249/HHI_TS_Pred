// R14-NF-168-v3: pure near/far scoring and post-coefficient state feedback.
// State ownership/CG rollback belong to the caller. No context or coefficient writes.
#pragma once
#include "TsR13Prediction.h"
#include <cstdint>
#include <climits>

namespace TsFixedPrediction
{
struct R14Decision
{
  int n=0,nearCount=0,farCount=0,k=2,r=0,current=0,predictor=0;
  // Dynamic: 0..K are valid. Fixed: only r is evaluated, all other entries -1.
  int winners[5]{-1,-1,-1,-1,-1};
  bool scored=false;
};
struct R14Update
{
  int state=0,target=0,direction=0,beforeR=0,afterR=0;
  bool eligible=false,sameWinners=false;
};

inline R14Decision r14Prepare(const R14Config &config,int state,
                             const int (&h)[5],unsigned rice,int range)
{
  R14Decision out;
  out.k=config.k; out.r=r14Output(config,state);
  out.current=std::max(h[0],h[1]); out.predictor=out.current;
  int values[5],near[5],far[5],unique=0;
  for(int j=0;j<5;++j)
  {
    CHECK(h[j]<0,"R14 history requires nonnegative magnitudes");
    if(!h[j]) { continue; }
    ++out.n; if(j<2) { ++out.nearCount; } else { ++out.farCount; }
    int i=0; while(i<unique && values[i]<h[j]) { ++i; }
    if(i==unique || values[i]!=h[j])
    {
      for(int z=unique;z>i;--z)
      { values[z]=values[z-1]; near[z]=near[z-1]; far[z]=far[z-1]; }
      values[i]=h[j]; near[i]=far[i]=0; ++unique;
    }
    if(j<2) { ++near[i]; } else { ++far[i]; }
  }
  const int first=config.dynamic?0:out.r,last=config.dynamic?config.k:out.r;
  if(out.n<3)
  {
    // Preserve the sparse raw Current representation, including p=1.
    for(int r=first;r<=last;++r) { out.winners[r]=out.current; }
    return out;
  }
  out.scored=true;
  int base[5],raised[5];
  const int largest=values[unique-1];
  for(int i=0;i<unique;++i)
  {
    base[i]=syntaxCost(unsigned(values[i]),rice,range);
    raised[i]=values[i]<largest ? syntaxCost(unsigned(values[i])+1u,rice,range) : base[i];
  }
  int candidates[6],count=1;
  candidates[0]=out.current<=1?0:out.current;
  if(candidates[0]) { candidates[count++]=0; }
  for(int i=0;i<unique;++i)
    if(values[i]>1 && values[i]!=candidates[0]) { candidates[count++]=values[i]; }
  int64_t bestScores[5]{INT64_MAX,INT64_MAX,INT64_MAX,INT64_MAX,INT64_MAX};
  for(int c=0;c<count;++c)
  {
    int64_t nearLoss=0,farLoss=0;
    for(int i=0;i<unique;++i)
    {
      const int64_t loss=r13CachedLoss168(values[i],candidates[c],base[i],raised[i]);
      nearLoss+=near[i]*loss; farLoss+=far[i]*loss;
    }
    int64_t score=config.k*nearLoss+first*farLoss;
    for(int r=first;r<=last;++r,score+=farLoss)
      if(score<bestScores[r]) { bestScores[r]=score; out.winners[r]=candidates[c]; }
  }
  out.predictor=out.winners[out.r];
  return out;
}

inline int r14FeedbackCost(int a,int p,unsigned rice,int range)
{
  CHECK(a<0 || p<0,"R14 feedback requires nonnegative magnitudes");
  if(!a) { return 0; }
  if(p<=1) { return syntaxCost(unsigned(a),rice,range); }
  if(p==a) { return 1; }
  return syntaxCost(unsigned(a)+(p>a?1u:0u),rice,range);
}

inline R14Update r14Commit(const R14Config &config,int state,
                          const R14Decision &d,int a,unsigned rice,int range)
{
  R14Update out;
  out.state=state; out.beforeR=out.afterR=out.target=r14Output(config,state);
  CHECK(a<0 || d.k!=config.k || d.r!=out.beforeR,"Invalid R14 commit/prepare pair");
  out.eligible=config.dynamic && a>0 && d.n>=3 && d.nearCount>0 && d.farCount>0;
  if(!out.eligible) { return out; }
  out.sameWinners=true;
  for(int r=0;r<=config.k;++r)
  {
    CHECK(d.winners[r]<0,"R14 dynamic feedback requires the full grid");
    if(d.winners[r]!=d.winners[0]) { out.sameWinners=false; }
  }
  if(out.sameWinners) { return out; }
  // Every action is either an exact hit, C(a), or C(a+1). Query each cost once,
  // and never request a+1 when no winner can overpredict the observed magnitude.
  const int base=syntaxCost(unsigned(a),rice,range);
  bool needRaised=false;
  for(int r=0;r<=config.k;++r) { needRaised|=d.winners[r]>1 && d.winners[r]>a; }
  const int raised=needRaised?syntaxCost(unsigned(a)+1u,rice,range):base;
  int bestCost=INT_MAX,bestDistance=INT_MAX;
  for(int r=0;r<=config.k;++r)
  {
    const int p=d.winners[r];
    const int cost=p<=1?base:p==a?1:p>a?raised:base;
    const int distance=std::abs(r-out.beforeR);
    if(cost<bestCost || (cost==bestCost && (distance<bestDistance || (distance==bestDistance && r>out.target))))
    { bestCost=cost; bestDistance=distance; out.target=r; }
  }
  out.direction=(out.target>out.beforeR)-(out.target<out.beforeR);
  out.state=std::max(0,std::min(config.pair?2*config.k+1:config.k,state+out.direction));
  out.afterR=r14Output(config,out.state);
  return out;
}
}
