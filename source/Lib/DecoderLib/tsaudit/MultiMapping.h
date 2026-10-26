#pragma once
// Isolated R15 observer. One TU in memory; all methods, no sampling or schedules.
#include "Replay.h"
#include "CommonLib/TsMultiMapping.h"
#include <chrono>
#include <memory>
#include <iostream>
#include <filesystem>
namespace TsMultiAudit
{
using TsMultiMapping::Action;
inline bool enabled()
{ static const bool on=[](){auto p=std::getenv("TS_R15_AUDIT");CHECK(p && std::string(p)!="1","TS_R15_AUDIT must be absent or 1");return p!=nullptr;}();return on; }
template<class T> inline void array(std::ostream &o,const T &v)
{ o<<'[';bool comma=false;for(auto x:v) { if(comma) { o<<','; }comma=true;o<<x; }o<<']'; }
inline void emit(const std::string &s) { std::cout<<"@TS_R15 "<<s<<'\n';CHECK(!std::cout,"R15 output failure"); }
inline TsAudit::Replay replay(const TsAudit::Snapshot &s,const std::vector<Action> &p)
{
  CHECK(p.size()!=s.q.size(),"Action sequence length mismatch");
  auto g=s.g;TsAudit::Sink sink(s.entry);int bins=s.budget;
  for(g.cg=0;g.cg<int(g.groupSig.size());++g.cg)
  { auto path=TsFixedPrediction::replayRateCG(g,s.q.data(),[&](int i){return p[i];},bins,s.rice,sink);sink.result.paths.push_back({path.pass1,path.pass2,bins}); }
  TsAudit::Replay r;r.bins=std::move(sink.result);r.visits=sink.visits;
  for(const auto &c:sink.ctx) { r.exit.emplace_back(c); }return r;
}
inline std::array<int,5> neighborhood(const TsAudit::Snapshot &s,int scan,const std::vector<int> &inverse)
{
  std::array<int,5> h{};int pos=s.g.scan[scan],x=pos%s.g.w,y=pos/s.g.w;
  int offset[]={x?-1:0,y?-s.g.w:0,x && y?-s.g.w-1:0,x>1?-2:0,y>1?-2*s.g.w:0};
  for(int j=0;j<5;++j) if(offset[j]) { CHECK(inverse[pos+offset[j]]>=scan,"Noncausal R15 scan");h[j]=int(std::abs(int64_t(s.q[pos+offset[j]]))); }
  return h;
}
// Rows are small fixed-count aggregates, emitted at EOF. Arrays: n, distinct
// observations, |V|, searched/returned/effective depth, magnitude diagnostic,
// positive/zero/negative extensions, neutral steps and root changes.
struct Activity
{
  std::array<uint64_t,6> n{},distinct{},magnitude{};
  std::array<uint64_t,7> candidates{},searched{},returned{},effective{};
  uint64_t positions=0,nonzero=0,fallback=0,changedAction=0,changedMagnitude=0,regularChanged=0;
  uint64_t positive=0,zero=0,negative=0,neutralSteps=0,rootChanges=0;
  TsMultiMapping::Operations ops;
};
struct Collector
{
  std::unique_ptr<TsAudit::Snapshot> pending;
  std::array<std::array<Activity,21>,3> activity{};
  uint64_t all=0,target=0,bdpcm=0,unsupported=0,verified=0,positions=0,nz=0,replays=0;
  uint64_t selectNs=0,replayNs=0,streamHash=0;
  std::string fixtureDir;
  Collector()
  {
    CHECK(std::getenv("TS_CORPUS") || std::getenv("TS_SCORE_AUDIT") || std::getenv("TS_CORPUS_SCHEDULE"),"R15/corpus/sampled audit or legacy schedule are mutually exclusive");
    CHECK(TsFixedPrediction::mode()!=98 && TsFixedPrediction::mode()!=99,"R15 needs native R13-1 or R13-2");
    CHECK(TsFixedPrediction::r13DiagnosticScope()!=0,"R15 requires all-component source scope");
    if(const char *p=std::getenv("TS_R15_FIXTURES")) { fixtureDir=p;CHECK(fixtureDir.empty(),"Empty fixture directory");std::filesystem::create_directories(fixtureDir); }
    std::ostringstream o;o<<"{\"kind\":\"header\",\"revision\":\""<<TsMultiMapping::revision<<"\",\"action_protocol\":\""<<TsMultiMapping::protocol<<"\",\"native_policy\":"<<TsFixedPrediction::mode()<<",\"rate_scale\":32768,\"engine\":\"PREFIX\",\"method_mg_ids\":[";
    for(size_t i=0;i<TsMultiMapping::methods().size();++i) { if(i) { o<<','; }o<<TsMultiMapping::methods()[i].mg; }o<<"],\"full_tu_replay\":true,\"sampling\":false}";emit(o.str());
  }
  TsAudit::Native *begin(const TransformUnit &tu,CompID c,const Ctx &ctx)
  {
    CHECK(pending!=nullptr,"Nested R15 capture");++all;
    if(tu.cu->getBdpcmMode(c)!=BdpcmMode::NONE) { ++bdpcm;return nullptr; }
    const auto &a=tu.blocks[c];const int range=tu.cs->sps->getMaxLog2TrDynamicRange(toChannelType(c));
    if(a.width>64 || a.height>64 || a.area()>4096 || range<8 || range>20) { ++unsupported;return nullptr; }
    ++target;pending=std::make_unique<TsAudit::Snapshot>();auto &s=*pending;TsAudit::captureIdentity(s,tu,c);s.policy=TsFixedPrediction::mode();
    s.rice=1+(tu.cu->slice->m_sps->m_spsRangeExtension.m_tsrcRicePresentFlag?tu.cu->slice->m_tsrcIndex:0);
    s.budget=(a.area()*7)>>2;s.entry=TsAudit::saveContext(ctx);return &s.native;
  }
  void end(const TransformUnit &tu,CompID comp,const Ctx &ctx)
  {
    if(!pending) { return; }auto &s=*pending;TsAudit::captureGeometry(s,tu,comp);s.exit=TsAudit::saveContext(ctx);
    const auto old=TsAudit::decisions(s);auto native=TsAudit::replay(s,TsAudit::predictors(old,s.policy==98?3:4));++replays;TsAudit::validateNative(s,native);++verified;
    std::vector<int> inverse(s.q.size());for(size_t i=0;i<s.q.size();++i) { inverse[s.g.scan[i]]=int(i); }
    uint64_t scanHash=14695981039346656037ULL;for(int v:s.g.scan) { scanHash=TsAudit::hashNumber(scanHash,v); }
    std::array<uint64_t,21> rates{},actionHashes{};std::array<int64_t,21> scores{};
    std::map<std::vector<Action>,int> cache;std::vector<TsAudit::Replay> results;
    const bool fixture=!fixtureDir.empty() && verified<=2;
    std::map<Action,int> dictionary;std::vector<std::vector<int>> actionIds;
    std::vector<Action> staticEq;
    for(size_t m=0;m<TsMultiMapping::methods().size();++m)
    {
      const auto start=std::chrono::steady_clock::now();const auto &method=TsMultiMapping::methods()[m];auto &a=activity[comp][m];
      std::vector<Action> actions;actions.reserve(s.q.size());uint64_t hash=14695981039346656037ULL;
      std::vector<bool> mappedChange(s.q.size());
      for(size_t i=0;i<s.q.size();++i)
      {
        const auto h=neighborhood(s,int(i),inverse);const auto r=TsMultiMapping::select(h,method,s.rice,s.g.range);
        const int mag=int(std::abs(int64_t(s.q[s.g.scan[i]]))); // observed AFTER choosing; not a selector input
        const auto base=TsMultiMapping::canonical(TsMultiMapping::single(old[i].pred[1]));
        if(m<3) { CHECK(r.action!=TsMultiMapping::canonical(TsMultiMapping::single(old[i].pred[m])),"R15 changed an existing static control"); }
        actions.push_back(r.action);scores[m]+=r.score;hash=TsAudit::hashNumber(hash,r.action.count);for(int j=0;j<r.action.count;++j) { hash=TsAudit::hashNumber(hash,r.action.targets[j]); }
        ++a.positions;a.nonzero+=mag!=0;++a.n[r.n];std::set<int> distinct(h.begin(),h.end());distinct.erase(0);++a.distinct[distinct.size()];++a.candidates[r.candidates];
        ++a.searched[r.searched.count];++a.returned[r.returned.count];++a.effective[r.action.count];a.fallback+=r.fallback;
        a.positive+=r.positive;a.zero+=r.neutral;a.negative+=r.negative;a.neutralSteps+=r.zeroSteps;a.rootChanges+=r.rootChanged;a.ops+=r.ops;
        ++a.magnitude[mag<=2?mag:mag<=4?3:mag<=8?4:5];a.changedAction+=r.action!=base;
        mappedChange[i]=TsMultiMapping::map(mag,r.action)!=TsMultiMapping::map(mag,base);a.changedMagnitude+=mappedChange[i];
      }
      if(method.mg==4) { staticEq=actions; }
      if(method.mg==8) { CHECK(actions!=staticEq,"G_EQ_K2 and N_EQ_K2 differ"); }
      selectNs+=std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::steady_clock::now()-start).count();
      actionHashes[m]=hash;auto it=cache.find(actions);
      if(fixture)
      {
        std::vector<int> ids;for(const auto &action:actions) { auto found=dictionary.find(action);if(found==dictionary.end()) { int id=int(dictionary.size());found=dictionary.emplace(action,id).first; }ids.push_back(found->second); }actionIds.push_back(std::move(ids));
      }
      if(it==cache.end())
      {
        const auto t=std::chrono::steady_clock::now();auto r=replay(s,actions);++replays;
        replayNs+=std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::steady_clock::now()-t).count();
        // Only rate and pass boundaries are retained per branch, never all bins.
        r.bins.events.clear();r.bins.events.shrink_to_fit();r.exit.clear();r.exit.shrink_to_fit();
        const int k=int(results.size());results.push_back(std::move(r));it=cache.emplace(std::move(actions),k).first;
      }
      const auto &r=results[it->second];rates[m]=r.bins.bits;
      for(size_t i=0;i<s.q.size();++i) { const auto &path=r.bins.paths[i>>s.g.logCG];a.regularChanged+=mappedChange[i] && int(i)<=path.p1; }
    }
    const auto nonzero=std::count_if(s.q.begin(),s.q.end(),[](int v){return v!=0;});positions+=s.q.size();nz+=nonzero;
    streamHash=TsAudit::hashNumber(streamHash,s.qHash());streamHash=TsAudit::hashNumber(streamHash,TsAudit::contextHash(s.entry));streamHash=TsAudit::hashNumber(streamHash,scanHash);
    std::ostringstream o;o<<"{\"kind\":\"tu\",\"poc\":"<<s.poc<<",\"component\":"<<s.component<<",\"x\":"<<s.x<<",\"y\":"<<s.y<<",\"w\":"<<s.g.w<<",\"h\":"<<s.g.h<<",\"qp\":"<<s.qp<<",\"slice_type\":\""<<TsAudit::sliceName(s.sliceType)<<"\",\"is_intra_cu\":"<<s.isIntraCu<<",\"nonzero\":"<<nonzero<<",\"positions\":"<<s.q.size()<<",\"q_hash\":\""<<s.qHash()<<"\",\"entry_hash\":\""<<TsAudit::contextHash(s.entry)<<"\",\"scan_hash\":\""<<scanHash<<"\",\"native_rate_frac\":"<<native.bins.bits<<",\"rates_frac\":";
    array(o,rates);o<<",\"scores\":";array(o,scores);o<<",\"action_hashes\":";array(o,actionHashes);o<<'}';emit(o.str());
    if(fixture)
    {
      const std::string stem=fixtureDir+"/tu_"+std::to_string(verified);
      CHECK(!TsAudit::save(s,stem+".tsa",4*1024*1024),"R15 fixture snapshot size limit");
      std::vector<Action> ordered(dictionary.size());for(const auto &entry:dictionary) { ordered[entry.second]=entry.first; }
      std::ostringstream f;f<<"{\"protocol\":\""<<TsMultiMapping::protocol<<"\",\"revision\":\""<<TsMultiMapping::revision<<"\",\"native_policy\":"<<s.policy<<",\"tu\":"<<o.str()<<",\"rice\":"<<s.rice<<",\"range\":"<<s.g.range<<",\"q\":";array(f,s.q);f<<",\"scan\":";array(f,s.g.scan);f<<",\"dictionary\":[";
      for(size_t j=0;j<ordered.size();++j) { if(j) { f<<','; }f<<'[';for(int k=0;k<ordered[j].count;++k) { if(k) { f<<','; }f<<ordered[j].targets[k]; }f<<']'; }
      f<<"],\"action_ids\":[";for(size_t j=0;j<actionIds.size();++j) { if(j) { f<<','; }array(f,actionIds[j]); }f<<"]}\n";
      CHECK(f.str().size()>2*1024*1024,"R15 action fixture size limit");std::ofstream output(stem+".actions.json");output<<f.str();output.close();CHECK(!output,"Cannot save action fixture");
    }
    pending.reset();
  }
  void finish(bool success)
  {
    if(success) { CHECK(pending!=nullptr,"Incomplete R15 TU"); }
    for(int c=0;c<3;++c) for(int m=0;m<21;++m)
    {
      const auto &a=activity[c][m];std::ostringstream o;o<<"{\"kind\":\"activity\",\"component\":"<<c<<",\"mg\":"<<TsMultiMapping::methods()[m].mg<<",\"positions\":"<<a.positions<<",\"nonzero\":"<<a.nonzero<<",\"fallback\":"<<a.fallback<<",\"changed_action\":"<<a.changedAction<<",\"changed_magnitude\":"<<a.changedMagnitude<<",\"regular_changed\":"<<a.regularChanged<<",\"positive\":"<<a.positive<<",\"zero\":"<<a.zero<<",\"negative\":"<<a.negative<<",\"neutral_steps\":"<<a.neutralSteps<<",\"root_changes\":"<<a.rootChanges;
      const auto field=[&](const char *key,const auto &v){o<<",\""<<key<<"\":";array(o,v);};
      field("n",a.n);field("distinct",a.distinct);field("candidates",a.candidates);field("searched",a.searched);field("returned",a.returned);field("effective",a.effective);field("magnitude",a.magnitude);
      const auto &v=a.ops;o<<",\"operations\":["<<v.candidates<<','<<v.queries<<','<<v.hits<<','<<v.adds<<','<<v.multiplies<<','<<v.compares<<','<<v.rankUpdates<<','<<v.pruned<<','<<v.loops<<"]}";emit(o.str());
    }
    std::ostringstream o;o<<"{\"kind\":\"footer\",\"complete\":"<<(success && !pending && !unsupported && verified==target?"true":"false")<<",\"all_ts_tu\":"<<all<<",\"target_tu\":"<<target<<",\"bdpcm_tu\":"<<bdpcm<<",\"unsupported_tu\":"<<unsupported<<",\"verified_tu\":"<<verified<<",\"positions\":"<<positions<<",\"nonzero\":"<<nz<<",\"replays\":"<<replays<<",\"selector_observation_ns\":"<<selectNs<<",\"replay_ns\":"<<replayNs<<",\"population_digest\":\""<<streamHash<<"\",\"methods_complete\":21}";emit(o.str());
  }
};
inline std::unique_ptr<Collector> &storage() { static std::unique_ptr<Collector> p;return p; }
inline Collector &collector() { auto &p=storage();if(!p) { p=std::make_unique<Collector>(); }return *p; }
} // namespace TsMultiAudit
