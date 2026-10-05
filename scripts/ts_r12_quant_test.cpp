// Native TS-RDOQ unit test with synthetic residual arrays, not frame coding.
#include "CommonLib/QuantRDOQ.h"
#include "CommonLib/CodingStructure.h"
#include "CommonLib/Rom.h"
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <memory>
#include <random>
#include <vector>

int main()
{
  using namespace TsFixedPrediction;
  CHECK(!r12(mode()) && mode()!=73,"R12 quant test requires R12 or R10-3");
  std::ofstream exactPayload;
  const auto payloadWord=[&](uint64_t value) {
    for(int byte=0;byte<8;++byte) { exactPayload.put(char((value>>(8*byte))&255)); }
  };
  if(const char *path=std::getenv("TS_R12_EXACT_PAYLOAD"))
    if(*path)
    {
      exactPayload.open(path,std::ios::binary|std::ios::trunc);
      CHECK(!exactPayload.is_open(),"Cannot open exact quantization payload");
      exactPayload<<"TSR12QUANTv1\n"; payloadWord(180);
    }
  initROM(); XuPool pool; CodingStructure cs(pool); SPS sps; PPS pps; Slice slice; PicHeader pictureHeader;
  sps.m_chromaFormatIdc=ChromaFormat::_420; sps.m_maxCuWidth=sps.m_maxCuHeight=64;
  sps.m_bitDepths[ChannelType::LUMA]=sps.m_bitDepths[ChannelType::CHROMA]=10;
  // Synthetic fixture: valid identity chroma QP mapping, not a CTC SPS claim.
  for(auto &table:sps.m_chromaQpMappingTable.m_chromaQpMappingTables)
    for(int qp=0;qp<=MAX_QP;++qp) { table[qp]=qp; }
  pps.m_picWidthInLumaSamples=pps.m_picHeightInLumaSamples=64;
  PreCalcValues pcv(sps,pps,true); cs.sps=&sps; cs.pps=&pps; cs.pcv=&pcv; cs.slice=&slice;
  slice.m_sps=&sps; slice.m_pps=&pps; slice.m_picHeader=&pictureHeader; cs.picHeader=&pictureHeader;
  auto storage=std::make_unique<QuantRDOQ>(nullptr); auto &quant=*storage;
  quant.init(64,true,true,false); quant.setUseScalingList(false);
  const int ranges[]={sps.getMaxLog2TrDynamicRange(ChannelType::LUMA),sps.getMaxLog2TrDynamicRange(ChannelType::CHROMA)};
  quant.setFlatScalingList(ranges,sps.m_bitDepths);
  std::mt19937 rng(12102026); uint64_t digest=1469598103934665603ULL,zero=0,cleared=0;
  for(int trial=0;trial<180;++trial)
  {
    const int w=1<<(2+trial%4),h=1<<(2+(trial/4)%4); const CompID comp=CompID(trial%3);
    CodingUnit cu(ChromaFormat::_420,Area(0,0,w,h)); TransformUnit tu(static_cast<const UnitArea&>(cu));
    cu.cs=&cs; cu.slice=&slice; cu.qp=10+trial%38; cu.predMode=trial%2?MODE_INTRA:MODE_INTER;
    slice.m_eSliceType=trial%2?I_SLICE:P_SLICE; tu.cs=&cs; tu.cu=&cu; tu.mtsIdx[comp]=MtsType::SKIP;
    std::vector<TCoeff> y(w*h),cb(w*h/4),cr(w*h/4),src(tu.blocks[comp].area());
    std::vector<uint8_t> sy(y.size()),sb(cb.size()),sr(cr.size());
    TCoeff *coeff[]={y.data(),cb.data(),cr.data()}; uint8_t *signs[]={sy.data(),sb.data(),sr.data()};
    EnumArray<Pel*,ChannelType> plt{}; EnumArray<bool*,ChannelType> run{}; tu.init(coeff,signs,plt,run);
    auto &q=comp==COMP_Y?y:comp==COMP_Cb?cb:cr; QpParam qp(tu,comp);
    Ctx ctx(static_cast<const BinProbModel_Std*>(nullptr)); ctx.init(cu.qp,slice.m_eSliceType);
    std::vector<uint64_t> ctxBits;
    const auto &store=static_cast<const CtxStore<BinProbModel_Std>&>(ctx);
    for(unsigned i=0;i<ContextSetCfg::NumberOfContexts;++i)
    { ctxBits.push_back(store[i].estFracBits(0)); ctxBits.push_back(store[i].estFracBits(1)); }
    quant.setLambda(double(1u<<(trial%12)));
    for(auto &v:src) { v=trial%13==0?0:trial%13==1?1:int(rng()%511)-255; }
    const auto original=src; TCoeff sum=0;
    const auto call=[&]() { sum=0; quant.quant(tu,comp,CCoeffBuf(src.data(),tu.blocks[comp]),sum,qp,ctx); };
    call(); const auto expected=q; const auto expectedSum=sum;
    CHECK(src!=original,"Quantization changed source");
    if(trial%13==0) { CHECK(sum!=0,"Zero early exit failed"); ++zero; }
    if(!sum && trial%13) { ++cleared; }
    for(auto v:q) { digest=(digest^uint64_t(int64_t(v)))*1099511628211ULL; }
    // Poison the output, explore another residual branch, then return to original.
    std::fill(q.begin(),q.end(),123); std::fill(src.begin(),src.end(),0); call();
    CHECK(sum!=0,"Cleared input branch failed"); src=original; call();
    CHECK(q!=expected || sum!=expectedSum,"TS-RDOQ branch state leaked");
    if(exactPayload.is_open())
    {
      for(uint64_t value:{uint64_t(trial),uint64_t(tu.blocks[comp].width),uint64_t(tu.blocks[comp].height),
                         uint64_t(comp),uint64_t(cu.qp),uint64_t(q.size()),uint64_t(int64_t(sum))})
        payloadWord(value);
      for(auto value:q) { payloadWord(uint64_t(int64_t(value))); }
      CHECK(!exactPayload.good(),"Cannot write exact quantization payload");
    }
    for(unsigned i=0;i<ContextSetCfg::NumberOfContexts;++i)
      CHECK(store[i].estFracBits(0)!=ctxBits[2*i] || store[i].estFracBits(1)!=ctxBits[2*i+1],"Real CABAC state changed");
  }
  CHECK(!cleared,"Missing quantized all-zero coverage");
  if(exactPayload.is_open()) { exactPayload.close(); CHECK(exactPayload.fail(),"Cannot close exact quantization payload"); }
  destroyROM(); std::cout<<"PASS "<<name()<<" synthetic TS-RDOQ trials=180 zero="<<zero<<" cleared="<<cleared<<" digest="<<digest<<'\n';
}
