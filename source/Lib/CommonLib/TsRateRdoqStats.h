#pragma once
#include <array>
#include <map>
#include <mutex>
#include <tuple>
#include <cstdio>
#include <cstdlib>
#include <cstring>
namespace TsFixedPrediction
{
inline bool rateRdoqShadow()
{
  static const bool on=std::getenv("TS_RATE_RDOQ_SHADOW") && std::strcmp(std::getenv("TS_RATE_RDOQ_SHADOW"),"0");
  return on;
}
struct RateRdoqStats
{
  using Key=std::tuple<int,unsigned,unsigned,int,int>;
  std::mutex mutex;
  std::map<Key,std::array<uint64_t,9>> rows;
  void add(const Key &key,const std::array<uint64_t,9> &v)
  {
    std::lock_guard<std::mutex> lock(mutex);
    auto &row=rows[key];for(int i=0;i<9;++i)row[i]+=v[i];
  }
  ~RateRdoqStats()
  {
    if(rows.empty())return;
    std::fprintf(stderr,"TS_RATE_RDOQ_HEADER component,width,height,cu_qp,support,trial_positions,regular_positions,predictor_diff,old_extra_up,new_extra_up,candidate_set_diff,provisional_level_diff,new_level_maps_to_1,old_level_maps_to_1\n");
    for(const auto &kv:rows)
    {
      const auto &k=kv.first;
      std::fprintf(stderr,"TS_RATE_RDOQ %d,%u,%u,%d,%d",std::get<0>(k),std::get<1>(k),std::get<2>(k),std::get<3>(k),std::get<4>(k));
      for(auto v:kv.second)std::fprintf(stderr,",%llu",(unsigned long long)v);
      std::fprintf(stderr,"\n");
    }
  }
};
inline RateRdoqStats &rateRdoqStats(){static RateRdoqStats s;return s;}
}
