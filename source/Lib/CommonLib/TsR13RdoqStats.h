// R13 diagnostic only: local same-history RDOQ probes, never decision feedback.
#pragma once
#include "TsR13Prediction.h"
#include <array>
#include <map>
#include <mutex>

namespace TsFixedPrediction
{
struct R13RdoqStats
{
  // All TS RDOQ search trials, including later discarded TUs. The final field
  // distinguishes a kept/nonzero trial CG from an all-zero trial CG; it does
  // NOT mean that this TU was finally selected by mode decision.
  using Key=std::array<int,12>; // policy,POC,c,W,H,QP,intra,budget-band,n,probe,rice,zero-CG
  enum Field { POS,NZ,PDIFF,ACTUAL_UP,PROBE_UP,UP_DIFF,QDIFF,QUP,QDOWN,
    TO_ZERO,FROM_ZERO,FIXED_QDIFF,SEARCH_QDIFF,ACTUAL_HIT,PROBE_HIT,
    ACTUAL_NEAR_DOWN,ACTUAL_NEAR_UP,PROBE_NEAR_DOWN,PROBE_NEAR_UP,
    ACTUAL_D,PROBE_D,ACTUAL_R,PROBE_R,DELTA_D_OVER_LAMBDA,DELTA_R,
    DELTA_J_OVER_LAMBDA,FIXED_DELTA_J_OVER_LAMBDA,LAMBDA_SUM,COUNT };
  using Value=std::array<double,COUNT>;
  using Rows=std::map<Key,Value>;
  Rows rows;
  std::mutex mutex;
  void addCG(const Rows &local,bool zero)
  {
    std::lock_guard<std::mutex> lock(mutex);
    for(const auto &entry:local)
    {
      auto key=entry.first; key[11]=int(zero);
      auto &dest=rows[key];
      for(int i=0;i<COUNT;++i) { dest[i]+=entry.second[i]; }
    }
  }
  ~R13RdoqStats()
  {
    if(rows.empty()) { return; }
    const char *fields[]={"position_count","actual_nonzero","predictor_changed",
      "actual_extra_up","probe_extra_up","extra_up_changed","quant_level_changed",
      "quant_level_increased","quant_level_decreased","to_zero","from_zero",
      "fixed_candidates_quant_changed","native_vs_fixed_quant_changed",
      "actual_pre_cg_level_hit","probe_local_level_hit","actual_round_minus_one",
      "actual_round_plus_one","probe_round_minus_one","probe_round_plus_one",
      "actual_distortion","probe_distortion","actual_rate_est_bits","probe_rate_est_bits",
      "delta_distortion_over_lambda","delta_rate_est_bits","delta_rd_over_lambda",
      "fixed_candidates_delta_rd_over_lambda","lambda_sum"};
    static_assert(sizeof(fields)/sizeof(fields[0])==COUNT,"R13 RDOQ schema mismatch");
    std::fprintf(stderr,"TS_R13_DIAG_RDOQ_HEADER trajectory_policy,poc,component,width,height,cu_qp,intra,budget_band,n,probe_mode,rice,trial_cg_zero");
    for(const auto *field:fields) { std::fprintf(stderr,",%s",field); }
    std::fprintf(stderr,"\n");
    for(const auto &entry:rows)
    {
      std::fprintf(stderr,"TS_R13_DIAG_RDOQ "); bool first=true;
      for(int key:entry.first) { std::fprintf(stderr,"%s%d",first?"":",",key); first=false; }
      for(double value:entry.second) { std::fprintf(stderr,",%.17g",value); }
      std::fprintf(stderr,"\n");
    }
  }
};
inline R13RdoqStats &r13RdoqStats() { static R13RdoqStats s; return s; }
}
