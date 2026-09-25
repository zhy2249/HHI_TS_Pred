// Actual CABAC on artificial TUs, including a regular-path witness per mode.
#include "CommonLib/ContextModelling.h"
#include "CommonLib/Rom.h"
#include "EncoderLib/CABACWriter.h"
#include "DecoderLib/CABACReader.h"
#include <iostream>
#include <random>
#include <stdexcept>
#define require(ok) do { if(!(ok))throw std::runtime_error("R6 codec test line "+std::to_string(__LINE__)); } while(false)
int main()
{
  using namespace TsFixedPrediction;
  require(r6(mode())); initROM();
  std::mt19937 rng(20260923);
  XuPool pool; CodingStructure cs(pool); SPS sps; Slice slice;
  cs.sps=&sps; slice.m_sps=&sps; sps.m_dualITree=false;
  sps.m_bitDepths[ChannelType::LUMA]=sps.m_bitDepths[ChannelType::CHROMA]=10;
  uint64_t cgs=0,predictions=0,parentMapped=0;
  for(int trial=0;trial<240;++trial)
  {
    const int w=trial?1<<(1+trial%5):4,h=trial?1<<(1+(trial/5)%5):16;
    const CompID comp=CompID(trial%3);const int scale=comp==COMP_Y?1:2;
    CodingUnit cu(ChromaFormat::_420,Area(0,0,w*scale,h*scale));
    TransformUnit tu(ChromaFormat::_420,Area(0,0,w*scale,h*scale));
    cu.cs=&cs;cu.slice=&slice;cu.qp=rng()%64;cu.predMode=trial%2?MODE_INTRA:MODE_INTER;
    tu.cs=&cs;tu.cu=&cu;tu.mtsIdx[comp]=MtsType::SKIP;
    const auto bdpcm=trial && trial%11==0?BdpcmMode::HOR:trial && trial%13==0?BdpcmMode::VER:BdpcmMode::NONE;
    const unsigned rice=1+trial%4;
    sps.m_spsRangeExtension.m_tsrcRicePresentFlag=true;slice.m_tsrcIndex=rice-1;
    CoeffCodingContext enc(tu,comp,false,bdpcm),dec(tu,comp,false,bdpcm);
    enc.remRegBins=dec.remRegBins=(w*h*7)>>2;
    std::vector<TCoeff> q(w*h),decoded(w*h),inverse(w*h);
    for(int s=0;s<w*h;++s)inverse[enc.blockPos(s)]=s;
    for(auto &v:q)v=rng()%3?int(rng()%(trial%2?19:32767))-(trial%2?9:16383):0;
    if(trial%9==0)std::fill(q.begin(),q.end(),0);
    if(!trial)
    {
      // Deterministically find a small artificial witness, never tune the rule.
      bool found=false;
      const int at[]={2*w+1,w+2,w+1,2*w,2};
      for(int code=0;code<32768&&!found;++code)
      {
        int c=code;for(int k:at){q[k]=c%8;c/=8;}
        const auto r=enc.r6PredictionTS(mode(),inverse[2*w+2],q.data());
        if(mode() >= 30 && !r.luOnly) { continue; } // Cover mean/min, not merely shared sparse NoPred.
        for(int a=1;a<=10;++a)if(remap(a,r.predictor)!=remap(a,r.parent))
        {q[2*w+2]=a;found=true;break;}
      }
      require(found);
    }
    if(!q[0])q[0]=-3;
    OutputBitstream bits;BinEncoder_Std binEnc;CABACWriter writer(binEnc,nullptr);
    writer.initBitstream(&bits);binEnc.reset(cu.qp,I_SLICE);std::vector<int> budgets;
    for(int g=0;g<=enc.lastSubSet();++g)
    {
      enc.initSubblock(g);bool significant=false;
      for(int s=enc.minSubPos();s<=enc.maxSubPos();++s)
      {
        const int pos=enc.blockPos(s);significant|=q[pos]!=0;
        const auto read=[&](int x,int y){if(x<0||y<0)return 0;require(x<w&&y<h&&inverse[y*w+x]<s);return int(q[y*w+x]);};
        const auto r=r6Predict(mode(),read,pos%w,pos/w,rice,enc.maxLog2TrDRange());
        require(r.predictor==enc.magnitudePredictorTS(s,q.data()));
        auto poison=q;for(int k=s;k<w*h;++k)poison[enc.blockPos(k)]=int(rng()%511)-255;
        require(r.predictor==enc.magnitudePredictorTS(s,poison.data()));
        auto unsignedView=q;for(auto &v:unsignedView)v=std::abs(v);
        require(r.predictor==enc.magnitudePredictorTS(s,unsignedView.data()));
        parentMapped+=remap(std::abs(int(q[pos])),r.predictor)!=remap(std::abs(int(q[pos])),r.parent);
        ++predictions;
      }
      if(significant) { enc.setSigGroup(); }
      unsigned riceBits[8]={};
      writer.residual_coding_subblockTS(enc,q.data(),riceBits,rice,false);
      if(!trial && enc.minSubPos()<=inverse[2*w+2] && inverse[2*w+2]<=enc.maxSubPos())
        require(enc.remRegBins>=4); // Witness uses regular coding, not bypass.
      enc.finishTsPredictorCG(q.data(),true,true);
      require(!enc.tsPredictorState()&&!enc.tsPredictorRecentMargin());budgets.push_back(enc.remRegBins);
    }
    binEnc.encodeBinTrm(1);binEnc.finish();bits.writeByteAlignment();
    InputBitstream input;input.getFifo()=bits.getFifo();BinDecoder_Std binDec;CABACReader reader(binDec,nullptr);
    reader.initBitstream(&input);binDec.reset(cu.qp,I_SLICE);
    for(int g=0;g<=dec.lastSubSet();++g)
    {
      dec.initSubblock(g);reader.residual_coding_subblockTS(dec,decoded.data(),rice);
      require(dec.remRegBins==budgets[g]);
      for(int s=dec.minSubPos();s<=dec.maxSubPos();++s)require(decoded[dec.blockPos(s)]==q[dec.blockPos(s)]);
      dec.finishTsPredictorCG(decoded.data(),true,true);require(!dec.tsPredictorState()&&!dec.tsPredictorRecentMargin());++cgs;
    }
    require(binDec.decodeBinTrm()==1);binDec.finish();require(q==decoded);
  }
  require(parentMapped>0);
  std::cout<<"PASS "<<name()<<": 240 native TU, CG="<<cgs<<" causal/sign/poison="<<predictions<<" artificial mapped-vs-R3="<<parentMapped<<'\n';
  destroyROM();
}
