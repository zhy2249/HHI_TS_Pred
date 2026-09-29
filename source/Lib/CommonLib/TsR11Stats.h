// Optional final-Writer observation only. Never consulted by a selector.
#pragma once
#include <array>
#include <cstdint>
#include <cstdio>
#include <map>
#include <mutex>
namespace TsFixedPrediction
{
struct R11Stats
{
  using Key=std::array<int,24>;
  enum Field {TU,CG,COEFF,NZ,REGULAR,REGULAR_NZ,CI_UNIQUE,CI_TIE,NO_EVIDENCE,EMPTY,DEFAULT_A,DEFAULT_C,SELECT_D,
    ACTION_BASE,MAP_BASE,SAME_ADDED,CROSS_ADDED,
    CI_A,CI_B,CI_C,CI_D,CF_A,CF_B,CF_C,CF_D,PATH_A,PATH_B,PATH_C,PATH_D,
    REGRET_CI_A,REGRET_CI_B,REGRET_CI_C,REGRET_CI_D,
    REGRET_CF_A,REGRET_CF_B,REGRET_CF_C,REGRET_CF_D,
    REGRET_PATH_A,REGRET_PATH_B,REGRET_PATH_C,REGRET_PATH_D,
    SELECT_CI,SELECT_CF,SELECT_PATH,SELECT_REGRET_CI,SELECT_REGRET_CF,SELECT_REGRET_PATH,COUNT};
  std::map<Key,std::array<int64_t,COUNT>> rows;
  std::mutex mutex;
  void add(const Key &k,const std::array<int64_t,COUNT> &v)
  { std::lock_guard<std::mutex> lock(mutex); auto &r=rows[k]; for(int i=0;i<COUNT;++i) { r[i]+=v[i]; } }
  ~R11Stats()
  {
    if(rows.empty()) { return; }
    std::fprintf(stderr,"TS_R11_STATS_HEADER trajectory_policy,mode,component,width,height,cu_qp,intra,bdpcm,cg_count,cg_index,n,n1,d,cutoff,v0_size,v3_size,v4_size,validation_size,effective_samples,distinct_actions,selected_expert,best_target_ci,best_target_cf,best_target_path,tu_count,cg_count_census,coeff_count,nonzero_count,regular_count,regular_nonzero,ci_strict_winner,ci_minimum_tie,structural_no_evidence,empty_validation,default_A,default_C,selected_D,action_vs_r10_3,remap_vs_r10_3,same_cg_added,earlier_cg_added,target_ci_A,target_ci_B,target_ci_C,target_ci_D,target_cf_A,target_cf_B,target_cf_C,target_cf_D,target_actual_path_cf_A,target_actual_path_cf_B,target_actual_path_cf_C,target_actual_path_cf_D,target_regret_ci_A,target_regret_ci_B,target_regret_ci_C,target_regret_ci_D,target_regret_cf_A,target_regret_cf_B,target_regret_cf_C,target_regret_cf_D,target_regret_path_A,target_regret_path_B,target_regret_path_C,target_regret_path_D,target_ci_selected,target_cf_selected,target_actual_path_cf_selected,target_regret_ci_selected,target_regret_cf_selected,target_regret_path_selected\n");
    for(const auto &r:rows)
    {
      std::fprintf(stderr,"TS_R11_STATS "); bool first=true;
      for(int k:r.first) { std::fprintf(stderr,"%s%d",first?"":",",k); first=false; }
      for(auto v:r.second) { std::fprintf(stderr,",%lld",(long long)v); }
      std::fprintf(stderr,"\n");
    }
  }
};
inline R11Stats &r11Stats() { static R11Stats s; return s; }
}
