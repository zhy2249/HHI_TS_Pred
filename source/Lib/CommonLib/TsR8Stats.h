// Aggregated final-Writer observations, not selector state or measured rate gain.
#pragma once
#include <array>
#include <map>
#include <mutex>
#include <tuple>
#include <cstdio>
#include <cstdint>
namespace TsFixedPrediction
{
struct R8Stats
{
  // n=cutoff=-1: CG census; otherwise coefficient rows split by n and actual pass.
  using Key = std::tuple<int,int,unsigned,unsigned,int,int,int,int,int,int,int>;
  enum Field { TU, CG, EMPTY, COEFF, NZ, ACTIVE, ACTIVE_NZ, PCURRENT, PIDENTITY, POTHER,
    VS_CURRENT, VS_PARENT, VS_R3, MAP_CURRENT, MAP_PARENT, MAP_R3,
    RAW_CURRENT, RAW_IDENTITY, RAW_OTHER, ACCEPT, REJECT_IDENTITY, REJECT_OTHER,
    TIE_CURRENT, GAIN_Q15, MARGIN_Q15, CANDIDATES, MOD0, MOD1, MOD2, MODHIGH,
    LU_ONLY, CURRENT_IDENTITY, NEW_CANDIDATE, VS_RAW, SELECTED_SCORE, SELECTED_REGRET,
    GUARD_VS_PARENT, MARGIN_NEG, MARGIN_ZERO, MARGIN_LT1, MARGIN_GE1, COUNT };
  std::map<Key, std::array<int64_t, COUNT>> rows;
  std::mutex mutex;
  void add(const Key &key, const std::array<int64_t, COUNT> &v)
  {
    std::lock_guard<std::mutex> lock(mutex);
    auto &row = rows[key];
    for (int i = 0; i < COUNT; ++i) { row[i] += v[i]; }
  }
  ~R8Stats()
  {
    if (rows.empty()) { return; }
    const char *fields[] = {"tu_count","cg_count","empty_cg","coeff_count","nonzero_count",
      "active_count","active_nonzero","p_current","p_identity","p_other",
      "p_vs_current","p_vs_parent","p_vs_r3","remap_vs_current","remap_vs_parent","remap_vs_r3",
      "raw_current","raw_identity","raw_other","raw_guard_accept","raw_guard_reject_identity","raw_guard_reject_other",
      "candidate_tie_current","raw_gain_q15_sum","raw_margin_q15_sum","candidate_count_sum",
      "modified0","modified1","modified2","modified_high","lu_only","current_identity_equivalent",
      "selected_outside_P0","selected_vs_raw","selected_score_q15_sum","selected_regret_q15_sum",
      "raw_guard_vs_parent","raw_margin_negative","raw_margin_zero","raw_margin_positive_lt1bit","raw_margin_ge1bit"};
    static_assert(sizeof(fields)/sizeof(fields[0]) == COUNT, "R8 stats columns");
    std::fprintf(stderr, "TS_R8_STATS_HEADER mode,component,width,height,cu_qp,intra,bdpcm,cg_count_in_tu,cg_index,support,cutoff");
    for (const auto *f : fields) { std::fprintf(stderr, ",%s", f); }
    std::fprintf(stderr, "\n");
    for (const auto &row : rows)
    {
      const auto &k = row.first;
      std::fprintf(stderr, "TS_R8_STATS %d,%d,%u,%u,%d,%d,%d,%d,%d,%d,%d", std::get<0>(k),std::get<1>(k),
        std::get<2>(k),std::get<3>(k),std::get<4>(k),std::get<5>(k),std::get<6>(k),std::get<7>(k),std::get<8>(k),std::get<9>(k),std::get<10>(k));
      for (auto v : row.second) { std::fprintf(stderr, ",%lld", (long long)v); }
      std::fprintf(stderr, "\n");
    }
  }
};
inline R8Stats &r8Stats() { static R8Stats s; return s; }
}
