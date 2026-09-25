// Conditional final-TS diagnostics, NOT unbiased rate estimates. No POC/coefficient rows.
#pragma once
#include <array>
#include <cstdint>
#include <cstdio>
#include <map>
#include <mutex>
#include <tuple>

namespace TsFixedPrediction
{
struct R4Stats
{
  using Key = std::tuple<int, int, unsigned, unsigned, int, int, int, int, int>;
  enum Field { TU, CG, COEFF, NZ, ACTIVE, BYPASS, SCOPE, EMPTY,
    DIFFERENT, MAPPED, PARENT_DIFFERENT, PARENT_MAPPED, PCURRENT, PIDENTITY, POTHER,
    R3_CURRENT, R3_IDENTITY, R3_OTHER, R3_PROPOSED, R3_ACCEPTED, R3_REJECTED,
    SUPPRESSED, ATTEMPTED, ACCEPTED, RESCUE,
    SUPPORT0, SUPPORT1, SUPPORT2, SUPPORT3, SUPPORT4, SUPPORT5,
    GPOS, GZERO, GNEG, HPOS, HZERO, HNEG, B0, B1, B2, B3PLUS,
    DIR_TIE, DIR_H, DIR_V, DIR_BOUNDARY, MODEL_R3, MODEL_C, MODEL_N, MODEL_D, MODEL_S,
    SIGN_SAME, SIGN_OPPOSITE, SIGN_ZERO, PLANE_VS_GRADIENT, PLANE_NEW_NONIDENTITY,
    HIT, UNDER, OVER, ABS_ERROR, MOD0, MOD1, MOD2, MOD_HIGH, COST_POS, COST_NEG, COUNT };
  std::map<Key, std::array<uint64_t, COUNT>> rows;
  std::mutex mutex;
  void add(const Key &key, const std::array<uint64_t, COUNT> &values)
  {
    std::lock_guard<std::mutex> lock(mutex);
    auto &row = rows[key];
    for (int i = 0; i < COUNT; ++i) { row[i] += values[i]; }
  }
  ~R4Stats()
  {
    if (rows.empty()) { return; }
    const char *const fields[] = {
      "tu_count","cg_count","coeff_count","nonzero_count","active_count","bypass_count","scope_enabled_cg","empty_cg",
      "p_different","remap_different","p_vs_r3","remap_vs_r3","p_current","p_identity","p_other",
      "r3_current","r3_identity","r3_other","r3_proposed","r3_accepted","r3_rejected",
      "suppressed","attempted","accepted","rescue",
      "support0","support1","support2","support3","support4","support5",
      "g_positive","g_zero","g_negative","h_positive","h_zero","h_negative","b0","b1","b2","b3plus",
      "dir_tie","dir_horizontal","dir_vertical","dir_boundary","model_r3","model_current","model_nopred","model_directional","model_plane",
      "sign_same","sign_opposite","sign_zero","plane_vs_gradient","plane_new_nonidentity",
      "hit","under","over","abs_error_sum","modified0","modified1","modified2","modified_high","proxy_gain_positive","proxy_gain_negative_abs"
    };
    static_assert(sizeof(fields) / sizeof(fields[0]) == COUNT, "R4 stats columns mismatch");
    std::fprintf(stderr, "TS_R4_STATS_HEADER policy,component,width,height,cu_qp,intra,bdpcm,cg_count_in_tu,cg_index");
    for (const auto *field : fields) { std::fprintf(stderr, ",%s", field); }
    std::fprintf(stderr, "\n");
    for (const auto &entry : rows)
    {
      const auto &k = entry.first;
      std::fprintf(stderr, "TS_R4_STATS %d,%d,%u,%u,%d,%d,%d,%d,%d", std::get<0>(k), std::get<1>(k),
        std::get<2>(k), std::get<3>(k), std::get<4>(k), std::get<5>(k), std::get<6>(k), std::get<7>(k), std::get<8>(k));
      for (uint64_t value : entry.second) { std::fprintf(stderr, ",%llu", (unsigned long long)value); }
      std::fprintf(stderr, "\n");
    }
  }
};
inline R4Stats &r4Stats() { static R4Stats stats; return stats; }
}
