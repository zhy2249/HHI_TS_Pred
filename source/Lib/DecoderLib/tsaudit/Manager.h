#pragma once
#include "CommonLib/Picture.h"
#include "CommonLib/UnitTools.h"
#include "BinTrace.h"
#include <cstdlib>
#include <memory>
#include <fstream>
#if JVET_BJUT_TS_FIXED_PREDICTOR
#include "Replay.h"
#include <filesystem>
namespace TsAudit
{
inline int envInt(const char *key,int fallback,int low,int high)
{ const char *s=std::getenv(key); if(!s || !*s) { return fallback; } char *end=nullptr; const long v=std::strtol(s,&end,10); CHECK(*end || v<low || v>high,"Invalid TS audit option"); return int(v); }
inline std::string envString(const char *key,const std::string &fallback="")
{ const char *s=std::getenv(key); return s?s:fallback; }
inline bool enabled() { static const bool on=!envString("TS_SCORE_AUDIT").empty(); return on; }
template<class V> inline void arrayJson(std::ostream &o,const V &v)
{ o<<'['; bool first=true; for(const auto &a:v) { if(!first) { o<<','; } first=false; o<<a; } o<<']'; }
struct Counts { uint64_t tu=0,coeff=0,nz=0,targetNz=0,targetCoeff=0,bdpcm=0,eligible=0; std::array<uint64_t,5> amplitude{}; std::array<uint64_t,6> support{}; };
struct Manager
{
  std::string root,profile; int first=0,last=INT_MAX,component=-1,quota=2;
  int replayLimit=96,visitLimit=125000; uint64_t seed=20261025;
  int poc=-1,selectionSlot=-1; uint64_t rawBytes=0,snapshotBytes=0,replays=0,visits=0,totalReplays=0,totalVisits=0,audited=0,skipped=0,selected=0;
  uint64_t cachePeak=0,snapshotSkipped=0; bool truncated=false; std::ofstream raw; std::array<Counts,3> counts;
  std::array<std::vector<std::unique_ptr<Snapshot>>,3> slots;
  std::unique_ptr<Snapshot> pending;
  std::set<int> finished;
  int targetX=-1,targetY=-1,targetW=-1,targetH=-1;
  Manager()
  {
    root=envString("TS_SCORE_AUDIT"); profile=envString("TS_AUDIT_PROFILE","standard");
    CHECK(profile!="summary" && profile!="standard" && profile!="detail","Unknown audit profile");
    CHECK(TsFixedPrediction::mode()!=98 && TsFixedPrediction::mode()!=99,"Score audit requires explicitly bound R13 EQ/SP native policy");
    CHECK(TsFixedPrediction::r13DiagnosticScope()!=0,"Audit requires all-component R13 scope");
    first=envInt("TS_AUDIT_FIRST",0,0,INT_MAX); last=envInt("TS_AUDIT_LAST",INT_MAX,first,INT_MAX);
    component=envInt("TS_AUDIT_COMPONENT",-1,-1,2); quota=envInt("TS_AUDIT_TUS",2,1,2);
    replayLimit=envInt("TS_AUDIT_REPLAYS",96,1,96); visitLimit=envInt("TS_AUDIT_VISITS",125000,1,125000);
    seed=envInt("TS_AUDIT_SEED",20261025,0,INT_MAX);
    if(profile=="detail") { std::istringstream in(envString("TS_AUDIT_TU")); char a,b,c; in>>targetX>>a>>targetY>>b>>targetW>>c>>targetH; CHECK(!in || a!=',' || b!=',' || c!=',' || first!=last || component<0,"detail requires one POC, component and x,y,w,h"); }
    std::filesystem::create_directories(root+"/snapshots"); raw.open(root+"/audit.jsonl"); CHECK(!raw,"Cannot open audit output");
  }
  bool accepts(int p,int c) const { return p>=first && p<=last && (component<0 || component==c); }
  void emit(const std::string &line)
  { if(rawBytes+line.size()+1>8*1024*1024) { truncated=true; return; } raw<<line<<'\n'; rawBytes+=line.size()+1; CHECK(!raw,"Audit output write failed"); }
  uint64_t priority(const TransformUnit &tu,CompID c) const
  { uint64_t h=seed; const auto &a=tu.blocks[c]; for(int v:{tu.cu->slice->m_poc,int(c),a.x,a.y,int(a.width),int(a.height)}) { h=hashNumber(h,v); } return h; }
  void frameStart(int p)
  { if(poc==p) { return; } flush(); CHECK(finished.count(p),"Audit does not support interleaved/repeated picture layers"); poc=p; counts={}; replays=visits=0; }
  Native *begin(const TransformUnit &tu,CompID c,const Ctx &ctx)
  {
    const int p=tu.cu->slice->m_poc; if(!accepts(p,int(c))) { return nullptr; }
    frameStart(p); ++counts[c].tu;
    if(tu.cu->getBdpcmMode(c)!=BdpcmMode::NONE) { ++counts[c].bdpcm; return nullptr; }
    const auto &a=tu.blocks[c];
    if(profile=="summary" || (profile=="detail" && (a.x!=targetX || a.y!=targetY || int(a.width)!=targetW || int(a.height)!=targetH))) { return nullptr; }
    ++counts[c].eligible; auto &group=slots[c]; const uint64_t key=priority(tu,c); selectionSlot=int(group.size());
    if(group.size()>=unsigned(quota))
    { selectionSlot=0; for(int i=1;i<quota;++i) if(group[i]->priority>group[selectionSlot]->priority) { selectionSlot=i; }
      if(key>=group[selectionSlot]->priority) { return nullptr; } }
    CHECK(a.area()>4096,"Audit snapshot TU exceeds supported limit");
    pending=std::make_unique<Snapshot>(); auto &s=*pending;
    s.poc=p; s.component=int(c); s.x=a.x; s.y=a.y; s.qp=tu.cu->qp; s.intra=tu.cu->predMode==MODE_INTRA;
    s.policy=TsFixedPrediction::mode(); s.rice=1+(tu.cu->slice->m_sps->m_spsRangeExtension.m_tsrcRicePresentFlag?tu.cu->slice->m_tsrcIndex:0);
    s.budget=(a.area()*7)>>2; s.priority=key; s.entry=saveContext(ctx); return &s.native;
  }
  void end(const TransformUnit &tu,CompID c,const Ctx &ctx)
  {
    if(!accepts(tu.cu->slice->m_poc,int(c))) { return; }
    const auto &a=tu.blocks[c]; const auto *q=tu.getCoeffs(c).buf; auto &pop=counts[c]; pop.coeff+=a.area();
    CoeffCodingContext geom(tu,c,false,tu.cu->getBdpcmMode(c));
    for(int i=0;i<int(a.area());++i)
    { const int v=std::abs(q[i]); pop.nz+=v!=0; if(tu.cu->getBdpcmMode(c)==BdpcmMode::NONE) { pop.targetNz+=v!=0; ++pop.targetCoeff; } ++pop.amplitude[v<3?v:v<5?3:4]; int h[5]; geom.r13SupportTS(i,q,h); int n=0; for(int x:h) { n+=x!=0; } ++pop.support[n]; }
    if(!pending) { return; }
    captureGeometry(*pending,tu,c); pending->exit=saveContext(ctx);
    // Deep serialization/restoration is checked on every retained candidate.
    for(const auto &model:pending->entry) { const auto restored=model.restore(); CHECK(Model(restored).v!=model.v,"Context roundtrip failed"); }
    uint64_t bytes=0;
    auto usage=[](const Snapshot &s) { return uint64_t(sizeof(s))+40*(s.entry.capacity()+s.exit.capacity())+sizeof(Event)*s.native.events.capacity()+sizeof(Path)*s.native.paths.capacity()+4*(s.q.capacity()+s.g.scan.capacity()+s.g.sig.capacity()+s.g.sign.capacity()+s.g.gt1.capacity()+s.g.groupCtx.capacity()+s.g.groupSig.capacity()+s.g.groupCode.capacity()); };
    for(const auto &list:slots)
    {
      for(const auto &item:list) { bytes+=usage(*item); }
    }
    bytes+=usage(*pending);
    cachePeak=std::max(cachePeak,bytes);
    CHECK(bytes>64*1024*1024,"Audit cache exceeds declared supported geometry bound");
    auto &group=slots[c]; if(selectionSlot==int(group.size())) { group.push_back(std::move(pending)); } else { group[selectionSlot]=std::move(pending); }
  }
  bool canReplay(const Snapshot &s) const { return replays<unsigned(replayLimit) && visits+3*s.q.size()<=unsigned(visitLimit); }
  Replay countedReplay(const Snapshot &s,const std::vector<int> &p)
  { CHECK(!canReplay(s),"Audit internal replay budget error"); auto r=replay(s,p); ++replays; ++totalReplays; visits+=r.visits; totalVisits+=r.visits; return r; }
  std::string key(const Snapshot &s) const
  { std::ostringstream o; o<<s.poc<<'_'<<s.component<<'_'<<s.x<<'_'<<s.y<<'_'<<s.g.w<<'_'<<s.g.h; return o.str(); }
  void audit(Snapshot &s)
  {
    ++selected; s.seen=counts[s.component].eligible;
    if(!canReplay(s)) { ++skipped; emit("{\"kind\":\"skip\",\"poc\":"+std::to_string(s.poc)+",\"component\":"+std::to_string(s.component)+",\"reason\":\"replay_budget\"}"); return; }
    auto d=decisions(s); const int native=s.policy==98?3:4; std::array<std::vector<int>,7> p;
    for(int m=0;m<7;++m) { p[m]=predictors(d,m); }
    std::map<std::vector<int>,Replay> cache;
    cache.emplace(p[native],countedReplay(s,p[native])); const auto &nativeReplay=cache.at(p[native]); try { validateNative(s,nativeReplay); } catch(...) { save(s,root+"/invalid_snapshot.tsa"); throw; } ++audited;
    std::array<int64_t,7> rates{}; rates.fill(-1);
    for(int m=0;m<7;++m)
    { auto it=cache.find(p[m]); if(it==cache.end() && canReplay(s)) { it=cache.emplace(p[m],countedReplay(s,p[m])).first; }
      if(it!=cache.end()) { rates[m]=int64_t(it->second.bins.bits); } }
    const auto id=key(s); std::string snapshot="snapshots/"+id+".tsa";
    if(save(s,root+"/"+snapshot,64*1024*1024-snapshotBytes))
    { snapshotBytes+=std::filesystem::file_size(root+"/"+snapshot);
      const auto restored=load(root+"/"+snapshot); CHECK(contextHash(restored.entry)!=contextHash(s.entry) || restored.q!=s.q,"Snapshot roundtrip mismatch"); }
    else { snapshot.clear(); ++snapshotSkipped; }
    std::ostringstream o;
    o<<"{\"kind\":\"tu\",\"id\":\""<<id<<"\",\"poc\":"<<s.poc<<",\"component\":"<<s.component<<",\"x\":"<<s.x<<",\"y\":"<<s.y<<",\"w\":"<<s.g.w<<",\"h\":"<<s.g.h<<",\"qp\":"<<s.qp<<",\"intra\":"<<s.intra<<",\"q_hash\":\""<<s.qHash()<<"\",\"entry_hash\":\""<<contextHash(s.entry)<<"\",\"nz\":"<<std::count_if(s.q.begin(),s.q.end(),[](int v){return v!=0;})<<",\"coeff\":"<<s.q.size()<<",\"tu_population\":"<<s.seen<<",\"tu_selected\":"<<slots[s.component].size()<<",\"native_validated\":true,\"rates_frac\":";
    arrayJson(o,rates); o<<",\"snapshot\":\""<<snapshot<<"\"}"; emit(o.str());
    std::vector<int> eligible,disagreement;
    for(int i=0;i<int(d.size());++i) if(s.q[s.g.scan[i]] && d[i].n>=3)
    { eligible.push_back(i); if(d[i].pred[1]!=d[i].pred[2] || d[i].pred[1]!=d[i].pred[3] || d[i].pred[3]!=d[i].pred[4]) { disagreement.push_back(i); } }
    auto order=[&](int a,int b) { return hashNumber(s.priority,a)<hashNumber(s.priority,b); };
    std::sort(eligible.begin(),eligible.end(),order); std::sort(disagreement.begin(),disagreement.end(),order);
    std::vector<std::pair<int,int>> chosen; for(size_t i=0;i<std::min<size_t>(2,eligible.size());++i) { chosen.emplace_back(eligible[i],0); }
    disagreement.erase(std::remove_if(disagreement.begin(),disagreement.end(),[&](int i){return std::find_if(chosen.begin(),chosen.end(),[&](auto v){return v.first==i;})!=chosen.end();}),disagreement.end());
    for(size_t i=0;i<std::min<size_t>(2,disagreement.size());++i) { chosen.emplace_back(disagreement[i],1); }
    for(auto choice:chosen)
    {
      const int i=choice.first,a=std::abs(s.q[s.g.scan[i]]); const auto &v=d[i];
      std::map<int,std::pair<int64_t,int64_t>> costs;
      auto direct=[&](const Replay &r) { uint64_t n=0; for(const auto &e:r.bins.events) if(e.scan==i) { n+=e.cost; } return int64_t(n); };
      const int nativeMap=TsFixedPrediction::remap(a,v.pred[native]);
      costs[nativeMap]={int64_t(nativeReplay.bins.bits),direct(nativeReplay)};
      bool complete=true;
      for(int candidate:v.plus)
      { int mapped=TsFixedPrediction::remap(a,candidate); if(costs.count(mapped)) { continue; }
        if(!canReplay(s)) { complete=false; break; }
        auto overridden=p[native]; overridden[i]=candidate; auto r=countedReplay(s,overridden); costs[mapped]={int64_t(r.bins.bits),direct(r)}; }
      if(!complete) { ++skipped; emit("{\"kind\":\"point_skip\",\"poc\":"+std::to_string(s.poc)+",\"component\":"+std::to_string(s.component)+",\"scan\":"+std::to_string(i)+",\"reason\":\"replay_budget\"}"); continue; }
      std::vector<int64_t> c0,cp; for(int t:v.c0) { c0.push_back(costs.at(TsFixedPrediction::remap(a,t)).first); } for(int t:v.plus) { cp.push_back(costs.at(TsFixedPrediction::remap(a,t)).first); }
      const auto min0=*std::min_element(c0.begin(),c0.end()),minP=*std::min_element(cp.begin(),cp.end());
      std::array<int64_t,7> actual{},regret{}; for(int m=0;m<7;++m) { actual[m]=costs.at(TsFixedPrediction::remap(a,v.pred[m])).first; regret[m]=actual[m]-(m>=5?minP:min0); }
      const auto eq=costs.at(TsFixedPrediction::remap(a,v.pred[3])),sp=costs.at(TsFixedPrediction::remap(a,v.pred[4]));
      const auto &nativePath=s.native.paths[i>>s.g.logCG];
      const int raster=s.g.scan[i],xx=raster%s.g.w,yy=raster/s.g.w;
      const int missing=(xx==0)+(yy==0)+(!xx || !yy)+(xx<2)+(yy<2);

      std::ostringstream z;
      z<<"{\"kind\":\"point\",\"tu\":\""<<id<<"\",\"poc\":"<<s.poc<<",\"component\":"<<s.component<<",\"scan\":"<<i<<",\"a\":"<<a<<",\"n\":"<<v.n<<",\"intra\":"<<s.intra<<",\"regular_active\":"<<(i<=nativePath.p1)<<",\"pass1_last\":"<<nativePath.p1<<",\"pass2_last\":"<<nativePath.p2<<",\"cg_end_budget\":"<<nativePath.end<<",\"missing_neighbors\":"<<missing<<",\"area\":"<<s.q.size()<<",\"sample\":\""<<(choice.second?"disagreement":"uniform")<<"\",\"position_population\":"<<(choice.second?disagreement.size():eligible.size())<<",\"position_selected\":"<<std::min<size_t>(2,choice.second?disagreement.size():eligible.size())<<",\"tu_population\":"<<s.seen<<",\"tu_selected\":"<<slots[s.component].size()<<",\"H\":";
      arrayJson(z,v.h); z<<",\"c0\":"; arrayJson(z,v.c0); z<<",\"cplus\":"; arrayJson(z,v.plus); z<<",\"scores168\":[";
      for(int m=0;m<7;++m) { if(m) { z<<','; } arrayJson(z,v.score[m]); } z<<"],\"weight_sum\":"; arrayJson(z,v.weights);
      z<<",\"pred\":"; arrayJson(z,v.pred); z<<",\"c0_cost_frac\":"; arrayJson(z,c0); z<<",\"cplus_cost_frac\":"; arrayJson(z,cp);
      z<<",\"cost_frac\":"; arrayJson(z,actual); z<<",\"regret_frac\":"; arrayJson(z,regret);
      z<<",\"distinguishable\":"<<(*std::max_element(c0.begin(),c0.end())!=min0)<<",\"distinguishable_plus\":"<<(*std::max_element(cp.begin(),cp.end())!=minP)<<",\"hist\":"<<v.hist<<",\"hist_count\":"<<v.histCount<<",\"history_nz\":"<<v.historySize<<",\"coverage_frac\":"<<min0-minP<<",\"direct_sp_eq_frac\":"<<sp.second-eq.second<<",\"propagation_sp_eq_frac\":"<<(sp.first-eq.first)-(sp.second-eq.second)<<'}'; emit(z.str());
    }
  }
  void flush()
  {
    if(poc<0) { return; }
    for(int c=0;c<3;++c) for(auto &s:slots[c]) { audit(*s); }
    for(int c=0;c<3;++c) if(accepts(poc,c))
    { const auto &v=counts[c]; std::ostringstream o; o<<"{\"kind\":\"frame\",\"poc\":"<<poc<<",\"component\":"<<c<<",\"tu\":"<<v.tu<<",\"coeff\":"<<v.coeff<<",\"nz\":"<<v.nz<<",\"bdpcm_tu\":"<<v.bdpcm<<",\"target_nz\":"<<v.targetNz<<",\"target_coeff\":"<<v.targetCoeff<<",\"eligible_tu\":"<<v.eligible<<",\"selected_tu\":"<<slots[c].size()<<",\"amplitude\":"; arrayJson(o,v.amplitude); o<<",\"support\":"; arrayJson(o,v.support); o<<'}'; emit(o.str()); }
    for(auto &v:slots) { v.clear(); } finished.insert(poc); poc=-1;
  }
  void finish(bool success)
  {
    if(success) { flush(); } raw.flush();
    std::ofstream o(root+"/native_validation.json");
    o<<"{\"revision\":\""<<revision<<"\",\"valid\":"<<(success?"true":"false")<<",\"native_verified_tu\":"<<audited<<",\"selected_tu\":"<<selected<<",\"skipped_budget\":"<<skipped<<",\"replays\":"<<totalReplays<<",\"coefficient_visits\":"<<totalVisits<<",\"core_truncated\":"<<(truncated?"true":"false")<<",\"cache_peak_bytes\":"<<cachePeak<<",\"snapshot_skipped_budget\":"<<snapshotSkipped<<",\"raw_bytes\":"<<rawBytes<<",\"snapshot_bytes\":"<<snapshotBytes<<"}\n";
    CHECK(!o,"Cannot write audit validation");
  }
};
inline std::unique_ptr<Manager> &storage() { static std::unique_ptr<Manager> value; return value; }
inline Manager &manager() { auto &value=storage(); if(!value) { value=std::make_unique<Manager>(); } return *value; }
inline Native *begin(const TransformUnit &tu,CompID c,const Ctx &ctx) { return enabled()?manager().begin(tu,c,ctx):nullptr; }
inline void end(const TransformUnit &tu,CompID c,const Ctx &ctx) { if(enabled()) { manager().end(tu,c,ctx); } }
inline void finish(bool success)
{
  if(!enabled() || !storage()) { return; }
  if(success) { manager().finish(true); }
  else { try { manager().finish(false); } catch(const std::exception &e) { std::cerr<<"Audit failure manifest: "<<e.what()<<'\n'; } }
}
inline void picture(const Picture &pic)
{
  static const auto hashPath=envString("TS_AUDIT_HASH");
  if(enabled()) { CHECK(pic.m_layerId!=0,"Audit supports only single-layer streams"); }
  if(!hashPath.empty())
  { PictureHash digest; const auto *sps=pic.m_cs->sps; const int chars=calcMD5(pic.getRecoBuf(),digest,sps->m_bitDepths);
    std::ofstream o(hashPath,std::ios::app); o<<pic.m_poc<<','<<hashToString(digest,chars)<<'\n'; CHECK(!o,"Cannot write audit reconstruction hash"); }
  if(enabled() && pic.m_poc>=manager().first && pic.m_poc<=manager().last)
  { manager().frameStart(pic.m_poc); manager().flush(); }
}
}
#else
namespace TsAudit
{
inline bool enabled() { return false; }
inline Native *begin(const TransformUnit &,CompID,const Ctx &) { return nullptr; }
inline void end(const TransformUnit &,CompID,const Ctx &) {}
inline void finish(bool) {}
inline void picture(const Picture &) {}
}
#endif
