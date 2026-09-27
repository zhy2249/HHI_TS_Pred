// R9 native fixed-q proposal/injection test; artificial states, NOT CTC evidence.
#include "CommonLib/QuantRDOQ.h"
#include "CommonLib/TsR9Quant.h"
#include "CommonLib/CodingStructure.h"
#include "CommonLib/Rom.h"
#include <iostream>
#include <memory>
#include <random>
#include <vector>

int main()
{
#if JVET_BJUT_TS_FIXED_PREDICTOR
  using namespace TsFixedPrediction;
  CHECK(!r9Quant(mode()),"Run with r9_quant_down or r9_quant_down_up");
  initROM();
  XuPool pool; CodingStructure cs(pool); SPS sps; PPS pps; Slice slice;
  sps.m_chromaFormatIdc=ChromaFormat::_420; sps.m_maxCuWidth=sps.m_maxCuHeight=64;
  sps.m_bitDepths[ChannelType::LUMA]=sps.m_bitDepths[ChannelType::CHROMA]=10;
  pps.m_picWidthInLumaSamples=pps.m_picHeightInLumaSamples=64;
  PreCalcValues pcv(sps,pps,true);
  cs.sps=&sps; cs.pps=&pps; cs.pcv=&pcv; cs.slice=&slice;
  slice.m_sps=&sps; slice.m_pps=&pps; slice.m_eSliceType=I_SLICE;
  CodingUnit cu(ChromaFormat::_420,Area(0,0,8,8));
  cu.cs=&cs; cu.slice=&slice; cu.predMode=MODE_INTRA;
  TransformUnit tu(static_cast<const UnitArea&>(cu)); tu.cs=&cs; tu.cu=&cu;
  std::vector<TCoeff> q(64),cb(16),cr(16),src(64);
  std::vector<uint8_t> sy(64),sb(16),sr(16);
  TCoeff *coeff[]={q.data(),cb.data(),cr.data()};
  uint8_t *signs[]={sy.data(),sb.data(),sr.data()};
  EnumArray<Pel*,ChannelType> plt{}; EnumArray<bool*,ChannelType> run{};
  tu.init(coeff,signs,plt,run); tu.mtsIdx[COMP_Y]=MtsType::SKIP;
  auto quantStorage=std::make_unique<QuantRDOQ>(nullptr);
  auto &quant=*quantStorage; quant.init(64,true,true,false); quant.setUseScalingList(false);
  const int ranges[]={sps.getMaxLog2TrDynamicRange(ChannelType::LUMA),sps.getMaxLog2TrDynamicRange(ChannelType::CHROMA)};
  quant.setFlatScalingList(ranges,sps.m_bitDepths);
  std::mt19937 rng(20260926);
  uint64_t down=0,up=0,rejected=0,hash=1469598103934665603ULL;
  for(int trialNo=0;trialNo<256;++trialNo)
  {
    cu.qp=10+trialNo%28; QpParam qp(tu,COMP_Y);
    Ctx ctx(static_cast<const BinProbModel_Std*>(nullptr)); ctx.init(cu.qp,I_SLICE);
    quant.setLambda(double(1u<<(trialNo%12)));
    for(auto &v:src) { v=trialNo%17==0?0:int(rng()%511)-255; }
    if(trialNo%17==1) { std::fill(src.begin(),src.end(),1); }
    if(trialNo%17==2) { std::fill(src.begin(),src.end(),0); src[0]=8; }
    const auto input=src;
    R9QuantTrial trial; trial.component=int(COMP_Y); tu.tsR9Trial=&trial;
    TCoeff sum=0; quant.quant(tu,COMP_Y,CCoeffBuf(src.data(),tu.Y()),sum,qp,ctx);
    CHECK(!trial.captured || trial.q0!=q,"R9 missing baseline");
    const auto q0=q;
    for(int v:q0) { hash=(hash^uint64_t(int64_t(v)))*1099511628211ULL; }
    for(int t=0;t<2;++t)
    {
      rejected+=trial.cbfRejected[t];
      hash=(hash^uint64_t(trial.pos[t]+1))*1099511628211ULL;
      hash=(hash^uint64_t(int64_t(trial.value[t])))*1099511628211ULL;
      if(trial.pos[t]<0) { continue; }
      trial.phase=t+1; trial.injected=false; sum=0;
      quant.quant(tu,COMP_Y,CCoeffBuf(src.data(),tu.Y()),sum,qp,ctx);
      CHECK(!trial.injected || src!=input,"R9 injection failed or changed input");
      auto expected=q0; expected[trial.pos[t]]=trial.value[t];
      CHECK(q!=expected || sum==0,"R9 proposal is not an independent fixed-CBF edit");
      if(t==0) { ++down; CHECK(std::abs(q0[trial.pos[t]])!=1 || q[trial.pos[t]]!=0,"Invalid D"); }
      else { ++up; CHECK(q0[trial.pos[t]]!=0 || q[trial.pos[t]]!=(src[trial.pos[t]]<0?-1:1),"Invalid U"); }
    }
    trial.phase=3; sum=0;
    quant.quant(tu,COMP_Y,CCoeffBuf(src.data(),tu.Y()),sum,qp,ctx);
    CHECK(q!=q0,"R9 baseline replay changed");
    tu.tsR9Trial=nullptr; sum=0;
    quant.quant(tu,COMP_Y,CCoeffBuf(src.data(),tu.Y()),sum,qp,ctx);
    CHECK(q!=q0,"R9 request leaked into ordinary quantization");
  }
  CHECK(!down || !up,"R9 native quant coverage missing");
  CHECK(!rejected,"Missing CBF rejection coverage");
  std::cout<<"PASS "<<name()<<" trials=256 down="<<down<<" up="<<up<<" cbf_reject="<<rejected<<" proposal_hash="<<hash<<'\n';
  destroyROM();
#else
  std::cerr<<"Requires TS predictor master ON\n";
  return 1;
#endif
}
