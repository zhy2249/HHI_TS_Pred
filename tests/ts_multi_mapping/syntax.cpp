// Local arithmetic TSRC Writer -> Reader fixtures only, never EncoderApp.
// Reader derives actions after restoring causal neighbors in pass 3. Context
// IDs are derived independently from the decoded significance/signs.
#include "DecoderLib/tsaudit/MultiMapping.h"
#include "CommonLib/Rom.h"
#include "EncoderLib/BinEncoder.h"
#include "DecoderLib/BinDecoder.h"
#include <random>
#include <filesystem>
using namespace TsAudit;
using TsMultiMapping::Action;

static std::array<int,5> neighborhood(const CoeffCodingContext &g,int s,const TCoeff *q)
{
  const int w=int(g.width()),pos=g.blockPos(s),x=pos%w,y=pos/w;std::array<int,5> h{};
  const int offsets[]={x?-1:0,y?-w:0,x && y?-1-w:0,x>1?-2:0,y>1?-2*w:0};
  for(int j=0;j<5;++j) if(offsets[j]) { h[j]=int(std::abs(int64_t(q[pos+offsets[j]]))); }
  return h;
}
template<class Choose>
static void readCG(CoeffCodingContext &g,TCoeff *q,int rice,BinDecoder_Std &dec,Choose choose)
{
  const int first=g.minSubPos(),last=g.maxSubPos();bool sig=g.isLastSubSet() && g.noneSigGroup();
  if(!sig) { sig=dec.decodeBin(g.sigGroupCtxId(true)); }
  if(!sig) { if(dec.tsAudit) { dec.tsAudit->paths.push_back({-1,-1,g.remRegBins}); }return; }g.setSigGroup();
  int p1=-1,p2=-1,nz=0;std::vector<int> signs(last-first+1),levels(last-first+1);
  for(int s=first;s<=last && g.remRegBins>=4;++s)
  {
    int flag=!nz && s==last;if(!flag) { flag=dec.decodeBin(g.sigCtxIdAbsTS(s,q));--g.remRegBins; }
    if(flag)
    {
      ++nz;signs[s-first]=dec.decodeBin(g.signCtxIdAbsTS(s,q,g.bdpcm()));--g.remRegBins;
      const int gt=dec.decodeBin(g.lrg1CtxIdAbsTS(s,q,g.bdpcm()));--g.remRegBins;
      int par=0;if(gt) { par=dec.decodeBin(g.parityCtxIdAbsTS());--g.remRegBins; }
      levels[s-first]=1+gt+par;q[g.blockPos(s)]=(signs[s-first]?-1:1)*levels[s-first];
    }p1=s;
  }
  for(int s=first;s<=last && g.remRegBins>=4;++s)
  { for(int c=2;c<=8;c+=2) if(levels[s-first]>=c) { levels[s-first]+=2*dec.decodeBin(g.greaterXCtxIdAbsTS(c/2));--g.remRegBins; }p2=s; }
  for(int s=first;s<=last;++s)
  {
    const int cutoff=s<=p2?10:s<=p1?2:0;int a=levels[s-first];
    if(a>=cutoff)
    { int rem=dec.decodeRemAbsEP(rice,COEF_REMAIN_BIN_REDUCTION,g.maxLog2TrDRange());a+=s<=p1?rem*2:rem;if(a && s>p1) { signs[s-first]=dec.decodeBinEP(); } }
    const auto action=choose(g,s,q);
    if(cutoff && g.bdpcm()==BdpcmMode::NONE) { a=TsMultiMapping::unmap(a,action); }
    q[g.blockPos(s)]=(signs[s-first]?-1:1)*a;
  }
  // Main Reader postpones signs until CG end; for these selectors abs(q) and
  // significance suffice. Prior-CG sign contexts see the same final signed q.
  if(dec.tsAudit) { dec.tsAudit->paths.push_back({p1,p2,g.remRegBins}); }
}

int main(int argc,char **argv)
{
  try {
    if(argc==4 && std::string(argv[1])=="--snapshot")
    {
      const auto s=load(argv[2]);std::vector<int> inverse(s.q.size());for(size_t i=0;i<s.q.size();++i) { inverse[s.g.scan[i]]=i; }
      std::ofstream out(argv[3]);CHECK(!out,"Cannot open snapshot replay receipt");
      out<<"{\"protocol\":\""<<TsMultiMapping::protocol<<"\",\"q_hash\":\""<<s.qHash()<<"\",\"entry_hash\":\""<<contextHash(s.entry)<<"\",\"methods\":[";
      bool comma=false;
      for(const auto &m:TsMultiMapping::methods())
      {
        std::vector<Action> actions;uint64_t hash=14695981039346656037ULL;
        for(size_t i=0;i<s.q.size();++i) { auto a=TsMultiMapping::select(TsMultiAudit::neighborhood(s,i,inverse),m,s.rice,s.g.range).action;actions.push_back(a);hash=hashNumber(hash,a.count);for(int j=0;j<a.count;++j) { hash=hashNumber(hash,a.targets[j]); } }
        auto r=TsMultiAudit::replay(s,actions);if(comma) { out<<','; }comma=true;out<<"{\"mg\":"<<m.mg<<",\"rate_frac\":"<<r.bins.bits<<",\"action_hash\":\""<<hash<<"\",\"exit_hash\":\""<<contextHash(r.exit)<<"\"}";
      }out<<"]}\n";out.close();CHECK(!out,"Cannot save snapshot replay receipt");return 0;
    }
    initROM();XuPool pool;CodingStructure cs(pool);SPS sps;PPS pps;Slice slice;
    sps.m_chromaFormatIdc=ChromaFormat::_420;sps.m_maxCuWidth=sps.m_maxCuHeight=128;sps.m_dualITree=false;
    sps.m_bitDepths[ChannelType::LUMA]=sps.m_bitDepths[ChannelType::CHROMA]=10;
    pps.m_picWidthInLumaSamples=pps.m_picHeightInLumaSamples=128;PreCalcValues pcv(sps,pps,true);
    cs.sps=&sps;cs.pps=&pps;cs.pcv=&pcv;cs.slice=&slice;slice.m_sps=&sps;slice.m_pps=&pps;
    std::mt19937 rng(20261026);uint64_t checked=0,bypass=0,zeroGroups=0,high=0,causal=0;
    for(int trial=0;trial<24;++trial)
    {
      const CompID comp=CompID(trial%3);const int scale=comp==COMP_Y?1:2;
      const int w=1<<(2+trial%3),h=1<<(2+(trial/3)%3),cw=w*scale,ch=h*scale;
      CodingUnit cu(ChromaFormat::_420,Area(0,0,cw,ch));TransformUnit tu(static_cast<const UnitArea&>(cu));
      cu.cs=&cs;cu.slice=&slice;cu.qp=22+trial%16;cu.predMode=trial%2?MODE_INTRA:MODE_INTER;slice.m_eSliceType=SliceType(trial%3);
      cu.bdpcmMode[0]=cu.bdpcmMode[1]=BdpcmMode::NONE;tu.cs=&cs;tu.cu=&cu;tu.mtsIdx[comp]=MtsType::SKIP;
      std::vector<TCoeff> y(cw*ch),u(cw*ch/4),v(cw*ch/4);std::vector<uint8_t> ys(y.size()),us(u.size()),vs(v.size());
      TCoeff *buffers[]={y.data(),u.data(),v.data()};uint8_t *signs[]={ys.data(),us.data(),vs.data()};EnumArray<Pel*,ChannelType> plt{};EnumArray<bool*,ChannelType> run{};tu.init(buffers,signs,plt,run);
      auto *q=tu.getCoeffs(comp).buf;for(int i=0;i<w*h;++i) { q[i]=trial%3==0?(rng()%9?0:1):int(rng()%65)-32; }q[0]=3;
      const int rice=1+trial%8;Snapshot snap;snap.rice=rice;snap.budget=(w*h*7)>>2;captureGeometry(snap,tu,comp);
      if(trial%4==0) { CoeffCodingContext c(tu,comp,false,BdpcmMode::NONE);for(int i=16;i<32 && i<w*h;++i) { q[c.blockPos(i)]=0; }snap.g=Geometry{};captureGeometry(snap,tu,comp); }
      if(trial%5==0) { q[w*h-1]=trial%2?(1<<snap.g.range)-1:-(1<<snap.g.range);++high;snap.g=Geometry{};captureGeometry(snap,tu,comp); }
      for(int method=0;method<22;++method)
      {
        const auto choose=[&](const CoeffCodingContext &g,int s,const TCoeff *data) {
          if(method==21) { Action a;for(int target:{7,1,31,2,9,3}) { a=TsMultiMapping::append(a,target); }return a; }
          return TsMultiMapping::select(neighborhood(g,s,data),TsMultiMapping::methods()[method],rice,g.maxLog2TrDRange()).action;
        };
        std::vector<Action> actions;CoeffCodingContext base(tu,comp,false,BdpcmMode::NONE);
        for(int s=0;s<w*h;++s)
        {
          auto a=choose(base,s,q);actions.push_back(a);
          if(s%11==0) { std::vector<TCoeff> future(q,q+w*h);for(int j=s;j<w*h;++j) { future[base.blockPos(j)]=42; }CHECK(choose(base,s,future.data())!=a,"Current/future affected action");++causal; }
        }
        OutputBitstream bits;BinEncoder_Std enc;enc.init(&bits);enc.reset(cu.qp,slice.m_eSliceType);
        snap.entry=saveContext(enc);CoeffCodingContext ec(tu,comp,false,BdpcmMode::NONE);int budget=snap.budget;Native expected;
        for(int cg=0;cg<=ec.lastSubSet();++cg)
        { ec.initSubblock(cg,snap.g.groupSig[cg]);auto path=TsFixedPrediction::replayRateCG(ec,q,[&](int i){return actions[i];},budget,rice,enc);expected.paths.push_back({path.pass1,path.pass2,budget});zeroGroups+=!snap.g.groupSig[cg]; }
        auto exit=saveContext(enc);enc.encodeBinTrm(1);enc.finish();bits.writeByteAlignment();
        InputBitstream input;input.getFifo()=bits.getFifo();BinDecoder_Std dec;dec.init(&input);dec.reset(cu.qp,slice.m_eSliceType);Native native;dec.tsAudit=&native;
        CoeffCodingContext dc(tu,comp,false,BdpcmMode::NONE);dc.remRegBins=snap.budget;std::vector<TCoeff> decoded(w*h);
        for(int cg=0;cg<=dc.lastSubSet();++cg) { dc.initSubblock(cg);readCG(dc,decoded.data(),rice,dec,choose); }
        dec.tsAudit=nullptr;CHECK(!std::equal(decoded.begin(),decoded.end(),q),"Mapping syntax round trip failed");
        const auto end=saveContext(dec);for(size_t i=0;i<end.size();++i) { CHECK(end[i].v!=exit[i].v,"Syntax exit state mismatch"); }
        // Replay must also match the independently decoded bin trace.
        auto replay=TsMultiAudit::replay(snap,actions);
        CHECK(replay.bins.bits!=native.bits || replay.bins.events.size()!=native.events.size(),"Mapped replay rate mismatch");
        for(size_t i=0;i<native.events.size();++i) { auto a=native.events[i],b=replay.bins.events[i];CHECK(a.id!=b.id || a.value!=b.value || a.cost!=b.cost,"Mapped replay bin mismatch");bypass+=a.id<0; }
        CHECK(replay.bins.paths.size()!=expected.paths.size() || native.paths.size()!=expected.paths.size(),"Path count mismatch");
        for(size_t i=0;i<expected.paths.size();++i) { auto a=native.paths[i],b=replay.bins.paths[i];CHECK(a.p1!=b.p1 || a.p2!=b.p2 || a.end!=b.end,"Reader pass/budget mismatch"); }
        CHECK(dec.decodeBinTrm()!=1,"Termination mismatch");dec.finish();++checked;
      }
    }
    CHECK(!zeroGroups || !bypass || !high || !causal,"Missing fixture coverage");destroyROM();
    std::cout<<"{\"complete\":true,\"syntax_roundtrips\":"<<checked<<",\"bypass_bins\":"<<bypass<<",\"zero_groups\":"<<zeroGroups<<",\"high_amplitude_TU\":"<<high<<",\"causal_perturbations\":"<<causal<<",\"encoder_app_invoked\":false}\n";
  }catch(const std::exception &e) { std::cerr<<e.what()<<'\n';return 1; }
}
