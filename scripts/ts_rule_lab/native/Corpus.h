#pragma once
// TS-RULE-LAB-v1. Decoder-only fixed-q observation. No EncoderLib dependency.
// Integration candidate: native build and on/off acceptance are still required.
#include "Replay.h"
#include <cstdlib>
#include <iostream>
#include <memory>
#include <limits>
#include <array>
#include <algorithm>
#include <map>
#include <sstream>
#include <string>
#include <vector>

namespace TsCorpus {
inline bool wantLabels() { const char *v=std::getenv("TS_CORPUS_POINTS"); CHECK(v && std::string(v)!="0" && std::string(v)!="1","TS_CORPUS_POINTS must be 0/1"); return v && std::string(v)=="1"; }
constexpr const char *revision="TS-RULE-LAB-v1";
constexpr const char *actions[]={"CURRENT","STATIC_EQ","STATIC_SP","KEEP_F0","KEEP_F1","KEEP_F2","KEEP_F3","KEEP_F4","KEEP_EQ_H","KEEP_SP_H"};
constexpr int actionCount=10;
inline bool enabled() { static bool yes=[](){const char *p=std::getenv("TS_CORPUS"); CHECK(p && std::string(p)!="1","TS_CORPUS must be 1 or absent"); return p!=nullptr;}(); return yes; }
template<class V> inline void arr(std::ostream &o,const V &v) { o<<'[';bool first=true;for(auto x:v){if(!first)o<<',';first=false;o<<x;}o<<']'; }
inline void emit(const std::string &s) { std::cout<<"@TS_CORPUS "<<s<<'\n'; CHECK(!std::cout,"Corpus output failure"); }
struct Choices {
  std::vector<TsAudit::Decision> d;
  std::array<std::vector<int>,actionCount> pred;
};
inline Choices choices(const TsAudit::Snapshot &s) {
  Choices c;c.d=TsAudit::decisions(s);
  for(size_t i=0;i<c.d.size();++i) {
    const auto &d=c.d[i];
    c.pred[0].push_back(d.pred[0]);c.pred[1].push_back(d.pred[1]);c.pred[2].push_back(d.pred[2]);
    for(int r=0;r<=4;++r) {
      int best=d.pred[0];int64_t bestCost=std::numeric_limits<int64_t>::max();
      if(d.n>=3) for(int p:d.c0) {
        int64_t near=0,far=0;
        for(int j=0;j<5;++j) if(d.h[j]) {
          auto v=TsFixedPrediction::r13Loss168(d.h[j],p,s.rice,s.g.range);
          if(j<2)near+=v;else far+=v;
        }
        auto cost=4*near+r*far;if(cost<bestCost){bestCost=cost;best=p;}
      }
      c.pred[3+r].push_back(best);
    }
    c.pred[8].push_back(d.pred[5]);c.pred[9].push_back(d.pred[6]);
    CHECK(c.pred[5].back()!=d.pred[4] || c.pred[7].back()!=d.pred[3],"Corpus grid is not equivalent to R13 endpoints");
  }
  return c;
}
struct Schedule {
  std::ifstream in;int models=0;
  Schedule() {
    const char *path=std::getenv("TS_CORPUS_SCHEDULE");if(!path)return;
    in.open(path);std::string magic;int version=0;in>>magic>>version>>models;
    CHECK(!in || magic!="TSCPRED" || version!=1 || models<1 || models>64,"Invalid corpus prediction schedule");
  }
  std::vector<std::vector<int>> read(const TsAudit::Snapshot &s) {
    if(!models)return {};
    int poc,comp,x,y,w,h,n;uint64_t qhash,chash;
    in>>poc>>comp>>x>>y>>w>>h>>qhash>>chash>>n;
    CHECK(!in || poc!=s.poc || comp!=s.component || x!=s.x || y!=s.y || w!=s.g.w || h!=s.g.h || n!=int(s.q.size()) || qhash!=s.qHash() || chash!=TsAudit::contextHash(s.entry),"Schedule TU/input identity mismatch");
    std::vector<std::vector<int>> out(models,std::vector<int>(n));
    for(auto &v:out)for(int &p:v){in>>p;CHECK(!in || p<0 || uint64_t(p)>(uint64_t(1)<<s.g.range),"Invalid scheduled predictor");}
    return out;
  }
  void finish(){if(models){std::string extra;CHECK(bool(in>>extra),"Unconsumed prediction schedule");}}
};
struct Collector {
  std::unique_ptr<TsAudit::Snapshot> pending;
  Schedule schedule;
  uint64_t all=0,target=0,bdpcm=0,unsupported=0,verified=0,points=0,replays=0,positions=0,nz=0;
  std::array<uint64_t,3> allComponent{},targetComponent{};
  Collector() {
    CHECK(std::getenv("TS_SCORE_AUDIT"),"Corpus and sampled audit must be separate runs");
    CHECK(TsFixedPrediction::mode()!=98 && TsFixedPrediction::mode()!=99,"Corpus needs native R13-1 or R13-2");
    CHECK(TsFixedPrediction::r13DiagnosticScope()!=0,"Corpus requires all-component source scope");
    std::ostringstream o;o<<"{\"kind\":\"header\",\"revision\":\""<<revision<<"\",\"rate_scale\":32768,\"native_policy\":"<<TsFixedPrediction::mode()<<",\"mode\":\""<<(schedule.models?"evaluate":"labels")<<"\",\"actions\":[";
    for(int a=0;a<actionCount;++a){if(a)o<<',';o<<'"'<<actions[a]<<'"';}o<<"],\"all_point_labels\":"<<(wantLabels()?"true":"false")<<"}";emit(o.str());
  }
  TsAudit::Native *begin(const TransformUnit &tu,CompID c,const Ctx &ctx) {
    CHECK(pending!=nullptr,"Nested TS corpus capture unsupported");++all;++allComponent[c];
    if(tu.cu->getBdpcmMode(c)!=BdpcmMode::NONE){++bdpcm;return nullptr;}
    const auto &a=tu.blocks[c];const int range=tu.cs->sps->getMaxLog2TrDynamicRange(toChannelType(c));
    if(a.width>64 || a.height>64 || a.area()>4096 || range<8 || range>20){++unsupported;return nullptr;}
    ++target;++targetComponent[c];pending=std::make_unique<TsAudit::Snapshot>();auto &s=*pending;
    TsAudit::captureIdentity(s,tu,c);s.policy=TsFixedPrediction::mode();
    s.rice=1+(tu.cu->slice->m_sps->m_spsRangeExtension.m_tsrcRicePresentFlag?tu.cu->slice->m_tsrcIndex:0);
    s.budget=(a.area()*7)>>2;s.entry=TsAudit::saveContext(ctx);return &s.native;
  }
  TsAudit::Replay replay(const TsAudit::Snapshot &s,const std::vector<int> &p){++replays;return TsAudit::replay(s,p);}
  void end(const TransformUnit &tu,CompID c,const Ctx &ctx) {
    if(!pending)return;
    auto &s=*pending;TsAudit::captureGeometry(s,tu,c);s.exit=TsAudit::saveContext(ctx);
    const auto ch=choices(s);const int native=s.policy==98?7:5;
    auto nr=replay(s,ch.pred[native]);TsAudit::validateNative(s,nr);++verified;
    std::map<std::vector<int>,int64_t> rateCache;rateCache.emplace(ch.pred[native],int64_t(nr.bins.bits));
    std::array<int64_t,actionCount> rates{};
    for(int a=0;a<actionCount;++a){auto it=rateCache.find(ch.pred[a]);if(it==rateCache.end())it=rateCache.emplace(ch.pred[a],int64_t(replay(s,ch.pred[a]).bins.bits)).first;rates[a]=it->second;}
    std::ostringstream o;o<<"{\"kind\":\"tu\",\"poc\":"<<s.poc<<",\"component\":"<<s.component<<",\"x\":"<<s.x<<",\"y\":"<<s.y<<",\"w\":"<<s.g.w<<",\"h\":"<<s.g.h<<",\"qp\":"<<s.qp<<",\"slice_type\":\""<<TsAudit::sliceName(s.sliceType)<<"\",\"is_intra_cu\":"<<s.isIntraCu<<",\"rice\":"<<s.rice<<",\"rice_cutoff\":"<<COEF_REMAIN_BIN_REDUCTION<<",\"range\":"<<s.g.range<<",\"q_hash\":\""<<s.qHash()<<"\",\"entry_hash\":\""<<TsAudit::contextHash(s.entry)<<"\",\"native_verified\":true,\"rates_frac\":";
    arr(o,rates);o<<",\"nonzero\":"<<std::count_if(s.q.begin(),s.q.end(),[](int v){return v!=0;});
    positions+=s.q.size();nz+=std::count_if(s.q.begin(),s.q.end(),[](int a){return a!=0;});
    if(schedule.models) {
      auto alternatives=schedule.read(s);std::vector<int64_t> modelRates;
      for(const auto &p:alternatives) {
        auto it=rateCache.find(p);
        if(it==rateCache.end())it=rateCache.emplace(p,int64_t(replay(s,p).bins.bits)).first;
        modelRates.push_back(it->second);
      }
      o<<",\"model_rates_frac\":";arr(o,modelRates);
    } else {
      o<<",\"q\":";arr(o,s.q);o<<",\"scan\":";arr(o,s.g.scan);o<<",\"points\":[";bool first=true;
      for(size_t i=0;i<s.q.size();++i) {
        const int a=std::abs(s.q[s.g.scan[i]]);const auto &d=ch.d[i];
        if(!wantLabels() || !a || d.n<3)continue;
        ++points;
        auto direct=[&](const TsAudit::Replay &r){int64_t v=0;for(const auto &e:r.bins.events)if(e.scan==int(i))v+=e.cost;return v;};
        std::map<int,std::pair<int64_t,int64_t>> costs;
        costs[TsFixedPrediction::remap(a,ch.pred[native][i])]={int64_t(nr.bins.bits),direct(nr)};
        for(int p:d.plus) {
          const int map=TsFixedPrediction::remap(a,p);if(costs.count(map))continue;
          auto ps=ch.pred[native];ps[i]=p;auto result=replay(s,ps);costs[map]={int64_t(result.bins.bits),direct(result)};
        }
        std::array<int,actionCount> ps{};std::array<int64_t,actionCount> deltas{},directDeltas{};
        for(int j=0;j<actionCount;++j){ps[j]=ch.pred[j][i];const auto v=costs.at(TsFixedPrediction::remap(a,ps[j]));deltas[j]=v.first-int64_t(nr.bins.bits);directDeltas[j]=v.second-direct(nr);}
        std::vector<int64_t> c0,cp;
        for(int p:d.c0)c0.push_back(costs.at(TsFixedPrediction::remap(a,p)).first-int64_t(nr.bins.bits));
        for(int p:d.plus)cp.push_back(costs.at(TsFixedPrediction::remap(a,p)).first-int64_t(nr.bins.bits));
        const auto eq=costs.at(TsFixedPrediction::remap(a,ps[7])),sp=costs.at(TsFixedPrediction::remap(a,ps[5]));
        if(!first) { o<<','; }
        first=false;
        o<<"{\"scan\":"<<i<<",\"a\":"<<a<<",\"pred\":";arr(o,ps);o<<",\"delta_frac\":";arr(o,deltas);o<<",\"direct_delta_frac\":";arr(o,directDeltas);
        o<<",\"c0\":";arr(o,d.c0);o<<",\"cplus\":";arr(o,d.plus);o<<",\"c0_delta_frac\":";arr(o,c0);o<<",\"cplus_delta_frac\":";arr(o,cp);
        o<<",\"direct_sp_eq_frac\":"<<sp.second-eq.second<<",\"propagation_sp_eq_frac\":"<<(sp.first-eq.first)-(sp.second-eq.second)<<'}';
      }
      o<<']';
    }
    o<<'}';emit(o.str());pending.reset();
  }
  void finish(bool success) {
    if(success){CHECK(pending!=nullptr,"Incomplete final TU");schedule.finish();}
    std::ostringstream o;o<<"{\"kind\":\"footer\",\"complete\":"<<(success && unsupported==0 && target==verified?"true":"false")<<",\"all_ts_tu\":"<<all<<",\"target_tu\":"<<target<<",\"bdpcm_tu\":"<<bdpcm<<",\"unsupported_tu\":"<<unsupported<<",\"verified_tu\":"<<verified<<",\"positions\":"<<positions<<",\"nonzero\":"<<nz<<",\"labeled_positions\":"<<points<<",\"replays\":"<<replays<<",\"all_component\":";arr(o,allComponent);o<<",\"target_component\":";arr(o,targetComponent);o<<'}';emit(o.str());
  }
};
inline std::unique_ptr<Collector> &storage(){static std::unique_ptr<Collector> p;return p;}
inline Collector &collector(){auto &p=storage();if(!p)p=std::make_unique<Collector>();return *p;}
inline TsAudit::Native *begin(const TransformUnit &tu,CompID c,const Ctx &ctx){return enabled()?collector().begin(tu,c,ctx):nullptr;}
inline void end(const TransformUnit &tu,CompID c,const Ctx &ctx){if(enabled())collector().end(tu,c,ctx);}
inline void finish(bool success){if(enabled())collector().finish(success);}
} // namespace TsCorpus
