#include "CommonLib/TsRateReplay.h"
#include "CommonLib/Rom.h"
#include "EncoderLib/CABACWriter.h"
#include "DecoderLib/CABACReader.h"
#include <iostream>
#include <random>
#include <stdexcept>
#define require(ok) do { if(!(ok))throw std::runtime_error("Rate test line "+std::to_string(__LINE__)); } while(false)
static void equalCtx(const Ctx &a,const Ctx &b)
{
  const auto &x=static_cast<const CtxStore<BinProbModel_Std>&>(a);
  const auto &y=static_cast<const CtxStore<BinProbModel_Std>&>(b);
  for(unsigned i=0;i<ContextSetCfg::NumberOfContexts;++i)
  {
    require(x[i].getState()==y[i].getState());
    require(x[i].estFracBits(0)==y[i].estFracBits(0) && x[i].estFracBits(1)==y[i].estFracBits(1));
    require(x[i].getWinSizes()==y[i].getWinSizes());
    require(x[i].getAdaptRateWeight()==y[i].getAdaptRateWeight());
    for(int j=0;j<2;++j)require(x[i].getAdaptRateOffset(j)==y[i].getAdaptRateOffset(j));
  }
}
int main()
{
  using namespace TsFixedPrediction;
  require(mode()==13 || needsTsRateContext(mode())); initROM();
  std::mt19937 rng(20260924);
  RateTable neutral;
  for(auto *b:{&neutral.gt1,&neutral.parity,&neutral.gt[0],&neutral.gt[1],&neutral.gt[2],&neutral.gt[3]})
    b->intBits[0]=b->intBits[1]=1<<SCALE_BITS;
  for(unsigned rice=1;rice<=8;++rice)
    for(unsigned a=0;a<32768;++a)
      require(neutral.cost(a,rice,15)==int64_t(syntaxCost(a,rice,15))<<SCALE_BITS);
  for(int k=0;k<40000;++k)
  {
    int nz[5]; const int n=k%6;
    for(int j=0;j<n;++j)nz[j]=1+rng()%63;
    const int current=n?nz[0]:0;
    const auto d=rateDecision(current,nz,n,[&](int a){return neutral.cost(a,1,15);});
    const auto old=guardedLocalPredict(current,nz,n,1,15);
    require(equivalentPredictors(d.winner,old.winner)&&equivalentPredictors(d.predictor,old.predictor));
    require(d.gain==int64_t(old.gain)<<SCALE_BITS && d.margin()==int64_t(old.margin())*(1<<SCALE_BITS));
  }
  XuPool pool; CodingStructure cs(pool); SPS sps; Slice slice;
  cs.sps=&sps; slice.m_sps=&sps; sps.m_dualITree=false;
  sps.m_bitDepths[ChannelType::LUMA]=sps.m_bitDepths[ChannelType::CHROMA]=10;
  uint64_t groups=0,poisons=0;
  for(int trial=0;trial<160;++trial)
  {
    const int w=1<<(1+trial%5),h=1<<(1+(trial/5)%5);
    const CompID comp=CompID(trial%3); const int scale=comp==COMP_Y?1:2;
    CodingUnit cu(ChromaFormat::_420,Area(0,0,w*scale,h*scale));
    TransformUnit tu(ChromaFormat::_420,Area(0,0,w*scale,h*scale));
    cu.cs=&cs; cu.slice=&slice; cu.qp=rng()%64; cu.predMode=trial%2?MODE_INTRA:MODE_INTER;
    tu.cs=&cs; tu.cu=&cu; tu.mtsIdx[comp]=MtsType::SKIP;
    const auto bdpcm=trial%13?BdpcmMode::NONE:BdpcmMode::HOR;
    const int rice=1+trial%8; sps.m_spsRangeExtension.m_tsrcRicePresentFlag=true; slice.m_tsrcIndex=rice-1;
    CoeffCodingContext enc(tu,comp,false,bdpcm),dec(tu,comp,false,bdpcm);
    enc.remRegBins=dec.remRegBins=trial%3?(w*h*7)>>2:trial%12;
    std::vector<TCoeff> q(w*h),decoded(w*h);
    for(auto &a:q)a=rng()%3?int(rng()%(trial%2?21:4096))-10:0;
    if(trial%9==0)std::fill(q.begin(),q.end(),0);
    q[0]=-3;
    if(r8(mode()) && trial%31==0)
      for(int i=0;i<w*h;++i)q[i]=i%3==0?-32768:i%3==1?32767:1;
    OutputBitstream bits; BinEncoder_Std bin; CABACWriter writer(bin,nullptr);
    writer.initBitstream(&bits); bin.reset(cu.qp,I_SLICE);
    std::vector<int> budgets;
    for(int g=0;g<=enc.lastSubSet();++g)
    {
      enc.initSubblock(g); bool sig=false;
      for(int s=enc.minSubPos();s<=enc.maxSubPos();++s)sig|=q[enc.blockPos(s)]!=0;
      if(sig)enc.setSigGroup();
      enc.freezeTsRateContext(writer.getCtx()); Ctx untouched(writer.getCtx());
      for(int s=enc.minSubPos();s<=enc.maxSubPos();++s)
      {
        auto poisoned=q;
        for(int k=s;k<w*h;++k)poisoned[enc.blockPos(k)]=int(rng()%63)-31;
        require(ratePredictor(enc,s,q.data())==ratePredictor(enc,s,poisoned.data())); ++poisons;
      }
      equalCtx(untouched,writer.getCtx());
      Ctx clone(writer.getCtx()); auto replay=enc; int bins=enc.remRegBins;
      FractionalSink sink{static_cast<CtxStore<BinProbModel_Std>&>(clone)};
      replayRateCG(replay,q.data(),[&](int s){return ratePredictor(enc,s,q.data());},bins,rice,sink);
      BitEstimator_Std estimator; estimator.getCtx()=writer.getCtx(); estimator.resetBits();
      CABACWriter estimate(estimator,nullptr); auto native=enc; unsigned rb[8]{};
      estimate.residual_coding_subblockTS(native,q.data(),rb,rice,false);
      require(sink.bits==estimator.getEstFracBits() && bins==native.remRegBins);
      equalCtx(clone,estimator.getCtx()); equalCtx(untouched,writer.getCtx());
      writer.residual_coding_subblockTS(enc,q.data(),rb,rice,false);
      require(enc.remRegBins==bins); equalCtx(clone,writer.getCtx()); budgets.push_back(bins); ++groups;
    }
    bin.encodeBinTrm(1);bin.finish();bits.writeByteAlignment();
    InputBitstream input;input.getFifo()=bits.getFifo();BinDecoder_Std decoder;CABACReader reader(decoder,nullptr);
    reader.initBitstream(&input);decoder.reset(cu.qp,I_SLICE);
    for(int g=0;g<=dec.lastSubSet();++g)
    {
      dec.initSubblock(g);reader.residual_coding_subblockTS(dec,decoded.data(),rice);
      require(dec.remRegBins==budgets[g]);
      for(int s=dec.minSubPos();s<=dec.maxSubPos();++s)require(q[dec.blockPos(s)]==decoded[dec.blockPos(s)]);
    }
    require(decoder.decodeBinTrm()==1); decoder.finish(); require(q==decoded);
  }
  destroyROM();
  std::cout<<"PASS "<<name()<<": neutral lengths=262144 old-score cases=40000 native TU=160 CG="<<groups<<" causal="<<poisons<<'\n';
}
