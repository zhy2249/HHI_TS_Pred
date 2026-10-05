// Native synthetic TS-RDOQ and BDPCM quantization; never frame/video coding.
#include "CommonLib/QuantRDOQ.h"
#include "CommonLib/CodingStructure.h"
#include "CommonLib/Rom.h"
#include <cerrno>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <memory>
#include <random>
#include <vector>

int main()
{
  using namespace TsFixedPrediction;
  CHECK(mode()!=1 && !r3(mode()) && !r6(mode()),"R36 quant test requires Current/R3/R6");
  constexpr unsigned trials=240;
  unsigned repeats=1;
  if(const char *value=std::getenv("TS_R36_BENCH_REPEAT"))
  {
    char *end=nullptr; errno=0;
    const unsigned long parsed=std::strtoul(value,&end,10);
    CHECK(errno || end==value || *end || parsed<1 || parsed>1000,
          "TS_R36_BENCH_REPEAT must be an integer in [1,1000]");
    repeats=unsigned(parsed);
  }
  std::ofstream payload;
  const auto word=[&](uint64_t value) {
    for(int byte=0;byte<8;++byte) { payload.put(char((value>>(8*byte))&255)); }
  };
  if(const char *path=std::getenv("TS_R36_EXACT_PAYLOAD"))
    if(*path)
    {
      CHECK(repeats!=1,"Repeated benchmark must not write an exact-validation payload");
      payload.open(path,std::ios::binary|std::ios::trunc);
      CHECK(!payload.is_open(),"Cannot open exact quantization payload");
      payload<<"TSR36QUANTv1\n"; word(trials);
    }
  initROM(); XuPool pool; CodingStructure cs(pool); SPS sps; PPS pps; Slice slice; PicHeader pictureHeader;
  sps.m_chromaFormatIdc=ChromaFormat::_420; sps.m_maxCuWidth=sps.m_maxCuHeight=64;
  sps.m_bitDepths[ChannelType::LUMA]=sps.m_bitDepths[ChannelType::CHROMA]=10;
  // Fixture identity QP mapping, not a claim about CTC SPS parameters.
  for(auto &table:sps.m_chromaQpMappingTable.m_chromaQpMappingTables)
    for(int qp=0;qp<=MAX_QP;++qp) { table[qp]=qp; }
  pps.m_picWidthInLumaSamples=pps.m_picHeightInLumaSamples=64;
  PreCalcValues pcv(sps,pps,true); cs.sps=&sps; cs.pps=&pps; cs.pcv=&pcv; cs.slice=&slice;
  slice.m_sps=&sps; slice.m_pps=&pps; slice.m_picHeader=&pictureHeader; cs.picHeader=&pictureHeader;
  auto storage=std::make_unique<QuantRDOQ>(nullptr); auto &quant=*storage;
  quant.init(64,true,true,false); quant.setUseScalingList(false);
  const int ranges[]={sps.getMaxLog2TrDynamicRange(ChannelType::LUMA),sps.getMaxLog2TrDynamicRange(ChannelType::CHROMA)};
  quant.setFlatScalingList(ranges,sps.m_bitDepths);
  std::mt19937 rng(4102026); uint64_t digest=1469598103934665603ULL,zero=0,cleared=0,bdpcmTrials[3]{};
  for(unsigned repeat=0;repeat<repeats;++repeat)
  {
  // Each benchmark repeat visits precisely the same 240 input fixtures. Keep
  // the default one-repeat validation output and payload exactly unchanged.
  rng.seed(4102026);
  for(unsigned trial=0;trial<trials;++trial)
  {
    const int w=1<<(2+trial%4),h=1<<(2+(trial/4)%4); const CompID comp=CompID(trial%3);
    CodingUnit cu(ChromaFormat::_420,Area(0,0,w,h)); TransformUnit tu(static_cast<const UnitArea&>(cu));
    const auto bdpcm=trial%8==6?BdpcmMode::HOR:trial%8==7?BdpcmMode::VER:BdpcmMode::NONE;
    ++bdpcmTrials[int(bdpcm)];
    cu.cs=&cs; cu.slice=&slice; cu.qp=10+trial%38;
    cu.predMode=bdpcm!=BdpcmMode::NONE || trial%2?MODE_INTRA:MODE_INTER;
    cu.bdpcmMode[0]=cu.bdpcmMode[1]=bdpcm;
    slice.m_eSliceType=cu.predMode==MODE_INTRA?I_SLICE:P_SLICE;
    sps.m_spsRangeExtension.m_tsrcRicePresentFlag=true; slice.m_tsrcIndex=trial%8;
    tu.cs=&cs; tu.cu=&cu; tu.mtsIdx[comp]=MtsType::SKIP;
    std::vector<TCoeff> y(w*h),cb(w*h/4),cr(w*h/4),src(tu.blocks[comp].area());
    std::vector<uint8_t> sy(y.size()),sb(cb.size()),sr(cr.size());
    TCoeff *coeff[]={y.data(),cb.data(),cr.data()}; uint8_t *signs[]={sy.data(),sb.data(),sr.data()};
    EnumArray<Pel*,ChannelType> plt{}; EnumArray<bool*,ChannelType> run{}; tu.init(coeff,signs,plt,run);
    auto &q=comp==COMP_Y?y:comp==COMP_Cb?cb:cr; QpParam qp(tu,comp);
    Ctx ctx(static_cast<const BinProbModel_Std*>(nullptr)); ctx.init(cu.qp,slice.m_eSliceType);
    const Ctx untouched(ctx);
    const auto &before=static_cast<const CtxStore<BinProbModel_Std>&>(untouched);
    const auto &after=static_cast<const CtxStore<BinProbModel_Std>&>(ctx);
    quant.setLambda(double(1u<<(trial%12)));
    for(unsigned i=0;i<src.size();++i)
    {
      const int raw=int(rng()%511)-255;
      src[i]=trial%13==0?0:trial%13==1?1:trial%13==2?(i%7?0:raw):
        trial%13==3?(i%5==0?-7:7):raw;
    }
    const auto original=src; TCoeff sum=0;
    const auto call=[&]() { sum=0; quant.quant(tu,comp,CCoeffBuf(src.data(),tu.blocks[comp]),sum,qp,ctx); };
    call(); const auto expected=q; const auto expectedSum=sum;
    CHECK(src!=original,"Quantization changed source");
    if(trial%13==0) { CHECK(sum!=0,"Zero early exit failed"); ++zero; }
    if(!sum && trial%13) { ++cleared; }
    for(auto v:q) { digest=(digest^uint64_t(int64_t(v)))*1099511628211ULL; }
    // Revisit the identical input after a different all-zero branch and poisoned
    // output. No coefficient cache or diagnostic history may leak across trials.
    std::fill(q.begin(),q.end(),123); std::fill(src.begin(),src.end(),0); call();
    CHECK(sum!=0,"Cleared input branch failed"); src=original; call();
    CHECK(q!=expected || sum!=expectedSum,"TS-RDOQ branch state leaked");
    if(payload.is_open())
    {
      for(uint64_t value:{uint64_t(trial),uint64_t(tu.blocks[comp].width),uint64_t(tu.blocks[comp].height),
                         uint64_t(comp),uint64_t(cu.qp),uint64_t(bdpcm),uint64_t(q.size()),uint64_t(int64_t(sum))})
        word(value);
      for(auto value:q) { word(uint64_t(int64_t(value))); }
      CHECK(!payload.good(),"Cannot write exact quantization payload");
    }
    for(unsigned i=0;i<ContextSetCfg::NumberOfContexts;++i)
    {
      CHECK(before[i].getState()!=after[i].getState() || before[i].getWinSizes()!=after[i].getWinSizes() ||
            before[i].getAdaptRateWeight()!=after[i].getAdaptRateWeight(),"Real CABAC state changed");
      for(int bin=0;bin<2;++bin)
        CHECK(before[i].estFracBits(bin)!=after[i].estFracBits(bin) ||
              before[i].getAdaptRateOffset(bin)!=after[i].getAdaptRateOffset(bin),"Real CABAC state changed");
    }
  }
  }
  CHECK(!cleared,"Missing quantized all-zero coverage");
  if(payload.is_open()) { payload.close(); CHECK(payload.fail(),"Cannot close exact quantization payload"); }
  destroyROM();
  std::cout<<"PASS "<<name()<<" synthetic TS-RDOQ trials="<<trials<<" zero="<<zero<<" cleared="<<cleared
           <<" bdpcm_none="<<bdpcmTrials[0]<<" bdpcm_hor="<<bdpcmTrials[1]<<" bdpcm_ver="<<bdpcmTrials[2]
           <<" digest="<<digest<<'\n';
  if(repeats!=1) { std::cout<<"TS_R36_BENCH_REPEAT "<<repeats<<" total_trials="<<repeats*trials<<'\n'; }
}
