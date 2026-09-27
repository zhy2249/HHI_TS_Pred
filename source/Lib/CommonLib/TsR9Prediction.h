// R9-20260927-v1. Pure causal scoring; immutable caller-supplied CF10 costs.
#pragma once
#include "TsR8Prediction.h"

namespace TsFixedPrediction
{
struct R9Decision
{
  MagnitudeAction action{0,0}, base{0,0};
  int n=0,n1=0,n2=0,current=0,candidates=0,expert=0,validation=0,experts=1;
  bool axis=false,axisCost=false;
  int64_t score=0,baseScore=0,validationLoss[3]{};
};
template<class Cost>
int64_t r9Objective(MagnitudeAction action,const int (&a)[5],const Cost &cost,int mode)
{
  int n=0,n1=0,n2=0;
  int64_t s=0,b=0;
  for (int v:a) if(v)
  {
    ++n; n1+=v==1; n2+=v>=2;
    const int64_t c=cost(remap(v,action)); s+=c; b=std::max(b,cost(v)-c);
  }
  if(mode==4) { return 2*s+b; }
  if(mode==5 || mode==13) { return n*s+n2*b; }
  return s+b+(mode==6 && action.predictor>=2 ? n1*std::max<int64_t>(0,cost(2)-cost(1)) : 0);
}
// modes9/10 use this same A expert, then causal validation in ContextModelling.
template<class Cost>
R9Decision r9Decision(int mode,const int (&a)[5],int limit,const Cost &cost)
{
  CHECK(mode<1 || mode>13,"Invalid R9 decision");
  R9Decision d;
  for(int v:a) { CHECK(v<0 || v>limit,"R9 magnitude range"); d.n+=v!=0; d.n1+=v==1; d.n2+=v>=2; }
  d.current=r8Canonical(std::max(a[0],a[1]));
  const auto parent=r8Decision(12,a,limit,cost,[](int){return int64_t(0);});
  d.base={parent.predictor,0};
  const bool complete=mode==1 || mode==2 || mode==7 || mode==8;
  const auto sparse=[&]() { return d.n==2 && a[0] && a[1] ? d.current : 0; };
  if(d.n<3)
  {
    int p=mode==1 ? d.current : sparse();
    if(mode==3 || mode==13)
    {
      d.axis=d.n==2 && ((a[0]>=2 && a[0]==a[3] && !a[1]) || (a[1]>=2 && a[1]==a[4] && !a[0]));
      d.axisCost=d.axis && cost(d.current)>cost(1);
      if(d.axisCost) { p=d.current; }
    }
    d.action=canonicalAction(p,mode==7?1:0);
    if(mode==8)
    {
      const auto alt=canonicalAction(p,1);
      if(r9Objective(alt,a,cost,2)<r9Objective(d.action,a,cost,2)) { d.action=alt; }
    }
  }
  else
  {
    int values[12]{},count=0;
    const auto add=[&](int v) {
      if(std::find(values,values+count,v)==values+count) { CHECK(count>=12,"R9 candidate overflow"); values[count++]=v; }
    };
    add(0); add(d.current);
    for(int v:a) if(v) { add(v); if(complete && v<limit) { add(v+1); } }
    std::sort(values,values+count);
    const auto bestForK=[&](int k) {
      MagnitudeAction best=canonicalAction(d.current,k);
      auto bestScore=r9Objective(best,a,cost,mode);
      for(int j=0;j<count;++j)
      {
        const auto action=canonicalAction(values[j],k);
        const auto score=r9Objective(action,a,cost,mode);
        if(score<bestScore || (score==bestScore && (mode==8 && k==1 ? action.predictor<best.predictor :
            r8TieLess(action.predictor,best.predictor,canonicalAction(d.current,k).predictor))))
        { best=action; bestScore=score; }
      }
      return best;
    };
    d.action=bestForK(mode==7?1:0);
    if(mode==8)
    {
      // P12 action first, strictly-better updates only. Remaining ties k=0 then p.
      const auto alt=bestForK(1);
      if(r9Objective(alt,a,cost,2)<r9Objective(d.action,a,cost,2)) { d.action=alt; }
    }
    d.candidates=count;
  }
  d.score=r9Objective(d.action,a,cost,mode);
  d.baseScore=r9Objective(d.base,a,cost,mode);
  return d;
}
}
