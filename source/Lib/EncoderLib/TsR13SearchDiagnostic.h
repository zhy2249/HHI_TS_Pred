// Read-only, bounded encoder search observations for R13 diagnosis.
// Default OFF. No hypothetical coding and no production-state updates.
#pragma once
#include "CommonLib/CodingStructure.h"
#include "CommonLib/Contexts.h"
#include "CommonLib/Picture.h"
#include "CommonLib/UnitPartitioner.h"
#include <cerrno>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <iomanip>
#include <map>
#include <sstream>
#include <string>
#include <vector>

namespace R13SearchDiagnostic
{
inline int option(const char *name, int fallback, int minimum, int maximum)
{
  const char *v=std::getenv(name);
  if(!v || !*v) return fallback;
  char *end=nullptr; errno=0;
  const long n=std::strtol(v,&end,10);
  CHECK(errno || *end || n<minimum || n>maximum,"Invalid R13 search diagnostic option");
  return int(n);
}
struct Options
{
  bool enabled=option("TS_R13_SEARCH_TRACE",0,0,1)!=0;
  int poc=option("TS_R13_SEARCH_POC",16,-1,1000000);
  int ctu=option("TS_R13_SEARCH_CTU",-1,-1,1000000);
  int limit=option("TS_R13_SEARCH_LIMIT",200000,1,10000000);
};
inline const Options &options() { static const Options o; return o; }
inline uint64_t hashValue(uint64_t h,uint64_t v)
{
  for(unsigned s=0;s<64;s+=8) { h^=(v>>s)&255; h*=UINT64_C(1099511628211); }
  return h;
}
template<class T> inline uint64_t bufferHash(const AreaBuf<T> &b)
{
  uint64_t h=UINT64_C(14695981039346656037);
  h=hashValue(h,b.width); h=hashValue(h,b.height);
  for(unsigned y=0;y<b.height;++y) for(unsigned x=0;x<b.width;++x)
    h=hashValue(h,uint64_t(int64_t(b.buf[y*b.stride+x])));
  return h;
}
// Fingerprint of public CABAC probability and adaptation accessors. It is NOT
// a claim to serialize every hidden encoder cache or the arithmetic coder.
inline uint64_t contextHash(const Ctx &ctx)
{
  uint64_t h=UINT64_C(14695981039346656037);
  const auto &models=static_cast<const CtxStore<BinProbModel_Std>&>(ctx);
  for(unsigned i=0;i<ContextSetCfg::NumberOfContexts;++i)
  {
    const auto p=models[i].getState();
    h=hashValue(h,p.first); h=hashValue(h,p.second);
    h=hashValue(h,models[i].state());
    h=hashValue(h,models[i].getFracBitsArray().intBits[0]);
    h=hashValue(h,models[i].getFracBitsArray().intBits[1]);
  }
  std::vector<uint8_t> v,a,b;
  ctx.saveWeights(v); for(auto n:v) h=hashValue(h,n);
  ctx.saveWinSizes(v); for(auto n:v) h=hashValue(h,n);
  ctx.saveRateOffsets(a,b); for(auto n:a) h=hashValue(h,n); for(auto n:b) h=hashValue(h,n);
  for(unsigned i=0;i<RExt__GOLOMB_RICE_ADAPTATION_STATISTICS_SETS;++i) h=hashValue(h,ctx.getGRAdaptStats(i));
  return h;
}
struct Fields
{
  std::ostringstream out;
  Fields() { out<<std::setprecision(17); }
  template<class T> Fields &add(const char *key,T value) { out<<",\""<<key<<"\":"<<+value; return *this; }
  Fields &number(const char *key,double value)
  {
    out<<",\""<<key<<"\":";
    if(std::isfinite(value)) out<<value; else out<<"null";
    return *this;
  }
  Fields &text(const char *key,const std::string &value)
  {
    // Diagnostic strings are internal enum/event/path literals, never user text.
    out<<",\""<<key<<"\":\""<<value<<"\""; return *this;
  }
};
struct Node { unsigned id=0,parent=0; std::string path; std::map<std::string,unsigned> visits; };
struct State
{
  bool active=false,detailed=false,truncated=false;
  int poc=-1,ctu=-1;
  unsigned sequence=0,nodes=0;
  std::vector<Node> stack;
  std::map<std::string,unsigned> roots;
};
inline State &state() { static thread_local State s; return s; }
inline bool active() { return options().enabled && state().active && state().detailed; }
inline void emit(const char *event,const Fields &fields,bool coarse=false)
{
  auto &s=state();
  if(!s.active || (!s.detailed && !coarse)) return;
  if(s.sequence>=unsigned(options().limit))
  {
    if(!s.truncated)
    {
      std::fprintf(stderr,"TS_R13_SEARCH {\"schema\":1,\"event\":\"truncated\",\"poc\":%d,\"ctu\":%d,\"limit\":%d}\n",s.poc,s.ctu,options().limit);
      s.truncated=true;
    }
    return;
  }
  const Node node=s.stack.empty()?Node{}:s.stack.back();
  std::fprintf(stderr,"TS_R13_SEARCH {\"schema\":1,\"seq\":%u,\"event\":\"%s\",\"poc\":%d,\"ctu\":%d,\"node\":%u,\"parent\":%u,\"node_path\":\"%s\"%s}\n",
    ++s.sequence,event,s.poc,s.ctu,node.id,node.parent,node.path.c_str(),fields.out.str().c_str());
}
inline void areaFields(Fields &f,const UnitArea &area,ChannelType channel)
{
  f.add("x",area.lx()).add("y",area.ly()).add("w",area.lwidth()).add("h",area.lheight()).add("channel",int(channel));
}
inline void structureFields(Fields &f,const CodingStructure &cs)
{
  f.number("cost",cs.cost).add("dist",cs.dist).add("frac_bits",cs.fracBits).number("db_offset",cs.costDbOffset).add("cu_count",cs.cus.size());
  if(!cs.cus.empty())
  {
    const auto &cu=*cs.cus.front();
    f.add("pred_mode",int(cu.predMode)).add("qp",cu.qp).add("skip",int(cu.skip)).add("root_cbf",int(cu.rootCbf))
     .add("merge",int(cu.mergeFlag)).add("imv",int(cu.imv)).add("sbt",int(cu.sbtInfo));
  }
}
class CtuScope
{
  bool enabled=false;
  const CodingStructure *coding=nullptr;
  UnitArea region;
public:
  CtuScope(const CodingStructure &cs,const UnitArea &area,unsigned address,const Ctx &ctx)
  {
    const auto &o=options(); if(!o.enabled) return;
    enabled=true; coding=&cs; region=area;
    auto &s=state(); s=State{};
    s.poc=cs.slice->m_poc; s.ctu=int(address);
    s.active=(o.poc<0 || o.poc==s.poc) && (o.ctu<0 || o.ctu==s.ctu);
    s.detailed=o.ctu>=0;
    if(!s.active) return;
    Fields f; areaFields(f,area,ChannelType::LUMA);
    f.add("ctx_hash",contextHash(ctx)).add("slice_qp",cs.slice->m_iSliceQp)
     .add("slice_type",int(cs.slice->m_eSliceType)).add("detailed",int(s.detailed));
    const auto clipped=clipArea(area.Y(),cs.picture->Y());
    f.add("org_y_hash",bufferHash(cs.getOrgBuf(clipped)));
    // Only completed top/left neighbours, never the not-yet-coded CTU buffer.
    const CPelBuf reco=cs.picture->getRecoBuf().Y();
    uint64_t neighbour=UINT64_C(14695981039346656037);
    unsigned count=0;
    if(area.ly()>0)
      for(int x=area.lx();x<int(area.lx()+clipped.width);++x)
      { neighbour=hashValue(neighbour,uint64_t(int64_t(reco.at(x,area.ly()-1)))); ++count; }
    if(area.lx()>0)
      for(int y=area.ly();y<int(area.ly()+clipped.height);++y)
      { neighbour=hashValue(neighbour,uint64_t(int64_t(reco.at(area.lx()-1,y)))); ++count; }
    f.add("completed_neighbour_y_hash",neighbour).add("completed_neighbour_y_samples",count);
    emit("ctu_begin",f,true);
    if(s.detailed)
      for(int l=0;l<2;++l) for(int i=0;i<cs.slice->m_numRefIdx[RefPicList(l)];++i)
      {
        const Picture *ref=cs.slice->getRefPic(RefPicList(l),i);
        Fields r; r.add("list",l).add("index",i).add("ref_poc",ref->m_poc);
        r.add("reco_y_hash",bufferHash(ref->getRecoBuf().Y()));
        if(isChromaEnabled(ref->chromaFormat))
        { r.add("reco_u_hash",bufferHash(ref->getRecoBuf().Cb())).add("reco_v_hash",bufferHash(ref->getRecoBuf().Cr())); }
        emit("ctu_reference",r);
      }
  }
  ~CtuScope()
  {
    if(!enabled) return;
    auto &s=state();
    if(s.active)
    {
      Fields f; f.add("emitted",s.sequence).add("truncated",int(s.truncated));
      const auto clipped=clipArea(region,*coding->picture);
      const CPelUnitBuf reco=coding->picture->getRecoBuf(clipped);
      f.add("reco_y_hash",bufferHash(reco.Y()));
      if(isChromaEnabled(reco.chromaFormat))
      { f.add("reco_u_hash",bufferHash(reco.Cb())).add("reco_v_hash",bufferHash(reco.Cr())); }
      emit("ctu_end",f,true);
    }
    s.active=false;
  }
};
class CuScope
{
  bool enabled=false;
public:
  CuScope(const CodingStructure &cs,const Partitioner &p,const Ctx &ctx)
  {
    if(!active()) return;
    enabled=true; auto &s=state();
    std::ostringstream k; k<<cs.area.lx()<<"_"<<cs.area.ly()<<"_"<<cs.area.lwidth()<<"_"<<cs.area.lheight()<<"_"<<int(p.chType)<<"_"<<p.currDepth;
    auto &visits=s.stack.empty()?s.roots:s.stack.back().visits;
    const unsigned visit=++visits[k.str()];
    Node n; n.id=++s.nodes; n.parent=s.stack.empty()?0:s.stack.back().id;
    n.path=(s.stack.empty()?std::string{}:s.stack.back().path)+"/"+k.str()+"#"+std::to_string(visit);
    s.stack.push_back(n);
    Fields f; areaFields(f,cs.area,p.chType);
    f.add("depth",p.currDepth).add("qt_depth",p.currQtDepth).add("bt_depth",p.currBtDepth)
     .add("mt_depth",p.currMtDepth).add("base_qp",cs.baseQP).add("ctx_hash",contextHash(ctx));
    f.add("org_y_hash",bufferHash(cs.getOrgBuf(clipArea(cs.area.Y(),cs.picture->Y()))));
    emit("cu_begin",f);
  }
  ~CuScope() { if(enabled) { emit("cu_end",Fields{}); state().stack.pop_back(); } }
};
} // namespace R13SearchDiagnostic
