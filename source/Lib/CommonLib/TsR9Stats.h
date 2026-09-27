// Final-Writer census, kept separate from encoder search trials.
#pragma once
#include <array>
#include <map>
#include <mutex>
#include <cstdio>
namespace TsFixedPrediction
{
struct R9Stats
{
  using Key=std::array<int,19>;
  enum Field {TU,CG,COEFF,NZ,REGULAR,REGULAR_NZ,AXIS,AXIS_COST,ACTION_CHANGED,MAP_CHANGED,
    K1,EXPERT_A,EXPERT_B,EXPERT_C,VALIDATION,EXPERTS,SCORE_GAIN,TARGET_GAIN,
    LOSS_A,LOSS_B,LOSS_C,REGRET_A,REGRET_B,REGRET_C,REGRET_SELECTED,COUNT};
  std::map<Key,std::array<int64_t,COUNT>> rows;
  std::mutex mutex;
  void add(const Key &k,const std::array<int64_t,COUNT> &v)
  { std::lock_guard<std::mutex> lock(mutex); auto &r=rows[k]; for(int i=0;i<COUNT;++i) { r[i]+=v[i]; } }
  ~R9Stats()
  {
    if(rows.empty()) { return; }
    std::fprintf(stderr,"TS_R9_STATS_HEADER mode,component,width,height,cu_qp,intra,bdpcm,cg_count,cg_index,n,n1,d,cutoff,target_bucket,current_magnitude,current_repeats,validation_size,distinct_experts,selected_expert,tu_count,cg_count_census,coeff_count,nonzero_count,regular_count,regular_nonzero,axis_match,axis_cost_pass,action_vs_r8_12,remap_vs_r8_12,k1_nonidentity,expert_A,expert_B,expert_C,validation_count_sum,distinct_experts_sum,neighborhood_gain_q15_sum,target_gain_q15_sum,validation_loss_A_q15_sum,validation_loss_B_q15_sum,validation_loss_C_q15_sum,validation_regret_A_q15_sum,validation_regret_B_q15_sum,validation_regret_C_q15_sum,validation_regret_selected_q15_sum\n");
    for(const auto &r:rows)
    {
      std::fprintf(stderr,"TS_R9_STATS "); bool first=true;
      for(int k:r.first) { std::fprintf(stderr,"%s%d",first?"":",",k); first=false; }
      for(auto v:r.second) { std::fprintf(stderr,",%lld",(long long)v); }
      std::fprintf(stderr,"\n");
    }
  }
};
inline R9Stats &r9Stats() { static R9Stats s; return s; }
}
