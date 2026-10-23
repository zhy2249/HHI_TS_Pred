// Final-Writer, bounded-dimensional observation; never used by the selector.
#pragma once
#include "TsR13Prediction.h"
#include <map>
#include <mutex>
namespace TsFixedPrediction
{
struct R13Stats
{
  // Sequence/configuration belong to the enclosing job manifest, not an
  // unbounded string key. CG/TU totals use cutoff=n=weight=-1 sentinel rows.
  using Key=std::array<int,12>; // trajectory,shadow,component,W,H,QP,intra,bdpcm,CGs,cutoff,n,weight
  enum Field { TU,CG,COEFF,NZ,REMAP_POSITION,REMAP_NZ,SPARSE,SCORED,
    SELECT_CURRENT,SELECT_IDENTITY,SELECT_OTHER,IDENTITY_ACTION,TIED_BEST,
    VALID_MARGIN,MARGIN_SUM,BEST_SCORE_SUM,SECOND_SCORE_SUM,CURRENT_SCORE_SUM,
    VS_R2,MAP_VS_R2,VS_PAIR,MAP_VS_PAIR,CURRENT_TIE_BROKEN,
    HIT,DOWN,UP,WEIGHTED_HIT,WEIGHTED_DOWN,WEIGHTED_UP,
    UNIT_SAMPLE,TWO_SAMPLE,VALID_L,VALID_U,VALID_D,VALID_LL,VALID_UU,
    NZ_L,NZ_U,NZ_D,NZ_LL,NZ_UU,COUNT };
  std::map<Key,std::array<int64_t,COUNT>> rows;
  std::mutex mutex;
  int detailCount=0,traceCount[2]{};
  void add(const Key &key,const std::array<int64_t,COUNT> &value)
  {
    std::lock_guard<std::mutex> lock(mutex);
    auto &row=rows[key]; for(int i=0;i<COUNT;++i) { row[i]+=value[i]; }
  }
  void detail(int poc,int component,int width,int height,int cg,int scan,int target,
              int cutoff,const int (&h)[5],int old,const R13Decision &u,const R13Decision &s)
  {
    std::lock_guard<std::mutex> lock(mutex);
    if(detailCount>=r13Observation().detailLimit) { return; } ++detailCount;
    std::fprintf(stderr,"TS_R13_DETAIL poc=%d c=%d w=%d h=%d cg=%d scan=%d target=%d cutoff=%d support=",
      poc,component,width,height,cg,scan,target,cutoff);
    for(int v:h) { std::fprintf(stderr,"%d,",v); }
    std::fprintf(stderr," r2=%d uniform=%d spatial=%d scores(p/u/s)=",old,u.predictor,s.predictor);
    for(int i=0;i<u.candidateCount;++i)
      std::fprintf(stderr,"[%d/%lld/%lld]",u.candidates[i],(long long)u.scores[i],(long long)s.scores[i]);
    std::fprintf(stderr," scored=%d score-scale=168\n",int(u.scored));
  }
  void trace(bool writer,int poc,int component,int width,int height,int qp,int cg,int bins,uint64_t hash)
  {
    std::lock_guard<std::mutex> lock(mutex);
    if(traceCount[int(writer)]>=r13Observation().detailLimit) { return; } ++traceCount[int(writer)];
    std::fprintf(stderr,"TS_R13_TRACE role=%c trajectory=%d poc=%d c=%d w=%d h=%d qp=%d cg=%d bins=%d hash=%llu\n",
      writer?'W':'R',mode(),poc,component,width,height,qp,cg,bins,(unsigned long long)hash);
  }
  ~R13Stats()
  {
    if(rows.empty()) { return; }
    const char *const fields[]={"tu_count","cg_count","coeff_count","nonzero_count",
      "actual_remap_position","actual_remap_nonzero","sparse_count","scored_count",
      "selected_current_equiv","selected_identity_not_current","selected_other","identity_action",
      "tied_best","valid_margin_count","margin_sum168","best_score_sum168","second_score_sum168","current_score_sum168",
      "p_vs_r2","actual_remap_vs_r2","p_uniform_vs_spatial","actual_remap_uniform_vs_spatial","current_tie_broken",
      "direct_support","down_support","up_support","weighted_direct_support","weighted_down_support","weighted_up_support",
      "unit_samples","two_samples","valid_L","valid_U","valid_D","valid_LL","valid_UU",
      "nonzero_L","nonzero_U","nonzero_D","nonzero_LL","nonzero_UU"};
    static_assert(sizeof(fields)/sizeof(fields[0])==COUNT,"R13 statistics schema mismatch");
    std::fprintf(stderr,"TS_R13_STATS_HEADER trajectory_policy,shadow_mode,component,width,height,cu_qp,intra,bdpcm,cg_count_in_tu,cutoff,n,weight_sum");
    for(const auto *field:fields) { std::fprintf(stderr,",%s",field); } std::fprintf(stderr,"\n");
    for(const auto &entry:rows)
    {
      std::fprintf(stderr,"TS_R13_STATS "); bool first=true;
      for(int k:entry.first) { std::fprintf(stderr,"%s%d",first?"":",",k); first=false; }
      for(auto value:entry.second) { std::fprintf(stderr,",%lld",(long long)value); }
      std::fprintf(stderr,"\n");
    }
  }
};
inline R13Stats &r13Stats() { static R13Stats s; return s; }
}
