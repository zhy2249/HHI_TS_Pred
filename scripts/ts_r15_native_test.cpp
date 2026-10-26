// Synthetic TU-local CABAC/RDOQ fixtures. Never performs frame/video coding.
#include "CommonLib/TsRateReplay.h"
#include "CommonLib/TsMultiMapping.h"
#include "CommonLib/QuantRDOQ.h"
#include "CommonLib/CodingStructure.h"
#include "CommonLib/Rom.h"
#include "EncoderLib/CABACWriter.h"
#include "DecoderLib/CABACReader.h"
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <memory>
#include <random>
#include <stdexcept>
#include <vector>

#define require(ok) do { if(!(ok)) throw std::runtime_error("R15 native test line " + std::to_string(__LINE__)); } while(false)
namespace {
struct Artifact
{
  std::ofstream file;
  uint64_t digest=1469598103934665603ULL;
  Artifact *mirror=nullptr;
  explicit Artifact(const char *variable)
  {
    if(const char *path=std::getenv(variable)) if(*path)
    {
      file.open(path,std::ios::binary|std::ios::trunc);
      require(file.is_open());
    }
  }
  void byte(unsigned value)
  {
    if(mirror) { mirror->byte(value); }
    digest=(digest^uint8_t(value))*1099511628211ULL;
    if(file.is_open()) { file.put(char(value)); require(file.good()); }
  }
  void word(uint64_t value) { for(int i=0;i<8;++i) { byte(unsigned(value>>(8*i))&255); } }
};
void equalCtx(const Ctx &a,const Ctx &b)
{
  const auto &x=static_cast<const CtxStore<BinProbModel_Std>&>(a);
  const auto &y=static_cast<const CtxStore<BinProbModel_Std>&>(b);
  for(unsigned i=0;i<ContextSetCfg::NumberOfContexts;++i)
  {
    require(x[i].getState()==y[i].getState());
    require(x[i].getWinSizes()==y[i].getWinSizes());
    require(x[i].getAdaptRateWeight()==y[i].getAdaptRateWeight());
    for(int bin=0;bin<2;++bin)
    {
      require(x[i].estFracBits(bin)==y[i].estFracBits(bin));
      require(x[i].getAdaptRateOffset(bin)==y[i].getAdaptRateOffset(bin));
    }
  }
}
void contextArtifact(Artifact &a,const Ctx &ctx)
{
  const auto &x=static_cast<const CtxStore<BinProbModel_Std>&>(ctx);
  for(unsigned i=0;i<ContextSetCfg::NumberOfContexts;++i)
  {
    const auto state=x[i].getState();
    a.word(state.first); a.word(state.second);
    a.word(x[i].getWinSizes()); a.word(x[i].getAdaptRateWeight());
    for(int bin=0;bin<2;++bin) { a.word(x[i].estFracBits(bin)); a.word(x[i].getAdaptRateOffset(bin)); }
  }
}

struct Metrics { uint64_t tu=0,cg=0,causal=0,changed=0,multi=0,bypass=0,zeroCG=0; };
void roundTrip(TransformUnit &tu,CompID comp,const std::vector<TCoeff> &q,int rice,int budget,
               Artifact &artifact,Metrics &metrics)
{
  using namespace TsFixedPrediction;
  const auto bdpcm=tu.cu->bdpcmMode[int(toChannelType(comp))];
  CoeffCodingContext enc(tu,comp,false,bdpcm),dec(tu,comp,false,bdpcm);
#if JVET_BJUT_TS_FIXED_PREDICTOR
  const bool target=r15(mode()) && bdpcm==BdpcmMode::NONE && !tu.cu->slice->m_tsResidualCodingDisabledFlag
                    && tu.mtsIdx[comp]==MtsType::SKIP;
  require(enc.tsR15Active()==target && dec.tsR15Active()==target);
#endif
  enc.remRegBins=dec.remRegBins=budget;
  std::vector<TCoeff> decoded(q.size()); const auto original=q;
  OutputBitstream bits; BinEncoder_Std bin; CABACWriter writer(bin,nullptr);
  writer.initBitstream(&bits); bin.reset(tu.cu->qp,tu.cu->slice->m_eSliceType);
  std::vector<int> budgets; std::vector<Ctx> contexts;
  for(int g=0;g<=enc.lastSubSet();++g)
  {
    enc.initSubblock(g); bool sig=false;
    for(int s=enc.minSubPos();s<=enc.maxSubPos();++s) { sig|=q[enc.blockPos(s)]!=0; }
    if(sig) { enc.setSigGroup(); } else { ++metrics.zeroCG; }
    std::vector<TsMultiMapping::Action> actions(q.size());
    const Ctx untouched(writer.getCtx());
    if(sig) for(int s=enc.minSubPos();s<=enc.maxSubPos();++s)
    {
      auto poisoned=q;
      for(int t=s;t<int(q.size());++t) { poisoned[enc.blockPos(t)]=(t&1)?32767:-32768; }
      auto select=[&](const TCoeff *levels) {
#if JVET_BJUT_TS_FIXED_PREDICTOR
        if(target) { return enc.prepareTsR15(s,levels); }
#endif
        return TsMultiMapping::single(ratePredictor(enc,s,levels));
      };
      actions[s]=select(q.data()); require(actions[s]==select(poisoned.data())); ++metrics.causal;
      // Compare the selected whole action to the independent NAIVE engine.
#if JVET_BJUT_TS_FIXED_PREDICTOR
      if(target)
      {
        int h[5]; enc.r13SupportTS(s,q.data(),h);
        require(actions[s]==TsMultiMapping::select({{h[0],h[1],h[2],h[3],h[4]}},
          TsMultiMapping::publicMethod(r15PublicMode(mode())),rice,enc.maxLog2TrDRange(),
          TsMultiMapping::Engine::NAIVE).action);
      }
#endif
      int l,u; enc.neighTS(l,u,s,q.data()); const int a=std::abs(int(q[enc.blockPos(s)]));
      metrics.changed+=TsMultiMapping::map(a,actions[s])!=remap(a,std::max(std::abs(l),std::abs(u)));
      metrics.multi+=actions[s].count>1;
    }
    Ctx clone(writer.getCtx()); auto replay=enc; int remaining=enc.remRegBins;
    FractionalSink sink{static_cast<CtxStore<BinProbModel_Std>&>(clone)};
    replayRateCG(replay,q.data(),[&](int s) { return actions[s]; },remaining,rice,sink);
    BitEstimator_Std estimator; estimator.getCtx()=writer.getCtx(); estimator.resetBits();
    CABACWriter estimate(estimator,nullptr); auto native=enc; unsigned rb[8]{};
    estimate.residual_coding_subblockTS(native,q.data(),rb,rice,false);
    require(sink.bits==estimator.getEstFracBits() && remaining==native.remRegBins);
    equalCtx(clone,estimator.getCtx()); equalCtx(untouched,writer.getCtx());
    metrics.bypass+=enc.remRegBins<4;
    writer.residual_coding_subblockTS(enc,q.data(),rb,rice,false);
    require(enc.remRegBins==remaining); equalCtx(clone,writer.getCtx());
#if JVET_BJUT_TS_FIXED_PREDICTOR
    enc.finishTsPredictorCG(q.data(),true,true,true);
#endif
    equalCtx(clone,writer.getCtx()); require(q==original);
    budgets.push_back(remaining); contexts.push_back(writer.getCtx()); ++metrics.cg;
    artifact.word(g); artifact.word(remaining); artifact.word(sink.bits); contextArtifact(artifact,clone);
  }
  bin.encodeBinTrm(1); bin.finish(); bits.writeByteAlignment();
  artifact.word(bits.getFifo().size()); for(auto b:bits.getFifo()) { artifact.byte(b); }
  InputBitstream input; input.getFifo()=bits.getFifo(); BinDecoder_Std decoder; CABACReader reader(decoder,nullptr);
  reader.initBitstream(&input); decoder.reset(tu.cu->qp,tu.cu->slice->m_eSliceType);
  for(int g=0;g<=dec.lastSubSet();++g)
  {
    dec.initSubblock(g); reader.residual_coding_subblockTS(dec,decoded.data(),rice);
    require(dec.remRegBins==budgets[g]); equalCtx(contexts[g],reader.getCtx());
    for(int s=dec.minSubPos();s<=dec.maxSubPos();++s) { require(q[dec.blockPos(s)]==decoded[dec.blockPos(s)]); }
#if JVET_BJUT_TS_FIXED_PREDICTOR
    dec.finishTsPredictorCG(decoded.data(),true,true,false);
#endif
    equalCtx(contexts[g],reader.getCtx());
  }
  require(decoder.decodeBinTrm()==1); decoder.finish(); require(q==decoded); ++metrics.tu;
}
void printMetrics(const char *label,const Metrics &m)
{
  std::cout<<"TS_R15_"<<label<<" TU="<<m.tu<<" CG="<<m.cg<<" causal="<<m.causal<<" map_vs_current="<<m.changed
           <<" multi="<<m.multi<<" bypass_CG="<<m.bypass<<" zero_CG="<<m.zeroCG<<'\n';
}
void syntaxFixtures(Artifact &artifact,Artifact &nonTarget,Artifact &target)
{
  using namespace TsFixedPrediction;
  XuPool pool; CodingStructure cs(pool); SPS sps; Slice slice;
  cs.sps=&sps; cs.slice=&slice; slice.m_sps=&sps; sps.m_dualITree=false;
  sps.m_bitDepths[ChannelType::LUMA]=sps.m_bitDepths[ChannelType::CHROMA]=10;
  std::mt19937 rng(26102026); Metrics metrics,bdpcmMetrics;
  for(int trial=0;trial<180;++trial)
  {
    const int w=1<<(1+trial%5),h=1<<(1+(trial/5)%5);
    const CompID comp=CompID(trial%3); const int scale=comp==COMP_Y?1:2;
    CodingUnit cu(ChromaFormat::_420,Area(0,0,w*scale,h*scale));
    TransformUnit tu(static_cast<const UnitArea&>(cu));
    cu.cs=&cs; cu.slice=&slice; cu.qp=trial%64; cu.predMode=trial%2?MODE_INTRA:MODE_INTER;
    tu.cs=&cs; tu.cu=&cu; tu.mtsIdx[comp]=MtsType::SKIP;
    const auto bdpcm=trial%11==0?BdpcmMode::HOR:trial%11==1?BdpcmMode::VER:BdpcmMode::NONE;
    cu.bdpcmMode[0]=cu.bdpcmMode[1]=bdpcm;
    slice.m_eSliceType=SliceType(trial%3); slice.m_isLossless=trial%17==0;
    const int rice=1+trial%8; sps.m_spsRangeExtension.m_tsrcRicePresentFlag=true; slice.m_tsrcIndex=rice-1;
    slice.m_tsResidualCodingDisabledFlag=false;
    const int budget=trial%3==0?0:trial%3==1?trial%12:(w*h*7)>>2;
    std::vector<TCoeff> q(w*h);
    for(auto &a:q) { a=rng()%3?int(rng()%(trial%2?21:4096))-10:0; }
    if(trial%9==0) { std::fill(q.begin(),q.end(),0); }
    if(trial%31==0) for(int i=0;i<w*h;++i) { q[i]=i%3==0?-32768:i%3==1?32767:1; }
    q[0]=-3;
    artifact.mirror=bdpcm==BdpcmMode::NONE?&target:nullptr;
    roundTrip(tu,comp,q,rice,budget,artifact,metrics);
    artifact.mirror=nullptr;
    if(bdpcm!=BdpcmMode::NONE) { roundTrip(tu,comp,q,rice,budget,nonTarget,bdpcmMetrics); }
    slice.m_tsResidualCodingDisabledFlag=true;
    CoeffCodingContext disabled(tu,comp,false,bdpcm);
#if JVET_BJUT_TS_FIXED_PREDICTOR
    require(!disabled.tsR15Active());
#endif
    require(disabled.magnitudePredictorTS(0,q.data())==(mode()==0?0:-1));
    slice.m_tsResidualCodingDisabledFlag=false; tu.mtsIdx[comp]=MtsType::DCT2_DCT2;
#if JVET_BJUT_TS_FIXED_PREDICTOR
    CoeffCodingContext normal(tu,comp,false,bdpcm); require(!normal.tsR15Active());
#endif
  }
  require(metrics.bypass && metrics.zeroCG && metrics.causal);
  if(r15(mode()) && r15PublicMode(mode())!=1) { require(metrics.multi); }
  printMetrics("SYNTAX",metrics);
}
void quantFixtures(Artifact &artifact,Artifact &nonTargetArtifact,Artifact &target)
{
  XuPool pool; CodingStructure cs(pool); SPS sps; PPS pps; Slice slice; PicHeader pictureHeader;
  sps.m_chromaFormatIdc=ChromaFormat::_420; sps.m_maxCuWidth=sps.m_maxCuHeight=64;
  sps.m_bitDepths[ChannelType::LUMA]=sps.m_bitDepths[ChannelType::CHROMA]=10;
  for(auto &table:sps.m_chromaQpMappingTable.m_chromaQpMappingTables)
    for(int qp=0;qp<=MAX_QP;++qp) { table[qp]=qp; }
  pps.m_picWidthInLumaSamples=pps.m_picHeightInLumaSamples=64;
  PreCalcValues pcv(sps,pps,true); cs.sps=&sps; cs.pps=&pps; cs.pcv=&pcv; cs.slice=&slice;
  slice.m_sps=&sps; slice.m_pps=&pps; slice.m_picHeader=&pictureHeader; cs.picHeader=&pictureHeader;
  auto regular=std::make_unique<QuantRDOQ>(nullptr),plain=std::make_unique<QuantRDOQ>(nullptr);
  regular->init(64,true,true,false); plain->init(64,false,false,false);
  const int ranges[]={sps.getMaxLog2TrDynamicRange(ChannelType::LUMA),sps.getMaxLog2TrDynamicRange(ChannelType::CHROMA)};
  for(QuantRDOQ *q:{regular.get(),plain.get()}) { q->setUseScalingList(false); q->setFlatScalingList(ranges,sps.m_bitDepths); }
  std::mt19937 rng(4102026); unsigned zero=0,cleared=0,bdpcmTrials[3]{},lossless=0,rdoqOff=0,disabled=0,normal=0,small=0;
  Metrics decodedMetrics;
  for(unsigned trial=0;trial<288;++trial)
  {
    const int w=1<<(2+trial%4),h=1<<(2+(trial/4)%4); const CompID comp=CompID(trial%3);
    CodingUnit cu(ChromaFormat::_420,Area(0,0,w,h)); TransformUnit tu(static_cast<const UnitArea&>(cu));
    const auto bdpcm=trial%8==6?BdpcmMode::HOR:trial%8==7?BdpcmMode::VER:BdpcmMode::NONE;
    ++bdpcmTrials[int(bdpcm)]; cu.cs=&cs; cu.slice=&slice; cu.qp=10+trial%38;
    cu.predMode=bdpcm!=BdpcmMode::NONE || trial%2?MODE_INTRA:MODE_INTER;
    cu.bdpcmMode[0]=cu.bdpcmMode[1]=bdpcm;
    slice.m_eSliceType=cu.predMode==MODE_INTRA?I_SLICE:P_SLICE;
    slice.m_isLossless=trial%17==0; lossless+=slice.m_isLossless;
    slice.m_tsResidualCodingDisabledFlag=trial%19==0; disabled+=slice.m_tsResidualCodingDisabledFlag;
    sps.m_spsRangeExtension.m_tsrcRicePresentFlag=true; slice.m_tsrcIndex=trial%8;
    const bool usePlain=trial%13==4,transformed=trial%23==0 && bdpcm==BdpcmMode::NONE;
    auto &quant=*(usePlain?plain:regular); rdoqOff+=usePlain; normal+=transformed;
    tu.cs=&cs; tu.cu=&cu; tu.mtsIdx[comp]=transformed?MtsType::DCT2_DCT2:MtsType::SKIP;
    small+=tu.blocks[comp].width<=2 || tu.blocks[comp].height<=2;
    std::vector<TCoeff> y(w*h),cb(w*h/4),cr(w*h/4),src(tu.blocks[comp].area());
    std::vector<uint8_t> sy(y.size()),sb(cb.size()),sr(cr.size());
    TCoeff *coeff[]={y.data(),cb.data(),cr.data()}; uint8_t *signs[]={sy.data(),sb.data(),sr.data()};
    EnumArray<Pel*,ChannelType> plt{}; EnumArray<bool*,ChannelType> run{}; tu.init(coeff,signs,plt,run);
    auto &q=comp==COMP_Y?y:comp==COMP_Cb?cb:cr; QpParam qp(tu,comp);
    Ctx ctx(static_cast<const BinProbModel_Std*>(nullptr)); ctx.init(cu.qp,slice.m_eSliceType); const Ctx untouched(ctx);
    quant.setLambda(double(1u<<(trial%12)));
    for(unsigned i=0;i<src.size();++i)
    {
      const int raw=int(rng()%511)-255;
      src[i]=trial%13==0?0:trial%13==1?1:trial%13==2?(i%7?0:raw):trial%13==3?(i%5==0?-7:7):raw;
    }
    const auto original=src; TCoeff sum=0;
    const auto call=[&]() { sum=0; quant.quant(tu,comp,CCoeffBuf(src.data(),tu.blocks[comp]),sum,qp,ctx); };
    call(); const auto expected=q; const auto expectedSum=sum; require(src==original); equalCtx(untouched,ctx);
    if(trial%13==0) { require(sum==0); ++zero; } else if(!sum) { ++cleared; }
    std::fill(q.begin(),q.end(),123); std::fill(src.begin(),src.end(),0); call(); require(sum==0);
    src=original; call(); require(q==expected && sum==expectedSum); equalCtx(untouched,ctx);
    artifact.mirror=bdpcm==BdpcmMode::NONE && !slice.m_tsResidualCodingDisabledFlag && !transformed?&target:nullptr;
    for(uint64_t value:{uint64_t(trial),uint64_t(tu.blocks[comp].width),uint64_t(tu.blocks[comp].height),
                       uint64_t(comp),uint64_t(cu.qp),uint64_t(bdpcm),uint64_t(q.size()),uint64_t(int64_t(sum))}) { artifact.word(value); }
    for(auto value:q) { artifact.word(uint64_t(int64_t(value))); }
    contextArtifact(artifact,ctx);
    if(sum && !transformed && !slice.m_tsResidualCodingDisabledFlag)
      roundTrip(tu,comp,q,1+slice.m_tsrcIndex,(q.size()*7)>>2,artifact,decodedMetrics);
    artifact.mirror=nullptr;
    if(bdpcm!=BdpcmMode::NONE || slice.m_tsResidualCodingDisabledFlag || transformed || usePlain || slice.m_isLossless)
    {
      nonTargetArtifact.word(trial); nonTargetArtifact.word(q.size()); nonTargetArtifact.word(uint64_t(int64_t(sum)));
      for(auto value:q) { nonTargetArtifact.word(uint64_t(int64_t(value))); }
    }
  }
  require(cleared && zero && lossless && rdoqOff && disabled && normal && small);
  std::cout<<"TS_R15_QUANT TU=288 zero="<<zero<<" cleared="<<cleared<<" bdpcm_none="<<bdpcmTrials[0]
           <<" bdpcm_hor="<<bdpcmTrials[1]<<" bdpcm_ver="<<bdpcmTrials[2]<<" lossless="<<lossless
           <<" rdoq_off="<<rdoqOff<<" tsrc_disabled="<<disabled<<" normal_transform="<<normal<<" small="<<small<<'\n';
  printMetrics("QUANT_ROUNDTRIP",decodedMetrics);
}
}
int main()
{
  using namespace TsFixedPrediction;
  require(mode()==0 || mode()==1 || r15(mode()));
  announce(); initROM(); Artifact artifact("TS_R15_EXACT_PAYLOAD"),nonTarget("TS_R15_NONTARGET_PAYLOAD"),target("TS_R15_TARGET_PAYLOAD");
  syntaxFixtures(artifact,nonTarget,target); quantFixtures(artifact,nonTarget,target); destroyROM();
  std::cout<<"PASS "<<name()<<" synthetic TSRC+RDOQ; sequence_encode_decode=false\n"
           <<"TS_R15_NATIVE_DIGEST "<<artifact.digest<<'\n'<<"TS_R15_NONTARGET_DIGEST "<<nonTarget.digest<<'\n'
           <<"TS_R15_TARGET_DIGEST "<<target.digest<<'\n';
}
