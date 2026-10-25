// R13-DUAL-DECODE-AUDIT-v1. Observation only; no EncoderLib dependency.
#pragma once
#include "CommonLib/CodingStructure.h"
#include "BinTrace.h"
#include "CommonLib/TsRateReplay.h"
#include "CommonLib/TsR13Prediction.h"
#include <fstream>
#include <sstream>
#include <map>
#include <set>
#include <numeric>

namespace TsAudit
{
constexpr const char *revision="R13-DUAL-DECODE-AUDIT-impl1";
constexpr const char *names[]={"CURRENT","STATIC_EQ","STATIC_SP","KEEP_EQ","KEEP_SP","KEEP_EQ_H","KEEP_SP_H"};
inline uint64_t hashNumber(uint64_t h,uint64_t v)
{ for(int i=0;i<8;++i) { h=(h^uint8_t(v))*1099511628211ULL; v>>=8; } return h; }
inline uint64_t hashBytes(const std::string &s)
{ uint64_t h=14695981039346656037ULL; for(unsigned char c:s) { h=(h^c)*1099511628211ULL; } return h; }
struct Model
{
  std::array<unsigned,10> v{}; // state[2], stateUsed[2], window, weight, offset[2], frac[2]
  Model()=default;
  explicit Model(const BinProbModel_Std &p)
  { const auto a=p.getState(),b=p.getStateUsed(); v={a.first,a.second,b.first,b.second,p.getWinSizes(),p.getAdaptRateWeight(),p.getAdaptRateOffset(0),p.getAdaptRateOffset(1),p.estFracBits(0),p.estFracBits(1)}; }
  BinProbModel_Std restore() const
  {
    CHECK(v[0]>32767 || v[1]>32767 || v[2]>32767 || v[3]>32767 ||
      (v[4]>>4)<2 || (v[4]&15)<2 || (v[4]>>4)>9 || (v[4]&15)>9 ||
      (v[5]>>3)>4 || (v[5]&7)>4 || v[6]>255 || v[7]>255,"Invalid audit probability fields");
    BinProbModel_Std p; p.setState({v[0],v[1]}); p.setStateUsed({v[2],v[3]});
    p.setWinSizes(v[4]); p.setAdaptRateWeight(v[5]); p.setAdaptRateOffset(v[6],0); p.setAdaptRateOffset(v[7],1);
    CHECK(p.estFracBits(0)!=v[8] || p.estFracBits(1)!=v[9],"Audit probability snapshot cannot reproduce fractional bits");
    return p;
  }
};
using Models=std::vector<Model>;
inline Models saveContext(const Ctx &ctx)
{ Models out; const auto &s=static_cast<const CtxStore<BinProbModel_Std>&>(ctx); for(unsigned i=0;i<ContextSetCfg::NumberOfContexts;++i) { out.emplace_back(s[i]); } return out; }
inline uint64_t contextHash(const Models &m)
{ uint64_t h=14695981039346656037ULL; for(const auto &p:m) for(auto v:p.v) { h=hashNumber(h,v); } return h; }
struct Geometry
{
  int w=0,h=0,logCG=0,range=0,bd=0,cg=0,parity=0;
  std::array<int,4> gt{};
  std::vector<int> scan,sig,sign,gt1,groupCtx,groupSig,groupCode;
  int minSubPos() const { return cg<<logCG; }
  int maxSubPos() const { return ((cg+1)<<logCG)-1; }
  bool isLastSubSet() const { return cg+1==int(groupSig.size()); }
  bool only1stSigGroup() const { return !groupCode[cg]; }
  bool isSigGroup() const { return groupSig[cg]; }
  unsigned sigGroupCtxId(bool) const { return groupCtx[cg]; }
  BdpcmMode bdpcm() const { return BdpcmMode(bd); }
  int blockPos(int s) const { return scan[s]; }
  int sigCtxIdAbsTS(int s,const TCoeff *) const { return sig[s]; }
  int signCtxIdAbsTS(int s,const TCoeff *,BdpcmMode) const { return sign[s]; }
  int lrg1CtxIdAbsTS(int s,const TCoeff *,BdpcmMode) const { return gt1[s]; }
  int parityCtxIdAbsTS() const { return parity; }
  int greaterXCtxIdAbsTS(int i) const { return gt[i-1]; }
  int maxLog2TrDRange() const { return range; }
};
struct Snapshot
{
  int poc=0,component=0,x=0,y=0,qp=0,intra=0,policy=0,rice=1,budget=0,population=0;
  uint64_t priority=0,seen=0; // priority is determined without q or method outcomes
  Geometry g;
  std::vector<TCoeff> q;
  Models entry,exit;
  Native native;
  uint64_t qHash() const { uint64_t h=14695981039346656037ULL; for(auto v:q) { h=hashNumber(h,int64_t(v)); } return h; }
};
inline void captureGeometry(Snapshot &s,const TransformUnit &tu,CompID comp)
{
  CoeffCodingContext c(tu,comp,false,tu.cu->getBdpcmMode(comp)); auto &g=s.g;
  g.w=c.width(); g.h=c.height(); g.logCG=c.log2CGSize(); g.range=c.maxLog2TrDRange(); g.bd=int(c.bdpcm());
  g.parity=c.parityCtxIdAbsTS(); for(int i=0;i<4;++i) { g.gt[i]=c.greaterXCtxIdAbsTS(i+1); }
  const int count=g.w*g.h; const auto *q=tu.getCoeffs(comp).buf; s.q.assign(q,q+count);
  std::bitset<MLS_GRP_NUM> groups;
  for(int i=0;i<count;++i) { if(q[c.blockPos(i)]) { groups.set(i>>g.logCG); } }
  for(int k=0;k<count>>g.logCG;++k)
  {
    c.initSubblock(k,groups[k]);
    g.groupCtx.push_back(c.sigGroupCtxId(true)); g.groupSig.push_back(groups[k]);
    g.groupCode.push_back(!c.isLastSubSet() || !c.only1stSigGroup());
    for(int i=c.minSubPos();i<=c.maxSubPos();++i)
    { g.scan.push_back(c.blockPos(i)); g.sig.push_back(c.sigCtxIdAbsTS(i,q)); g.sign.push_back(c.signCtxIdAbsTS(i,q,c.bdpcm())); g.gt1.push_back(c.lrg1CtxIdAbsTS(i,q,c.bdpcm())); }
  }
}
struct Sink
{
  std::vector<BinProbModel_Std> ctx;
  Native result;
  int scan=-1,pass=0;
  uint64_t visits=0;
  explicit Sink(const Models &m) { for(const auto &p:m) { ctx.push_back(p.restore()); } }
  void position(int s,int p) { scan=s; pass=p; visits+=(s>=0); }
  void put(int id,unsigned b,unsigned cost) { result.bin(id,b,cost); auto &e=result.events.back(); e.scan=scan; e.pass=pass; }
  void encodeBin(unsigned b,unsigned id) { CHECK(id>=ctx.size(),"Invalid audit context id"); put(id,b,ctx[id].estFracBits(b)); ctx[id].update(b); }
  void encodeBinEP(unsigned b) { put(-1,b,32768); }
  void ep(unsigned v,unsigned n) { CHECK(n>32,"Invalid audit EP length"); for(int i=int(n)-1;i>=0;--i) { encodeBinEP((v>>i)&1); } }
  void encodeRemAbsEP(unsigned value,unsigned rice,unsigned cutoff,int range)
  {
    if(value<(cutoff<<rice)) { unsigned n=(value>>rice)+1; ep((1u<<n)-2,n); ep(value&((1u<<rice)-1),rice); return; }
    unsigned cap=32-cutoff-range,p=0,code=(value>>rice)-cutoff,len;
    if(code>=((1u<<cap)-1)) { p=cap; len=range; }
    else { while(code>((2u<<p)-2)) { ++p; } len=p+rice+1; }
    ep((1u<<(p+cutoff))-1,p+cutoff);
    ep(((code-((1u<<p)-1))<<rice)|(value&((1u<<rice)-1)),len);
  }
};
struct Replay { Native bins; Models exit; uint64_t visits=0; };
inline Replay replay(const Snapshot &s,const std::vector<int> &p)
{
  CHECK(p.size()!=s.q.size(),"Predictor sequence length mismatch");
  Geometry g=s.g; Sink sink(s.entry); int budget=s.budget;
  for(g.cg=0;g.cg<int(g.groupSig.size());++g.cg)
  { auto path=TsFixedPrediction::replayRateCG(g,s.q.data(),[&](int i){return p[i];},budget,s.rice,sink); sink.result.paths.push_back({path.pass1,path.pass2,budget}); }
  Replay out; out.bins=std::move(sink.result); out.visits=sink.visits;
  for(const auto &c:sink.ctx) { out.exit.emplace_back(c); } return out;
}
inline void validateNative(const Snapshot &s,const Replay &r)
{
  CHECK(r.bins.bits!=s.native.bits || r.bins.events.size()!=s.native.events.size() || r.bins.paths.size()!=s.native.paths.size(),"Native/replay rate or event count mismatch");
  for(size_t i=0;i<r.bins.events.size();++i)
  { const auto &a=r.bins.events[i],&b=s.native.events[i]; CHECK(a.id!=b.id || a.value!=b.value || a.cost!=b.cost,"Native/replay bin order/value/context/cost mismatch"); }
  for(size_t i=0;i<r.bins.paths.size();++i)
  { const auto &a=r.bins.paths[i],&b=s.native.paths[i]; CHECK(a.p1!=b.p1 || a.p2!=b.p2 || a.end!=b.end,"Native/replay pass or budget mismatch"); }
  CHECK(s.exit.size()!=r.exit.size(),"Exit context length mismatch");
  for(size_t i=0;i<s.exit.size();++i) { CHECK(s.exit[i].v!=r.exit[i].v,"Native/replay exit probability state mismatch"); }
}
struct Decision
{
  std::array<int,5> h{};
  int n=0,hist=0,histCount=0,historySize=0;
  std::vector<int> c0,plus;
  std::array<int,7> pred{},weights{};
  std::array<std::vector<int64_t>,7> score;
};
inline std::vector<Decision> decisions(const Snapshot &s)
{
  using namespace TsFixedPrediction;
  std::vector<Decision> out; std::map<int,int> frequencies; int hist=0,bestCount=0,historySize=0;
  std::vector<int> inverse(s.q.size()); for(size_t i=0;i<s.g.scan.size();++i) { inverse[s.g.scan[i]]=i; }
  for(size_t i=0;i<s.q.size();++i)
  {
    Decision d; const int pos=s.g.scan[i],x=pos%s.g.w,y=pos/s.g.w;
    int offsets[5]={x? -1:0,y? -s.g.w:0,x&&y?-1-s.g.w:0,x>1?-2:0,y>1?-2*s.g.w:0};
    for(int j=0;j<5;++j) if(offsets[j]) { CHECK(inverse[pos+offsets[j]]>=int(i),"Noncausal snapshot scan"); d.h[j]=std::abs(s.q[pos+offsets[j]]); d.n+=d.h[j]!=0; }
    d.hist=hist; d.histCount=bestCount; d.historySize=historySize;
    const int current=std::max(d.h[0],d.h[1]);
    d.c0.push_back(current>1?current:0);
    if(d.n>=3)
    { if(current>1) { d.c0.push_back(0); } std::set<int> values(d.h.begin(),d.h.end()); for(int a:values) if(a>1 && a!=current) { d.c0.push_back(a); } }
    d.plus=d.c0;
    if(d.n>=3 && hist>1 && std::find(d.plus.begin(),d.plus.end(),hist)==d.plus.end()) { d.plus.push_back(hist); }
    CHECK(d.plus.size()>7,"Historical candidate capacity exceeded");
    d.pred.fill(current);
    for(int mode=1;mode<7;++mode)
    {
      if(d.n<3) { continue; }
      const bool spatial=mode==2 || mode==4 || mode==6;
      const auto &candidates=mode>=5?d.plus:d.c0; int64_t best=INT64_MAX;
      for(int p:candidates)
      {
        int64_t score=0;
        for(int j=0;j<5;++j) if(d.h[j])
        {
          const int w=spatial && j<2?2:1;
          score+=w*(mode<=2 ? int64_t(168)*syntaxCost(remap(d.h[j],p),s.rice,s.g.range) : r13Loss168(d.h[j],p,s.rice,s.g.range));
        }
        d.score[mode].push_back(score); if(score<best) { best=score; d.pred[mode]=p; }
      }
      for(int j=0;j<5;++j) if(d.h[j]) { d.weights[mode]+=spatial && j<2?2:1; }
    }
    int h[5]; std::copy(d.h.begin(),d.h.end(),h);
    CHECK(d.pred[3]!=r13Predict(1,h,s.rice,s.g.range) || d.pred[4]!=r13Predict(2,h,s.rice,s.g.range),"Audit changed R13 predictor rules");
    out.push_back(d);
    const int a=std::abs(s.q[pos]); if(a) { ++historySize; const int count=++frequencies[a]; if(count>bestCount || (count==bestCount && a<hist)) { hist=a; bestCount=count; } }
  }
  return out;
}
inline std::vector<int> predictors(const std::vector<Decision> &d,int policy)
{ std::vector<int> p; for(const auto &v:d) { p.push_back(v.pred[policy]); } return p; }

// Portable ASCII decimal fields with a checksum over the exact payload bytes.
// No object representations, pointers, padding, locale-dependent floats or ABI.
inline bool save(const Snapshot &s,const std::string &path,uint64_t maxBytes=UINT64_MAX)
{
  std::ostringstream o; const auto &g=s.g;
  o<<s.poc<<' '<<s.component<<' '<<s.x<<' '<<s.y<<' '<<s.qp<<' '<<s.intra<<' '<<s.policy<<' '<<s.rice<<' '<<s.budget<<' '<<s.population<<' '<<s.priority<<' '<<s.seen<<'\n';
  o<<g.w<<' '<<g.h<<' '<<g.logCG<<' '<<g.range<<' '<<g.bd<<' '<<g.parity<<' '; for(auto v:g.gt) { o<<v<<' '; } o<<'\n';
  auto vec=[&](const auto &v) { o<<v.size()<<' '; for(auto a:v) { o<<a<<' '; } o<<'\n'; };
  vec(s.q); vec(g.scan); vec(g.sig); vec(g.sign); vec(g.gt1); vec(g.groupCtx); vec(g.groupSig); vec(g.groupCode);
  for(const auto *v:{&s.entry,&s.exit}) { o<<v->size()<<'\n'; for(const auto &p:*v) { for(auto a:p.v) { o<<a<<' '; } o<<'\n'; } }
  o<<s.native.bits<<' '<<s.native.events.size()<<'\n'; for(const auto &e:s.native.events) { o<<e.id<<' '<<e.value<<' '<<e.cost<<'\n'; }
  o<<s.native.paths.size()<<'\n'; for(const auto &p:s.native.paths) { o<<p.p1<<' '<<p.p2<<' '<<p.end<<'\n'; }
  const auto payload=o.str(); std::ostringstream header;
  header<<"TSAUDIT 1 "<<payload.size()<<' '<<hashBytes(payload)<<'\n';
  // Test the exact serialized length before opening a file. A large TU must
  // never exceed the disk budget merely because the preceding file was small.
  if(header.str().size()+payload.size()>maxBytes) { return false; }
  std::ofstream file(path,std::ios::binary); file<<header.str()<<payload;
  file.close(); CHECK(!file,"Cannot write audit snapshot"); return true;
}
inline Snapshot load(const std::string &path)
{
  std::ifstream file(path,std::ios::binary); std::string magic; unsigned version; uint64_t length,checksum;
  CHECK(!(file>>magic>>version>>length>>checksum) || magic!="TSAUDIT" || version!=1 || length>8*1024*1024,"Invalid audit snapshot header");
  CHECK(file.get()!='\n',"Invalid snapshot delimiter"); std::string payload(length,'\0'); file.read(&payload[0],length);
  CHECK(uint64_t(file.gcount())!=length || file.peek()!=EOF || hashBytes(payload)!=checksum,"Audit snapshot checksum/length mismatch");
  std::istringstream in(payload); Snapshot s; auto &g=s.g;
  in>>s.poc>>s.component>>s.x>>s.y>>s.qp>>s.intra>>s.policy>>s.rice>>s.budget>>s.population>>s.priority>>s.seen;
  in>>g.w>>g.h>>g.logCG>>g.range>>g.bd>>g.parity; for(auto &v:g.gt) { in>>v; }
  CHECK(g.w<1 || g.h<1 || g.w>64 || g.h>64 || g.w*g.h>4096 || g.logCG<0 || g.logCG>4 || g.range<8 || g.range>20 || s.rice<0 || s.rice>8 || s.component<0 || s.component>2 || (s.policy!=98 && s.policy!=99) || s.budget!=(g.w*g.h*7)>>2,"Unsupported audit snapshot geometry/policy");
  auto vec=[&](auto &v,int expected) { unsigned n=0; in>>n; CHECK(n!=unsigned(expected),"Invalid snapshot vector size"); v.resize(n); for(auto &a:v) { in>>a; } };
  const int n=g.w*g.h,cgs=n>>g.logCG;
  vec(s.q,n); vec(g.scan,n); vec(g.sig,n); vec(g.sign,n); vec(g.gt1,n); vec(g.groupCtx,cgs); vec(g.groupSig,cgs); vec(g.groupCode,cgs);
  std::set<int> positions(g.scan.begin(),g.scan.end()); CHECK(positions.size()!=unsigned(n) || *positions.begin()!=0 || *positions.rbegin()!=n-1,"Invalid audit scan permutation");
  for(auto *v:{&s.entry,&s.exit}) { unsigned count=0; in>>count; CHECK(count!=ContextSetCfg::NumberOfContexts,"Snapshot/software context schema differs"); v->resize(count); for(auto &p:*v) { for(auto &a:p.v) { in>>a; } p.restore(); } }
  for(const auto *v:{&g.sig,&g.sign,&g.gt1,&g.groupCtx}) for(int id:*v) { CHECK(id<0 || unsigned(id)>=ContextSetCfg::NumberOfContexts,"Invalid context index"); }
  for(int id:g.gt) { CHECK(id<0 || unsigned(id)>=ContextSetCfg::NumberOfContexts,"Invalid greater context index"); }
  CHECK(g.parity<0 || unsigned(g.parity)>=ContextSetCfg::NumberOfContexts,"Invalid parity context index");
  for(auto a:s.q) { CHECK(a<-(1<<g.range) || a>=(1<<g.range),"Invalid snapshot coefficient"); }
  for(int v:g.groupSig) { CHECK(v!=0 && v!=1,"Invalid CG flag"); }
  size_t count=0; in>>s.native.bits>>count; CHECK(count>131072,"Snapshot bin limit exceeded");
  s.native.events.resize(count); uint64_t bits=0;
  for(auto &e:s.native.events) { in>>e.id>>e.value>>e.cost; CHECK(e.value>1 || e.id< -1 || e.id>=int(s.entry.size()),"Invalid snapshot bin"); bits+=e.cost; }
  CHECK(bits!=s.native.bits,"Invalid snapshot bin total"); in>>count; CHECK(count!=unsigned(cgs),"Invalid snapshot pass count");
  s.native.paths.resize(count); for(auto &p:s.native.paths) { in>>p.p1>>p.p2>>p.end; }
  CHECK(!in,"Truncated snapshot fields"); std::string extra; CHECK(bool(in>>extra),"Extra snapshot fields"); return s;
}
}
