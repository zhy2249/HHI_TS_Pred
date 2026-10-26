#pragma once
#include "CommonLib/Picture.h"
#include "CommonLib/UnitTools.h"
#include "BinTrace.h"
#include <cstdlib>
#include <memory>
#include <fstream>
#if JVET_BJUT_TS_FIXED_PREDICTOR
#include "Replay.h"
#include "Corpus.h"
#if JVET_BJUT_TS_R15_ANALYSIS
#include "MultiMapping.h"
#endif
#include "Budget.h"
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

struct Counts
{
  uint64_t tu=0,coeff=0,nz=0,targetNz=0,targetCoeff=0,bdpcm=0,eligible=0;
  uint64_t eligibleCoeff=0,eligibleNz=0,scoringTu=0,scoringNz=0,samplingPopulation=0,unsupported=0,captureSkipped=0;
  std::array<uint64_t,5> amplitude{};
  std::array<uint64_t,6> support{};
  std::array<uint64_t,12> sliceCu{}; // [B,P,I,L] x [intra,inter,other]
};
struct Coverage
{
  uint64_t selected=0,native=0,fullPolicy=0,snapshots=0,selectedCoeff=0,selectedNz=0;
  std::array<uint64_t,7> policy{};
  std::array<uint64_t,2> requested{},done{}; // uniform, then disagreement-enriched
  uint64_t nativeSkipped=0,policySkipped=0,pointSkipped=0,snapshotSkipped=0,replays=0,visits=0;
};
inline void coverageJson(std::ostream &o,const Coverage &v)
{
  o<<"{\"selected_tu\":"<<v.selected<<",\"selected_coeff\":"<<v.selectedCoeff<<",\"selected_nz\":"<<v.selectedNz
   <<",\"native_verified_tu\":"<<v.native<<",\"all_policy_tu\":"<<v.fullPolicy<<",\"policy_done_tu\":";
  arrayJson(o,v.policy); o<<",\"point_requested\":"; arrayJson(o,v.requested); o<<",\"point_done\":"; arrayJson(o,v.done);
  o<<",\"snapshots_saved\":"<<v.snapshots<<",\"native_skipped_budget\":"<<v.nativeSkipped
   <<",\"policy_group_skipped_budget\":"<<v.policySkipped<<",\"point_skipped_budget\":"<<v.pointSkipped
   <<",\"snapshot_skipped_budget\":"<<v.snapshotSkipped<<",\"replays\":"<<v.replays<<",\"coefficient_visits\":"<<v.visits<<'}';
}
struct Manager
{
  std::string root,profile;
  int first=0,last=INT_MAX,component=-1,quota=2,replayLimit=96,visitLimit=125000;
  uint64_t seed=20261025,rawLimit=8*1024*1024,snapshotLimit=64*1024*1024;
  int poc=-1,selectionSlot=-1,targetX=-1,targetY=-1,targetW=-1,targetH=-1;
  uint64_t rawBytes=0,snapshotBytes=0,cachePeak=0,outputDropped=0,captureSkippedTotal=0;
  std::array<uint64_t,3> componentSnapshotBytes{};
  bool truncated=false;
  std::ofstream raw;
  std::array<Counts,3> counts;
  std::array<Coverage,3> coverage,total;
  std::map<std::string,uint64_t> dropped;
  std::array<std::vector<std::unique_ptr<Snapshot>>,3> slots;
  std::unique_ptr<Snapshot> pending;
  std::set<int> finished;
  Budget budget;
  Manager()
  {
    root=envString("TS_SCORE_AUDIT"); profile=envString("TS_AUDIT_PROFILE","standard");
    CHECK(profile!="summary" && profile!="standard" && profile!="detail","Unknown audit profile");
    CHECK(TsFixedPrediction::mode()!=98 && TsFixedPrediction::mode()!=99,"Score audit requires explicitly bound R13 EQ/SP native policy");
    CHECK(TsFixedPrediction::r13DiagnosticScope()!=0,"Audit requires all-component R13 scope");
    first=envInt("TS_AUDIT_FIRST",0,0,INT_MAX); last=envInt("TS_AUDIT_LAST",INT_MAX,first,INT_MAX);
    component=envInt("TS_AUDIT_COMPONENT",-1,-1,2); quota=envInt("TS_AUDIT_TUS",2,1,2);
    replayLimit=envInt("TS_AUDIT_REPLAYS",96,0,96); visitLimit=envInt("TS_AUDIT_VISITS",125000,0,125000);
    rawLimit=envInt("TS_AUDIT_RAW_BYTES",int(rawLimit),0,int(rawLimit));
    snapshotLimit=envInt("TS_AUDIT_SNAPSHOT_BYTES",int(snapshotLimit),0,int(snapshotLimit));
    seed=envInt("TS_AUDIT_SEED",20261025,0,INT_MAX);
    if(profile=="detail")
    { std::istringstream in(envString("TS_AUDIT_TU")); char a,b,c; in>>targetX>>a>>targetY>>b>>targetW>>c>>targetH;
      CHECK(!in || a!=',' || b!=',' || c!=',' || first!=last || component<0,"detail requires one POC, component and x,y,w,h"); }
    std::filesystem::create_directories(root+"/snapshots"); raw.open(root+"/audit.jsonl"); CHECK(!raw,"Cannot open audit output");
  }
  bool accepts(int p,int c) const { return p>=first && p<=last && (component<0 || component==c); }
  bool eligible(const TransformUnit &tu,CompID c) const
  {
    const auto &a=tu.blocks[c]; const int range=tu.cs->sps->getMaxLog2TrDynamicRange(toChannelType(c));
    return tu.cu->getBdpcmMode(c)==BdpcmMode::NONE && a.width<=64 && a.height<=64 && a.area()<=4096 && range>=8 && range<=20;
  }
  void emit(const std::string &line,const std::string &kind)
  {
    if(rawBytes+line.size()+1>rawLimit) { truncated=true; ++outputDropped; ++dropped[kind]; return; }
    raw<<line<<'\n'; rawBytes+=line.size()+1; CHECK(!raw,"Audit output write failed");
  }
  uint64_t priority(const TransformUnit &tu,CompID c) const
  {
    uint64_t h=seed; const auto &a=tu.blocks[c];
    for(int v:{tu.cu->slice->m_poc,int(c),a.x,a.y,int(a.width),int(a.height)}) { h=hashNumber(h,v); }
    return sampleHash(h);
  }
  void frameStart(int p)
  {
    if(poc==p) { return; }
    flush(); CHECK(finished.count(p),"Audit does not support interleaved/repeated picture layers");
    poc=p; counts={}; coverage={};
  }
  Native *begin(const TransformUnit &tu,CompID c,const Ctx &ctx)
  {
    const int p=tu.cu->slice->m_poc; if(!accepts(p,int(c))) { return nullptr; }
    frameStart(p); auto &pop=counts[c]; ++pop.tu;
    const int slice=tu.cu->slice->m_eSliceType;
    CHECK(slice<0 || slice>=NUMBER_OF_SLICE_TYPES,"Invalid actual Slice type");
    ++pop.sliceCu[3*slice+(tu.cu->predMode==MODE_INTRA?0:tu.cu->predMode==MODE_INTER?1:2)];
    if(tu.cu->getBdpcmMode(c)!=BdpcmMode::NONE) { ++pop.bdpcm; return nullptr; }
    if(!eligible(tu,c)) { ++pop.unsupported; return nullptr; }
    ++pop.eligible; // Full cheap census, independent of summary/detail/sampling.
    const auto &a=tu.blocks[c];
    if(profile=="detail" && (a.x!=targetX || a.y!=targetY || int(a.width)!=targetW || int(a.height)!=targetH)) { return nullptr; }
    ++pop.samplingPopulation;
    if(profile=="summary") { return nullptr; }
    auto &group=slots[c]; const uint64_t key=priority(tu,c); selectionSlot=int(group.size());
    if(group.size()>=unsigned(quota))
    {
      selectionSlot=0; for(int i=1;i<quota;++i) if(group[i]->priority>group[selectionSlot]->priority) { selectionSlot=i; }
      if(key>=group[selectionSlot]->priority) { return nullptr; }
    }
    pending=std::make_unique<Snapshot>(); auto &s=*pending;
    captureIdentity(s,tu,c);
    s.policy=TsFixedPrediction::mode(); s.rice=1+(tu.cu->slice->m_sps->m_spsRangeExtension.m_tsrcRicePresentFlag?tu.cu->slice->m_tsrcIndex:0);
    s.budget=(a.area()*7)>>2; s.priority=key; s.entry=saveContext(ctx); return &s.native;
  }
  void end(const TransformUnit &tu,CompID c,const Ctx &ctx)
  {
    if(!accepts(tu.cu->slice->m_poc,int(c))) { return; }
    const auto &a=tu.blocks[c]; const auto *q=tu.getCoeffs(c).buf; auto &pop=counts[c]; pop.coeff+=a.area();
    const bool target=tu.cu->getBdpcmMode(c)==BdpcmMode::NONE, valid=eligible(tu,c); bool scoring=false;
    CoeffCodingContext geom(tu,c,false,tu.cu->getBdpcmMode(c));
    for(int i=0;i<int(a.area());++i)
    {
      const int v=std::abs(q[geom.blockPos(i)]); pop.nz+=v!=0;
      if(target) { pop.targetNz+=v!=0; ++pop.targetCoeff; }
      if(valid) { pop.eligibleNz+=v!=0; ++pop.eligibleCoeff; }
      ++pop.amplitude[v<3?v:v<5?3:4];
      int h[5]; geom.r13SupportTS(i,q,h); int n=0; for(int x:h) { n+=x!=0; } ++pop.support[n];
      if(valid && v && n>=3) { scoring=true; ++pop.scoringNz; }
    }
    pop.scoringTu+=scoring;
    if(!pending) { return; }
    captureGeometry(*pending,tu,c); pending->exit=saveContext(ctx);
    for(const auto &model:pending->entry) { CHECK(Model(model.restore()).v!=model.v,"Context roundtrip failed"); }
    auto usage=[](const Snapshot &s)
    { return uint64_t(sizeof(s))+40*(s.entry.capacity()+s.exit.capacity())+sizeof(Event)*s.native.events.capacity()+sizeof(Path)*s.native.paths.capacity()+4*(s.q.capacity()+s.g.scan.capacity()+s.g.sig.capacity()+s.g.sign.capacity()+s.g.gt1.capacity()+s.g.groupCtx.capacity()+s.g.groupSig.capacity()+s.g.groupCode.capacity()); };
    uint64_t bytes=usage(*pending); for(const auto &list:slots) for(const auto &item:list) { bytes+=usage(*item); }
    cachePeak=std::max(cachePeak,bytes);
    if(bytes>64*1024*1024) { ++pop.captureSkipped; ++captureSkippedTotal; pending.reset(); return; }
    auto &group=slots[c]; if(selectionSlot==int(group.size())) { group.push_back(std::move(pending)); } else { group[selectionSlot]=std::move(pending); }
  }
  Replay countedReplay(const Snapshot &s,const std::vector<int> &p)
  {
    CHECK(!budget.fits(1,s.q.size()),"Audit internal replay budget error"); auto r=replay(s,p);
    ++budget.replays; budget.visits+=r.visits;
    ++coverage[s.component].replays; coverage[s.component].visits+=r.visits; return r;
  }
  std::string key(const Snapshot &s) const
  { std::ostringstream o; o<<s.poc<<'_'<<s.component<<'_'<<s.x<<'_'<<s.y<<'_'<<s.g.w<<'_'<<s.g.h; return o.str(); }
  void audit(Snapshot &s)
  {
    auto &cv=coverage[s.component]; ++cv.selected; cv.selectedCoeff+=s.q.size();
    const auto nz=std::count_if(s.q.begin(),s.q.end(),[](int v){return v!=0;}); cv.selectedNz+=nz;
    s.seen=counts[s.component].samplingPopulation;
    auto d=decisions(s); const int native=s.policy==98?3:4; std::array<std::vector<int>,7> p;
    for(int m=0;m<7;++m) { p[m]=predictors(d,m); }
    std::map<std::vector<int>,Replay> cache;
    if(budget.fits(1,s.q.size()))
    {
      cache.emplace(p[native],countedReplay(s,p[native]));
      try { validateNative(s,cache.at(p[native])); } catch(...) { save(s,root+"/invalid_snapshot.tsa"); throw; }
      ++cv.native;
    }
    else { ++cv.nativeSkipped; }
    const bool nativeDone=!cache.empty();
    std::set<std::vector<int>> missing;
    for(const auto &v:p) if(!cache.count(v)) { missing.insert(v); }
    // Reserve the whole method family before replaying any alternative. Order
    // changes cannot favor an early policy when resources run out.
    const bool policyDone=nativeDone && budget.fits(missing.size(),s.q.size());
    if(policyDone) { for(const auto &v:missing) { cache.emplace(v,countedReplay(s,v)); } ++cv.fullPolicy; }
    else { ++cv.policySkipped; }
    std::array<int64_t,7> rates; rates.fill(-1);
    for(int m=0;m<7;++m) if(cache.count(p[m])) { rates[m]=int64_t(cache.at(p[m]).bins.bits); ++cv.policy[m]; }
    const auto id=key(s); std::string snapshot="snapshots/"+id+".tsa";
    const uint64_t componentDiskLimit=equalShare(snapshotLimit,3,s.component);
    const bool snapshotDone=save(s,root+"/"+snapshot,componentDiskLimit-componentSnapshotBytes[s.component]);
    if(snapshotDone)
    {
      const auto bytes=std::filesystem::file_size(root+"/"+snapshot);
      snapshotBytes+=bytes; componentSnapshotBytes[s.component]+=bytes; ++cv.snapshots;
      const auto restored=load(root+"/"+snapshot);
      CHECK(contextHash(restored.entry)!=contextHash(s.entry) || restored.q!=s.q || restored.sliceType!=s.sliceType || restored.isIntraCu!=s.isIntraCu || restored.isInterCu!=s.isInterCu,"Snapshot roundtrip mismatch");
    }
    else { snapshot.clear(); ++cv.snapshotSkipped; }
    std::vector<int> eligible,disagreement;
    for(int i=0;i<int(d.size());++i) if(s.q[s.g.scan[i]] && d[i].n>=3)
    { eligible.push_back(i); if(d[i].pred[1]!=d[i].pred[2] || d[i].pred[1]!=d[i].pred[3] || d[i].pred[3]!=d[i].pred[4]) { disagreement.push_back(i); } }
    auto order=[&](int a,int b) { return sampleHash(hashNumber(s.priority^0x706f736974696f6eULL,a))<sampleHash(hashNumber(s.priority^0x706f736974696f6eULL,b)); };
    std::sort(eligible.begin(),eligible.end(),order); std::sort(disagreement.begin(),disagreement.end(),order);
    std::array<std::vector<int>,2> chosen;
    for(size_t i=0;i<std::min<size_t>(2,eligible.size());++i) { chosen[0].push_back(eligible[i]); }
    disagreement.erase(std::remove_if(disagreement.begin(),disagreement.end(),[&](int i){return std::find(chosen[0].begin(),chosen[0].end(),i)!=chosen[0].end();}),disagreement.end());
    for(size_t i=0;i<std::min<size_t>(2,disagreement.size());++i) { chosen[1].push_back(disagreement[i]); }
    std::array<uint64_t,2> pointDone{},requested{};
    for(int sampleClass=0;sampleClass<2;++sampleClass)
    {
      requested[sampleClass]=chosen[sampleClass].size(); cv.requested[sampleClass]+=chosen[sampleClass].size();
      unsigned need=0;
      for(int i:chosen[sampleClass])
      {
        std::set<int> maps; const int a=std::abs(s.q[s.g.scan[i]]);
        for(int candidate:d[i].plus) { maps.insert(TsFixedPrediction::remap(a,candidate)); }
        maps.erase(TsFixedPrediction::remap(a,d[i].pred[native])); need+=maps.size();
      }
      // Uniform positions are an atomic group, ahead of enriched positions.
      // Incomplete groups never become a silently reweighted population sample.
      const bool groupDone=policyDone && budget.fits(need,s.q.size());
      if(!groupDone)
      {
        cv.pointSkipped+=chosen[sampleClass].size();
        continue;
      }
      for(int i:chosen[sampleClass])
      {
        const int a=std::abs(s.q[s.g.scan[i]]); const auto &v=d[i];
        const auto &nativeReplay=cache.at(p[native]);
        std::map<int,std::pair<int64_t,int64_t>> costs;
        auto direct=[&](const Replay &r) { uint64_t n=0; for(const auto &e:r.bins.events) if(e.scan==i) { n+=e.cost; } return int64_t(n); };
        costs[TsFixedPrediction::remap(a,v.pred[native])]={int64_t(nativeReplay.bins.bits),direct(nativeReplay)};
        for(int candidate:v.plus)
        {
          const int mapped=TsFixedPrediction::remap(a,candidate); if(costs.count(mapped)) { continue; }
          auto overridden=p[native]; overridden[i]=candidate; auto r=countedReplay(s,overridden);
          costs[mapped]={int64_t(r.bins.bits),direct(r)};
        }
        std::vector<int64_t> c0,cp;
        for(int t:v.c0) { c0.push_back(costs.at(TsFixedPrediction::remap(a,t)).first); }
        for(int t:v.plus) { cp.push_back(costs.at(TsFixedPrediction::remap(a,t)).first); }
        ++pointDone[sampleClass]; ++cv.done[sampleClass];
      const auto min0=*std::min_element(c0.begin(),c0.end()),minP=*std::min_element(cp.begin(),cp.end());
      std::array<int64_t,7> actual{},regret{}; for(int m=0;m<7;++m) { actual[m]=costs.at(TsFixedPrediction::remap(a,v.pred[m])).first; regret[m]=actual[m]-(m>=5?minP:min0); }
      const auto eq=costs.at(TsFixedPrediction::remap(a,v.pred[3])),sp=costs.at(TsFixedPrediction::remap(a,v.pred[4]));
      const auto &nativePath=s.native.paths[i>>s.g.logCG];
      const int raster=s.g.scan[i],xx=raster%s.g.w,yy=raster/s.g.w;
      const int missing=(xx==0)+(yy==0)+(!xx || !yy)+(xx<2)+(yy<2);

      std::ostringstream z;
      z<<"{\"kind\":\"point\",\"tu\":\""<<id<<"\",\"poc\":"<<s.poc<<",\"component\":"<<s.component<<",\"scan\":"<<i<<",\"a\":"<<a<<",\"n\":"<<v.n<<",\"slice_type\":\""<<sliceName(s.sliceType)<<"\",\"is_intra_cu\":"<<s.isIntraCu<<",\"is_inter_cu\":"<<s.isInterCu<<",\"regular_active\":"<<(i<=nativePath.p1)<<",\"pass1_last\":"<<nativePath.p1<<",\"pass2_last\":"<<nativePath.p2<<",\"cg_end_budget\":"<<nativePath.end<<",\"missing_neighbors\":"<<missing<<",\"area\":"<<s.q.size()<<",\"sample\":\""<<(sampleClass?"disagreement":"uniform")<<"\",\"position_population\":"<<(sampleClass?disagreement.size():eligible.size())<<",\"position_selected\":"<<std::min<size_t>(2,sampleClass?disagreement.size():eligible.size())<<",\"tu_population\":"<<s.seen<<",\"tu_selected\":"<<slots[s.component].size()<<",\"H\":";
      arrayJson(z,v.h); z<<",\"c0\":"; arrayJson(z,v.c0); z<<",\"cplus\":"; arrayJson(z,v.plus); z<<",\"scores168\":[";
      for(int m=0;m<7;++m) { if(m) { z<<','; } arrayJson(z,v.score[m]); } z<<"],\"weight_sum\":"; arrayJson(z,v.weights);
      z<<",\"pred\":"; arrayJson(z,v.pred); z<<",\"c0_cost_frac\":"; arrayJson(z,c0); z<<",\"cplus_cost_frac\":"; arrayJson(z,cp);
      z<<",\"cost_frac\":"; arrayJson(z,actual); z<<",\"regret_frac\":"; arrayJson(z,regret);
      z<<",\"distinguishable\":"<<(*std::max_element(c0.begin(),c0.end())!=min0)<<",\"distinguishable_plus\":"<<(*std::max_element(cp.begin(),cp.end())!=minP)<<",\"hist\":"<<v.hist<<",\"hist_count\":"<<v.histCount<<",\"history_nz\":"<<v.historySize<<",\"coverage_frac\":"<<min0-minP<<",\"direct_sp_eq_frac\":"<<sp.second-eq.second<<",\"propagation_sp_eq_frac\":"<<(sp.first-eq.first)-(sp.second-eq.second)<<'}'; emit(z.str(),"point");
      }
    }
    const bool pointsDone=policyDone && pointDone==requested;
    std::ostringstream o;
    o<<"{\"kind\":\"tu\",\"id\":\""<<id<<"\",\"poc\":"<<s.poc<<",\"component\":"<<s.component
     <<",\"x\":"<<s.x<<",\"y\":"<<s.y<<",\"w\":"<<s.g.w<<",\"h\":"<<s.g.h<<",\"qp\":"<<s.qp
     <<",\"slice_type\":\""<<sliceName(s.sliceType)<<"\",\"is_intra_cu\":"<<s.isIntraCu<<",\"is_inter_cu\":"<<s.isInterCu
     <<",\"q_hash\":\""<<s.qHash()<<"\",\"entry_hash\":\""<<contextHash(s.entry)<<"\",\"nz\":"<<nz
     <<",\"coeff\":"<<s.q.size()<<",\"tu_population\":"<<s.seen<<",\"tu_selected\":"<<slots[s.component].size()
     <<",\"native_replay_complete\":"<<(nativeDone?"true":"false")<<",\"policy_complete\":[";
    for(int m=0;m<7;++m) { if(m) { o<<','; } o<<(rates[m]>=0?"true":"false"); }
    o<<"],\"policy_missing_reason\":[";
    for(int m=0;m<7;++m) { if(m) { o<<','; } if(rates[m]>=0) { o<<"null"; } else { o<<'"'<<(nativeDone?"policy_group_budget":"native_budget")<<'"'; } }
    o<<"],\"rates_frac\":[";
    for(int m=0;m<7;++m) { if(m) { o<<','; } if(rates[m]>=0) { o<<rates[m]; } else { o<<"null"; } }
    o<<"],\"all_policy_complete\":"<<(policyDone?"true":"false")<<",\"point_oracle_complete\":"<<(pointsDone?"true":"false")
     <<",\"point_missing_reason\":"<<(pointsDone?"null":policyDone?"\"point_group_budget\"":"\"policy_group_budget\"")
     <<",\"point_requested\":"; arrayJson(o,requested); o<<",\"point_done\":"; arrayJson(o,pointDone);
    o<<",\"snapshot_complete\":"<<(snapshotDone?"true":"false")<<",\"snapshot_missing_reason\":"<<(snapshotDone?"null":"\"component_disk_budget\"")
     <<",\"snapshot\":\""<<snapshot<<"\",\"budget_replays\":"<<budget.maxReplays
     <<",\"budget_visits\":"<<budget.maxVisits<<",\"used_replays\":"<<budget.replays<<",\"used_visits\":"<<budget.visits<<'}';
    emit(o.str(),"tu");
  }
  void flush()
  {
    if(poc<0) { return; }
    for(int c=0;c<3;++c)
    {
      auto &group=slots[c]; std::sort(group.begin(),group.end(),[](const auto &a,const auto &b){return a->priority<b->priority;});
      for(unsigned i=0;i<group.size();++i)
      { budget=tuBudget(replayLimit,visitLimit,poc,c,group.size(),i); audit(*group[i]); }
    }
    for(int c=0;c<3;++c) if(accepts(poc,c))
    {
      const auto &v=counts[c]; const auto &cv=coverage[c]; std::ostringstream o;
      o<<"{\"kind\":\"frame\",\"schema\":2,\"poc\":"<<poc<<",\"component\":"<<c<<",\"tu\":"<<v.tu
       <<",\"coeff\":"<<v.coeff<<",\"nz\":"<<v.nz<<",\"target_tu\":"<<v.tu-v.bdpcm<<",\"bdpcm_tu\":"<<v.bdpcm
       <<",\"target_nz\":"<<v.targetNz<<",\"target_coeff\":"<<v.targetCoeff<<",\"eligible_tu\":"<<v.eligible
       <<",\"eligible_coeff\":"<<v.eligibleCoeff<<",\"eligible_nz\":"<<v.eligibleNz<<",\"scoring_eligible_tu\":"<<v.scoringTu
       <<",\"scoring_eligible_nz\":"<<v.scoringNz<<",\"sampling_population_tu\":"<<v.samplingPopulation
       <<",\"unsupported_tu\":"<<v.unsupported<<",\"capture_skipped\":"<<v.captureSkipped<<",\"selected_tu\":"<<slots[c].size()
       <<",\"slice_cu_counts\":"; arrayJson(o,v.sliceCu); o<<",\"coverage\":"; coverageJson(o,cv);
      o<<",\"amplitude\":"; arrayJson(o,v.amplitude); o<<",\"support\":"; arrayJson(o,v.support); o<<'}'; emit(o.str(),"frame");
      auto &t=total[c];
      t.selected+=cv.selected; t.selectedCoeff+=cv.selectedCoeff; t.selectedNz+=cv.selectedNz; t.native+=cv.native; t.fullPolicy+=cv.fullPolicy; t.snapshots+=cv.snapshots;
      for(int m=0;m<7;++m) { t.policy[m]+=cv.policy[m]; }
      for(int k=0;k<2;++k) { t.requested[k]+=cv.requested[k]; t.done[k]+=cv.done[k]; }
      t.nativeSkipped+=cv.nativeSkipped; t.policySkipped+=cv.policySkipped; t.pointSkipped+=cv.pointSkipped; t.snapshotSkipped+=cv.snapshotSkipped;
      t.replays+=cv.replays; t.visits+=cv.visits;
    }
    for(auto &v:slots) { v.clear(); } finished.insert(poc); poc=-1;
  }
  void finish(bool success)
  {
    if(success) { flush(); } raw.flush();
    uint64_t selected=0,native=0,full=0,snapshots=0,skipped=0,replays=0,visits=0,snapshotSkipped=0;
    std::array<uint64_t,7> policy{}; bool points=true;
    for(const auto &v:total)
    {
      selected+=v.selected; native+=v.native; full+=v.fullPolicy; snapshots+=v.snapshots;
      skipped+=v.nativeSkipped+v.policySkipped+v.pointSkipped; replays+=v.replays; visits+=v.visits; snapshotSkipped+=v.snapshotSkipped;
      points=points && v.requested==v.done; for(int m=0;m<7;++m) { policy[m]+=v.policy[m]; }
    }
    const bool requested=profile!="summary",outputComplete=!truncated;
    std::ofstream o(root+"/native_validation.json");
    auto flag=[&](bool v) { o<<(requested?(v?"true":"false"):"null"); };
    o<<"{\"schema\":2,\"revision\":\""<<revision<<"\",\"valid\":"<<(success?"true":"false")
     <<",\"decode_complete\":"<<(success?"true":"false")<<",\"native_replay_complete\":"; flag(success && !captureSkippedTotal && selected==native);
    o<<",\"policy_complete\":["; for(int m=0;m<7;++m) { if(m) { o<<','; } flag(success && policy[m]==selected); }
    o<<"],\"point_oracle_complete\":"; flag(success && full==selected && points);
    o<<",\"snapshot_complete\":"; flag(success && snapshots==selected);
    o<<",\"output_complete\":"<<(outputComplete?"true":"false")<<",\"audit_complete\":";
    flag(success && outputComplete && !captureSkippedTotal && native==selected && full==selected && points && snapshots==selected);
    o<<",\"native_verified_tu\":"<<native<<",\"selected_tu\":"<<selected<<",\"skipped_budget\":"<<skipped
     <<",\"replays\":"<<replays<<",\"coefficient_visits\":"<<visits<<",\"core_truncated\":"<<(truncated?"true":"false")
     <<",\"cache_peak_bytes\":"<<cachePeak<<",\"snapshot_skipped_budget\":"<<snapshotSkipped<<",\"raw_bytes\":"<<rawBytes
     <<",\"snapshot_bytes\":"<<snapshotBytes<<",\"capture_skipped\":"<<captureSkippedTotal<<",\"component_snapshot_bytes\":";
    arrayJson(o,componentSnapshotBytes);
    o<<",\"output_dropped_records\":"<<outputDropped<<",\"output_dropped_by_kind\":{";
    bool comma=false; for(const auto &v:dropped) { if(comma) { o<<','; } comma=true; o<<'"'<<v.first<<"\":"<<v.second; }
    o<<"},\"component_coverage\":["; for(int c=0;c<3;++c) { if(c) { o<<','; } coverageJson(o,total[c]); } o<<"]}\n";
    CHECK(!o,"Cannot write audit validation");
  }
};
inline std::unique_ptr<Manager> &storage() { static std::unique_ptr<Manager> value; return value; }
inline Manager &manager() { auto &value=storage(); if(!value) { value=std::make_unique<Manager>(); } return *value; }
inline Native *begin(const TransformUnit &tu,CompID c,const Ctx &ctx)
{
#if JVET_BJUT_TS_R15_ANALYSIS
  if(TsMultiAudit::enabled()) { return TsMultiAudit::collector().begin(tu,c,ctx); }
#endif
  if(TsCorpus::enabled()) { return TsCorpus::begin(tu,c,ctx); }return enabled()?manager().begin(tu,c,ctx):nullptr;
}
inline void end(const TransformUnit &tu,CompID c,const Ctx &ctx)
{
#if JVET_BJUT_TS_R15_ANALYSIS
  if(TsMultiAudit::enabled()) { TsMultiAudit::collector().end(tu,c,ctx);return; }
#endif
  if(TsCorpus::enabled()) { TsCorpus::end(tu,c,ctx);return; }if(enabled()) { manager().end(tu,c,ctx); }
}
inline void finish(bool success)
{
#if JVET_BJUT_TS_R15_ANALYSIS
  if(TsMultiAudit::enabled()) { TsMultiAudit::collector().finish(success);return; }
#endif
  if(TsCorpus::enabled()) { TsCorpus::finish(success); return; }
  if(!enabled() || !storage()) { return; }
  if(success) { manager().finish(true); }
  else { try { manager().finish(false); } catch(const std::exception &e) { std::cerr<<"Audit failure manifest: "<<e.what()<<'\n'; } }
}
inline void picture(const Picture &pic)
{
  static const auto hashPath=envString("TS_AUDIT_HASH");
#if JVET_BJUT_TS_R15_ANALYSIS
  if(TsMultiAudit::enabled()) { CHECK(pic.m_layerId!=0,"R15 supports only single-layer streams"); }
#endif
  if(enabled() || TsCorpus::enabled()) { CHECK(pic.m_layerId!=0,"Audit/corpus supports only single-layer streams"); }
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
