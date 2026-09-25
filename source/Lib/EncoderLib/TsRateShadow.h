// Observation at the FINAL old-R3 Writer only. Never called by search estimators.
#pragma once
#include "CommonLib/TsRateReplay.h"
#include <array>
#include <map>
#include <mutex>
#include <tuple>

namespace TsRateShadow
{
using namespace TsFixedPrediction;
enum Field { POS, NZ, ELIGIBLE, WINNER_DIFF, SELECTED_DIFF, RAW_MAPPED, GUARD_MAPPED,
  OLD_CURRENT, TIE_CURRENT, TIE_BROKEN, WINNER_FROM_TIE, OLD_ACCEPT, NEW_ACCEPT,
  ACCEPT_REJECT, REJECT_ACCEPT, SAME_WINNER, MARGIN_DIFF, MARGIN_ABS, MARGIN_LT1, MARGIN_GE1,
  G_OLD, G_NEW, H_OLD, H_NEW, R6_REGION, R6_RAW_IDENTITY, R6_RAW_NONZERO,
  R6_NEW_CURRENT, R6_NEW_IDENTITY, R6_NEW_OLD_WINNER, R6_NEW_OTHER,
  R6_RAW_NEW_CURRENT, R6_RAW_NEW_IDENTITY, R6_RAW_NEW_OLD_WINNER, R6_RAW_NEW_OTHER,
  PAIRS, OLD_ERROR, NEW_ERROR, OLD_TIE_REAL_DIFF, NEW_TIE_REAL_DIFF,
  OLD_INVERSION, NEW_INVERSION, RAW_REAL_DELTA, GUARD_REAL_DELTA,
  RAW_BETTER, RAW_WORSE, GUARD_BETTER, GUARD_WORSE,
  PATH_ERROR, PATH_INVERSION, NP_REJECT, NP_REJECT_DELTA, NP_REJECT_BETTER, NP_REJECT_WORSE, COUNT };
using Key = std::tuple<int,unsigned,unsigned,int,int,int,int,int,int,int>;
using CGKey = std::tuple<int,unsigned,unsigned,int,int>;
struct Store
{
  std::mutex mutex;
  std::map<Key,std::array<int64_t,COUNT>> rows;
  std::map<CGKey,std::array<int64_t,5>> groups;
  ~Store()
  {
    if (rows.empty()) { return; }
    const char *fields[] = {"positions","nonzero","eligible","winner_disagree","selected_disagree","raw_remap_diff","guard_remap_diff",
      "old_raw_current","current_tie","current_tie_broken","new_winner_from_current_tie","old_accept","new_accept",
      "old_accept_new_reject","old_reject_new_accept","same_winner","same_winner_margin_diff","margin_abs_diff_q15","margin_diff_lt1bit","margin_diff_ge1bit",
      "G_old_q15","G_new_q15","H_old_q15","H_new_q15","r6_region","r6_old_raw_identity","r6_old_raw_nonzero",
      "r6_new_current","r6_new_identity","r6_new_old_winner","r6_new_other",
      "r6_raw_new_current","r6_raw_new_identity","r6_raw_new_old_winner","r6_raw_new_other",
      "cost_pairs","old_delta_abs_error_q15","new_delta_abs_error_q15","old_cost_tie_real_diff","new_cost_tie_real_diff",
      "old_cost_inversion","new_cost_inversion","raw_real_delta_q15","guard_real_delta_q15",
      "raw_actual_better","raw_actual_worse","guard_actual_better","guard_actual_worse",
      "path_oracle_delta_abs_error_q15","path_oracle_cost_inversion","new_identity_guard_rejected",
      "identity_reject_override_delta_q15","identity_reject_override_better","identity_reject_override_worse"};
    static_assert(sizeof(fields)/sizeof(fields[0])==COUNT,"Rate shadow schema mismatch");
    std::fprintf(stderr,"TS_RATE_SHADOW_HEADER component,width,height,cu_qp,support,cutoff,old_raw_kind,new_raw_kind,old_guard_kind,new_guard_kind");
    for (auto f: fields) { std::fprintf(stderr,",%s",f); } std::fprintf(stderr,"\n");
    for (const auto &kv: rows)
    {
      const auto &k=kv.first;
      std::fprintf(stderr,"TS_RATE_SHADOW %d,%u,%u,%d,%d,%d,%d,%d,%d,%d",std::get<0>(k),std::get<1>(k),std::get<2>(k),std::get<3>(k),
        std::get<4>(k),std::get<5>(k),std::get<6>(k),std::get<7>(k),std::get<8>(k),std::get<9>(k));
      for (auto v:kv.second) { std::fprintf(stderr,",%lld",(long long)v); } std::fprintf(stderr,"\n");
    }
    std::fprintf(stderr,"TS_RATE_CG_HEADER component,width,height,cu_qp,cg_count_in_tu,cgs,old_rate_q15,new_raw_rate_q15,new_guard_rate_q15,old_raw_rate_q15\n");
    for (const auto &kv:groups)
    {
      const auto &k=kv.first;
      std::fprintf(stderr,"TS_RATE_CG %d,%u,%u,%d,%d",std::get<0>(k),std::get<1>(k),std::get<2>(k),std::get<3>(k),std::get<4>(k));
      for(auto v:kv.second){ std::fprintf(stderr,",%lld",(long long)v); } std::fprintf(stderr,"\n");
    }
  }
};
inline Store &store() { static Store v; return v; }
inline bool enabled()
{
  static const bool yes = std::getenv("TS_RATE_SHADOW") && std::strcmp(std::getenv("TS_RATE_SHADOW"),"0");
  return yes;
}
inline int kind(int p,int current) { return equivalentPredictors(p,current) ? 0 : p<=1 ? 1 : 2; }
inline int regionKind(int p,const RateDecision &old)
{
  return equivalentPredictors(p,old.current)?0:p<=1?1:equivalentPredictors(p,old.winner)?2:3;
}
inline bool inversion(int64_t a,int64_t b) { return (a<0 && b>0)||(a>0 && b<0); }

inline void observe(const TransformUnit &tu, CompID comp, CoeffCodingContext original,
                    const TCoeff *q, const Ctx &entry, unsigned rice)
{
  CHECK(mode()!=13,"Rate shadow must retain original R3 decisions");
  if (original.bdpcm()!=BdpcmMode::NONE) { return; }
  original.freezeTsRateContext(entry);
  const int first=original.minSubPos(), last=original.maxSubPos(), size=last-first+1;
  std::vector<RateDecision> old(size), now(size);
  std::vector<int> oldp(size),rawp(size),guardp(size),oldrawp(size);
  for(int s=first;s<=last;++s)
  {
    const int i=s-first;
    old[i]=original.ratePredictionTS(s,q,true); now[i]=original.ratePredictionTS(s,q);
    oldp[i]=old[i].predictor; rawp[i]=now[i].winner; guardp[i]=now[i].predictor;
    oldrawp[i]=old[i].winner;
    CHECK(!equivalentPredictors(oldp[i],ratePredictor(original,s,q)),"Old score reconstruction differs from R3");
  }
  RateReplayPath path;
  const auto simulate=[&](const std::vector<int> &p, RateReplayPath *out=nullptr) {
    Ctx copy(entry); auto cc=original; int bins=original.remRegBins;
    FractionalSink sink{static_cast<CtxStore<BinProbModel_Std>&>(copy)};
    auto trace=replayRateCG(cc,q,[&](int s){return p[s-first];},bins,rice,sink);
    if(out){*out=trace;}
    return int64_t(sink.bits);
  };
  const int64_t baseline=simulate(oldp,&path), rawRate=simulate(rawp), guardRate=simulate(guardp);
  // Cross-check independent replay against the native Writer on a deep copy.
  BitEstimator_Std estimator; estimator.getCtx()=entry; estimator.resetBits();
  CABACWriter native(estimator,nullptr); auto check=original; unsigned riceBits[8]{};
  native.residual_coding_subblockTS(check,q,riceBits,rice,false);
  CHECK(int64_t(estimator.getEstFracBits())!=baseline,"Rate replay does not match native CABAC fractional bits");
  auto &output=store(); std::lock_guard<std::mutex> lock(output.mutex);
  auto &cg=output.groups[{int(comp),original.width(),original.height(),tu.cu->qp,original.lastSubSet()+1}];
  ++cg[0]; cg[1]+=baseline; cg[2]+=rawRate; cg[3]+=guardRate; cg[4]+=simulate(oldrawp);
  for(int s=first;s<=last;++s)
  {
    const int i=s-first,a=std::abs(int(q[original.blockPos(s)]));
    const auto &o=old[i]; const auto &v=now[i];
    const int cutoff=s<=path.pass2?10:s<=path.pass1?2:0;
    auto &c=output.rows[{int(comp),original.width(),original.height(),tu.cu->qp,o.n,cutoff,
                        kind(o.winner,o.current),kind(v.winner,o.current),kind(o.predictor,o.current),kind(v.predictor,o.current)}];
    ++c[POS]; c[NZ]+=a!=0;
    if(!a || !cutoff || o.n<3) { continue; } // State explicit denominators; no phantom bypass activity.
    ++c[ELIGIBLE]; c[WINNER_DIFF]+=!equivalentPredictors(o.winner,v.winner);
    c[SELECTED_DIFF]+=!equivalentPredictors(o.predictor,v.predictor);
    c[RAW_MAPPED]+=remap(a,o.winner)!=remap(a,v.winner);
    c[GUARD_MAPPED]+=remap(a,o.predictor)!=remap(a,v.predictor);
    c[OLD_CURRENT]+=!o.proposed();
    bool tie=false, broken=false, winnerFromTie=false;
    for(int k=1;k<o.count;++k)
    {
      CHECK(o.candidates[k]!=v.candidates[k],"Candidate sets must agree");
      if(o.scores[k]==o.currentScore)
      {
        tie=true; broken|=v.scores[k]<v.currentScore;
        winnerFromTie|=!o.proposed() && equivalentPredictors(v.winner,o.candidates[k]);
      }
    }
    c[TIE_CURRENT]+=tie; c[TIE_BROKEN]+=broken; c[WINNER_FROM_TIE]+=winnerFromTie;
    c[OLD_ACCEPT]+=o.accepted(); c[NEW_ACCEPT]+=v.accepted();
    c[ACCEPT_REJECT]+=o.accepted()&&!v.accepted(); c[REJECT_ACCEPT]+=!o.accepted()&&v.accepted();
    c[G_OLD]+=o.gain; c[G_NEW]+=v.gain; c[H_OLD]+=o.margin(); c[H_NEW]+=v.margin();
    if(equivalentPredictors(o.winner,v.winner))
    {
      ++c[SAME_WINNER]; const auto diff=std::abs(o.margin()-v.margin());
      c[MARGIN_DIFF]+=diff!=0; c[MARGIN_ABS]+=diff;
      c[MARGIN_LT1]+=diff>0 && diff<(1<<SCALE_BITS); c[MARGIN_GE1]+=diff>=(1<<SCALE_BITS);
    }
    if(o.proposed() && o.gain>0 && o.margin()<=0)
    {
      ++c[R6_REGION]; ++c[o.winner<=1?R6_RAW_IDENTITY:R6_RAW_NONZERO];
      ++c[R6_NEW_CURRENT+regionKind(v.predictor,o)]; ++c[R6_RAW_NEW_CURRENT+regionKind(v.winner,o)];
    }
    std::vector<int64_t> real(o.count);
    auto changed=oldp;
    for(int k=0;k<o.count;++k)
    {
      changed[i]=o.candidates[k]; real[k]=simulate(changed);
    }
    const auto branch=[&](int p){
      for(int k=0;k<o.count;++k) { if(equivalentPredictors(p,o.candidates[k]))return real[k]; }
      THROW("Missing predictor branch"); return int64_t(0);
    };
    int l,u; original.neighTS(l,u,s,q);
    const auto &table=original.tsRateTable((l!=0)+(u!=0));
    const auto oc=[&](int p){return int64_t(syntaxCost(remap(a,p),rice,original.maxLog2TrDRange()))<<SCALE_BITS;};
    const auto nc=[&](int p){return table.cost(remap(a,p),rice,original.maxLog2TrDRange());};
    // Post-hoc known anchor pass boundary: diagnostic only, NEVER used by selector.
    const auto pc=[&](int p){return table.cost(remap(a,p),rice,original.maxLog2TrDRange(),cutoff);};
    for(int k=1;k<o.count;++k)
    {
      const int p=o.candidates[k]; const auto actual=real[k]-real[0];
      const auto prev=oc(p)-oc(o.current), next=nc(p)-nc(o.current);
      ++c[PAIRS]; c[OLD_ERROR]+=std::abs(prev-actual); c[NEW_ERROR]+=std::abs(next-actual);
      c[OLD_TIE_REAL_DIFF]+=prev==0 && actual!=0; c[NEW_TIE_REAL_DIFF]+=next==0 && actual!=0;
      c[OLD_INVERSION]+=inversion(prev,actual); c[NEW_INVERSION]+=inversion(next,actual);
      const auto pathDelta=pc(p)-pc(o.current);
      c[PATH_ERROR]+=std::abs(pathDelta-actual); c[PATH_INVERSION]+=inversion(pathDelta,actual);
    }
    const auto rawDelta=branch(v.winner)-branch(o.winner), guardDelta=branch(v.predictor)-branch(o.predictor);
    c[RAW_REAL_DELTA]+=rawDelta; c[GUARD_REAL_DELTA]+=guardDelta;
    c[RAW_BETTER]+=rawDelta<0; c[RAW_WORSE]+=rawDelta>0; c[GUARD_BETTER]+=guardDelta<0; c[GUARD_WORSE]+=guardDelta>0;
    if(v.proposed() && v.winner<=1 && v.margin()<=0)
    {
      const auto delta=branch(v.winner)-branch(v.current);
      ++c[NP_REJECT]; c[NP_REJECT_DELTA]+=delta; c[NP_REJECT_BETTER]+=delta<0; c[NP_REJECT_WORSE]+=delta>0;
    }
  }
}
}
