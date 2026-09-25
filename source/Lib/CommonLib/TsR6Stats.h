// Final Writer-only conditional activity, never algorithm state or CABAC rate.
#pragma once
#include <array>
#include <cstdint>
#include <cstdio>
#include <map>
#include <mutex>
#include <tuple>
namespace TsFixedPrediction
{
struct R6Stats
{
  using Key = std::tuple<int, int, unsigned, unsigned, int, int, int, int, int>;
  enum Field { TU, CG, COEFF, NZ, ACTIVE, ACTIVE_NZ, BYPASS, SCOPE, EMPTY,
    DIFFERENT, MAPPED, PARENT_DIFFERENT, PARENT_MAPPED, PCURRENT, PIDENTITY, POTHER,
    R3_PROPOSED, R3_ACCEPTED, R3_REJECTED, ATTEMPTED,
    DENSE_CURRENT, DENSE_REJECTED, DENSE_ACCEPTED, FALLBACK_CURRENT, FALLBACK_REJECTED,
    CURRENT_HITS0, CURRENT_HITS1, CURRENT_HITS_MULTI, SCORE_TIE,
    SUPPORT0, SUPPORT1, SUPPORT2, SUPPORT3, SUPPORT4, SUPPORT5,
    MAPPED_N0, MAPPED_N1, MAPPED_N2, MAPPED_N3, MAPPED_N4, MAPPED_N5,
    LU_ONLY, LU_EQUAL, LU_UNEQUAL, LU_DIFFERENT, LU_MAPPED,
    HIT, UNDER, OVER, ABS_ERROR, MOD0, MOD1, MOD2, MOD_HIGH,
    COST_POS, COST_NEG, PARENT_COST_POS, PARENT_COST_NEG, COUNT };
  std::map<Key, std::array<uint64_t, COUNT>> rows;
  std::mutex mutex;
  void add(const Key &key, const std::array<uint64_t, COUNT> &values)
  {
    std::lock_guard<std::mutex> lock(mutex);
    auto &row = rows[key];
    for (int i = 0; i < COUNT; ++i) { row[i] += values[i]; }
  }
  ~R6Stats()
  {
    if (rows.empty()) { return; }
    const char *const fields[] = {
      "tu_count","cg_count","coeff_count","nonzero_count","active_count","active_nonzero","bypass_count","scope_enabled_cg","empty_cg",
      "p_different","remap_different","p_vs_r3","remap_vs_r3","p_current","p_identity","p_other",
      "r3_proposed","r3_accepted","r3_rejected","attempted",
      "dense_no_proposal","dense_rejected","dense_accepted","fallback_no_proposal","fallback_rejected",
      "current_hits0","current_hits1","current_hits_multi","candidate_tie_current",
      "support0","support1","support2","support3","support4","support5",
      "remap_vs_r3_n0","remap_vs_r3_n1","remap_vs_r3_n2","remap_vs_r3_n3","remap_vs_r3_n4","remap_vs_r3_n5",
      "lu_only","lu_equal","lu_unequal","lu_p_vs_r3","lu_remap_vs_r3",
      "hit","under","over","abs_error_sum","modified0","modified1","modified2","modified_high",
      "proxy_gain_positive","proxy_gain_negative_abs","proxy_vs_r3_positive","proxy_vs_r3_negative_abs"
    };
    static_assert(sizeof(fields) / sizeof(fields[0]) == COUNT, "R6 stats columns mismatch");
    std::fprintf(stderr, "TS_R6_STATS_HEADER policy,component,width,height,cu_qp,intra,bdpcm,cg_count_in_tu,cg_index");
    for (const auto *field : fields) { std::fprintf(stderr, ",%s", field); }
    std::fprintf(stderr, "\n");
    for (const auto &entry : rows)
    {
      const auto &k = entry.first;
      std::fprintf(stderr, "TS_R6_STATS %d,%d,%u,%u,%d,%d,%d,%d,%d", std::get<0>(k), std::get<1>(k),
        std::get<2>(k), std::get<3>(k), std::get<4>(k), std::get<5>(k), std::get<6>(k), std::get<7>(k), std::get<8>(k));
      for (uint64_t value : entry.second) { std::fprintf(stderr, ",%llu", (unsigned long long)value); }
      std::fprintf(stderr, "\n");
    }
  }
};
inline R6Stats &r6Stats() { static R6Stats stats; return stats; }
}
