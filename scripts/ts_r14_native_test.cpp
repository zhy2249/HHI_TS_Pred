// Synthetic TU-local CABAC/RDOQ fixtures. Never performs frame/video coding.
#include "CommonLib/TsRateReplay.h"
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

#define require(ok) do { if(!(ok)) throw std::runtime_error("R14 native test line " + std::to_string(__LINE__)); } while(false)
namespace {
struct Artifact
{
  std::ofstream file;
  uint64_t digest=1469598103934665603ULL;
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
void syntaxFixtures(Artifact &artifact,Artifact &nonTargetArtifact)
{
  using namespace TsFixedPrediction;
  XuPool pool; CodingStructure cs(pool); SPS sps; Slice slice;
  cs.sps=&sps; cs.slice=&slice; slice.m_sps=&sps; sps.m_dualITree=false;
  sps.m_bitDepths[ChannelType::LUMA]=sps.m_bitDepths[ChannelType::CHROMA]=10;
  std::mt19937 rng(23102026);
  uint64_t groups=0,causal=0,lowBudget=0,pureBypass=0,changedP=0,changedMap=0;
  uint64_t eligible=0,updates=0,bypassUpdates=0,zeroGroups=0,lossless=0,small=0,rollback=0;
  for(int trial=0;trial<180;++trial)
  {
    const int w=1<<(1+trial%5),h=1<<(1+(trial/5)%5);
    const CompID comp=CompID(trial%3); const int scale=comp==COMP_Y?1:2;
    CodingUnit cu(ChromaFormat::_420,Area(0,0,w*scale,h*scale));
    TransformUnit tu(ChromaFormat::_420,Area(0,0,w*scale,h*scale));
    cu.cs=&cs; cu.slice=&slice; cu.qp=trial%64; cu.predMode=trial%2?MODE_INTRA:MODE_INTER;
    tu.cs=&cs; tu.cu=&cu; tu.mtsIdx[comp]=MtsType::SKIP;
    const auto bdpcm=trial%11==0?BdpcmMode::HOR:trial%11==1?BdpcmMode::VER:BdpcmMode::NONE;
    cu.bdpcmMode[0]=cu.bdpcmMode[1]=bdpcm;
    slice.m_isLossless=trial%17==0; lossless+=slice.m_isLossless; small+=w==2 || h==2;
    const int rice=1+trial%8; sps.m_spsRangeExtension.m_tsrcRicePresentFlag=true; slice.m_tsrcIndex=rice-1;
    slice.m_tsResidualCodingDisabledFlag=false;
    CoeffCodingContext enc(tu,comp,false,bdpcm),dec(tu,comp,false,bdpcm);
    require(enc.tsR14Active()==(r14(mode()) && bdpcm==BdpcmMode::NONE));
    enc.remRegBins=dec.remRegBins=trial%3==0?0:trial%3==1?trial%12:(w*h*7)>>2;
    const bool allBypass=enc.remRegBins==0;
    lowBudget+=enc.remRegBins<4; pureBypass+=allBypass;
    std::vector<TCoeff> q(w*h),decoded(w*h);
    for(auto &a:q) { a=rng()%3?int(rng()%(trial%2?21:4096))-10:0; }
    if(trial%9==0) { std::fill(q.begin(),q.end(),0); }
    if(trial%31==0) for(int i=0;i<w*h;++i) { q[i]=i%3==0?-32768:i%3==1?32767:1; }
    q[0]=-3;
    const auto original=q;
    OutputBitstream bits; BinEncoder_Std bin; CABACWriter writer(bin,nullptr);
    writer.initBitstream(&bits); bin.reset(cu.qp,I_SLICE);
    std::vector<int> budgets,states; std::vector<Ctx> contexts;
    for(int g=0;g<=enc.lastSubSet();++g)
    {
      enc.initSubblock(g); bool sig=false;
      for(int s=enc.minSubPos();s<=enc.maxSubPos();++s) { sig|=q[enc.blockPos(s)]!=0; }
      if(sig) { enc.setSigGroup(); } else { ++zeroGroups; }
      enc.freezeTsRateContext(writer.getCtx()); Ctx untouched(writer.getCtx());
      auto shadow=enc;
      shadow.beginTsR14CG();
      const int entryState=shadow.tsR14State();
      std::vector<int> predictors(w*h);
      for(int s=enc.minSubPos();s<=enc.maxSubPos();++s)
      {
        auto poisoned=q;
        for(int k=s;k<w*h;++k) { poisoned[enc.blockPos(k)]=int(rng()%63)-31; }
        int p;
        if(enc.tsR14Active())
        {
          const int before=shadow.tsR14State();
          const auto d=shadow.prepareTsR14(s,q.data());
          const auto other=shadow.prepareTsR14(s,poisoned.data());
          require(shadow.tsR14State()==before && d.predictor==other.predictor && d.n==other.n);
          for(int r=0;r<=d.k;++r) { require(d.winners[r]==other.winners[r]); }
          p=d.predictor;
          const auto u=shadow.commitTsR14(d,std::abs(int(q[enc.blockPos(s)])));
          eligible+=u.eligible; updates+=u.state!=before; bypassUpdates+=allBypass && u.state!=before;
          artifact.word(s); artifact.word(before); artifact.word(p); artifact.word(u.state);
        }
        else
        {
          p=ratePredictor(shadow,s,q.data());
          require(p==ratePredictor(shadow,s,poisoned.data()));
        }
        predictors[s]=p; ++causal;
        int l,u; enc.neighTS(l,u,s,q.data()); const int current=std::max(std::abs(l),std::abs(u));
        changedP+=!equivalentPredictors(p,current);
        changedMap+=remap(std::abs(int(q[enc.blockPos(s)])),p)!=remap(std::abs(int(q[enc.blockPos(s)])),current);
      }
      const int expectedState=shadow.tsR14State();
      if(enc.tsR14Active())
      {
        require(shadow.tsR14CGEntryState()==entryState);
        shadow.restoreTsR14State(entryState); require(shadow.tsR14State()==entryState); ++rollback;
        if(!sig) { require(expectedState==entryState); }
        CoeffCodingContext fresh(tu,comp,false,bdpcm);
        require(fresh.tsR14State()==fresh.tsR14Config().initialState);
      }
      equalCtx(untouched,writer.getCtx());
      Ctx clone(writer.getCtx()); auto replay=enc; int bins=enc.remRegBins;
      FractionalSink sink{static_cast<CtxStore<BinProbModel_Std>&>(clone)};
      replayRateCG(replay,q.data(),[&](int s) { return predictors[s]; },bins,rice,sink);
      BitEstimator_Std estimator; estimator.getCtx()=writer.getCtx(); estimator.resetBits();
      CABACWriter estimate(estimator,nullptr); auto native=enc; unsigned rb[8]{};
      estimate.residual_coding_subblockTS(native,q.data(),rb,rice,false);
      require(sink.bits==estimator.getEstFracBits() && bins==native.remRegBins);
      require(native.tsR14State()==expectedState);
      equalCtx(clone,estimator.getCtx()); equalCtx(untouched,writer.getCtx());
      writer.residual_coding_subblockTS(enc,q.data(),rb,rice,false);
      require(enc.remRegBins==bins && enc.tsR14State()==expectedState);
      equalCtx(clone,writer.getCtx()); budgets.push_back(bins); states.push_back(expectedState); ++groups;
      const auto observerContext=writer.getCtx();
      enc.finishTsPredictorCG(q.data(),true,true,true);
      equalCtx(observerContext,writer.getCtx());
      require(q==original && enc.remRegBins==bins && enc.tsR14State()==expectedState);
      contexts.push_back(writer.getCtx());
      artifact.word(g); artifact.word(bins); artifact.word(sink.bits); contextArtifact(artifact,writer.getCtx());
    }
    bin.encodeBinTrm(1); bin.finish(); bits.writeByteAlignment();
    for(uint64_t value:{uint64_t(trial),uint64_t(w),uint64_t(h),uint64_t(comp),uint64_t(cu.qp),
                       uint64_t(bdpcm),uint64_t(rice),uint64_t(bits.getFifo().size())}) { artifact.word(value); }
    for(auto byte:bits.getFifo()) { artifact.byte(byte); }
    if(bdpcm!=BdpcmMode::NONE)
    {
      nonTargetArtifact.word(trial); nonTargetArtifact.word(bits.getFifo().size());
      for(auto byte:bits.getFifo()) { nonTargetArtifact.byte(byte); }
    }
    InputBitstream input; input.getFifo()=bits.getFifo(); BinDecoder_Std decoder; CABACReader reader(decoder,nullptr);
    reader.initBitstream(&input); decoder.reset(cu.qp,I_SLICE);
    for(int g=0;g<=dec.lastSubSet();++g)
    {
      dec.initSubblock(g); reader.residual_coding_subblockTS(dec,decoded.data(),rice);
      require(dec.remRegBins==budgets[g] && dec.tsR14State()==states[g]); equalCtx(contexts[g],reader.getCtx());
      for(int s=dec.minSubPos();s<=dec.maxSubPos();++s) { require(q[dec.blockPos(s)]==decoded[dec.blockPos(s)]); }
      const auto observerContext=reader.getCtx();
      dec.finishTsPredictorCG(decoded.data(),true,true,false);
      equalCtx(observerContext,reader.getCtx()); require(dec.remRegBins==budgets[g] && dec.tsR14State()==states[g]);
    }
    require(decoder.decodeBinTrm()==1); decoder.finish(); require(q==decoded);
    // These are gate probes, not an attempt to invoke TSRC on a disabled TU.
    slice.m_tsResidualCodingDisabledFlag=true;
    CoeffCodingContext disabled(tu,comp,false,bdpcm); require(!disabled.tsR14Active());
    slice.m_tsResidualCodingDisabledFlag=false; tu.mtsIdx[comp]=MtsType::DCT2_DCT2;
    CoeffCodingContext transformed(tu,comp,false,bdpcm); require(!transformed.tsR14Active());
  }
  require(lowBudget && pureBypass && zeroGroups && lossless && small);
  if(r14(mode()))
  {
    require(changedP && changedMap && rollback);
    if(r14Config(r14PublicMode(mode())).dynamic) { require(eligible && updates && bypassUpdates); }
  }
  std::cout<<"TS_R14_SYNTAX TU=180 CG="<<groups<<" causal="<<causal<<" low_budget="<<lowBudget
           <<" pure_bypass="<<pureBypass<<" predictor_vs_current="<<changedP<<" mapping_vs_current="<<changedMap
           <<" eligible="<<eligible<<" updates="<<updates<<" bypass_updates="<<bypassUpdates
           <<" zero_CG="<<zeroGroups<<" rollback_api="<<rollback<<" lossless_TU="<<lossless<<" small_TU="<<small<<'\n';
}
void quantFixtures(Artifact &artifact,Artifact &nonTargetArtifact)
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
    for(uint64_t value:{uint64_t(trial),uint64_t(tu.blocks[comp].width),uint64_t(tu.blocks[comp].height),
                       uint64_t(comp),uint64_t(cu.qp),uint64_t(bdpcm),uint64_t(q.size()),uint64_t(int64_t(sum))}) { artifact.word(value); }
    for(auto value:q) { artifact.word(uint64_t(int64_t(value))); }
    contextArtifact(artifact,ctx);
    if(bdpcm!=BdpcmMode::NONE || slice.m_tsResidualCodingDisabledFlag || transformed || usePlain || slice.m_isLossless)
    {
      nonTargetArtifact.word(trial); nonTargetArtifact.word(q.size()); nonTargetArtifact.word(uint64_t(int64_t(sum)));
      for(auto value:q) { nonTargetArtifact.word(uint64_t(int64_t(value))); }
    }
  }
  require(cleared && zero && lossless && rdoqOff && disabled && normal && small);
  std::cout<<"TS_R14_QUANT TU=288 zero="<<zero<<" cleared="<<cleared<<" bdpcm_none="<<bdpcmTrials[0]
           <<" bdpcm_hor="<<bdpcmTrials[1]<<" bdpcm_ver="<<bdpcmTrials[2]<<" lossless="<<lossless
           <<" rdoq_off="<<rdoqOff<<" tsrc_disabled="<<disabled<<" normal_transform="<<normal<<" small="<<small<<'\n';
}
}
int main()
{
  using namespace TsFixedPrediction;
  require(mode()==1 || mode()==10 || mode()==13 || mode()==26 || mode()==98 || mode()==99 || r14(mode()));
  initROM(); Artifact artifact("TS_R14_EXACT_PAYLOAD"),nonTargetArtifact("TS_R14_NONTARGET_PAYLOAD");
  syntaxFixtures(artifact,nonTargetArtifact); quantFixtures(artifact,nonTargetArtifact); destroyROM();
  std::cout<<"PASS "<<name()<<" synthetic TSRC+RDOQ; sequence_encode_decode=false\n"
           <<"TS_R14_NATIVE_DIGEST "<<artifact.digest<<'\n'<<"TS_R14_NONTARGET_DIGEST "<<nonTargetArtifact.digest<<'\n';
}
