// Final-Writer, bounded-dimensional observation; never used by the selector.
#pragma once
#include "TsR13Prediction.h"
#include <map>
#include <mutex>
#include <string>
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

// Separate opt-in diagnosis schema: final selected TSRC blocks only. Unlike
// the historical support counters above, HIT/UNDER/OVER below compare p to the
// actual final target magnitude. No field is ever read by coding decisions.
struct R13Diagnostic
{
  using CGKey=std::array<int,10>;
  using CoeffKey=std::array<int,12>;
  enum CGField { CG_TU,CG_COUNT,CG_CODED,CG_COEFF,CG_NZ,
    BITS_CURRENT,BITS_UNIFORM,BITS_SPATIAL,BINS_CURRENT,BINS_UNIFORM,BINS_SPATIAL,
    S_VS_C_BETTER,S_VS_C_TIE,S_VS_C_WORSE,S_VS_C_GAIN,S_VS_C_LOSS,
    S_VS_U_BETTER,S_VS_U_TIE,S_VS_U_WORSE,S_VS_U_GAIN,S_VS_U_LOSS,
    BEST_CURRENT,BEST_UNIFORM,BEST_SPATIAL,CG_FIELDS };
  enum CoeffField { POS,NZ,REGULAR_NZ,HIT,UNDER,OVER,DOWN1,UP1,ABS_ERROR,
    P_EQ_CURRENT,P_EQ_UNIFORM,P_EQ_SPATIAL,MAP_CURRENT_DIFF,MAP_UNIFORM_DIFF,
    MAP_ONE,MAP_TWO,MAP_HIGH,PROXY_COST,PROXY_CURRENT,PROXY_UNIFORM,
    NEAR_SUPPORT,FAR_SUPPORT,EXACT_NEAR,EXACT_FAR,DOWN_NEAR,DOWN_FAR,UP_NEAR,UP_FAR,
    TARGET_MAG_SUM,PRED_MAG_SUM,COEFF_FIELDS };
  std::map<CGKey,std::array<int64_t,CG_FIELDS>> cg;
  std::map<CoeffKey,std::array<int64_t,COEFF_FIELDS>> coefficients;
  std::multimap<int64_t,std::string> examples;
  std::mutex mutex;
  void addCG(const CGKey &key,const std::array<int64_t,CG_FIELDS> &value)
  {
    std::lock_guard<std::mutex> lock(mutex);
    auto &row=cg[key]; for(int i=0;i<CG_FIELDS;++i) { row[i]+=value[i]; }
  }
  void addCoeff(const CoeffKey &key,const std::array<int64_t,COEFF_FIELDS> &value)
  {
    std::lock_guard<std::mutex> lock(mutex);
    auto &row=coefficients[key]; for(int i=0;i<COEFF_FIELDS;++i) { row[i]+=value[i]; }
  }
  bool wantsExample(int64_t loss)
  {
    std::lock_guard<std::mutex> lock(mutex);
    return loss>0 && r13Observation().detailLimit>0 &&
      (int(examples.size())<r13Observation().detailLimit || loss>examples.begin()->first);
  }
  void example(int64_t loss,const std::string &line)
  {
    std::lock_guard<std::mutex> lock(mutex);
    if(loss<=0 || !r13Observation().detailLimit) { return; }
    examples.emplace(loss,line);
    while(int(examples.size())>r13Observation().detailLimit) { examples.erase(examples.begin()); }
  }
  template<class Table,size_t N>
  static void dump(const char *prefix,const char *keys,const char *const (&fields)[N],const Table &table)
  {
    if(table.empty()) { return; }
    std::fprintf(stderr,"%s_HEADER %s",prefix,keys);
    for(const auto *field:fields) { std::fprintf(stderr,",%s",field); } std::fprintf(stderr,"\n");
    for(const auto &entry:table)
    {
      std::fprintf(stderr,"%s ",prefix); bool first=true;
      for(int k:entry.first) { std::fprintf(stderr,"%s%d",first?"":",",k); first=false; }
      for(auto v:entry.second) { std::fprintf(stderr,",%lld",(long long)v); }
      std::fprintf(stderr,"\n");
    }
  }
  ~R13Diagnostic()
  {
    const char *const cgFields[]={"tu_count","cg_count","coded_cg_count","coeff_count","nonzero_count",
      "current_fracbits","uniform_fracbits","spatial_fracbits","current_end_bins_sum","uniform_end_bins_sum","spatial_end_bins_sum",
      "spatial_vs_current_better","spatial_vs_current_tie","spatial_vs_current_worse","spatial_vs_current_gain_fracbits","spatial_vs_current_loss_fracbits",
      "spatial_vs_uniform_better","spatial_vs_uniform_tie","spatial_vs_uniform_worse","spatial_vs_uniform_gain_fracbits","spatial_vs_uniform_loss_fracbits",
      "best_current_count","best_uniform_count","best_spatial_count"};
    const char *const coeffFields[]={"coeff_count","nonzero_count","regular_nonzero_count","target_hit_count","target_under_count","target_over_count",
      "target_p_eq_a_minus1_count","target_p_eq_a_plus1_count","target_abs_error_sum",
      "p_current_equiv_count","p_uniform_equiv_count","p_spatial_equiv_count","actual_map_vs_current_count","actual_map_vs_uniform_count",
      "actual_map1_count","actual_map2_count","actual_map_gt2_count","all_nz_full_regular_proxy_sum","current_all_nz_full_regular_proxy_sum","uniform_all_nz_full_regular_proxy_sum",
      "near_support_sum","far_support_sum","exact_near_support","exact_far_support","down_near_support","down_far_support","up_near_support","up_far_support",
      "target_abs_sum","predictor_abs_sum"};
    static_assert(sizeof(cgFields)/sizeof(cgFields[0])==CG_FIELDS,"R13 diagnostic CG schema mismatch");
    static_assert(sizeof(coeffFields)/sizeof(coeffFields[0])==COEFF_FIELDS,"R13 diagnostic coefficient schema mismatch");
    dump("TS_R13_DIAG_CG","trajectory_policy,poc,component,width,height,cu_qp,intra,bdpcm,cg_count_in_tu,entry_budget_bucket",cgFields,cg);
    dump("TS_R13_DIAG_COEFF","trajectory_policy,poc,component,width,height,cu_qp,intra,bdpcm,shadow_mode,cutoff,n,target_bucket",coeffFields,coefficients);
    for(auto i=examples.rbegin();i!=examples.rend();++i) { std::fprintf(stderr,"TS_R13_DIAG_DETAIL %s\n",i->second.c_str()); }
  }
};
inline R13Diagnostic &r13Diagnostic() { static R13Diagnostic s; return s; }
}
