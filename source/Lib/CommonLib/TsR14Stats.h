// R14 observations only: final-Writer population and separate RDOQ trial totals.
#pragma once
#include "TsR14Prediction.h"
#include <map>
#include <mutex>
namespace TsFixedPrediction
{
struct R14Stats
{
  using Key=std::array<int,13>; // mode,c,W,H,QP,intra,bdpcm,target,CGs,cutoff,n,state,r
  enum Field { TU,CG,COEFF,NZ,TARGET,SPARSE,ZERO_EVENT,MISSING_NEAR,MISSING_FAR,FIXED_EVENT,
    ELIGIBLE,SAME_WINNERS,NEUTRAL,UP,DOWN,STATE_CHANGE,WEIGHT_CHANGE,PHASE_ONLY,
    P_CURRENT,MAP_CURRENT,P_INITIAL,MAP_INITIAL,REMAP_NZ,NEAR_SUM,FAR_SUM,TARGET_DISTANCE,FEEDBACK_TIE,
    STEP_BETTER,STEP_WORSE,STEP_EQUAL,NEXT_PAIR,NEXT_POS,NEXT_ZERO,NEXT_NEG,NEXT_GAIN,
    NEXT_CROSS_CG,NEXT_PHASE_PAIR,NEXT_PHASE_GAIN,NEXT_P_CHANGED,NEXT_MAP_CHANGED,DIRECTION_REVERSE,
    TU_VALID_SUM,TU_FIRST_WEIGHT_SUM,TU_WITH_WEIGHT,TU_NO_WEIGHT,TU_WITH_PDIFF,TU_NO_PDIFF,
    TU_REMAIN_VALID_SUM,NEXT_UNPAIRED,COUNT };
  std::map<Key,std::array<int64_t,COUNT>> rows;
  using TrialKey=std::array<int,8>; // mode,c,W,H,QP,intra,CGs,target
  std::map<TrialKey,std::array<int64_t,3>> trials;
  std::mutex mutex;
  int detailCount=0,traceCount[2]{};
  void add(const Key &key,const std::array<int64_t,COUNT> &value)
  {
    std::lock_guard<std::mutex> lock(mutex);
    auto &row=rows[key]; for(int i=0;i<COUNT;++i) { row[i]+=value[i]; }
  }
  void trial(const TrialKey &key,bool zeroed,bool changed)
  {
    std::lock_guard<std::mutex> lock(mutex);
    auto &row=trials[key]; ++row[0]; row[1]+=zeroed; row[2]+=zeroed && changed;
  }
  void detail(int poc,int component,int width,int height,int qp,int cg,int scan,int a,int cutoff,
              int before,const int (&h)[5],const R14Decision &d,const R14Update &u)
  {
    std::lock_guard<std::mutex> lock(mutex);
    if(detailCount>=r14Observation().detailLimit) { return; } ++detailCount;
    std::fprintf(stderr,"TS_R14_DETAIL numbering=compact-15-v1 role=W mode=%d poc=%d c=%d w=%d h=%d qp=%d cg=%d scan=%d a=%d cutoff=%d n=%d state_in=%d state_out=%d r_in=%d r_out=%d p=%d target=%d direction=%d support=",
      r14PublicMode(mode()),poc,component,width,height,qp,cg,scan,a,cutoff,d.n,before,u.state,u.beforeR,u.afterR,d.predictor,u.target,u.direction);
    for(int v:h) { std::fprintf(stderr,"%d,",v); }
    std::fprintf(stderr," winners=");
    for(int r=0;r<=d.k;++r) { std::fprintf(stderr,"%d,",d.winners[r]); }
    std::fprintf(stderr,"\n");
  }
  void trace(bool writer,int poc,int component,int width,int height,int qp,int cg,int bins,int before,int after,uint64_t hash)
  {
    std::lock_guard<std::mutex> lock(mutex);
    if(traceCount[int(writer)]>=r14Observation().detailLimit) { return; } ++traceCount[int(writer)];
    std::fprintf(stderr,"TS_R14_TRACE numbering=compact-15-v1 role=%c mode=%d poc=%d c=%d w=%d h=%d qp=%d cg=%d bins=%d state_in=%d state_out=%d hash=%llu\n",
      writer?'W':'R',r14PublicMode(mode()),poc,component,width,height,qp,cg,bins,before,after,(unsigned long long)hash);
  }
  ~R14Stats()
  {
    const char *const fields[]={"tu_count","cg_count","coeff_count","nonzero_count","target_count","sparse_count","zero_event_count","missing_near_count","missing_far_count","fixed_count",
      "eligible_count","same_winners_count","neutral_count","up_count","down_count","state_change_count","weight_change_count","phase_only_count",
      "p_vs_current","actual_remap_vs_current","p_vs_initial_weight","actual_remap_vs_initial_weight","actual_remap_nonzero","near_nonzero_sum","far_nonzero_sum","target_distance_sum","feedback_cost_tie_count",
      "step_better_count","step_worse_count","step_equal_count","next_pair_count","next_positive_count","next_zero_count","next_negative_count","next_gain_sum",
      "next_cross_cg_count","next_phase_pair_count","next_phase_gain_sum","next_p_changed","next_actual_remap_changed","direction_reverse_count",
      "tu_valid_sum","tu_first_weight_event_sum","tu_with_weight","tu_no_weight","tu_with_pdiff","tu_no_pdiff","tu_remaining_valid_sum","next_unpaired_count"};
    static_assert(sizeof(fields)/sizeof(fields[0])==COUNT,"R14 statistics schema mismatch");
    if(!rows.empty())
    {
      std::fprintf(stderr,"TS_R14_STATS_HEADER mode_n15,component,width,height,cu_qp,intra,bdpcm,target,cg_count_in_tu,cutoff,n,state,weight");
      for(const auto *field:fields) { std::fprintf(stderr,",%s",field); } std::fprintf(stderr,"\n");
      for(const auto &entry:rows)
      {
        std::fprintf(stderr,"TS_R14_STATS "); bool first=true;
        for(int k:entry.first) { std::fprintf(stderr,"%s%d",first?"":",",k); first=false; }
        for(auto value:entry.second) { std::fprintf(stderr,",%lld",(long long)value); }
        std::fprintf(stderr,"\n");
      }
    }
    if(!trials.empty())
    {
      std::fprintf(stderr,"TS_R14_TRIAL_HEADER mode_n15,component,width,height,cu_qp,intra,cg_count_in_tu,target,cg_trial_count,zero_cg_count,rolled_back_state_count\n");
      for(const auto &entry:trials)
      {
        std::fprintf(stderr,"TS_R14_TRIAL "); bool first=true;
        for(int k:entry.first) { std::fprintf(stderr,"%s%d",first?"":",",k); first=false; }
        for(auto value:entry.second) { std::fprintf(stderr,",%lld",(long long)value); }
        std::fprintf(stderr,"\n");
      }
    }
  }
};
inline R14Stats &r14Stats() { static R14Stats s; return s; }
}
