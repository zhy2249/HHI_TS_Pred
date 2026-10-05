// Encoder-only, stack-owned request. Never decoder input or persistent state.
#pragma once
#include "TsFixedPrediction.h"
#include <vector>
#include <array>
#include <map>
#include <mutex>
namespace TsFixedPrediction
{
struct R9QuantTrial
{
  int component=0,phase=0; // 0=capture q0/proposals; 1=D; 2=U; 3=restore q0.
  bool captured=false,injected=false;
  std::vector<TCoeff> q0;
  int pos[2]={-1,-1},value[2]={0,0};
  double cheap[2]={MAX_DOUBLE,MAX_DOUBLE};
  uint64_t eligible[2]{},cbfRejected[2]{};
};
struct R9QuantStats
{
  using Key=std::array<int,7>;
  struct Row { uint64_t trials=0,captured=0,d=0,u=0,rejectD=0,rejectU=0,testD=0,testU=0,winD=0,winU=0,invalid=0,finalD=0,finalU=0; double gain=0; };
  std::map<Key,Row> rows; std::mutex mutex;
  static bool enabled() { static const bool v=std::getenv("TS_R9_STATS") && std::strcmp(std::getenv("TS_R9_STATS"),"0"); return v; }
  void add(Key k,const R9QuantTrial &t,int testedD,int testedU,int winner,double gain,bool invalid)
  {
    if(!enabled()) { return; } std::lock_guard<std::mutex> lock(mutex); auto &r=rows[k];
    ++r.trials; r.captured+=t.captured; r.d+=t.eligible[0]; r.u+=t.eligible[1];
    r.rejectD+=t.cbfRejected[0]; r.rejectU+=t.cbfRejected[1]; r.testD+=testedD; r.testU+=testedU;
    r.winD+=winner==1; r.winU+=winner==2; r.gain+=gain; r.invalid+=invalid;
  }
  void final(Key k,int kind)
  { if(!enabled()) { return; } std::lock_guard<std::mutex> lock(mutex); auto &r=rows[k]; r.finalD+=kind==1; r.finalU+=kind==2; }
  ~R9QuantStats()
  {
    if(rows.empty()) { return; }
    std::fprintf(stderr,"TS_R9_SEARCH_HEADER mode,component,width,height,cu_qp,intra,owner,trials,captured,down_positions,up_positions,cbf_reject_down,cbf_reject_up,tested_down,tested_up,chosen_down,chosen_up,baseline_unusable,final_down,final_up,local_gain_sum\n");
    for(const auto &v:rows)
    {
      std::fprintf(stderr,"TS_R9_SEARCH "); bool first=true;
      for(int k:v.first) { std::fprintf(stderr,"%s%d",first?"":",",k); first=false; }
      const auto &r=v.second;
      for(uint64_t n:{r.trials,r.captured,r.d,r.u,r.rejectD,r.rejectU,r.testD,r.testU,r.winD,r.winU,r.invalid,r.finalD,r.finalU})
        { std::fprintf(stderr,",%llu",(unsigned long long)n); }
      std::fprintf(stderr,",%.17g\n",r.gain);
    }
  }
};
inline R9QuantStats &r9QuantStats() { static R9QuantStats s; return s; }
}
