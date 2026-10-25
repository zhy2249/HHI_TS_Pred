#pragma once
#include "Manager.h"
#if JVET_BJUT_TS_FIXED_PREDICTOR
namespace TsAudit
{
inline int offline(const std::string &input,const std::string &output)
{
  auto s=load(input); auto d=decisions(s); const int native=s.policy==98?3:4;
  std::filesystem::create_directories(output);
  std::ofstream summary(output+"/replay.json"),bins(output+"/bins.csv"),fields(output+"/snapshot_fields.json");
  CHECK(!summary || !bins || !fields,"Cannot open offline replay outputs");
  bins<<"policy,event,scan,pass,ctx_id,value,cost_frac\n";
  std::array<uint64_t,7> rates{};
  for(int mode=0;mode<7;++mode)
  {
    auto r=replay(s,predictors(d,mode)); if(mode==native) { validateNative(s,r); }
    rates[mode]=r.bins.bits;
    for(size_t i=0;i<r.bins.events.size();++i) { const auto &e=r.bins.events[i]; bins<<names[mode]<<','<<i<<','<<e.scan<<','<<e.pass<<','<<e.id<<','<<e.value<<','<<e.cost<<'\n'; }
  }
  summary<<"{\"revision\":\""<<revision<<"\",\"native_validated\":true,\"population\":\""<<(s.population?"SEARCH_FIXTURE":"FINAL_SELECTED")<<"\",\"poc\":"<<s.poc<<",\"slice_type\":\""<<sliceName(s.sliceType)<<"\",\"is_intra_cu\":"<<s.isIntraCu<<",\"is_inter_cu\":"<<s.isInterCu<<",\"component\":"<<s.component<<",\"x\":"<<s.x<<",\"y\":"<<s.y<<",\"w\":"<<s.g.w<<",\"h\":"<<s.g.h<<",\"rates_frac\":"; arrayJson(summary,rates); summary<<",\"sp_minus_eq_frac\":"<<int64_t(rates[4])-int64_t(rates[3])<<",\"coefficients\":[";
  for(size_t i=0;i<d.size();++i)
  { if(i) { summary<<','; } const auto &v=d[i]; summary<<"{\"scan\":"<<i<<",\"q\":"<<s.q[s.g.scan[i]]<<",\"H\":"; arrayJson(summary,v.h); summary<<",\"hist\":"<<v.hist<<",\"c0\":"; arrayJson(summary,v.c0); summary<<",\"cplus\":"; arrayJson(summary,v.plus); summary<<",\"pred\":"; arrayJson(summary,v.pred); summary<<",\"scores168\":["; for(int m=0;m<7;++m) { if(m) { summary<<','; } arrayJson(summary,v.score[m]); } summary<<"]}"; }
  summary<<"]}\n";
  fields<<"{\"schema\":2,\"model_fields\":[\"state0\",\"state1\",\"used0\",\"used1\",\"window\",\"weight\",\"offset0\",\"offset1\",\"frac0\",\"frac1\"],\"q_raster\":"; arrayJson(fields,s.q); fields<<",\"scan_to_raster\":"; arrayJson(fields,s.g.scan); fields<<",\"entry_models\":[";
  for(size_t i=0;i<s.entry.size();++i) { if(i) { fields<<','; } arrayJson(fields,s.entry[i].v); } fields<<"]}\n";
  summary.close(); bins.close(); fields.close(); CHECK(!summary || !bins || !fields,"Offline write failed");
  return 0;
}
}
#endif
