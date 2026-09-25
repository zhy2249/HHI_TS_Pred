// Final-writer-only online aggregates, emitted once at process exit, not per coefficient.
#pragma once
#include <array>
#include <map>
#include <mutex>
#include <tuple>

namespace TsFixedPrediction
{
struct R2Stats
{
  using Key = std::tuple<int, int, int, unsigned, unsigned, int, int, int>;
  enum Field { TU, CG, COEFF, NZ, ACTIVE, BYPASS, AVAILABLE, SUPPORT, MAJORITY,
               PCURRENT, PIDENTITY, POTHER, DIFFERENT, MAPPED, NCG, GP, GZ, GN,
               VIRTUAL_C, VIRTUAL_N, REAL_CTX_C, REAL_CTX_N, REAL_CTX_CGS, COUNT };
  std::map<Key, std::array<uint64_t, COUNT>> rows;
  std::mutex mutex;
  void add(const Key &key, const std::array<uint64_t, COUNT> &values)
  {
    std::lock_guard<std::mutex> lock(mutex);
    auto &row = rows[key];
    for (int i = 0; i < COUNT; ++i) { row[i] += values[i]; }
  }
  ~R2Stats()
  {
    if (rows.empty()) { return; }
    std::fprintf(stderr, "TS_R2_STATS_HEADER policy,poc,component,width,height,cu_qp,intra,bdpcm,tu_count,cg_count,coeff_count,nonzero_count,active_count,bypass_count,available_sum,nonzero_support_sum,majority_count,p_current,p_identity,p_other,p_different,remap_different,nopred_cg,gain_positive,gain_zero,gain_negative,virtual_current_frac,virtual_nopred_frac,real_context_current_frac,real_context_nopred_frac,real_context_cgs\n");
    for (const auto &entry : rows)
    {
      const auto &k = entry.first;
      std::fprintf(stderr, "TS_R2_STATS %d,%d,%d,%u,%u,%d,%d,%d", std::get<0>(k), std::get<1>(k),
                   std::get<2>(k), std::get<3>(k), std::get<4>(k), std::get<5>(k), std::get<6>(k), std::get<7>(k));
      for (uint64_t value : entry.second) { std::fprintf(stderr, ",%llu", (unsigned long long)value); }
      std::fprintf(stderr, "\n");
    }
  }
};
inline R2Stats &r2Stats() { static R2Stats stats; return stats; }
}
