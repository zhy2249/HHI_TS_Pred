// Native syntax fixtures, not frame encoding: independent Writer -> Reader,
// complete bin trace -> replay, serialization -> replay, historical candidates.
#include "DecoderLib/tsaudit/Replay.h"
#include "DecoderLib/tsaudit/Corpus.h"
#include "CommonLib/Rom.h"
#include "EncoderLib/CABACWriter.h"
#include "DecoderLib/CABACReader.h"
#include <iostream>
#include <random>
int main(int argc,char **argv)
{
  using namespace TsAudit;
  CHECK(argc!=2 && argc!=3,"Provide temporary snapshot path and optional corpus fixture JSONL");
  std::ofstream corpus;
  if(argc==3) { corpus.open(argv[2]); CHECK(!corpus,"Cannot open corpus fixture output"); }
  initROM(); XuPool pool; CodingStructure cs(pool); SPS sps; PPS pps; Slice slice;
  sps.m_chromaFormatIdc=ChromaFormat::_420;sps.m_maxCuWidth=sps.m_maxCuHeight=128;sps.m_dualITree=false;
  sps.m_bitDepths[ChannelType::LUMA]=sps.m_bitDepths[ChannelType::CHROMA]=10;
  pps.m_picWidthInLumaSamples=pps.m_picHeightInLumaSamples=128; PreCalcValues pcv(sps,pps,true);
  cs.sps=&sps;cs.pps=&pps;cs.pcv=&pcv;cs.slice=&slice;slice.m_sps=&sps;slice.m_pps=&pps;
  std::mt19937 rng(20261025); unsigned bypass=0,extended=0,bdpcm=0;
  for(int trial=0;trial<48;++trial)
  {
    const CompID comp=CompID(trial%3);const int scale=comp==COMP_Y?1:2;
    const int w=1<<(2+trial%4),h=1<<(2+(trial/4)%4);const int cw=w*scale,ch=h*scale;
    CodingUnit cu(ChromaFormat::_420,Area(0,0,cw,ch));TransformUnit tu(static_cast<const UnitArea&>(cu));
    cu.cs=&cs;cu.slice=&slice;cu.qp=22+trial%20;cu.predMode=trial%2?MODE_INTRA:MODE_INTER;
    slice.m_eSliceType=SliceType(trial%3);
    cu.bdpcmMode[0]=cu.bdpcmMode[1]=trial%7==0?BdpcmMode::HOR:trial%7==1?BdpcmMode::VER:BdpcmMode::NONE;
    bdpcm+=cu.getBdpcmMode(comp)!=BdpcmMode::NONE;tu.cs=&cs;tu.cu=&cu;tu.mtsIdx[comp]=MtsType::SKIP;
    sps.m_spsRangeExtension.m_tsrcRicePresentFlag=true;slice.m_tsrcIndex=trial%8;
    std::vector<TCoeff> y(cw*ch),u(cw*ch/4),v(cw*ch/4),decoded(w*h);std::vector<uint8_t> ys(y.size()),us(u.size()),vs(v.size());
    TCoeff *q[]={y.data(),u.data(),v.data()};uint8_t *signs[]={ys.data(),us.data(),vs.data()};EnumArray<Pel*,ChannelType> plt{};EnumArray<bool*,ChannelType> run{};tu.init(q,signs,plt,run);
    auto *actual=tu.getCoeffs(comp).buf;
    for(int i=0;i<w*h;++i) { actual[i]=trial%4==0?(rng()%19?0:1):int(rng()%65)-32; }
    actual[0]=3;
    Snapshot s;s.policy=TsFixedPrediction::mode();s.poc=trial;s.component=comp;s.qp=cu.qp;s.rice=1+slice.m_tsrcIndex;s.budget=(w*h*7)>>2;
    captureIdentity(s,tu,comp);
    CHECK(s.sliceType!=trial%3 || s.isIntraCu!=int(trial%2) || s.isInterCu!=int(!(trial%2)),"Slice and CU metadata conflated");
    captureGeometry(s,tu,comp);
    OutputBitstream bits;BinEncoder_Std enc;CABACWriter writer(enc,nullptr);writer.initBitstream(&bits);enc.reset(cu.qp,I_SLICE);
    CoeffCodingContext ec(tu,comp,false,cu.getBdpcmMode(comp));ec.remRegBins=s.budget;unsigned riceBits[8]{};
    for(int g=0;g<=ec.lastSubSet();++g) { ec.initSubblock(g,s.g.groupSig[g]);writer.residual_coding_subblockTS(ec,actual,riceBits,s.rice,false); }
    enc.encodeBinTrm(1);enc.finish();bits.writeByteAlignment();
    InputBitstream input;input.getFifo()=bits.getFifo();BinDecoder_Std dec;CABACReader reader(dec,nullptr);reader.initBitstream(&input);dec.reset(cu.qp,I_SLICE);
    s.entry=saveContext(dec.getCtx());dec.tsAudit=&s.native;
    CoeffCodingContext dc(tu,comp,false,cu.getBdpcmMode(comp));dc.remRegBins=s.budget;
    for(int g=0;g<=dc.lastSubSet();++g) { dc.initSubblock(g);s.native.paths.push_back({});reader.residual_coding_subblockTS(dc,decoded.data(),s.rice);s.native.paths.back().end=dc.remRegBins; }
    dec.tsAudit=nullptr;s.exit=saveContext(dec.getCtx());CHECK(s.q!=decoded,"Native decoding changed coefficients");CHECK(dec.decodeBinTrm()!=1,"Native termination mismatch");dec.finish();
    auto d=decisions(s);auto r=replay(s,predictors(d,s.policy==98?3:4));validateNative(s,r);
    if(argc==3 && cu.getBdpcmMode(comp)==BdpcmMode::NONE)
    {
      const auto ch=TsCorpus::choices(s); std::array<uint64_t,10> rates{};
      for(int m=0;m<10;++m) { rates[m]=replay(s,ch.pred[m]).bins.bits; }
      CHECK(rates[s.policy==98?7:5]!=r.bins.bits,"Corpus native control mismatch");
      corpus<<"{\"kind\":\"tu\",\"trial\":"<<trial<<",\"component\":"<<int(comp)<<",\"w\":"<<w<<",\"h\":"<<h
            <<",\"qp\":"<<s.qp<<",\"slice_type\":\""<<sliceName(s.sliceType)<<"\",\"is_intra_cu\":"<<s.isIntraCu
            <<",\"rice\":"<<s.rice<<",\"range\":"<<s.g.range<<",\"rice_cutoff\":"<<COEF_REMAIN_BIN_REDUCTION<<",\"q\":";
      TsCorpus::arr(corpus,s.q);corpus<<",\"scan\":";TsCorpus::arr(corpus,s.g.scan);
      corpus<<",\"pred\":[";for(int m=0;m<10;++m) { if(m) { corpus<<','; } TsCorpus::arr(corpus,ch.pred[m]); }
      corpus<<"],\"rates_frac\":";TsCorpus::arr(corpus,rates);corpus<<"}\n";
      CHECK(!corpus,"Corpus fixture write failed");
    }
    save(s,argv[1]);auto restored=load(argv[1]);auto loaded=replay(restored,predictors(decisions(restored),s.policy==98?3:4));validateNative(restored,loaded);CHECK(loaded.bins.bits!=r.bins.bits,"Offline rate differs");
    CHECK(restored.sliceType!=s.sliceType || restored.isIntraCu!=s.isIntraCu || restored.isInterCu!=s.isInterCu,"Snapshot lost Slice/CU metadata");
    // A disk limit must be checked before creating/truncating the destination.
    const auto missing=std::string(argv[1])+".budget_rejected";
    CHECK(save(s,missing,1) || std::ifstream(missing).good(),"Snapshot disk budget did not fail closed");
    bypass+=std::count_if(s.native.events.begin(),s.native.events.end(),[](auto e){return e.id<0;});
    std::map<int,int> history;
    for(size_t i=0;i<d.size();++i)
    { int hist=0,best=0;for(auto e:history) if(e.second>best) { hist=e.first;best=e.second; }
      CHECK(hist!=d[i].hist,"Historical mode differs from brute force");extended+=d[i].plus.size()>d[i].c0.size();
      if(i%17==0 && d[i].n>=3)
      { auto p=predictors(d,s.policy==98?3:4);std::map<int,uint64_t> actions;
        for(int candidate:d[i].plus) { p[i]=candidate;auto alternative=replay(s,p);const int mapped=TsFixedPrediction::remap(std::abs(s.q[s.g.scan[i]]),candidate);
          if(actions.count(mapped)) { CHECK(actions[mapped]!=alternative.bins.bits,"Same-remapping cache invalid"); } actions[mapped]=alternative.bins.bits; } }
      const int a=std::abs(s.q[s.g.scan[i]]);if(a) { ++history[a]; }
    }
  }
  CHECK(!bypass || !extended || !bdpcm,"Fixture coverage insufficient");destroyROM();
  std::cout<<"PASS native_TU=48 policy="<<TsFixedPrediction::mode()<<" bypass_bins="<<bypass<<" history_extensions="<<extended<<" bdpcm="<<bdpcm<<" sequence_encode_decode=false\n";
}
