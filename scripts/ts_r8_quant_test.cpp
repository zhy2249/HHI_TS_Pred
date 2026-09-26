// Artificial probability/input stress test: proves extended up is really
// evaluated by native TS-RDOQ. NOT evidence of CTC reachability or RD gain.
#include "CommonLib/QuantRDOQ.h"
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
  CHECK(!r8DualQuant(mode()),"Run with r8_r3_dual_quant or r8_raw_dual_quant");
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
  uint64_t extra=0,changed=0,zero=0;
  for(int trial=0;trial<512;++trial)
  {
    cu.qp=10+trial%28; QpParam qp(tu,COMP_Y);
    Ctx ctx(static_cast<const BinProbModel_Std*>(nullptr)); ctx.init(cu.qp,I_SLICE);
    CoeffCodingContext coding(tu,COMP_Y,false,BdpcmMode::NONE);
    // Valid representable probability states, not claimed naturally reached.
    auto &store=static_cast<CtxStore<BinProbModel_Std>&>(ctx);
    store[coding.parityCtxIdAbsTS()].setState({uint16_t(trial%2?32000:768),uint16_t(trial%2?32000:768)});
    quant.setLambda(double(1u<<(trial%12)));
    for(auto &v:src) { v=trial%17==0?0:int(rng()%511)-255; }
    const auto input=src;
    TCoeff sum=0;
    tu.tsR8ExtendedSearch=false; tu.tsR8ExtraCandidates=0;
    quant.quant(tu,COMP_Y,CCoeffBuf(src.data(),tu.Y()),sum,qp,ctx);
    const auto q0=q;
    std::fill(q.begin(),q.end(),0); sum=0;
    tu.tsR8ExtendedSearch=true;
    quant.quant(tu,COMP_Y,CCoeffBuf(src.data(),tu.Y()),sum,qp,ctx);
    extra+=tu.tsR8ExtraCandidates; changed+=q!=q0;
    CHECK(src!=input,"R8 quantization modified input");
    if(trial%17==0) { CHECK(sum!=0 || q!=q0,"Zero early exit changed"); ++zero; }
    const auto q1=q;
    tu.tsR8ExtendedSearch=false; sum=0;
    quant.quant(tu,COMP_Y,CCoeffBuf(src.data(),tu.Y()),sum,qp,ctx);
    CHECK(q!=q0,"Quantizer state leaked from extended to native branch");
    sum=0; tu.tsR8ExtendedSearch=true;
    quant.quant(tu,COMP_Y,CCoeffBuf(src.data(),tu.Y()),sum,qp,ctx);
    CHECK(q!=q1,"Extended branch is not repeatable");
  }
  CHECK(!extra || !changed,"Stress test failed to exercise additional candidate selection");
  std::cout<<"PASS "<<name()<<" native quant trials=512 extra_up="<<extra<<" changed="<<changed<<" zero="<<zero<<'\n';
  destroyROM();
#else
  std::cerr<<"Requires TS predictor master ON\n";
  return 1;
#endif
}
