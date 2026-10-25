// Opt-in, single-TU forensic replay. Never changes q, the live CABAC state,
// predictor policy, or encoder decisions. Scores168 are NOT fractional bits.
#pragma once
#include "CodingStructure.h"
#include "Contexts.h"
#if JVET_BJUT_TS_FIXED_PREDICTOR
#include "TsRateReplay.h"
#include "TsR13Prediction.h"
#include <array>
#include <cstdlib>
#include <fstream>
#include <string>
#include <vector>

namespace TsR13PredDetail
{
inline bool enabled()
{
  static const bool active=[] {
    const char *path=std::getenv("TS_R13_PRED_DETAIL");
    return path && *path;
  }();
  return active;
}

inline void requireEqualContext(const Ctx &a,const Ctx &b)
{
  const auto &x=static_cast<const CtxStore<BinProbModel_Std>&>(a);
  const auto &y=static_cast<const CtxStore<BinProbModel_Std>&>(b);
  for(unsigned i=0;i<ContextSetCfg::NumberOfContexts;++i)
  {
    CHECK(x[i].getState()!=y[i].getState() || x[i].getWinSizes()!=y[i].getWinSizes() ||
          x[i].getAdaptRateWeight()!=y[i].getAdaptRateWeight(),"R13 detail replay context mismatch");
    for(int bin=0;bin<2;++bin)
      CHECK(x[i].estFracBits(bin)!=y[i].estFracBits(bin) ||
            x[i].getAdaptRateOffset(bin)!=y[i].getAdaptRateOffset(bin),"R13 detail replay probability mismatch");
  }
}

struct Coefficient
{
  int h[5]{};
  unsigned available=0;
  int predictor[3]{};
  TsFixedPrediction::R13Decision decision[2];
  uint64_t bits[3][3]{};
  int pass1[3]{-1,-1,-1},pass2[3]{-1,-1,-1};
};

struct Sink
{
  CtxStore<BinProbModel_Std> &context;
  std::ofstream &file;
  std::vector<Coefficient> &coeff;
  const char *name;
  int branch,cg;
  uint64_t total=0;
  void bin(int scan,int pass,const char *syntax,unsigned value,unsigned id,int budget)
  {
    auto &ctx=context[id];
    const auto state=ctx.getState();
    const auto f0=ctx.estFracBits(0),f1=ctx.estFracBits(1);
    const uint64_t before=total;
    ctx.estFracBitsUpdate(value,total);
    const uint64_t cost=total-before;
    if(scan>=0) { coeff[scan].bits[branch][pass-1]+=cost; }
    file<<name<<','<<cg<<','<<scan<<','<<pass<<','<<syntax<<','<<value<<','<<id<<','
        <<state.first<<','<<state.second<<','<<f0<<','<<f1<<','<<cost<<','<<total<<','<<budget<<",1\n";
  }
  void bypass(int scan,const char *syntax,unsigned value,unsigned length,int budget)
  {
    const uint64_t cost=BinProbModelBase::estFracBitsEP(length);
    total+=cost; coeff[scan].bits[branch][2]+=cost;
    file<<name<<','<<cg<<','<<scan<<",3,"<<syntax<<','<<value<<",-1,-1,-1,32768,32768,"
        <<cost<<','<<total<<','<<budget<<','<<length<<'\n';
  }
};

// Same three-pass syntax as CABACWriter::residual_coding_subblockTS, with
// labels only. Each CG is also checked against the independent replayRateCG.
inline TsFixedPrediction::RateReplayPath traceCG(CoeffCodingContext &cctx,const TCoeff *q,
                                                int branch,int &budget,unsigned rice,Sink &sink)
{
  using namespace TsFixedPrediction;
  RateReplayPath path;
  const int first=cctx.minSubPos(),last=cctx.maxSubPos();
  if(!cctx.isLastSubSet() || !cctx.only1stSigGroup())
  {
    sink.bin(-1,0,"sig_group",cctx.isSigGroup(),cctx.sigGroupCtxId(true),budget);
    if(!cctx.isSigGroup()) { return path; }
  }
  const auto level=[&](int s,bool regular=true) {
    const int a=std::abs(int(q[cctx.blockPos(s)]));
    return !regular || cctx.bdpcm()!=BdpcmMode::NONE ? a : remap(a,sink.coeff[s].predictor[branch]);
  };
  int nonzero=0;
  for(int s=first;s<=last && budget>=4;++s)
  {
    const int v=q[cctx.blockPos(s)];
    if(nonzero || s!=last) { sink.bin(s,1,"sig",v!=0,cctx.sigCtxIdAbsTS(s,q),budget); --budget; }
    if(v)
    {
      ++nonzero;
      sink.bin(s,1,"sign",v<0,cctx.signCtxIdAbsTS(s,q,cctx.bdpcm()),budget); --budget;
      const int a=level(s);
      sink.bin(s,1,"gt1",a>1,cctx.lrg1CtxIdAbsTS(s,q,cctx.bdpcm()),budget); --budget;
      if(a>1) { sink.bin(s,1,"parity",(a-2)&1,cctx.parityCtxIdAbsTS(),budget); --budget; }
    }
    path.pass1=s;
  }
  for(int s=first;s<=last && budget>=4;++s)
  {
    const int a=level(s);
    const char *names[4]={"gt2","gt4","gt6","gt8"};
    for(int c=2;c<=8;c+=2)
      if(a>=c) { sink.bin(s,2,names[c/2-1],a>=c+2,cctx.greaterXCtxIdAbsTS(c/2),budget); --budget; }
    path.pass2=s;
  }
  for(int s=first;s<=last;++s)
  {
    const int cutoff=s<=path.pass2?10:s<=path.pass1?2:0;
    const int a=level(s,cutoff!=0);
    if(a>=cutoff)
    {
      const unsigned remainder=s<=path.pass1?(a-cutoff)>>1:a;
      sink.bypass(s,"remainder",remainder,riceLength(remainder,rice,cctx.maxLog2TrDRange()),budget);
      if(a && s>path.pass1) { sink.bypass(s,"sign_ep",q[cctx.blockPos(s)]<0,1,budget); }
    }
  }
  return path;
}

// Call once, immediately after the native residual_coding_coef() for a selected
// TS trial. entry is its pre-call context, nativeFracBits its exact bit delta.
// Prefix directory must already exist; callers own the narrow trial filter.
inline void observe(const TransformUnit &tu,CompID component,const Ctx &entry,uint64_t nativeFracBits)
{
  using namespace TsFixedPrediction;
  const char *prefix=std::getenv("TS_R13_PRED_DETAIL");
  if(!prefix || !*prefix) { return; }
  CHECK(tu.mtsIdx[component]!=MtsType::SKIP,"R13 detail requires a TS trial");
  const std::string root(prefix);
  std::ofstream coefficients(root+"_coeff.csv"),candidates(root+"_candidates.csv"),bins(root+"_bins.csv"),summary(root+"_summary.csv");
  CHECK(!coefficients || !candidates || !bins || !summary,"Cannot open R13 predictor detail output");
  coefficients<<"scan,cg,raster,x,y,q,abs_q,available_mask,L,U,D,LL,UU,n,branch,weight_sum,scored,tied,predictor,regular_remap,regular_active,actual_coding_level,cutoff,pass1_last,pass2_last,pass1_frac,pass2_frac,bypass_frac,total_frac\n";
  candidates<<"scan,branch,n,weight_sum,candidate_order,candidate,selected,total_score168,slot,slot_magnitude,slot_weight,base_syntax_cost,raised_syntax_cost,loss168,weighted_loss168\n";
  bins<<"branch,cg,scan,pass,syntax,value,ctx_id,state0,state1,frac0,frac1,cost_frac,cumulative_frac,regular_budget_before,bypass_length\n";
  summary<<"kind,branch,cg,poc,component,x,y,width,height,rice,range,first_scan,last_scan,significant,entry_budget,end_budget,pass1_last,pass2_last,rate_frac,native_frac,validated\n";
  CoeffCodingContext geometry(tu,component,false,tu.cu->bdpcmMode[isLuma(component)?0:1]);
  const auto &area=tu.blocks[component];
  const TCoeff *q=tu.getCoeffs(component).buf;
  const int count=geometry.maxNumCoeff(),initialBudget=(count*7)>>2;
  const unsigned rice=1+(tu.cu->slice->m_sps->m_spsRangeExtension.m_tsrcRicePresentFlag?tu.cu->slice->m_tsrcIndex:0);
  const int range=geometry.maxLog2TrDRange();
  const char *names[3]={"current","eq","sp"};
  // Save inputs before validation, allowing offline diagnosis without another
  // encoder run even if a future change makes a replay assertion fail.
  {
    std::ofstream input(root+"_input_q.csv"),snapshot(root+"_entry_context.csv");
    CHECK(!input || !snapshot,"Cannot save R13 detail replay inputs");
    input<<"scan,raster,q\n";
    for(int s=0;s<count;++s) { input<<s<<','<<geometry.blockPos(s)<<','<<q[geometry.blockPos(s)]<<'\n'; }
    snapshot<<"ctx_id,state0,state1,windows,weight,offset0,offset1,frac0,frac1\n";
    const auto &store=static_cast<const CtxStore<BinProbModel_Std>&>(entry);
    for(unsigned i=0;i<ContextSetCfg::NumberOfContexts;++i)
    {
      const auto &c=store[i]; const auto state=c.getState();
      snapshot<<i<<','<<state.first<<','<<state.second<<','<<unsigned(c.getWinSizes())<<','<<unsigned(c.getAdaptRateWeight())
              <<','<<unsigned(c.getAdaptRateOffset(0))<<','<<unsigned(c.getAdaptRateOffset(1))
              <<','<<c.estFracBits(0)<<','<<c.estFracBits(1)<<'\n';
    }
    input.close(); snapshot.close();
    CHECK(!input || !snapshot,"R13 detail replay input write failed");
  }
  std::vector<Coefficient> values(count);
  std::bitset<MLS_GRP_NUM> sigGroups;
  for(int s=0;s<count;++s)
  {
    auto &v=values[s];
    v.available=geometry.r13SupportTS(s,q,v.h);
    v.predictor[0]=std::max(v.h[0],v.h[1]);
    for(int m=1;m<=2;++m)
    {
      const auto d=r13Decision(m,v.h,rice,range); v.decision[m-1]=d; v.predictor[m]=d.predictor;
      for(int c=0;c<d.candidateCount;++c)
        for(int j=0;j<5;++j) if(v.h[j])
        {
          const int p=d.candidates[c],a=v.h[j],weight=m==2 && j<2?2:1;
          const int base=syntaxCost(unsigned(a),rice,range),raised=syntaxCost(unsigned(a)+1u,rice,range);
          const int64_t loss=r13Loss168(a,p,rice,range);
          candidates<<s<<','<<names[m]<<','<<d.n<<','<<d.weightSum<<','<<c<<','<<p<<','<<(p==d.predictor)
                    <<','<<d.scores[c]<<','<<j<<','<<a<<','<<weight<<','<<base<<','<<raised<<','<<loss<<','<<weight*loss<<'\n';
        }
    }
    if(q[geometry.blockPos(s)]) { sigGroups.set(s>>geometry.log2CGSize()); }
  }
  uint64_t totals[3]{};
  for(int m=0;m<3;++m)
  {
    Ctx branchContext(entry);
    auto contextGeometry=geometry;
    int budget=initialBudget;
    Sink sink{static_cast<CtxStore<BinProbModel_Std>&>(branchContext),bins,values,names[m],m,0};
    for(int cg=0;cg<=geometry.lastSubSet();++cg)
    {
      contextGeometry.initSubblock(cg,sigGroups[cg]); sink.cg=cg;
      const int beforeBudget=budget;
      const uint64_t before=sink.total;
      Ctx referenceContext(branchContext); auto referenceGeometry=contextGeometry;
      int referenceBudget=budget;
      FractionalSink reference{static_cast<CtxStore<BinProbModel_Std>&>(referenceContext)};
      const auto expected=replayRateCG(referenceGeometry,q,[&](int s){return values[s].predictor[m];},referenceBudget,rice,reference);
      const auto path=traceCG(contextGeometry,q,m,budget,rice,sink);
      CHECK(reference.bits!=sink.total-before || referenceBudget!=budget || expected.pass1!=path.pass1 || expected.pass2!=path.pass2,
            "R13 labeled replay differs from reference replay");
      requireEqualContext(referenceContext,branchContext);
      for(int s=contextGeometry.minSubPos();s<=contextGeometry.maxSubPos();++s)
        { values[s].pass1[m]=path.pass1; values[s].pass2[m]=path.pass2; }
      summary<<"CG,"<<names[m]<<','<<cg<<','<<tu.cu->slice->m_poc<<','<<int(component)<<','<<area.x<<','<<area.y<<','
             <<area.width<<','<<area.height<<','<<rice<<','<<range<<','<<contextGeometry.minSubPos()<<','<<contextGeometry.maxSubPos()
             <<','<<sigGroups[cg]<<','<<beforeBudget<<','<<budget<<','<<path.pass1<<','<<path.pass2<<','<<sink.total-before<<",,1\n";
    }
    totals[m]=sink.total;
    const bool native=(mode()==1 && m==0) || (mode()==98 && m==1) || (mode()==99 && m==2);
    if(native) { CHECK(sink.total!=nativeFracBits,"R13 detail does not match native TS estimator"); }
    summary<<"TU,"<<names[m]<<",-1,"<<tu.cu->slice->m_poc<<','<<int(component)<<','<<area.x<<','<<area.y<<','
           <<area.width<<','<<area.height<<','<<rice<<','<<range<<",0,"<<count-1<<",,"<<initialBudget<<','<<budget
           <<",,,"<<sink.total<<','<<nativeFracBits<<','<<native<<'\n';
  }
  for(int s=0;s<count;++s)
  {
    const auto &v=values[s]; const int raster=geometry.blockPos(s),a=std::abs(int(q[raster]));
    int n=0; for(int h:v.h) { n+=h!=0; }
    for(int m=0;m<3;++m)
    {
      const int cutoff=s<=v.pass2[m]?10:s<=v.pass1[m]?2:0;
      const bool active=cutoff!=0 && geometry.bdpcm()==BdpcmMode::NONE;
      const int mapped=remap(a,v.predictor[m]);
      coefficients<<s<<','<<(s>>geometry.log2CGSize())<<','<<raster<<','<<raster%area.width<<','<<raster/area.width<<','
                  <<q[raster]<<','<<a<<','<<v.available;
      for(int h:v.h) { coefficients<<','<<h; }
      coefficients<<','<<n<<','<<names[m]<<','<<(m?v.decision[m-1].weightSum:n)<<','<<(m?v.decision[m-1].scored:false)
                  <<','<<(m?v.decision[m-1].tiedBest:false)<<','<<v.predictor[m]<<','<<mapped<<','<<active<<','<<(active?mapped:a)
                  <<','<<cutoff<<','<<v.pass1[m]<<','<<v.pass2[m]<<','<<v.bits[m][0]<<','<<v.bits[m][1]<<','<<v.bits[m][2]
                  <<','<<v.bits[m][0]+v.bits[m][1]+v.bits[m][2]<<'\n';
    }
  }
  coefficients.close(); candidates.close(); bins.close(); summary.close();
  CHECK(!coefficients || !candidates || !bins || !summary,"R13 predictor detail write failed");
  std::fprintf(stderr,"TS_R13_PRED_DETAIL poc=%d component=%d x=%d y=%d width=%u height=%u current_frac=%llu eq_frac=%llu sp_frac=%llu sp_minus_eq_frac=%lld native_frac=%llu prefix=%s\n",
    tu.cu->slice->m_poc,int(component),area.x,area.y,area.width,area.height,
    (unsigned long long)totals[0],(unsigned long long)totals[1],(unsigned long long)totals[2],
    (long long)(int64_t(totals[2])-int64_t(totals[1])),(unsigned long long)nativeFracBits,prefix);
}
}
#else
namespace TsR13PredDetail
{
inline bool enabled() { return false; }
inline void observe(const TransformUnit &,CompID,const Ctx &,uint64_t) {}
}
#endif
