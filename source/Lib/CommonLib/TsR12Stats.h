// Bounded-dimensional online aggregation. Observation never enters decisions.
#pragma once
#include "TsR12Prediction.h"
#include <map>
#include <mutex>
namespace TsFixedPrediction
{
struct R12Stats
{
  using Key=std::array<int,10>; // trajectory,mode,component,W,H,QP,intra,bdpcm,cutoff,n
  enum Field {TU,CG,COEFF,NZ,REGULAR,EMPTY,EFFECTIVE,CI_TIE,CI_UNIQUE,GAP_Q,GAP_GT_Q,
    NEAR,LEGAL_LOO,DIRECT_UNIQUE,EXPERT_A,EXPERT_B,EXPERT_C,EXPERT_D,
    ACTION_BASE,MAP_BASE,CI_GAP,VALIDATION,VL,VU,VD,VLL,VUU,
    INNER,RAW_CHANGED,C_CHANGED,G_OLD,G_WEIGHTED,FULL_PENALTY,SOFT_PENALTY,
    RAW_ACCEPT,FULL_ACCEPT,SOFT_ACCEPT,DELTA_L,DELTA_U,DELTA_D,DELTA_LL,DELTA_UU,
    MAX_L,MAX_U,MAX_D,MAX_LL,MAX_UU,
    TARGET_CI_A,TARGET_CI_B,TARGET_CI_C,TARGET_CI_D,
    TARGET_CF_A,TARGET_CF_B,TARGET_CF_C,TARGET_CF_D,
    TARGET_PATH_A,TARGET_PATH_B,TARGET_PATH_C,TARGET_PATH_D,
    TARGET_CI_SELECTED,TARGET_CF_SELECTED,TARGET_PATH_SELECTED,
    TARGET_CI_BASE,TARGET_CF_BASE,TARGET_PATH_BASE,
    REGRET_CI_SELECTED,REGRET_CF_SELECTED,REGRET_PATH_SELECTED,COUNT};
  std::map<Key,std::array<int64_t,COUNT>> rows;
  std::mutex mutex;
  int detailCount=0;
  void add(const Key &key,const std::array<int64_t,COUNT> &values)
  { std::lock_guard<std::mutex> lock(mutex); auto &row=rows[key]; for(int k=0;k<COUNT;++k) { row[k]+=values[k]; } }
  void detail(int mode,int s,int target,int cutoff,const R12Decision &d)
  {
    std::lock_guard<std::mutex> lock(mutex);
    if(detailCount>=r12Observation().detailLimit) { return; } ++detailCount;
    std::fprintf(stderr,"TS_R12_DETAIL mode=%d scan=%d target=%d cutoff=%d h=",mode,s,target,cutoff);
    for(int v:d.support) { std::fprintf(stderr,"%d,",v); }
    const auto &i=d.inner;
    std::fprintf(stderr," weights=22111 inner=%d pcur=%d oldRaw=%d oldC=%d weightedRaw=%d G=%lld Gw=%lld full=%lld soft=%lld maxSlot=%d softSlot=%d delta=",
      int(r12WeightedC(mode)),i.current,i.oldRaw,i.oldC,i.raw,(long long)i.oldGain,(long long)i.gain,
      (long long)i.full,(long long)i.soft,i.maxSlot,i.softSlot);
    for(auto v:i.delta) { std::fprintf(stderr,"%lld,",(long long)v); }
    std::fprintf(stderr," effective=%d tie=%d gap=%lld near=%d loo=%d legal=%d direct=%d base=%d chosen=%d actions=",
      d.effective,d.ciTies,(long long)d.ciGap,d.nearMask,d.looMask,d.legalDeletes,d.directWinner,d.baseExpert,d.expert);
    for(int e=0;e<d.count;++e) { std::fprintf(stderr,"%d,",d.actions[e].predictor); }
    std::fprintf(stderr," rows(scan/slot/CI/CF)=");
    for(int j=0;j<d.validation;++j)
    {
      std::fprintf(stderr,"[%d/%d/",d.scan[j],d.slots[j]);
      for(int e=0;e<d.count;++e) { std::fprintf(stderr,"%lld,",(long long)d.ciRows[j][e]); }
      std::fprintf(stderr,"/");
      for(int e=0;e<d.count;++e) { std::fprintf(stderr,"%lld,",(long long)d.cfRows[j][e]); }
      std::fprintf(stderr,"]");
    }
    std::fprintf(stderr,"\n");
  }
  ~R12Stats()
  {
    if(rows.empty()) { return; }
    std::fprintf(stderr,"TS_R12_STATS_HEADER trajectory_policy,mode,component,width,height,cu_qp,intra,bdpcm,cutoff,n,tu_count,cg_count,coeff_count,nonzero_count,regular_count,empty_validation,effective_sum,ci_tie,ci_unique,gap_Q,gap_gt_Q,near_available,loo_deletions,direct_unique,selected_A,selected_B,selected_C,selected_D,action_vs_r10_3,remap_vs_r10_3,ci_gap_sum,validation_sum,slot_L,slot_U,slot_D,slot_LL,slot_UU,inner_count,inner_raw_changed,inner_C_changed,inner_G,inner_Gw,inner_full_penalty,inner_soft_penalty,inner_raw_accept,inner_full_accept,inner_soft_accept,delta_L,delta_U,delta_D,delta_LL,delta_UU,max_L,max_U,max_D,max_LL,max_UU,target_ci_A,target_ci_B,target_ci_C,target_ci_D,target_cf_A,target_cf_B,target_cf_C,target_cf_D,target_path_A,target_path_B,target_path_C,target_path_D,target_ci_selected,target_cf_selected,target_path_selected,target_ci_r10_3,target_cf_r10_3,target_path_r10_3,target_regret_ci_selected,target_regret_cf_selected,target_regret_path_selected\n");
    for(const auto &row:rows)
    {
      std::fprintf(stderr,"TS_R12_STATS "); bool first=true;
      for(int k:row.first) { std::fprintf(stderr,"%s%d",first?"":",",k); first=false; }
      for(auto v:row.second) { std::fprintf(stderr,",%lld",(long long)v); } std::fprintf(stderr,"\n");
    }
  }
};
inline R12Stats &r12Stats() { static R12Stats s; return s; }
}
